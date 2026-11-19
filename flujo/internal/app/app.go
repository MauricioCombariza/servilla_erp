// Package app arma el servicio: servicios, rutas y autenticación (lo usan main y los tests).
package app

import (
	"net/http"

	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/asignacion"
	"servilla/flujo/internal/auth"
	"servilla/flujo/internal/config"
	"servilla/flujo/internal/despacho"
	"servilla/flujo/internal/httpx"
	"servilla/flujo/internal/imile"
	"servilla/flujo/internal/offline"
	"servilla/flujo/internal/tulas"
)

type App struct {
	Tulas      *tulas.Servicio
	Asignacion *asignacion.Servicio
	Handler    http.Handler
}

// Nueva: consulta puede ser nil (consulta de tula a iMile apagada).
func Nueva(pool *pgxpool.Pool, cfg config.Config, sesion *imile.Sesion, consulta tulas.ConsultaImile) *App {
	servTulas := &tulas.Servicio{Pool: pool, IngresoActivo: cfg.IngresoActivo, Imile: consulta,
		DescargaActiva: cfg.DescargaActiva}
	servAsignacion := &asignacion.Servicio{Pool: pool, AsignacionActiva: cfg.AsignacionActiva}
	a := auth.New(pool, cfg.JWTSecret)

	mux := http.NewServeMux()
	servTulas.Rutas(mux, a)
	servAsignacion.Rutas(mux, a)
	sesion.Rutas(mux, a)
	(&offline.Servicio{Pool: pool, Tulas: servTulas, Asignacion: servAsignacion}).Rutas(mux, a)
	d := despacho.Handlers{Pool: pool}
	mux.HandleFunc("GET /api/paquetes-despacho/destino/{serial}",
		a.RequierePagina(d.Destino, "paquetes_despacho", tulas.PaginaEscaneo))
	mux.HandleFunc("GET /api/paquetes-despacho/base",
		a.RequierePagina(d.Base, tulas.PaginaEscaneo, asignacion.PaginaAsignacion))
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		if err := pool.Ping(r.Context()); err != nil {
			httpx.JSON(w, http.StatusServiceUnavailable, map[string]string{"status": "db caída"})
			return
		}
		httpx.JSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	return &App{Tulas: servTulas, Asignacion: servAsignacion, Handler: httpx.Middleware(mux)}
}
