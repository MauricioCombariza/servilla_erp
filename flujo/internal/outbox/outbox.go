// Package outbox: la cola de lo que hay que hacer en iMile (tabla imile_tareas).
//
// La lectura del paquete o la asignación se guardan al instante en la misma transacción
// que encola la tarea; los workers de iMile la toman después. Varias instancias o
// workers pueden reclamar a la vez sin pisarse (FOR UPDATE SKIP LOCKED), y una tarea
// tomada por un worker que se murió vuelve a la cola cuando vence su lease.
package outbox

import (
	"context"
	"errors"
	"math/rand"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/db"
)

const (
	TipoIngreso = "ingreso" // Paso 2.5: Llegada (Waybill No) / arrivalScanAWB
	TipoAsignar = "asignar" // Paso 3.3: Asignar repartidor / assignDA
	// Descarga de la tula (Descarga de escaneo / dsOffloadingScan): Serial = código de la
	// tula. La hacen los mismos workers de ingreso, antes que los paquetes.
	TipoDescarga = "descarga"

	EstadoPendiente = "pendiente"
	EstadoEnProceso = "en_proceso"
	EstadoHecha     = "hecha"
	EstadoFallida   = "fallida"
	EstadoCancelada = "cancelada"

	lease = 2 * time.Minute
)

type Tarea struct {
	ID           int64
	Tipo         string
	Serial       string
	Fecha        db.Fecha
	TulaSerialID *int64
	PersonalID   *int64
	EnvioID      *string
	Usuario      string
	Intentos     int
}

func Encolar(ctx context.Context, q db.DBTX, t Tarea) (int64, error) {
	var id int64
	err := q.QueryRow(ctx, `
		INSERT INTO imile_tareas (tipo, serial, fecha, tula_serial_id, personal_id, envio_id, usuario)
		VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
		t.Tipo, t.Serial, t.Fecha, t.TulaSerialID, t.PersonalID, t.EnvioID, t.Usuario,
	).Scan(&id)
	return id, err
}

// Reclamar toma la tarea pendiente más antigua del tipo. Con preferirPersonal, primero
// las de ese mensajero: la página de asignar ya lo tiene elegido en el selector DA.
// Devuelve nil si no hay nada que hacer.
func Reclamar(ctx context.Context, pool *pgxpool.Pool, tipo string, preferirPersonal *int64) (*Tarea, error) {
	return ReclamarDe(ctx, pool, []string{tipo}, preferirPersonal)
}

// ReclamarDe: como Reclamar, entre varios tipos; el primero de la lista va antes (las
// descargas de tula antes que los ingresos de sus paquetes).
func ReclamarDe(ctx context.Context, pool *pgxpool.Pool, tipos []string, preferirPersonal *int64) (*Tarea, error) {
	var t Tarea
	err := pool.QueryRow(ctx, `
		UPDATE imile_tareas SET estado = 'en_proceso', intentos = intentos + 1,
		       lease_hasta = now() + make_interval(secs => $3), actualizado = now()
		WHERE id = (
			SELECT id FROM imile_tareas
			WHERE tipo = ANY($1) AND estado = 'pendiente' AND proximo_intento <= now()
			ORDER BY array_position($1, tipo), (personal_id IS NOT DISTINCT FROM $2) DESC, id
			FOR UPDATE SKIP LOCKED LIMIT 1)
		RETURNING id, tipo, serial, fecha, tula_serial_id, personal_id, envio_id::text, usuario, intentos`,
		tipos, preferirPersonal, lease.Seconds(),
	).Scan(&t.ID, &t.Tipo, &t.Serial, &t.Fecha, &t.TulaSerialID, &t.PersonalID, &t.EnvioID, &t.Usuario, &t.Intentos)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &t, nil
}

// Terminar marca la tarea como hecha (o fallida si resultado no es de éxito) dentro de
// la transacción en la que se guarda el resultado en su tabla.
func Terminar(ctx context.Context, q db.DBTX, id int64, estado, resultado string, mensaje *string) error {
	_, err := q.Exec(ctx, `
		UPDATE imile_tareas SET estado = $2, resultado = $3, ultimo_error = $4,
		       lease_hasta = NULL, actualizado = now()
		WHERE id = $1`, id, estado, resultado, mensaje)
	return err
}

// Reintentar devuelve la tarea a la cola con espera exponencial (2 s, 4 s, 8 s… máx. 5 min)
// más un poco de azar para que no se reintenten todas en el mismo instante.
func Reintentar(ctx context.Context, q db.DBTX, t Tarea, motivo string) error {
	espera := time.Duration(1<<min(t.Intentos, 8)) * time.Second
	espera = min(espera, 5*time.Minute) + time.Duration(rand.Int63n(int64(time.Second)))
	_, err := q.Exec(ctx, `
		UPDATE imile_tareas SET estado = 'pendiente', ultimo_error = $2, lease_hasta = NULL,
		       proximo_intento = now() + make_interval(secs => $3), actualizado = now()
		WHERE id = $1`, t.ID, motivo, espera.Seconds())
	return err
}

// CancelarEnvio: el resto de tareas de ese envío ya no se hace (p. ej. el mensajero no está en iMile).
func CancelarEnvio(ctx context.Context, q db.DBTX, envioID string, motivo string) error {
	_, err := q.Exec(ctx, `
		UPDATE imile_tareas SET estado = 'cancelada', ultimo_error = $2, lease_hasta = NULL, actualizado = now()
		WHERE envio_id = $1::uuid AND estado IN ('pendiente', 'en_proceso')`, envioID, motivo)
	return err
}

// RecuperarVencidas: las tareas de un worker que se cayó (o de un reinicio) vuelven a la cola.
func RecuperarVencidas(ctx context.Context, pool *pgxpool.Pool) (int64, error) {
	tag, err := pool.Exec(ctx, `
		UPDATE imile_tareas SET estado = 'pendiente', lease_hasta = NULL, actualizado = now()
		WHERE estado = 'en_proceso' AND lease_hasta < now()`)
	return tag.RowsAffected(), err
}

// Despertador: un canal que recibe un aviso cada vez que se encola una tarea de ese tipo
// (LISTEN imile_tareas_nueva). Si se corta la conexión, se reconecta solo; mientras
// tanto los workers siguen revisando la cola cada pocos segundos.
func Despertador(ctx context.Context, pool *pgxpool.Pool, tipos ...string) map[string]chan struct{} {
	canales := map[string]chan struct{}{}
	for _, t := range tipos {
		canales[t] = make(chan struct{}, 1)
	}
	go func() {
		for ctx.Err() == nil {
			escuchar(ctx, pool, canales)
			select {
			case <-ctx.Done():
			case <-time.After(3 * time.Second):
			}
		}
	}()
	return canales
}

func escuchar(ctx context.Context, pool *pgxpool.Pool, canales map[string]chan struct{}) {
	conn, err := pool.Acquire(ctx)
	if err != nil {
		return
	}
	defer conn.Release()
	if _, err := conn.Exec(ctx, "LISTEN imile_tareas_nueva"); err != nil {
		return
	}
	for {
		n, err := conn.Conn().WaitForNotification(ctx)
		if err != nil {
			return
		}
		if c, ok := canales[n.Payload]; ok {
			select {
			case c <- struct{}{}:
			default: // ya hay un aviso sin leer: basta con uno
			}
		}
	}
}
