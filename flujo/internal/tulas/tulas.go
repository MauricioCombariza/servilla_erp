// Package tulas: descarga de tulas (Pasos 2.4 y 2.8). Port de backend/app/services/tulas_service.py
// con un cambio: el ingreso en iMile (2.5) ya no se hace dentro del escaneo; se encola y
// lo hacen los workers de iMile. El escaneo responde en milisegundos.
//
//   - Contador: con total esperado N empieza en N y baja con cada paquete leído (puede
//     quedar negativo); "Sin etiqueta" o sin total empieza en 0 y sube.
//   - Un serial ya leído en la misma tula no se vuelve a contar.
//   - Cada lectura se guarda en el momento: si el celular se apaga no se pierde nada.
//   - Una sola tula abierta por usuario; abrir otra pide confirmación (cerrar_anterior).
package tulas

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/db"
	"servilla/flujo/internal/despacho"
	"servilla/flujo/internal/httpx"
	"servilla/flujo/internal/imile"
	"servilla/flujo/internal/outbox"
)

const (
	EstadoAbierta = "abierta"
	EstadoCerrada = "cerrada"

	mensajeEnCola   = "En cola para iMile"
	mensajeApagado  = "Ingreso en iMile apagado (IMILE_INGRESO_ACTIVO)"
	esperaConsultaS = 10 * time.Second
)

// ConsultaImile: Paso 2.3 (qué paquetes trae la tula según iMile). nil = apagado.
type ConsultaImile interface {
	Consultar(ctx context.Context, codigo string) (imile.ConsultaTula, error)
}

type Servicio struct {
	Pool          *pgxpool.Pool
	Imile         ConsultaImile
	IngresoActivo bool
}

type Tula struct {
	ID                int64
	Codigo            *string
	SinEtiqueta       bool
	TotalEsperado     *int
	SerialesEsperados []string
	Estado            string
	Usuario           string
	Fecha             db.Fecha
	FechaApertura     time.Time
	FechaCierre       *time.Time
}

// TulaRead: mismo JSON que el backend Python.
type TulaRead struct {
	ID            int64      `json:"id"`
	Codigo        *string    `json:"codigo"`
	SinEtiqueta   bool       `json:"sin_etiqueta"`
	TotalEsperado *int       `json:"total_esperado"`
	Estado        string     `json:"estado"`
	Usuario       string     `json:"usuario"`
	Fecha         db.Fecha   `json:"fecha"`
	FechaApertura time.Time  `json:"fecha_apertura"`
	FechaCierre   *time.Time `json:"fecha_cierre"`
	Leidos        int        `json:"leidos"`
	Contador      int        `json:"contador"`   // lo que se muestra grande (Paso 2.4)
	Diferencia    *int       `json:"diferencia"` // positiva: faltan · negativa: sobran
}

type TulaAbierta struct {
	TulaRead
	ImileTotal *string `json:"imile_total"`
}

type TulaSerialRead struct {
	Serial       string    `json:"serial"`
	EnTabla      bool      `json:"en_tabla"`
	Zona         *string   `json:"zona"`
	Localidad    *string   `json:"localidad"`
	FechaEscaneo time.Time `json:"fecha_escaneo"`
	ImileEstado  *string   `json:"imile_estado"`
	ImileMensaje *string   `json:"imile_mensaje"`
}

type TulaDetalle struct {
	TulaRead
	Seriales    []TulaSerialRead `json:"seriales"`
	Faltantes   []string         `json:"faltantes"`    // null si iMile no dijo qué trae
	NoEsperados []string         `json:"no_esperados"` // null si iMile no dijo qué trae
}

type IngresoImile struct {
	Estado  *string `json:"estado"`
	Mensaje *string `json:"mensaje"`
}

type EscaneoResult struct {
	Tula        TulaRead         `json:"tula"`
	Destino     despacho.Destino `json:"destino"`
	YaEscaneado bool             `json:"ya_escaneado"`
	Imile       IngresoImile     `json:"imile"`
}

