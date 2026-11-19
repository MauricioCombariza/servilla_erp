package asignacion

import (
	"net/http"

	"servilla/flujo/internal/auth"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/httpx"
)

const PaginaAsignacion = "asignacion_zonas"

// Rutas: las mismas acciones de dos formas (como backend/app/routers/asignacion_zonas.py):
//   - /api/asignacion-zonas/…        con sesión del ERP
//   - /api/asignacion-qr/{token}/…   sin sesión, con el QR del día ("qr:<usuario del enlace>")
func (s *Servicio) Rutas(mux *http.ServeMux, a *auth.Auth) {
	sesion := func(h http.HandlerFunc) http.HandlerFunc { return a.RequierePagina(h, PaginaAsignacion) }
	s.rutas(mux, "/api/asignacion-zonas", sesion)
	s.rutas(mux, "/api/asignacion-qr/{token}", a.RequiereEnlaceQR)
}

func (s *Servicio) rutas(mux *http.ServeMux, prefijo string, p func(http.HandlerFunc) http.HandlerFunc) {
	mux.HandleFunc("GET "+prefijo+"/mensajero/{codigo}", p(s.hMensajero))
	mux.HandleFunc("PUT "+prefijo+"/mensajero/{codigo}", p(s.hAsignar))
	mux.HandleFunc("GET "+prefijo+"/{$}", p(s.hTablero))
	mux.HandleFunc("GET "+prefijo, p(s.hTablero))
	mux.HandleFunc("GET "+prefijo+"/mensajeros", p(s.hTotales))
	mux.HandleFunc("POST "+prefijo+"/mensajero/{codigo}/seriales", p(s.hAsignarSerial))
	mux.HandleFunc("DELETE "+prefijo+"/mensajero/{codigo}/seriales/{serial}", p(s.hQuitarSerial))
	mux.HandleFunc("GET "+prefijo+"/mensajero/{codigo}/seriales", p(s.hSeriales))
	mux.HandleFunc("PUT "+prefijo+"/mensajero/{codigo}/nombre-imile", p(s.hNombreImile))
	mux.HandleFunc("POST "+prefijo+"/mensajero/{codigo}/imile", p(s.hIniciarEnvio))
	mux.HandleFunc("GET "+prefijo+"/mensajero/{codigo}/imile", p(s.hEnvio))
}

func fecha(r *http.Request) (db.Fecha, error) {
	s := r.URL.Query().Get("fecha")
	if s == "" {
		return db.Hoy(), nil
	}
	f, err := db.ParseFecha(s)
	if err != nil {
		return f, httpx.Invalido("fecha inválida")
	}
	return f, nil
}

func responder[T any](w http.ResponseWriter, r *http.Request, status int, v T, err error) {
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	httpx.JSON(w, status, v)
}

func usuario(r *http.Request) string { return auth.DelContexto(r.Context()).Username }

func (s *Servicio) hMensajero(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	m, err := s.Mensajero(r.Context(), r.PathValue("codigo"), f)
	responder(w, r, http.StatusOK, m, err)
}

type AsignarZonasBody struct {
	Zonas     []string  `json:"zonas"`
	Fecha     *db.Fecha `json:"fecha"`
	Reasignar bool      `json:"reasignar"`
}

func (s *Servicio) hAsignar(w http.ResponseWriter, r *http.Request) {
	var b AsignarZonasBody
	if err := httpx.LeerJSON(w, r, &b); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	m, err := s.AsignarZonas(r.Context(), r.PathValue("codigo"), b.Zonas, db.FechaOpcional(b.Fecha), usuario(r), b.Reasignar)
	responder(w, r, http.StatusOK, m, err)
}

func (s *Servicio) hTablero(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	t, err := s.Tablero(r.Context(), f)
	responder(w, r, http.StatusOK, t, err)
}

func (s *Servicio) hTotales(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	t, err := s.Totales(r.Context(), f)
	responder(w, r, http.StatusOK, t, err)
}

type AsignarSerialBody struct {
	Serial string    `json:"serial"`
	Fecha  *db.Fecha `json:"fecha"`
}

func (s *Servicio) hAsignarSerial(w http.ResponseWriter, r *http.Request) {
	var b AsignarSerialBody
	if err := httpx.LeerJSON(w, r, &b); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	res, err := s.AsignarSerial(r.Context(), r.PathValue("codigo"), b.Serial, db.FechaOpcional(b.Fecha), usuario(r))
	responder(w, r, http.StatusOK, res, err)
}

func (s *Servicio) hQuitarSerial(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err == nil {
		err = s.QuitarSerial(r.Context(), r.PathValue("codigo"), r.PathValue("serial"), f)
	}
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Servicio) hSeriales(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	l, err := s.SerialesConImile(r.Context(), r.PathValue("codigo"), f)
	responder(w, r, http.StatusOK, l, err)
}

func (s *Servicio) hNombreImile(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	var b struct {
		NombreImile *string `json:"nombre_imile"`
	}
	if err := httpx.LeerJSON(w, r, &b); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	m, err := s.FijarNombreImile(r.Context(), r.PathValue("codigo"), b.NombreImile, f)
	responder(w, r, http.StatusOK, m, err)
}

func (s *Servicio) hIniciarEnvio(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	e, err := s.IniciarEnvio(r.Context(), r.PathValue("codigo"), f, usuario(r))
	responder(w, r, http.StatusAccepted, e, err)
}

func (s *Servicio) hEnvio(w http.ResponseWriter, r *http.Request) {
	f, err := fecha(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	e, err := s.Envio(r.Context(), r.PathValue("codigo"), f)
	responder(w, r, http.StatusOK, e, err)
}
