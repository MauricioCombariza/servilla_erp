// Package asignacion: asignación de zonas y seriales a mensajeros (Pasos 3.1 a 3.3).
// Port de backend/app/services/asignacion_zonas_service.py y asignacion_imile_service.py.
//
//   - 3.1: código del mensajero → nombre, desde `personal` (solo activos).
//   - 3.2: cada zona va completa a UN solo mensajero por día; si ya la tiene otro se
//     informa el choque y solo con reasignar se le pasa. También se reasigna serial por
//     serial: el mensajero final de un paquete es el de su serial si lo tiene; si no, el
//     de su zona.
//   - 3.3: "Asignar en iMile" encola una tarea por paquete pendiente; los workers de
//     iMile las hacen y el avance se lee de la cola (sobrevive a reinicios).
package asignacion

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/db"
	"servilla/flujo/internal/despacho"
	"servilla/flujo/internal/httpx"
)

const (
	OrigenZona   = "zona"
	OrigenSerial = "serial"
)

// Lo que no se vuelve a mandar: lo ya asignado y las guías que iMile tiene cerradas
var sinReenvio = map[string]bool{"ok": true, "repetido": true, "cerrada": true}

type Servicio struct {
	Pool             *pgxpool.Pool
	AsignacionActiva bool
}

type Mensajero struct {
	ID          int64
	Codigo      string
	Nombre      string
	NombreImile *string
}

func (m Mensajero) NombreEnImile() string {
	if m.NombreImile != nil && strings.TrimSpace(*m.NombreImile) != "" {
		return strings.TrimSpace(*m.NombreImile)
	}
	return m.Nombre
}

type MensajeroRead struct {
	Codigo string `json:"codigo"`
	Nombre string `json:"nombre"`
}

func (m *Mensajero) leer() *MensajeroRead {
	if m == nil {
		return nil
	}
	return &MensajeroRead{m.Codigo, m.Nombre}
}

const columnasPersonal = `id, trim(codigo), nombre_completo, nombre_imile`

func escanearMensajero(row pgx.Row) (*Mensajero, error) {
	var m Mensajero
	err := row.Scan(&m.ID, &m.Codigo, &m.Nombre, &m.NombreImile)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return &m, err
}

func BuscarMensajero(ctx context.Context, q db.DBTX, codigo string) (Mensajero, error) {
	m, err := escanearMensajero(q.QueryRow(ctx,
		`SELECT `+columnasPersonal+` FROM personal WHERE trim(codigo) = $1 AND activo = true`, strings.TrimSpace(codigo)))
	if err != nil {
		return Mensajero{}, err
	}
	if m == nil {
		return Mensajero{}, httpx.NoEncontrado("Mensajero no encontrado")
	}
	return *m, nil
}

type ZonasMensajero struct {
	Codigo      string   `json:"codigo"`
	Nombre      string   `json:"nombre"`
	Fecha       db.Fecha `json:"fecha"`
	Zonas       []string `json:"zonas"`
	NombreImile *string  `json:"nombre_imile"`
}

func (s *Servicio) Mensajero(ctx context.Context, codigo string, fecha db.Fecha) (ZonasMensajero, error) {
	m, err := BuscarMensajero(ctx, s.Pool, codigo)
	if err != nil {
		return ZonasMensajero{}, err
	}
	zonas, err := zonasDe(ctx, s.Pool, m.ID, fecha)
	return ZonasMensajero{m.Codigo, m.Nombre, fecha, zonas, m.NombreImile}, err
}

func zonasDe(ctx context.Context, q db.DBTX, personalID int64, fecha db.Fecha) ([]string, error) {
	rows, err := q.Query(ctx, `
		SELECT zona FROM asignaciones_zona WHERE fecha = $1 AND personal_id = $2 ORDER BY zona`, fecha, personalID)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, pgx.RowTo[string])
}

type Choque struct {
	Zona   string `json:"zona"`
	Codigo string `json:"codigo"`
	Nombre string `json:"nombre"`
}

