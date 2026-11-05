// flujo: servicio Go para Escaneo de tulas, Asignación de zonas y la sesión de iMile.
//
// Corre junto al backend FastAPI sobre la misma base PostgreSQL; nginx le manda solo las
// rutas de estos flujos (ver infra/nginx.conf). Las migraciones siguen en Alembic.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"servilla/flujo/internal/app"
	"servilla/flujo/internal/config"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/imile"
	"servilla/flujo/internal/tulas"
)

// La migración de Alembic que crea imile_tareas, operaciones_cliente y tulas.local_id
const migracionMinima = "049"

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	if err := correr(); err != nil {
		slog.Error("flujo terminó con error", "err", err)
		os.Exit(1)
	}
}

func correr() error {
	cfg, err := config.Cargar()
	if err != nil {
		return err
	}
	ctx, parar := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer parar()

	pool, err := db.Conectar(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer pool.Close()
	ctxMig, cancelarMig := context.WithTimeout(ctx, 5*time.Minute)
	err = db.EsperarMigracion(ctxMig, pool, migracionMinima, 2*time.Second)
	cancelarMig()
	if err != nil {
		return err
	}

	sesion := imile.NuevaSesion(cfg)
	defer sesion.Cerrar()

	var consulta tulas.ConsultaImile
	if cfg.ConsultaActiva {
		consulta = imile.NuevoConsultor(sesion, cfg.ConsultaCacheTTL)
	}
	aplicacion := app.Nueva(pool, cfg, sesion, consulta)

	// Workers de iMile: solo los de las automatizaciones encendidas
	workers := &imile.Workers{Pool: pool, Sesion: sesion, MaxIntentos: cfg.MaxIntentos}
	if cfg.IngresoActivo {
		workers.Ingreso = cfg.PoolIngreso
	}
	if cfg.AsignacionActiva {
		workers.Asignar = cfg.PoolAsignar
	}
	ctxWorkers, pararWorkers := context.WithCancel(context.Background())
	workers.Arrancar(ctxWorkers)
	slog.Info("flujo arrancó", "puerto", cfg.Puerto, "ingreso", workers.Ingreso, "asignar", workers.Asignar,
		"consulta_tula", cfg.ConsultaActiva)

	srv := &http.Server{
		Addr:              ":" + cfg.Puerto,
		Handler:           aplicacion.Handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	errSrv := make(chan error, 1)
	go func() { errSrv <- srv.ListenAndServe() }()

	select {
	case err := <-errSrv:
		pararWorkers()
		return err
	case <-ctx.Done():
	}
	slog.Info("apagando: se terminan las peticiones y tareas en curso")
	ctxApagado, cancelar := context.WithTimeout(context.Background(), 25*time.Second)
	defer cancelar()
	err = srv.Shutdown(ctxApagado)
	pararWorkers()
	workers.Esperar()
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
