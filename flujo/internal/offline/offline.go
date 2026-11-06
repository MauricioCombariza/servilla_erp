// Package offline: lo que el celular hizo sin señal llega aquí en lotes.
//
// Cada operación trae un op_id (UUID generado en el celular). El resultado se guarda en
// operaciones_cliente: si el mismo lote vuelve a llegar (se cortó la red antes de que
// llegara la respuesta), se responde lo mismo sin repetir nada. Las operaciones se
// aplican en orden; si una falla por algo del servidor (500), se detiene el lote ahí y
// el celular reintenta desde esa operación.
//
// Si el servicio se cae justo entre hacer una operación y guardar su resultado, al
// reintentar se vuelve a hacer: todas son idempotentes (leer un serial ya leído no lo
// cuenta dos veces, abrir con el mismo local_id devuelve la misma tula, asignar las
// mismas zonas deja lo mismo).
package offline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"regexp"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/asignacion"
	"servilla/flujo/internal/auth"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/httpx"
	"servilla/flujo/internal/tulas"
)

const maxPorLote = 200

var reUUID = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

type Servicio struct {
	Pool       *pgxpool.Pool
	Tulas      *tulas.Servicio
	Asignacion *asignacion.Servicio
}

type Op struct {
	OpID        string          `json:"op_id"`
	Tipo        string          `json:"tipo"`
	TulaLocalID *string         `json:"tula_local_id"`
	TulaID      *int64          `json:"tula_id"`
	Datos       json.RawMessage `json:"datos"`
	// Cuándo se hizo en el celular: solo para el log (la fecha del día la pone el servidor)
	Hora *time.Time `json:"hora"`
}

type Resultado struct {
	OpID   string `json:"op_id"`
	Status int    `json:"status"`
	Body   any    `json:"body"`
}

type Respuesta struct {
	Resultados []Resultado `json:"resultados"`
	// Ids del servidor de las tulas abiertas sin señal (local_id → id)
	Tulas map[string]int64 `json:"tulas"`
	// Cuántas operaciones del lote quedaron sin hacer (el celular las reenvía)
	Pendientes int `json:"pendientes"`
}

var paginaDe = map[string]string{
	"abrir_tula":     tulas.PaginaEscaneo,
	"serial":         tulas.PaginaEscaneo,
	"total":          tulas.PaginaEscaneo,
	"cerrar_tula":    tulas.PaginaEscaneo,
	"asignar_zonas":  asignacion.PaginaAsignacion,
	"asignar_serial": asignacion.PaginaAsignacion,
	"quitar_serial":  asignacion.PaginaAsignacion,
}

func (s *Servicio) Rutas(mux *http.ServeMux, a *auth.Auth) {
	mux.HandleFunc("POST /api/flujo/sync", a.RequierePagina(s.hSync, tulas.PaginaEscaneo, asignacion.PaginaAsignacion))
	mux.HandleFunc("GET /api/flujo/cambios", a.RequierePagina(s.hCambios, tulas.PaginaEscaneo))
}

func (s *Servicio) hSync(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Ops []Op `json:"ops"`
	}
	if err := httpx.LeerJSON(w, r, &body); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	if len(body.Ops) > maxPorLote {
		httpx.Fallar(w, r, httpx.Invalido(fmt.Sprintf("máximo %d operaciones por lote", maxPorLote)))
		return
	}
	u := auth.DelContexto(r.Context())
	resp := Respuesta{Resultados: []Resultado{}, Tulas: map[string]int64{}}
	for i, op := range body.Ops {
		res, err := s.aplicar(r.Context(), u, op, resp.Tulas)
		if err != nil {
			// Falla del servidor: se para aquí para no alterar el orden de lo que sigue
			slog.ErrorContext(r.Context(), "sync: operación sin hacer, se reintentará",
				"op_id", op.OpID, "tipo", op.Tipo, "usuario", u.Username, "err", err)
			resp.Pendientes = len(body.Ops) - i
			break
		}
		resp.Resultados = append(resp.Resultados, res)
	}
	httpx.JSON(w, http.StatusOK, resp)
}