// AsignarZonas deja al mensajero con exactamente `zonas` en `fecha`.
func (s *Servicio) AsignarZonas(ctx context.Context, codigo string, zonas []string, fecha db.Fecha,
	usuario string, reasignar bool) (ZonasMensajero, error) {
	var res ZonasMensajero
	err := db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		// Dos asignaciones del mismo día a la vez: una espera a la otra (choques consistentes)
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`, "zonas:"+fecha.String()); err != nil {
			return err
		}
		m, err := BuscarMensajero(ctx, tx, codigo)
		if err != nil {
			return err
		}
		pedidas := []string{}
		vistas := map[string]bool{}
		for _, z := range zonas {
			if z = strings.TrimSpace(z); z != "" && !vistas[z] {
				vistas[z] = true
				pedidas = append(pedidas, z)
			}
		}
		disponibles, err := despacho.ZonasDisponibles(ctx, tx)
		if err != nil {
			return err
		}
		validas := map[string]bool{}
		for _, z := range disponibles {
			validas[z] = true
		}
		invalidas := []string{}
		for _, z := range pedidas {
			if !validas[z] {
				invalidas = append(invalidas, z)
			}
		}
		if len(invalidas) > 0 {
			return &httpx.Error{Status: http.StatusBadRequest, Detail: map[string]any{
				"mensaje": "Zonas que no existen: " + strings.Join(invalidas, ", "), "zonas": invalidas}}
		}

		rows, err := tx.Query(ctx, `
			SELECT a.zona, trim(p.codigo), p.nombre_completo
			FROM asignaciones_zona a JOIN personal p ON p.id = a.personal_id
			WHERE a.fecha = $1 AND a.zona = ANY($2) AND a.personal_id <> $3`, fecha, pedidas, m.ID)
		if err != nil {
			return err
		}
		choques, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (Choque, error) {
			var c Choque
			err := row.Scan(&c.Zona, &c.Codigo, &c.Nombre)
			return c, err
		})
		if err != nil {
			return err
		}
		if len(choques) > 0 && !reasignar {
			return httpx.Conflicto(map[string]any{
				"mensaje": "Algunas zonas ya están asignadas a otro mensajero", "choques": choques})
		}

		// Se quitan las zonas que el mensajero ya no tiene y las que se le pasan desde otros
		if _, err := tx.Exec(ctx, `
			DELETE FROM asignaciones_zona WHERE fecha = $1 AND (personal_id = $2 OR zona = ANY($3))`,
			fecha, m.ID, pedidas); err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO asignaciones_zona (fecha, zona, personal_id, usuario)
			SELECT $1, z, $2, $3 FROM unnest($4::text[]) AS z`, fecha, m.ID, usuario, pedidas); err != nil {
			return err
		}
		res = ZonasMensajero{m.Codigo, m.Nombre, fecha, pedidas, m.NombreImile}
		return nil
	})
	return res, err
}

type ZonaDelDia struct {
	Zona           string         `json:"zona"`
	PaquetesLeidos int            `json:"paquetes_leidos"`
	Mensajero      *MensajeroRead `json:"mensajero"`
}

// Tablero: las zonas del día, con su mensajero y cuántos paquetes se leyeron en tulas de ese día.
func (s *Servicio) Tablero(ctx context.Context, fecha db.Fecha) ([]ZonaDelDia, error) {
	leidos := map[string]int{}
	rows, err := s.Pool.Query(ctx, `
		SELECT ts.zona, count(*) FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id
		WHERE t.fecha = $1 AND ts.zona IS NOT NULL GROUP BY ts.zona`, fecha)
	if err != nil {
		return nil, err
	}
	var zona string
	var n int
	if _, err := pgx.ForEachRow(rows, []any{&zona, &n}, func() error { leidos[zona] = n; return nil }); err != nil {
		return nil, err
	}

	asignadas := map[string]*MensajeroRead{}
	rows, err = s.Pool.Query(ctx, `
		SELECT a.zona, trim(p.codigo), p.nombre_completo
		FROM asignaciones_zona a JOIN personal p ON p.id = a.personal_id WHERE a.fecha = $1`, fecha)
	if err != nil {
		return nil, err
	}
	var m MensajeroRead
	if _, err := pgx.ForEachRow(rows, []any{&zona, &m.Codigo, &m.Nombre}, func() error {
		c := m
		asignadas[zona] = &c
		return nil
	}); err != nil {
		return nil, err
	}

	zonas, err := despacho.ZonasDisponibles(ctx, s.Pool)
	if err != nil {
		return nil, err
	}
	tablero := make([]ZonaDelDia, len(zonas))
	for i, z := range zonas {
		tablero[i] = ZonaDelDia{z, leidos[z], asignadas[z]}
	}
	return tablero, nil
}

