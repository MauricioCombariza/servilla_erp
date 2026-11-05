package imile

import (
	"errors"
	"net/http"

	"servilla/flujo/internal/auth"
	"servilla/flujo/internal/httpx"
)

// Rutas: /api/imile-sesion (como backend/app/routers/imile_sesion.py).
func (s *Sesion) Rutas(mux *http.ServeMux, a *auth.Auth) {
	mux.HandleFunc("GET /api/imile-sesion/estado", a.RequierePagina(s.hEstado, "paquetes_despacho"))
	mux.HandleFunc("POST /api/imile-sesion/conectar", a.RequierePagina(s.hConectar, "paquetes_despacho"))
}

func (s *Sesion) hEstado(w http.ResponseWriter, r *http.Request) {
	httpx.JSON(w, http.StatusOK, s.Estado())
}

// hConectar abre la sesión de iMile (o la reabre con forzar=true) y la deja en español.
func (s *Sesion) hConectar(w http.ResponseWriter, r *http.Request) {
	forzar := r.URL.Query().Get("forzar") == "true"
	err := s.AsegurarSesion(s.Generacion(), forzar)
	switch {
	case errors.Is(err, ErrCredencialesFaltantes):
		httpx.Fallar(w, r, &httpx.Error{Status: http.StatusServiceUnavailable, Detail: err.Error()})
	case err != nil:
		httpx.Fallar(w, r, &httpx.Error{Status: http.StatusBadGateway, Detail: err.Error()})
	default:
		httpx.JSON(w, http.StatusOK, s.Estado())
	}
}
