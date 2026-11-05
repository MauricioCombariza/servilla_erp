package imile

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/playwright-community/playwright-go"

	"servilla/flujo/internal/db"
	"servilla/flujo/internal/outbox"
)

const revisarCada = 2 * time.Second

// Workers: N páginas de Llegada y M de Asignar repartidor trabajando en paralelo sobre
// la cola imile_tareas. Cada página es de un solo worker.
type Workers struct {
	Pool        *pgxpool.Pool
	Sesion      *Sesion
	Ingreso     int
	Asignar     int
	MaxIntentos int

	wg sync.WaitGroup
}

func (w *Workers) Arrancar(ctx context.Context) {
	tipos := []string{}
	if w.Ingreso > 0 {
		tipos = append(tipos, outbox.TipoIngreso)
	}
	if w.Asignar > 0 {
		tipos = append(tipos, outbox.TipoAsignar)
	}
	if len(tipos) == 0 {
		return
	}
	if n, err := outbox.RecuperarVencidas(ctx, w.Pool); err == nil && n > 0 {
		slog.Info("imile: tareas recuperadas tras reinicio", "n", n)
	}
	avisos := outbox.Despertador(ctx, w.Pool, tipos...)
	for i := 0; i < w.Ingreso; i++ {
		w.lanzar(ctx, outbox.TipoIngreso, i, avisos[outbox.TipoIngreso])
	}
	for i := 0; i < w.Asignar; i++ {
		w.lanzar(ctx, outbox.TipoAsignar, i, avisos[outbox.TipoAsignar])
	}
	w.wg.Add(1)
	go func() {
		defer w.wg.Done()
		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				_, _ = outbox.RecuperarVencidas(ctx, w.Pool)
			}
		}
	}()
}

// Esperar a que los workers terminen la tarea que tienen en curso (apagado con gracia).
func (w *Workers) Esperar() { w.wg.Wait() }

func (w *Workers) lanzar(ctx context.Context, tipo string, i int, aviso <-chan struct{}) {
	w.wg.Add(1)
	go func() {
		defer w.wg.Done()
		wk := &worker{Workers: w, tipo: tipo, log: slog.With("worker", fmt.Sprintf("%s-%d", tipo, i))}
		wk.correr(ctx, aviso)
	}()
}

type worker struct {
	*Workers
	tipo string
	log  *slog.Logger
	page playwright.Page
	// mensajero elegido en el selector DA de esta página (para preferir sus tareas)
	personalActual *int64
}

func (wk *worker) correr(ctx context.Context, aviso <-chan struct{}) {
	for ctx.Err() == nil {
		t, err := outbox.Reclamar(ctx, wk.Pool, wk.tipo, wk.personalActual)
		if err != nil && ctx.Err() == nil {
			wk.log.Error("no se pudo leer la cola", "err", err)
		}
		if t == nil {
			select {
			case <-ctx.Done():
			case <-aviso:
			case <-time.After(revisarCada):
			}
			continue
		}
		// La tarea se termina aunque se esté apagando el servicio: ya está reclamada
		wk.hacer(context.WithoutCancel(ctx), *t)
	}
	if wk.page != nil {
		_ = wk.page.Close()
	}
}

func (wk *worker) hacer(ctx context.Context, t outbox.Tarea) {
	inicio := time.Now()
	var nombre string
	if t.Tipo == outbox.TipoAsignar {
		var err error
		if nombre, err = nombreEnImile(ctx, wk.Pool, t.PersonalID); err != nil {
			wk.fallar(ctx, t, err)
			return
		}
	}

	r, err := wk.conSesion(func(page playwright.Page) (Resultado, error) {
		if t.Tipo == outbox.TipoIngreso {
			return wk.Sesion.Ingresar(page, t.Serial)
		}
		return wk.Sesion.Asignar(page, nombre, t.Serial)
	})

	var noEsta *MensajeroNoEncontradoError
	switch {
	case errors.As(err, &noEsta):
		// Como en Python: se detiene el envío de ese mensajero y se avisa
		wk.personalActual = nil
		if t.EnvioID != nil {
			err = outbox.CancelarEnvio(ctx, wk.Pool, *t.EnvioID, noEsta.Mensaje)
		} else {
			err = outbox.Terminar(ctx, wk.Pool, t.ID, outbox.EstadoCancelada, Error, &noEsta.Mensaje)
		}
		if err != nil {
			wk.log.Error("no se pudo cancelar el envío", "err", err)
		}
	case err != nil:
		wk.fallar(ctx, t, err)
	case !r.Definitivo() && t.Intentos < wk.MaxIntentos:
		// iMile no contestó a tiempo: se vuelve a mandar (si ya había entrado, dirá "repetido")
		wk.reintentar(ctx, t, "iMile no devolvió respuesta")
	default:
		if t.Tipo == outbox.TipoAsignar {
			wk.personalActual = t.PersonalID
		}
		if err := wk.guardar(ctx, t, r, outbox.EstadoHecha); err != nil {
			wk.log.Error("no se pudo guardar el resultado", "err", err, "serial", t.Serial)
		}
	}
	wk.log.Info("tarea", "serial", t.Serial, "estado", r.Estado, "intento", t.Intentos, "ms", time.Since(inicio).Milliseconds())
}