// aplicar devuelve error solo si la operación debe reintentarse (falla del servidor).
func (s *Servicio) aplicar(ctx context.Context, u auth.Usuario, op Op, locales map[string]int64) (Resultado, error) {
	res := Resultado{OpID: op.OpID}
	if !reUUID.MatchString(op.OpID) {
		res.Status, res.Body = http.StatusUnprocessableEntity, map[string]any{"detail": "op_id debe ser un UUID"}
		return res, nil
	}

	var guardado []byte
	err := s.Pool.QueryRow(ctx, `SELECT resultado FROM operaciones_cliente WHERE op_id = $1`, op.OpID).Scan(&guardado)
	if err == nil {
		var prev Resultado
		if json.Unmarshal(guardado, &prev) == nil {
			prev.OpID = op.OpID
			s.recordarTula(op, prev, locales)
			return prev, nil
		}
	} else if !errors.Is(err, pgx.ErrNoRows) {
		return res, err
	}

	pagina, ok := paginaDe[op.Tipo]
	var cuerpo any
	switch {
	case !ok:
		err = httpx.Invalido("tipo de operación desconocido: " + op.Tipo)
	case !u.TienePagina(pagina):
		err = auth.ErrSinPermisos
	default:
		cuerpo, err = s.hacer(ctx, u.Username, op, locales)
	}

	var e *httpx.Error
	switch {
	case err == nil:
		res.Status, res.Body = http.StatusOK, cuerpo
	case errors.As(err, &e) && e.Status < 500:
		res.Status, res.Body = e.Status, map[string]any{"detail": e.Detail}
	case esErrorDeDatos(err):
		// Reintentarla daría lo mismo para siempre y trabaría todo lo que viene detrás
		slog.WarnContext(ctx, "sync: operación rechazada por la base", "op_id", op.OpID, "tipo", op.Tipo, "err", err)
		res.Status, res.Body = http.StatusUnprocessableEntity, map[string]any{"detail": "Dato inválido: " + err.Error()}
	default:
		return res, err
	}
	s.recordarTula(op, res, locales)

	b, err := json.Marshal(res)
	if err != nil {
		return res, err
	}
	if _, err := s.Pool.Exec(ctx, `
		INSERT INTO operaciones_cliente (op_id, usuario, tipo, resultado) VALUES ($1, $2, $3, $4)
		ON CONFLICT (op_id) DO NOTHING`, op.OpID, u.Username, op.Tipo, b); err != nil {
		return res, err
	}
	return res, nil
}

// esErrorDeDatos: el dato no cabe o no cumple una restricción (SQLSTATE clase 22 o 23).
// No es una falla pasajera del servidor: reintentar la misma operación nunca va a servir.
func esErrorDeDatos(err error) bool {
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) || len(pgErr.Code) < 2 {
		return false
	}
	clase := pgErr.Code[:2]
	return clase == "22" || clase == "23"
}

// recordarTula: tras abrir una tula sin señal, las operaciones siguientes del mismo lote
// (y el celular) ya conocen su id.
func (s *Servicio) recordarTula(op Op, res Resultado, locales map[string]int64) {
	if op.Tipo != "abrir_tula" || op.TulaLocalID == nil || res.Status != http.StatusOK {
		return
	}
	switch b := res.Body.(type) {
	case tulas.TulaAbierta:
		locales[*op.TulaLocalID] = b.ID
	case map[string]any: // leído de operaciones_cliente
		if id, ok := b["id"].(float64); ok {
			locales[*op.TulaLocalID] = int64(id)
		}
	}
}

func (s *Servicio) tulaID(ctx context.Context, op Op, locales map[string]int64) (int64, error) {
	if op.TulaID != nil {
		return *op.TulaID, nil
	}
	if op.TulaLocalID == nil {
		return 0, httpx.Invalido("falta tula_id o tula_local_id")
	}
	if id, ok := locales[*op.TulaLocalID]; ok {
		return id, nil
	}
	if !reUUID.MatchString(*op.TulaLocalID) {
		return 0, httpx.Invalido("tula_local_id debe ser un UUID")
	}
	var id int64
	err := s.Pool.QueryRow(ctx, `SELECT id FROM tulas WHERE local_id = $1`, *op.TulaLocalID).Scan(&id)
	if errors.Is(err, pgx.ErrNoRows) {
		return 0, httpx.NoEncontrado("La tula de esta lectura todavía no se abrió en el servidor")
	}
	return id, err
}

func decodificar(datos json.RawMessage, v any) error {
	if len(datos) == 0 {
		return nil
	}
	if err := json.Unmarshal(datos, v); err != nil {
		return httpx.Invalido("datos inválidos: " + err.Error())
	}
	return nil
}