func leer(t Tula, leidos int) TulaRead {
	r := TulaRead{
		ID: t.ID, Codigo: t.Codigo, SinEtiqueta: t.SinEtiqueta, TotalEsperado: t.TotalEsperado,
		Estado: t.Estado, Usuario: t.Usuario, Fecha: t.Fecha, FechaApertura: t.FechaApertura,
		FechaCierre: t.FechaCierre, Leidos: leidos, Contador: leidos,
	}
	if t.TotalEsperado != nil {
		d := *t.TotalEsperado - leidos
		r.Contador, r.Diferencia = d, &d
	}
	return r
}

// Largos de las columnas (tulas.codigo, tula_seriales.serial): lo que no cabe se rechaza
// con 422 en vez de llegar a la base como error que trabe la cola del celular.
const (
	MaxCodigo = 255
	MaxSerial = 50
)

const columnasTula = `id, codigo, sin_etiqueta, total_esperado, seriales_esperados, estado, usuario, fecha,
	fecha_apertura, fecha_cierre`

func escanearTula(row pgx.Row) (*Tula, error) {
	var t Tula
	err := row.Scan(&t.ID, &t.Codigo, &t.SinEtiqueta, &t.TotalEsperado, &t.SerialesEsperados, &t.Estado,
		&t.Usuario, &t.Fecha, &t.FechaApertura, &t.FechaCierre)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &t, err
}

func obtener(ctx context.Context, q db.DBTX, id int64, bloquear bool) (*Tula, error) {
	sql := `SELECT ` + columnasTula + ` FROM tulas WHERE id = $1`
	if bloquear {
		sql += ` FOR UPDATE`
	}
	t, err := escanearTula(q.QueryRow(ctx, sql, id))
	if err == nil && t == nil {
		return nil, httpx.NoEncontrado(fmt.Sprintf("Tula %d no encontrada", id))
	}
	return t, err
}

func abiertaDe(ctx context.Context, q db.DBTX, usuario string) (*Tula, error) {
	return escanearTula(q.QueryRow(ctx,
		`SELECT `+columnasTula+` FROM tulas WHERE usuario = $1 AND estado = 'abierta'`, usuario))
}

func leidos(ctx context.Context, q db.DBTX, tulaID int64) (int, error) {
	var n int
	err := q.QueryRow(ctx, `SELECT count(*) FROM tula_seriales WHERE tula_id = $1`, tulaID).Scan(&n)
	return n, err
}

func resumen(ctx context.Context, q db.DBTX, t Tula) (TulaRead, error) {
	n, err := leidos(ctx, q, t.ID)
	return leer(t, n), err
}

// ConflictoTulaAbierta: detail del 409 al abrir con otra abierta (la pantalla pregunta).
type ConflictoTulaAbierta struct {
	Mensaje     string   `json:"mensaje"`
	TulaAbierta TulaRead `json:"tula_abierta"`
}

func (s *Servicio) conflicto(ctx context.Context, q db.DBTX, t Tula) error {
	r, err := resumen(ctx, q, t)
	if err != nil {
		return err
	}
	return httpx.Conflicto(ConflictoTulaAbierta{"Hay una tula abierta. ¿Cerrarla y abrir la nueva?", r})
}

// consultar: Paso 2.3. Cualquier falla deja la tula sin total (se puede contar igual).
func (s *Servicio) consultar(ctx context.Context, codigo string) (*imile.ConsultaTula, string) {
	ctx, cancel := context.WithTimeout(ctx, esperaConsultaS)
	defer cancel()
	c, err := s.Imile.Consultar(ctx, codigo)
	if err != nil {
		return nil, "No se pudo consultar iMile: escribe el total a mano"
	}
	if !c.Encontrada {
		return nil, "iMile todavía no tiene esta tula descargada: escribe el total a mano"
	}
	return &c, fmt.Sprintf("iMile: la tula trae %d paquetes", *c.Total)
}

type AbrirTula struct {
	Codigo         *string `json:"codigo"`
	TotalEsperado  *int    `json:"total_esperado"`
	CerrarAnterior bool    `json:"cerrar_anterior"`
	LocalID        *string `json:"local_id"` // tula abierta en el celular sin señal
}

