// Replicador SCO → Postgres (ola 1 de la migración del FoxPro).
//
// Cada N minutos recorre los archivos configurados, manda a Postgres (esquema legacy) solo
// los registros nuevos, cambiados o borrados, y concilia. Ver docs/diseno_ola1_replicador.md.
//
//	replicador -config /etc/replicador/replicador.json            # ciclo continuo
//	replicador -config replicador.json -una-vez                    # una pasada y termina
package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/replicador/internal/config"
	"servilla/replicador/internal/destino"
	"servilla/replicador/internal/replica"
)

func main() {
	rutaConfig := flag.String("config", "/etc/replicador/replicador.json", "archivo de configuración")
	unaVez := flag.Bool("una-vez", false, "una sola pasada")
	flag.Parse()

	log := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	cfg, err := config.Leer(*rutaConfig)
	if err != nil {
		log.Error("configuración", "error", err)
		os.Exit(2)
	}

	ctx, parar := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer parar()

	pool, err := pgxpool.New(ctx, cfg.DBURL)
	if err != nil {
		log.Error("postgres", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	rep := replica.Replicador{
		Fuente:  cfg.LaFuente(),
		Destino: destino.Postgres{Pool: pool, Esquema: cfg.Esquema},
		Lote:    cfg.Lote,
		Log:     log,
	}
	archivos := cfg.LosArchivos()
	log.Info("replicador iniciado", "archivos", len(archivos), "intervalo_min", cfg.IntervaloMinutos)

	for {
		ciclo(ctx, log, rep, archivos)
		if *unaVez {
			return
		}
		select {
		case <-ctx.Done():
			log.Info("replicador detenido")
			return
		case <-time.After(time.Duration(cfg.IntervaloMinutos) * time.Minute):
		}
	}
}

func ciclo(ctx context.Context, log *slog.Logger, rep replica.Replicador, archivos []replica.Archivo) {
	inicio := time.Now()
	malos := 0
	for _, a := range archivos {
		if ctx.Err() != nil {
			return
		}
		r, err := rep.Pasada(ctx, a)
		switch {
		case err != nil:
			malos++
			log.Error("pasada", "tabla", a.Tabla, "error", err)
		case r.SinCambios:
			log.Debug("sin cambios", "tabla", a.Tabla)
		default:
			c := r.Conciliacion
			log.Info("pasada", "tabla", a.Tabla, "registros", c.RegistrosDBF, "incluidos", c.Incluidos,
				"enviados", c.Enviados, "borrados", c.Borrados, "segundos", c.Segundos)
		}
	}
	log.Info("ciclo", "archivos", len(archivos), "con_error", malos, "segundos", time.Since(inicio).Seconds())
}