func (s *Servicio) hacer(ctx context.Context, usuario string, op Op, locales map[string]int64) (any, error) {
	switch op.Tipo {
	case "abrir_tula":
		var a tulas.AbrirTula
		if err := decodificar(op.Datos, &a); err != nil {
			return nil, err
		}
		if op.TulaLocalID == nil || !reUUID.MatchString(*op.TulaLocalID) {
			return nil, httpx.Invalido("abrir_tula necesita tula_local_id (UUID)")
		}
		a.LocalID = op.TulaLocalID
		return s.Tulas.Abrir(ctx, usuario, a)

	case "serial":
		var d struct {
			Serial string `json:"serial"`
		}
		if err := decodificar(op.Datos, &d); err != nil {
			return nil, err
		}
		id, err := s.tulaID(ctx, op, locales)
		if err != nil {
			return nil, err
		}
		return s.Tulas.Escanear(ctx, id, d.Serial, usuario)

	case "total":
		var d struct {
			TotalEsperado *int `json:"total_esperado"`
		}
		if err := decodificar(op.Datos, &d); err != nil {
			return nil, err
		}
		id, err := s.tulaID(ctx, op, locales)
		if err != nil {
			return nil, err
		}
		return s.Tulas.FijarTotal(ctx, id, d.TotalEsperado)

	case "cerrar_tula":
		id, err := s.tulaID(ctx, op, locales)
		if err != nil {
			return nil, err
		}
		return s.Tulas.Cerrar(ctx, id)

	case "asignar_zonas":
		var d struct {
			Codigo string `json:"codigo"`
			asignacion.AsignarZonasBody
		}
		if err := decodificar(op.Datos, &d); err != nil {
			return nil, err
		}
		return s.Asignacion.AsignarZonas(ctx, d.Codigo, d.Zonas, db.FechaOpcional(d.Fecha), usuario, d.Reasignar)

	case "asignar_serial", "quitar_serial":
		var d struct {
			Codigo string    `json:"codigo"`
			Serial string    `json:"serial"`
			Fecha  *db.Fecha `json:"fecha"`
		}
		if err := decodificar(op.Datos, &d); err != nil {
			return nil, err
		}
		if op.Tipo == "asignar_serial" {
			return s.Asignacion.AsignarSerial(ctx, d.Codigo, d.Serial, db.FechaOpcional(d.Fecha), usuario)
		}
		if err := s.Asignacion.QuitarSerial(ctx, d.Codigo, d.Serial, db.FechaOpcional(d.Fecha)); err != nil {
			return nil, err
		}
		return map[string]bool{"quitado": true}, nil
	}
	return nil, httpx.Invalido("tipo de operación desconocido: " + op.Tipo)
}

// ========== CAMBIOS DE iMILE PARA LA PANTALLA ==========

type CambioSerial struct {
	TulaID       int64   `json:"tula_id"`
	Serial       string  `json:"serial"`
	ImileEstado  *string `json:"imile_estado"`
	ImileMensaje *string `json:"imile_mensaje"`
}

type Cambios struct {
	Cursor   time.Time      `json:"cursor"`
	Seriales []CambioSerial `json:"seriales"`
}

// hCambios: GET /api/flujo/cambios?desde=<cursor> → estado de iMile de los paquetes del
// usuario que cambió desde el cursor. El cursor vuelve 5 s atrás para no perder lo que
// se confirmó justo al mismo tiempo (el celular aplica los cambios repetidos sin problema).
func (s *Servicio) hCambios(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var c Cambios
	if err := s.Pool.QueryRow(ctx, `SELECT now() - interval '5 seconds'`).Scan(&c.Cursor); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	c.Seriales = []CambioSerial{}
	desde := r.URL.Query().Get("desde")
	if desde == "" {
		httpx.JSON(w, http.StatusOK, c)
		return
	}
	t, err := time.Parse(time.RFC3339Nano, desde)
	if err != nil {
		httpx.Fallar(w, r, httpx.Invalido("desde inválido (RFC 3339)"))
		return
	}
	rows, err := s.Pool.Query(ctx, `
		SELECT ts.tula_id, ts.serial, ts.imile_estado, ts.imile_mensaje
		FROM tula_seriales ts JOIN tulas tu ON tu.id = ts.tula_id
		WHERE tu.usuario = $1 AND tu.fecha >= $2 AND ts.imile_fecha > $3
		ORDER BY ts.imile_fecha LIMIT 1000`,
		auth.DelContexto(ctx).Username, db.Fecha{Time: db.Hoy().AddDate(0, 0, -1)}, t)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	c.Seriales, err = pgx.CollectRows(rows, func(row pgx.CollectableRow) (CambioSerial, error) {
		var x CambioSerial
		err := row.Scan(&x.TulaID, &x.Serial, &x.ImileEstado, &x.ImileMensaje)
		return x, err
	})
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	httpx.JSON(w, http.StatusOK, c)
}