// ========== REASIGNACIÓN SERIAL POR SERIAL ==========

type AsignacionSerial struct {
	Serial            string         `json:"serial"`
	Ultimos4          string         `json:"ultimos_4"`
	Zona              *string        `json:"zona"`
	MensajeroAnterior *MensajeroRead `json:"mensajero_anterior"` // a quién lo tenía (por zona o por serial)
	YaEraSuyo         bool           `json:"ya_era_suyo"`
}

// zonaDelSerial: la de su última lectura en una tula del día; si no se leyó, la de la base.
func zonaDelSerial(ctx context.Context, q db.DBTX, serial string, fecha db.Fecha) (*string, error) {
	var zona *string
	err := q.QueryRow(ctx, `
		SELECT ts.zona FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id
		WHERE ts.serial = $1 AND t.fecha = $2 ORDER BY ts.id DESC LIMIT 1`, serial, fecha).Scan(&zona)
	if err == nil {
		return zona, nil
	}
	if !errors.Is(err, pgx.ErrNoRows) {
		return nil, err
	}
	err = q.QueryRow(ctx, `SELECT zona FROM paquetes_despacho WHERE serial = $1`, serial).Scan(&zona)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	return zona, err
}

func mensajeroActual(ctx context.Context, q db.DBTX, serial string, zona *string, fecha db.Fecha) (*Mensajero, error) {
	m, err := escanearMensajero(q.QueryRow(ctx, `
		SELECT p.id, trim(p.codigo), p.nombre_completo, p.nombre_imile
		FROM personal p JOIN asignaciones_serial a ON a.personal_id = p.id
		WHERE a.fecha = $1 AND a.serial = $2`, fecha, serial))
	if err != nil || m != nil || zona == nil {
		return m, err
	}
	return escanearMensajero(q.QueryRow(ctx, `
		SELECT p.id, trim(p.codigo), p.nombre_completo, p.nombre_imile
		FROM personal p JOIN asignaciones_zona a ON a.personal_id = p.id
		WHERE a.fecha = $1 AND a.zona = $2`, fecha, *zona))
}