func (s *Servicio) Abrir(ctx context.Context, usuario string, a AbrirTula) (TulaAbierta, error) {
	var codigo *string
	if a.Codigo != nil {
		if c := strings.TrimSpace(*a.Codigo); c != "" {
			codigo = &c
		}
	}
	if codigo != nil && len([]rune(*codigo)) > MaxCodigo {
		return TulaAbierta{}, httpx.Invalido("El código leído no parece de una tula (muy largo)")
	}
	if a.TotalEsperado != nil && *a.TotalEsperado < 0 {
		return TulaAbierta{}, httpx.Invalido("total_esperado debe ser >= 0")
	}
	// La misma tula del celular que llega otra vez (reintento tras un corte)
	if a.LocalID != nil {
		t, err := escanearTula(s.Pool.QueryRow(ctx, `SELECT `+columnasTula+` FROM tulas WHERE local_id = $1`, *a.LocalID))
		if err != nil {
			return TulaAbierta{}, err
		}
		if t != nil {
			r, err := resumen(ctx, s.Pool, *t)
			return TulaAbierta{TulaRead: r}, err
		}
	}

	// Antes de preguntar a iMile: si hay otra abierta y no se confirmó, se responde ya
	anterior, err := abiertaDe(ctx, s.Pool, usuario)
	if err != nil {
		return TulaAbierta{}, err
	}
	if anterior != nil {
		if codigo != nil && anterior.Codigo != nil && *anterior.Codigo == *codigo {
			r, err := resumen(ctx, s.Pool, *anterior) // se volvió a escanear la misma tula: sigue abierta
			return TulaAbierta{TulaRead: r}, err
		}
		if !a.CerrarAnterior {
			return TulaAbierta{}, s.conflicto(ctx, s.Pool, *anterior)
		}
	}

	// El total escrito a mano manda; si no hay, se pregunta a iMile
	total := a.TotalEsperado
	var esperados []string
	var imileTotal *string
	if codigo != nil && total == nil && s.Imile != nil {
		consulta, msg := s.consultar(ctx, *codigo)
		imileTotal = &msg
		if consulta != nil {
			total, esperados = consulta.Total, consulta.Seriales
		}
	}

	var abierta TulaAbierta
	err = db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		// Dos aperturas del mismo usuario a la vez: una espera a la otra
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, "tulas:"+usuario); err != nil {
			return err
		}
		anterior, err := abiertaDe(ctx, tx, usuario)
		if err != nil {
			return err
		}
		if anterior != nil {
			if codigo != nil && anterior.Codigo != nil && *anterior.Codigo == *codigo {
				r, err := resumen(ctx, tx, *anterior)
				abierta = TulaAbierta{TulaRead: r}
				return err
			}
			if !a.CerrarAnterior {
				return s.conflicto(ctx, tx, *anterior)
			}
			if _, err := tx.Exec(ctx, `UPDATE tulas SET estado = 'cerrada', fecha_cierre = now() WHERE id = $1`, anterior.ID); err != nil {
				return err
			}
		}
		t, err := escanearTula(tx.QueryRow(ctx, `
			INSERT INTO tulas (codigo, sin_etiqueta, total_esperado, seriales_esperados, estado, usuario, fecha, local_id)
			VALUES ($1, $2, $3, $4, 'abierta', $5, $6, $7)
			RETURNING `+columnasTula, codigo, codigo == nil, total, esperados, usuario, db.Hoy(), a.LocalID))
		if err != nil {
			return err
		}
		abierta = TulaAbierta{TulaRead: leer(*t, 0), ImileTotal: imileTotal}
		return nil
	})
	return abierta, err
}

func (s *Servicio) FijarTotal(ctx context.Context, tulaID int64, total *int) (TulaRead, error) {
	if total != nil && *total < 0 {
		return TulaRead{}, httpx.Invalido("total_esperado debe ser >= 0")
	}
	t, err := obtener(ctx, s.Pool, tulaID, false)
	if err != nil {
		return TulaRead{}, err
	}
	if t.Estado != EstadoAbierta {
		return TulaRead{}, httpx.Conflicto("La tula ya está cerrada")
	}
	if _, err := s.Pool.Exec(ctx, `UPDATE tulas SET total_esperado = $2 WHERE id = $1`, tulaID, total); err != nil {
		return TulaRead{}, err
	}
	t.TotalEsperado = total
	return resumen(ctx, s.Pool, *t)
}

