// Package despacho: destino de un paquete (Paso 2.6) y la base del día para el celular.
//
// La base la sube y sectoriza el backend Python (/api/paquetes-despacho/cargar); aquí
// solo se lee.
package despacho

import (
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/db"
	"servilla/flujo/internal/httpx"
)

const (
	AvisoNoEsta      = "No está en la tabla"
	AvisoFueraDeZona = "Fuera de zona"
)

// Destino: mismo JSON que DestinoPaquete del backend Python.
type Destino struct {
	Serial                 string  `json:"serial"`
	Ultimos4               string  `json:"ultimos_4"`
	EnTabla                bool    `json:"en_tabla"`
	Direccion              *string `json:"direccion"`
	DireccionEstandarizada *string `json:"direccion_estandarizada"`
	Localidad              *string `json:"localidad"`
	Zona                   *string `json:"zona"`
	FueraDeZona            bool    `json:"fuera_de_zona"`
	Aviso                  *string `json:"aviso"`
}

func Ultimos4(serial string) string {
	r := []rune(serial)
	if len(r) <= 4 {
		return serial
	}
	return string(r[len(r)-4:])
}

func ptr(s string) *string { return &s }

// Buscar: port de buscar_destino. Un serial que no está en la tabla se informa pero no
// es error (el ingreso en iMile se hace igual); sin zona específica es "Fuera de zona".
func Buscar(ctx context.Context, q db.DBTX, serial string) (Destino, error) {
	serial = strings.TrimSpace(serial)
	d := Destino{Serial: serial, Ultimos4: Ultimos4(serial)}
	err := q.QueryRow(ctx, `
		SELECT direccion, direccion_estandarizada, localidad, zona
		FROM paquetes_despacho WHERE serial = $1`, serial,
	).Scan(&d.Direccion, &d.DireccionEstandarizada, &d.Localidad, &d.Zona)
	if errors.Is(err, pgx.ErrNoRows) {
		d.Aviso = ptr(AvisoNoEsta)
		return d, nil
	}
	if err != nil {
		return d, err
	}
	d.EnTabla = true
	if d.Zona == nil {
		d.FueraDeZona = true
		d.Aviso = ptr(AvisoFueraDeZona)
	}
	return d, nil
}

type Handlers struct{ Pool *pgxpool.Pool }

func (h Handlers) Destino(w http.ResponseWriter, r *http.Request) {
	d, err := Buscar(r.Context(), h.Pool, r.PathValue("serial"))
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	httpx.JSON(w, http.StatusOK, d)
}

// ========== BASE DEL DÍA PARA EL CELULAR (offline) ==========

// PaqueteBase: compacto, porque viaja entero al celular (claves de una letra).
type PaqueteBase struct {
	Serial    string  `json:"s"`
	Zona      *string `json:"z"`
	Localidad *string `json:"l"`
	Direccion *string `json:"d"`
}

type PersonaBase struct {
	Codigo      string  `json:"codigo"`
	Nombre      string  `json:"nombre"`
	NombreImile *string `json:"nombre_imile"`
}

type Base struct {
	Fecha    db.Fecha      `json:"fecha"`
	Desde    db.Fecha      `json:"desde"`
	Paquetes []PaqueteBase `json:"paquetes"`
	Personal []PersonaBase `json:"personal"`
	Zonas    []string      `json:"zonas"`
}