// AsignarSerial: reasigna un paquete al mensajero, por encima de su zona. Dice a quién lo tenía.
func (s *Servicio) AsignarSerial(ctx context.Context, codigo, serial string, fecha db.Fecha, usuario string) (AsignacionSerial, error) {
	serial = strings.TrimSpace(serial)
	if serial == "" {
		return AsignacionSerial{}, httpx.Invalido("serial vacío")
	}
	var res AsignacionSerial
	err := db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		m, err := BuscarMensajero(ctx, tx, codigo)
		if err != nil {
			return err
		}
		zona, err := zonaDelSerial(ctx, tx, serial, fecha)
		if err != nil {
			return err
		}
		anterior, err := mensajeroActual(ctx, tx, serial, zona, fecha)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO asignaciones_serial (fecha, serial, personal_id, usuario) VALUES ($1, $2, $3, $4)
			ON CONFLICT ON CONSTRAINT uq_asignaciones_serial_fecha_serial DO UPDATE SET
				personal_id = EXCLUDED.personal_id, usuario = EXCLUDED.usuario, fecha_creacion = now()`,
			fecha, serial, m.ID, usuario); err != nil {
			return err
		}
		res = AsignacionSerial{serial, despacho.Ultimos4(serial), zona, anterior.leer(), anterior != nil && anterior.ID == m.ID}
		return nil
	})
	return res, err
}

// QuitarSerial deshace la reasignación: el paquete vuelve al mensajero de su zona.
func (s *Servicio) QuitarSerial(ctx context.Context, codigo, serial string, fecha db.Fecha) error {
	m, err := BuscarMensajero(ctx, s.Pool, codigo)
	if err != nil {
		return err
	}
	tag, err := s.Pool.Exec(ctx, `
		DELETE FROM asignaciones_serial WHERE fecha = $1 AND serial = $2 AND personal_id = $3`,
		fecha, strings.TrimSpace(serial), m.ID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return httpx.NoEncontrado("Ese serial no estaba reasignado a este mensajero")
	}
	return nil
}

type SerialDelMensajero struct {
	Serial       string  `json:"serial"`
	Ultimos4     string  `json:"ultimos_4"`
	Zona         *string `json:"zona"`
	Origen       string  `json:"origen"`        // "zona" | "serial"
	ImileEstado  *string `json:"imile_estado"`  // null: todavía no se ha mandado a iMile para este mensajero
	ImileMensaje *string `json:"imile_mensaje"` //
}

// serialesDelMensajero: lo que le toca en el día. Los paquetes leídos de sus zonas que no
// se reasignaron a otro, más los que se le reasignaron uno a uno (la lista del 3.3).
func serialesDelMensajero(ctx context.Context, q db.DBTX, m Mensajero, fecha db.Fecha) ([]SerialDelMensajero, error) {
	type reasignado struct {
		serial     string
		personalID int64
	}
	rows, err := q.Query(ctx, `SELECT serial, personal_id FROM asignaciones_serial WHERE fecha = $1 ORDER BY id`, fecha)
	if err != nil {
		return nil, err
	}
	lista, err := pgx.CollectRows(rows, func(row pgx.CollectableRow) (reasignado, error) {
		var r reasignado
		err := row.Scan(&r.serial, &r.personalID)
		return r, err
	})
	if err != nil {
		return nil, err
	}
	reasignados := map[string]bool{}
	for _, r := range lista {
		reasignados[r.serial] = true
	}

	zonas, err := zonasDe(ctx, q, m.ID, fecha)
	if err != nil {
		return nil, err
	}
	susZonas := map[string]bool{}
	for _, z := range zonas {
		susZonas[z] = true
	}

	rows, err = q.Query(ctx, `
		SELECT ts.serial, ts.zona FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id
		WHERE t.fecha = $1 ORDER BY ts.id`, fecha)
	if err != nil {
		return nil, err
	}
	var serial string
	var zona *string
	zonaLeida := map[string]*string{} // última lectura del día de cada serial
	var resultado []SerialDelMensajero
	vistos := map[string]bool{}
	if _, err := pgx.ForEachRow(rows, []any{&serial, &zona}, func() error {
		zonaLeida[serial] = zona
		if zona != nil && susZonas[*zona] && !reasignados[serial] && !vistos[serial] {
			vistos[serial] = true
			resultado = append(resultado, SerialDelMensajero{Serial: serial, Ultimos4: despacho.Ultimos4(serial), Zona: zona, Origen: OrigenZona})
		}
		return nil
	}); err != nil {
		return nil, err
	}

	// Los reasignados a él que no se leyeron hoy: su zona sale de la base de despacho
	var sinLeer []string
	for _, r := range lista {
		if _, ok := zonaLeida[r.serial]; r.personalID == m.ID && !ok {
			sinLeer = append(sinLeer, r.serial)
		}
	}
	zonaBase := map[string]*string{}
	if len(sinLeer) > 0 {
		rows, err := q.Query(ctx, `SELECT serial, zona FROM paquetes_despacho WHERE serial = ANY($1)`, sinLeer)
		if err != nil {
			return nil, err
		}
		if _, err := pgx.ForEachRow(rows, []any{&serial, &zona}, func() error { zonaBase[serial] = zona; return nil }); err != nil {
			return nil, err
		}
	}
	for _, r := range lista {
		if r.personalID != m.ID {
			continue
		}
		z, ok := zonaLeida[r.serial]
		if !ok {
			z = zonaBase[r.serial]
		}
		resultado = append(resultado, SerialDelMensajero{Serial: r.serial, Ultimos4: despacho.Ultimos4(r.serial), Zona: z, Origen: OrigenSerial})
	}
	return resultado, nil
}

// SerialesConImile: la lista del mensajero (3.2) con lo que pasó en iMile con cada paquete.
func (s *Servicio) SerialesConImile(ctx context.Context, codigo string, fecha db.Fecha) ([]SerialDelMensajero, error) {
	m, err := BuscarMensajero(ctx, s.Pool, codigo)
	if err != nil {
		return nil, err
	}
	return serialesConImile(ctx, s.Pool, m, fecha)
}

func serialesConImile(ctx context.Context, q db.DBTX, m Mensajero, fecha db.Fecha) ([]SerialDelMensajero, error) {
	seriales, err := serialesDelMensajero(ctx, q, m, fecha)
	if err != nil || len(seriales) == 0 {
		return []SerialDelMensajero{}, err
	}
	lista := make([]string, len(seriales))
	for i, s := range seriales {
		lista[i] = s.Serial
	}
	type registro struct {
		personalID      int64
		estado, mensaje *string
		otro            string
	}
	registros := map[string]registro{}
	rows, err := q.Query(ctx, `
		SELECT a.serial, a.personal_id, a.estado, a.mensaje, p.nombre_completo
		FROM asignaciones_imile a JOIN personal p ON p.id = a.personal_id
		WHERE a.fecha = $1 AND a.serial = ANY($2)`, fecha, lista)
	if err != nil {
		return nil, err
	}
	var serial string
	var r registro
	if _, err := pgx.ForEachRow(rows, []any{&serial, &r.personalID, &r.estado, &r.mensaje, &r.otro}, func() error {
		registros[serial] = r
		return nil
	}); err != nil {
		return nil, err
	}
	for i := range seriales {
		r, ok := registros[seriales[i].Serial]
		switch {
		case !ok:
		case r.personalID != m.ID:
			// Se mandó a otro mensajero y luego se le pasó a este: hay que volver a mandarlo
			msg := "En iMile quedó con " + r.otro
			seriales[i].ImileMensaje = &msg
		default:
			seriales[i].ImileEstado, seriales[i].ImileMensaje = r.estado, r.mensaje
		}
	}
	return seriales, nil
}

type TotalMensajero struct {
	Codigo      string   `json:"codigo"`
	Nombre      string   `json:"nombre"`
	Zonas       []string `json:"zonas"`
	Paquetes    int      `json:"paquetes"`    // sus zonas + reasignados a él
	Reasignados int      `json:"reasignados"` // de esos paquetes, cuántos se le pasaron serial por serial
}

// Totales: cuántos paquetes lleva cada mensajero en el día, con la misma regla que
// serialesDelMensajero.
func (s *Servicio) Totales(ctx context.Context, fecha db.Fecha) ([]TotalMensajero, error) {
	rows, err := s.Pool.Query(ctx, `
		WITH reasignados AS (
			SELECT serial, personal_id FROM asignaciones_serial WHERE fecha = $1
		), por_zona AS (
			SELECT DISTINCT a.personal_id, ts.serial
			FROM tula_seriales ts JOIN tulas t ON t.id = ts.tula_id
			JOIN asignaciones_zona a ON a.fecha = $1 AND a.zona = ts.zona
			WHERE t.fecha = $1 AND NOT EXISTS (SELECT 1 FROM reasignados r WHERE r.serial = ts.serial)
		), personas AS (
			SELECT personal_id FROM asignaciones_zona WHERE fecha = $1
			UNION SELECT personal_id FROM reasignados
		)
		SELECT trim(p.codigo), p.nombre_completo,
		       COALESCE((SELECT array_agg(zona ORDER BY zona) FROM asignaciones_zona a
		                 WHERE a.fecha = $1 AND a.personal_id = p.id), '{}'),
		       (SELECT count(*) FROM por_zona z WHERE z.personal_id = p.id)
		         + (SELECT count(*) FROM reasignados r WHERE r.personal_id = p.id),
		       (SELECT count(*) FROM reasignados r WHERE r.personal_id = p.id)
		FROM personas x JOIN personal p ON p.id = x.personal_id
		ORDER BY 4 DESC, p.nombre_completo`, fecha)
	if err != nil {
		return nil, err
	}
	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (TotalMensajero, error) {
		var t TotalMensajero
		err := row.Scan(&t.Codigo, &t.Nombre, &t.Zonas, &t.Paquetes, &t.Reasignados)
		return t, err
	})
}

func (s *Servicio) FijarNombreImile(ctx context.Context, codigo string, nombre *string, fecha db.Fecha) (ZonasMensajero, error) {
	m, err := BuscarMensajero(ctx, s.Pool, codigo)
	if err != nil {
		return ZonasMensajero{}, err
	}
	var valor *string
	if nombre != nil {
		if v := strings.Join(strings.Fields(*nombre), " "); v != "" {
			valor = &v
		}
	}
	if _, err := s.Pool.Exec(ctx, `UPDATE personal SET nombre_imile = $2 WHERE id = $1`, m.ID, valor); err != nil {
		return ZonasMensajero{}, err
	}
	zonas, err := zonasDe(ctx, s.Pool, m.ID, fecha)
	return ZonasMensajero{m.Codigo, m.Nombre, fecha, zonas, valor}, err
}

// ========== PASO 3.3: ENVÍO A iMILE ==========

type EnvioImile struct {
	NombreImile string  `json:"nombre_imile"` // con el que se busca en iMile
	Total       int     `json:"total"`
	Hechos      int     `json:"hechos"`
	Asignados   int     `json:"asignados"`
	Fallidos    int     `json:"fallidos"`
	EnCurso     bool    `json:"en_curso"`
	Error       *string `json:"error"` // lo que detuvo el envío (p. ej. el mensajero no está en iMile)
}

// IniciarEnvio encola en iMile los paquetes del mensajero que todavía no quedaron con él.
func (s *Servicio) IniciarEnvio(ctx context.Context, codigo string, fecha db.Fecha, usuario string) (EnvioImile, error) {
	if !s.AsignacionActiva {
		return EnvioImile{}, &httpx.Error{Status: http.StatusServiceUnavailable,
			Detail: "La asignación en iMile está apagada (IMILE_ASIGNACION_ACTIVA)"}
	}
	var envio EnvioImile
	err := db.EnTx(ctx, s.Pool, func(tx pgx.Tx) error {
		m, err := BuscarMensajero(ctx, tx, codigo)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, `SELECT pg_advisory_xact_lock(hashtext($1))`,
			fmt.Sprintf("envio:%d:%s", m.ID, fecha)); err != nil {
			return err
		}
		var enCurso bool
		if err := tx.QueryRow(ctx, `
			SELECT EXISTS (SELECT 1 FROM imile_tareas WHERE tipo = 'asignar' AND personal_id = $1 AND fecha = $2
			               AND estado IN ('pendiente', 'en_proceso'))`, m.ID, fecha).Scan(&enCurso); err != nil {
			return err
		}
		if enCurso {
			return httpx.Conflicto(fmt.Sprintf("Ya se están mandando a iMile los paquetes de %s", m.Nombre))
		}
		seriales, err := serialesConImile(ctx, tx, m, fecha)
		if err != nil {
			return err
		}
		pendientes := []string{}
		for _, sr := range seriales {
			if sr.ImileEstado == nil || !sinReenvio[*sr.ImileEstado] {
				pendientes = append(pendientes, sr.Serial)
			}
		}
		envio = EnvioImile{NombreImile: m.NombreEnImile(), Total: len(pendientes), EnCurso: len(pendientes) > 0}
		if len(pendientes) == 0 {
			return nil
		}
		_, err = tx.Exec(ctx, `
			INSERT INTO imile_tareas (tipo, serial, fecha, personal_id, envio_id, usuario)
			SELECT 'asignar', s, $1, $2, e.id, $3
			FROM unnest($4::text[]) WITH ORDINALITY AS u(s, n), (SELECT gen_random_uuid() AS id) e
			ORDER BY n`, fecha, m.ID, usuario, pendientes)
		return err
	})
	return envio, err
}

// Envio: avance del último envío a iMile del mensajero en el día (nil si no se ha mandado).
func (s *Servicio) Envio(ctx context.Context, codigo string, fecha db.Fecha) (*EnvioImile, error) {
	m, err := BuscarMensajero(ctx, s.Pool, codigo)
	if err != nil {
		return nil, err
	}
	e := EnvioImile{NombreImile: m.NombreEnImile()}
	err = s.Pool.QueryRow(ctx, `
		WITH ultimo AS (
			SELECT envio_id FROM imile_tareas
			WHERE tipo = 'asignar' AND personal_id = $1 AND fecha = $2 ORDER BY id DESC LIMIT 1
		)
		SELECT count(*),
		       count(*) FILTER (WHERE estado IN ('hecha', 'fallida')),
		       -- ok y repetido: el paquete ya quedó con el mensajero en iMile
		       count(*) FILTER (WHERE estado = 'hecha' AND resultado IN ('ok', 'repetido')),
		       count(*) FILTER (WHERE estado IN ('pendiente', 'en_proceso')) > 0,
		       max(ultimo_error) FILTER (WHERE estado = 'cancelada')
		FROM imile_tareas WHERE envio_id = (SELECT envio_id FROM ultimo)`, m.ID, fecha,
	).Scan(&e.Total, &e.Hechos, &e.Asignados, &e.EnCurso, &e.Error)
	if err != nil {
		return nil, err
	}
	if e.Total == 0 {
		return nil, nil
	}
	e.Fallidos = e.Hechos - e.Asignados
	return &e, nil
}