// Escanear: lee un paquete de la tula, lo cuenta (si no estaba ya), deja encolado su
// ingreso en iMile (2.5) y devuelve su destino (2.6). Todo en una transacción corta.
func (s *Servicio) Escanear(ctx context.Context, tulaID int64, serial, usuario string) (EscaneoResult, error) {
	serial = strings.TrimSpace(serial)
	if serial == "" {
		return EscaneoResult{}, httpx.Invalido("serial vacío")
	}
	if len([]rune(serial)) > MaxSerial {
		return EscaneoResult{}, httpx.Invalido("El código leído no parece de un paquete (muy largo)")
	}
	var res EscaneoResult
	err := db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		// FOR SHARE: no se cierra la tula a mitad de una lectura; varias lecturas a la vez sí
		t, err := escanearTula(tx.QueryRow(ctx, `SELECT `+columnasTula+` FROM tulas WHERE id = $1 FOR SHARE`, tulaID))
		if err != nil {
			return err
		}
		if t == nil {
			return httpx.NoEncontrado(fmt.Sprintf("Tula %d no encontrada", tulaID))
		}
		if t.Estado != EstadoAbierta {
			return httpx.Conflicto("La tula ya está cerrada")
		}
		destino, err := despacho.Buscar(ctx, tx, serial)
		if err != nil {
			return err
		}
		estado, mensaje := imile.Omitido, mensajeApagado
		if s.IngresoActivo {
			estado, mensaje = imile.Pendiente, mensajeEnCola
		}
		var nuevoID int64
		err = tx.QueryRow(ctx, `
			INSERT INTO tula_seriales (tula_id, serial, en_tabla, zona, imile_estado, imile_mensaje, imile_fecha)
			VALUES ($1, $2, $3, $4, $5, $6, now())
			ON CONFLICT ON CONSTRAINT uq_tula_seriales_tula_serial DO NOTHING
			RETURNING id`, t.ID, destino.Serial, destino.EnTabla, destino.Zona, estado, mensaje,
		).Scan(&nuevoID)
		nuevo := err == nil
		if err != nil && !errors.Is(err, pgx.ErrNoRows) {
			return err
		}
		if nuevo && s.IngresoActivo {
			// El ingreso en iMile se hace siempre, aunque el serial no esté en la tabla
			if _, err := outbox.Encolar(ctx, tx, outbox.Tarea{
				Tipo: outbox.TipoIngreso, Serial: destino.Serial, Fecha: t.Fecha, TulaSerialID: &nuevoID, Usuario: usuario,
			}); err != nil {
				return err
			}
		}
		res = EscaneoResult{Destino: destino, YaEscaneado: !nuevo}
		if err := tx.QueryRow(ctx, `
			SELECT imile_estado, imile_mensaje FROM tula_seriales WHERE tula_id = $1 AND serial = $2`,
			t.ID, destino.Serial).Scan(&res.Imile.Estado, &res.Imile.Mensaje); err != nil {
			return err
		}
		res.Tula, err = resumen(ctx, tx, *t)
		return err
	})
	return res, err
}

// ReintentarImile: vuelve a encolar el ingreso en iMile de un paquete ya leído.
func (s *Servicio) ReintentarImile(ctx context.Context, tulaID int64, serial, usuario string) (TulaSerialRead, error) {
	serial = strings.TrimSpace(serial)
	var r TulaSerialRead
	err := db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		var id int64
		var fecha db.Fecha
		err := tx.QueryRow(ctx, `
			SELECT ts.id, t.fecha FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id
			WHERE ts.tula_id = $1 AND ts.serial = $2 FOR UPDATE OF ts`, tulaID, serial).Scan(&id, &fecha)
		if errors.Is(err, pgx.ErrNoRows) {
			return httpx.NoEncontrado(fmt.Sprintf("El serial %s no está leído en la tula %d", serial, tulaID))
		}
		if err != nil {
			return err
		}
		estado, mensaje := imile.Omitido, mensajeApagado
		if s.IngresoActivo {
			estado, mensaje = imile.Pendiente, "Reintentando…"
			var yaEnCola bool
			if err := tx.QueryRow(ctx, `
				SELECT EXISTS (SELECT 1 FROM imile_tareas WHERE tula_serial_id = $1 AND estado IN ('pendiente', 'en_proceso'))`,
				id).Scan(&yaEnCola); err != nil {
				return err
			}
			if !yaEnCola {
				if _, err := outbox.Encolar(ctx, tx, outbox.Tarea{
					Tipo: outbox.TipoIngreso, Serial: serial, Fecha: fecha, TulaSerialID: &id, Usuario: usuario,
				}); err != nil {
					return err
				}
			}
		}
		return tx.QueryRow(ctx, `
			UPDATE tula_seriales SET imile_estado = $2, imile_mensaje = $3, imile_fecha = now() WHERE id = $1
			RETURNING serial, en_tabla, zona, fecha_escaneo, imile_estado, imile_mensaje`, id, estado, mensaje,
		).Scan(&r.Serial, &r.EnTabla, &r.Zona, &r.FechaEscaneo, &r.ImileEstado, &r.ImileMensaje)
	})
	return r, err
}