// Base: GET /api/paquetes-despacho/base?fecha=&dias=3 → los paquetes con f_emi en los
// últimos `dias` días (un paquete de ayer también llega en las tulas de hoy), el personal
// activo y las zonas. Con ETag: si nada cambió responde 304 sin cuerpo.
func (h Handlers) Base(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	fecha := db.Hoy()
	if s := r.URL.Query().Get("fecha"); s != "" {
		f, err := db.ParseFecha(s)
		if err != nil {
			httpx.Fallar(w, r, httpx.Invalido("fecha inválida"))
			return
		}
		fecha = f
	}
	dias := 3
	if n, err := strconv.Atoi(r.URL.Query().Get("dias")); err == nil && n >= 1 && n <= 15 {
		dias = n
	}
	desde := db.Fecha{Time: fecha.AddDate(0, 0, -(dias - 1))}

	etag, err := h.etag(ctx, desde, fecha)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	w.Header().Set("ETag", etag)
	w.Header().Set("Cache-Control", "no-cache")
	if r.Header.Get("If-None-Match") == etag {
		w.WriteHeader(http.StatusNotModified)
		return
	}

	base := Base{Fecha: fecha, Desde: desde}
	if base.Paquetes, err = paquetes(ctx, h.Pool, desde, fecha); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	if base.Personal, err = personal(ctx, h.Pool); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	if base.Zonas, err = ZonasDisponibles(ctx, h.Pool); err != nil {
		httpx.Fallar(w, r, err)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if strings.Contains(r.Header.Get("Accept-Encoding"), "gzip") {
		w.Header().Set("Content-Encoding", "gzip")
		w.Header().Add("Vary", "Accept-Encoding")
		gz := gzip.NewWriter(w)
		defer gz.Close()
		_ = json.NewEncoder(gz).Encode(base)
		return
	}
	_ = json.NewEncoder(w).Encode(base)
}

// etag cambia si se sube o corrige un paquete del rango, o si cambia el personal activo.
func (h Handlers) etag(ctx context.Context, desde, hasta db.Fecha) (string, error) {
	var n int64
	var mod *time.Time
	var hashPersonal string
	// personal: hash del contenido (cambiar nombre_imile no toca fecha_modificacion)
	err := h.Pool.QueryRow(ctx, `
		SELECT (SELECT count(*) FROM paquetes_despacho WHERE f_emi BETWEEN $1 AND $2),
		       (SELECT max(fecha_modificacion) FROM paquetes_despacho WHERE f_emi BETWEEN $1 AND $2),
		       (SELECT left(md5(coalesce(string_agg(codigo || nombre_completo || coalesce(nombre_imile, ''),
		                                            ',' ORDER BY codigo), '')), 12)
		        FROM personal WHERE activo)`, desde, hasta,
	).Scan(&n, &mod, &hashPersonal)
	if err != nil {
		return "", err
	}
	unix := func(t *time.Time) int64 {
		if t == nil {
			return 0
		}
		return t.UnixMilli()
	}
	return fmt.Sprintf(`W/"%s-%s-%d-%d-%s"`, desde, hasta, n, unix(mod), hashPersonal), nil
}

func paquetes(ctx context.Context, q db.DBTX, desde, hasta db.Fecha) ([]PaqueteBase, error) {
	rows, err := q.Query(ctx, `
		SELECT serial, zona, localidad, COALESCE(direccion_estandarizada, direccion)
		FROM paquetes_despacho WHERE f_emi BETWEEN $1 AND $2 ORDER BY serial`, desde, hasta)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (PaqueteBase, error) {
		var p PaqueteBase
		err := row.Scan(&p.Serial, &p.Zona, &p.Localidad, &p.Direccion)
		return p, err
	})
}

func personal(ctx context.Context, q db.DBTX) ([]PersonaBase, error) {
	rows, err := q.Query(ctx, `
		SELECT trim(codigo), nombre_completo, nombre_imile FROM personal WHERE activo ORDER BY codigo`)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (PersonaBase, error) {
		var p PersonaBase
		err := row.Scan(&p.Codigo, &p.Nombre, &p.NombreImile)
		return p, err
	})
}

// ZonasDisponibles: port de vista_zonas_service.zonas_disponibles. Cada nombre una vez;
// las series en el orden de la tabla (60, 70, 80, 90, 10) y dentro de cada una por número.
func ZonasDisponibles(ctx context.Context, q db.DBTX) ([]string, error) {
	rows, err := q.Query(ctx, `
		SELECT nombre, min(orden) FROM sectorizacion_limites
		WHERE tipo = 'zona' AND activo = true GROUP BY nombre`)
	if err != nil {
		return nil, err
	}
	type fila struct {
		nombre string
		orden  int
	}
	filas, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (fila, error) {
		var f fila
		err := row.Scan(&f.nombre, &f.orden)
		return f, err
	})
	if err != nil {
		return nil, err
	}
	return ordenarZonas(filas, func(f fila) (string, int) { return f.nombre, f.orden }), nil
}