// conSesion corre fn con la página del worker. Si la sesión se cerró, vuelve a entrar
// (una vez para todos los workers) y lo intenta de nuevo.
func (wk *worker) conSesion(fn func(playwright.Page) (Resultado, error)) (Resultado, error) {
	if wk.page == nil {
		if err := wk.Sesion.AsegurarSesion(0, false); err != nil {
			return Resultado{}, err
		}
		p, err := wk.Sesion.NuevaPagina()
		if err != nil {
			return Resultado{}, err
		}
		wk.page = p
	}
	var r Resultado
	for intento := 0; intento < 2; intento++ {
		vista := wk.Sesion.Generacion()
		err := wk.Sesion.Usar(func() error {
			var err error
			r, err = fn(wk.page)
			return err
		})
		if !errors.Is(err, ErrSinSesion) {
			var noEsta *MensajeroNoEncontradoError
			if err != nil && !errors.As(err, &noEsta) {
				// La página pudo quedar en un estado raro: la próxima tarea abre una nueva
				_ = wk.page.Close()
				wk.page, wk.personalActual = nil, nil
			}
			return r, err
		}
		wk.log.Warn("imile: la sesión se cerró, volviendo a entrar")
		if err := wk.Sesion.AsegurarSesion(vista, false); err != nil {
			return Resultado{}, err
		}
	}
	return Resultado{}, ErrSinSesion
}

func (wk *worker) fallar(ctx context.Context, t outbox.Tarea, err error) {
	motivo := err.Error()
	if len(motivo) > 500 {
		motivo = motivo[:500]
	}
	if t.Intentos < wk.MaxIntentos {
		wk.reintentar(ctx, t, motivo)
		return
	}
	// Cualquier falla de iMile queda como error en ese paquete: nunca hace perder la lectura
	if err := wk.guardar(ctx, t, Resultado{Estado: Error, Mensaje: &motivo}, outbox.EstadoFallida); err != nil {
		wk.log.Error("no se pudo guardar el error", "err", err, "serial", t.Serial)
	}
}

func (wk *worker) reintentar(ctx context.Context, t outbox.Tarea, motivo string) {
	err := db.EnTx(ctx, wk.Pool, func(tx pgx.Tx) error {
		if err := outbox.Reintentar(ctx, tx, t, motivo); err != nil {
			return err
		}
		if t.TulaSerialID == nil {
			return nil
		}
		msg := fmt.Sprintf("Reintentando (%d/%d): %s", t.Intentos, wk.MaxIntentos, motivo)
		_, err := tx.Exec(ctx, `
			UPDATE tula_seriales SET imile_estado = 'pendiente', imile_mensaje = $2, imile_fecha = now()
			WHERE id = $1`, *t.TulaSerialID, msg)
		return err
	})
	if err != nil {
		wk.log.Error("no se pudo devolver la tarea a la cola", "err", err)
	}
}

// guardar el resultado donde lo lee la pantalla y cerrar la tarea, en una sola transacción.
func (wk *worker) guardar(ctx context.Context, t outbox.Tarea, r Resultado, estadoTarea string) error {
	return db.EnTx(ctx, wk.Pool, func(tx pgx.Tx) error {
		switch t.Tipo {
		case outbox.TipoIngreso:
			if t.TulaSerialID != nil {
				if _, err := tx.Exec(ctx, `
					UPDATE tula_seriales SET imile_estado = $2, imile_mensaje = $3, imile_fecha = now()
					WHERE id = $1`, *t.TulaSerialID, r.Estado, r.Mensaje); err != nil {
					return err
				}
			}
		case outbox.TipoAsignar:
			if _, err := tx.Exec(ctx, `
				INSERT INTO asignaciones_imile (fecha, serial, personal_id, estado, mensaje, codigo, usuario, fecha_envio)
				VALUES ($1, $2, $3, $4, $5, $6, $7, now())
				ON CONFLICT ON CONSTRAINT uq_asignaciones_imile_fecha_serial DO UPDATE SET
					personal_id = EXCLUDED.personal_id, estado = EXCLUDED.estado, mensaje = EXCLUDED.mensaje,
					codigo = EXCLUDED.codigo, usuario = EXCLUDED.usuario, fecha_envio = now()`,
				t.Fecha, t.Serial, t.PersonalID, r.Estado, r.Mensaje, r.Codigo, t.Usuario); err != nil {
				return err
			}
		}
		return outbox.Terminar(ctx, tx, t.ID, estadoTarea, r.Estado, r.Mensaje)
	})
}

// nombreEnImile: personal.nombre_imile o, si está vacío, el nombre del ERP.
func nombreEnImile(ctx context.Context, q db.DBTX, personalID *int64) (string, error) {
	if personalID == nil {
		return "", errors.New("tarea de asignación sin mensajero")
	}
	var nombre string
	err := q.QueryRow(ctx, `
		SELECT COALESCE(NULLIF(btrim(nombre_imile), ''), nombre_completo) FROM personal WHERE id = $1`,
		*personalID).Scan(&nombre)
	return nombre, err
}