// Cerrar: si al abrirla iMile aún no la tenía, se vuelve a preguntar para poder decir
// qué faltó. Si falla, se cierra igual.
func (s *Servicio) Cerrar(ctx context.Context, tulaID int64) (TulaDetalle, error) {
	t, err := obtener(ctx, s.Pool, tulaID, false)
	if err != nil {
		return TulaDetalle{}, err
	}
	if t.Estado != EstadoCerrada {
		var esperados []string
		var total *int
		if t.Codigo != nil && t.SerialesEsperados == nil && s.Imile != nil {
			if c, _ := s.consultar(ctx, *t.Codigo); c != nil {
				esperados, total = c.Seriales, c.Total
			}
		}
		t, err = escanearTula(s.Pool.QueryRow(ctx, `
			UPDATE tulas SET estado = 'cerrada', fecha_cierre = COALESCE(fecha_cierre, now()),
			       seriales_esperados = COALESCE(seriales_esperados, $2),
			       total_esperado = COALESCE(total_esperado, $3)
			WHERE id = $1 RETURNING `+columnasTula, tulaID, esperados, total))
		if err != nil {
			return TulaDetalle{}, err
		}
	}
	return s.detalle(ctx, *t)
}

func (s *Servicio) Detalle(ctx context.Context, tulaID int64) (TulaDetalle, error) {
	t, err := obtener(ctx, s.Pool, tulaID, false)
	if err != nil {
		return TulaDetalle{}, err
	}
	return s.detalle(ctx, *t)
}

func (s *Servicio) detalle(ctx context.Context, t Tula) (TulaDetalle, error) {
	rows, err := s.Pool.Query(ctx, `
		SELECT ts.serial, ts.en_tabla, ts.zona, pd.localidad, ts.fecha_escaneo, ts.imile_estado, ts.imile_mensaje
		FROM tula_seriales ts LEFT JOIN paquetes_despacho pd ON pd.serial = ts.serial
		WHERE ts.tula_id = $1 ORDER BY ts.fecha_escaneo, ts.id`, t.ID)
	if err != nil {
		return TulaDetalle{}, err
	}
	seriales, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (TulaSerialRead, error) {
		var r TulaSerialRead
		err := row.Scan(&r.Serial, &r.EnTabla, &r.Zona, &r.Localidad, &r.FechaEscaneo, &r.ImileEstado, &r.ImileMensaje)
		return r, err
	})
	if err != nil {
		return TulaDetalle{}, err
	}
	d := TulaDetalle{TulaRead: leer(t, len(seriales)), Seriales: seriales}
	if t.SerialesEsperados != nil {
		leidos := make([]string, len(seriales))
		for i, s := range seriales {
			leidos[i] = s.Serial
		}
		d.Faltantes, d.NoEsperados = Comparar(t.SerialesEsperados, leidos)
	}
	return d, nil
}

// Comparar: (faltantes, no esperados) contra lo que iMile dice que trae la tula.
func Comparar(esperados, leidos []string) ([]string, []string) {
	e, v := map[string]bool{}, map[string]bool{}
	for _, s := range esperados {
		e[s] = true
	}
	for _, s := range leidos {
		v[s] = true
	}
	faltantes, noEsperados := []string{}, []string{}
	for s := range e {
		if !v[s] {
			faltantes = append(faltantes, s)
		}
	}
	for s := range v {
		if !e[s] {
			noEsperados = append(noEsperados, s)
		}
	}
	sort.Strings(faltantes)
	sort.Strings(noEsperados)
	return faltantes, noEsperados
}

func (s *Servicio) Abierta(ctx context.Context, usuario string) (*TulaRead, error) {
	t, err := abiertaDe(ctx, s.Pool, usuario)
	if err != nil || t == nil {
		return nil, err
	}
	r, err := resumen(ctx, s.Pool, *t)
	return &r, err
}

func (s *Servicio) Listar(ctx context.Context, fecha db.Fecha) ([]TulaRead, error) {
	rows, err := s.Pool.Query(ctx, `
		SELECT `+columnasTula+`, (SELECT count(*) FROM tula_seriales ts WHERE ts.tula_id = tulas.id)
		FROM tulas WHERE fecha = $1 ORDER BY fecha_apertura`, fecha)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (TulaRead, error) {
		var t Tula
		var n int
		err := row.Scan(&t.ID, &t.Codigo, &t.SinEtiqueta, &t.TotalEsperado, &t.SerialesEsperados, &t.Estado,
			&t.Usuario, &t.Fecha, &t.FechaApertura, &t.FechaCierre, &n)
		return leer(t, n), err
	})
}

// PaquetesHoy: paquetes de la base de despacho subidos (o reemplazados) hoy, en hora de Bogotá.
func (s *Servicio) PaquetesHoy(ctx context.Context) (int, error) {
	var n int
	err := s.Pool.QueryRow(ctx, `SELECT count(*) FROM paquetes_despacho WHERE fecha_modificacion >= $1`,
		db.Hoy().InicioDelDia()).Scan(&n)
	return n, err
}

type ResumenDelDia struct {
	Fecha    db.Fecha `json:"fecha"`
	Tulas    int      `json:"tulas"`
	Paquetes int      `json:"paquetes"` // cada serial contado una sola vez
}

func (s *Servicio) DelDia(ctx context.Context) (ResumenDelDia, error) {
	r := ResumenDelDia{Fecha: db.Hoy()}
	err := s.Pool.QueryRow(ctx, `
		SELECT (SELECT count(*) FROM tulas WHERE fecha = $1),
		       (SELECT count(DISTINCT ts.serial) FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id WHERE t.fecha = $1)`,
		r.Fecha).Scan(&r.Tulas, &r.Paquetes)
	return r, err
}

type SerialSinLeer struct {
	Serial    string  `json:"serial"`
	Ultimos4  string  `json:"ultimos_4"`
	Zona      *string `json:"zona"`
	Localidad *string `json:"localidad"`
	Direccion *string `json:"direccion"`
}

type SinLeerDelDia struct {
	Fecha    db.Fecha        `json:"fecha"`
	Total    int             `json:"total"`
	Seriales []SerialSinLeer `json:"seriales"`
}

// SinLeer: paquetes de la base del día (f_emi) que no se han leído en ninguna tula.
func (s *Servicio) SinLeer(ctx context.Context, fecha db.Fecha) (SinLeerDelDia, error) {
	rows, err := s.Pool.Query(ctx, `
		SELECT pd.serial, pd.zona, pd.localidad, COALESCE(pd.direccion_estandarizada, pd.direccion)
		FROM paquetes_despacho pd
		WHERE pd.f_emi = $1 AND NOT EXISTS (SELECT 1 FROM tula_seriales ts WHERE ts.serial = pd.serial)
		ORDER BY pd.zona NULLS LAST, pd.serial`, fecha)
	if err != nil {
		return SinLeerDelDia{}, err
	}
	seriales, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (SerialSinLeer, error) {
		var p SerialSinLeer
		err := row.Scan(&p.Serial, &p.Zona, &p.Localidad, &p.Direccion)
		p.Ultimos4 = despacho.Ultimos4(p.Serial)
		return p, err
	})
	return SinLeerDelDia{Fecha: fecha, Total: len(seriales), Seriales: seriales}, err
}
