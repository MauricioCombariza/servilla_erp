package tulas

import (
	"net/http"
	"strconv"

	"servilla/flujo/internal/auth"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/httpx"
)

const PaginaEscaneo = "escaneo_tulas"

// Rutas: las mismas de backend/app/routers/tulas.py (prefijo /api/tulas).
func (s *Servicio) Rutas(mux *http.ServeMux, a *auth.Auth) {
	p := func(h http.HandlerFunc) http.HandlerFunc { return a.RequierePagina(h, PaginaEscaneo) }
	mux.HandleFunc("POST /api/tulas/{$}", p(s.hAbrir))
	mux.HandleFunc("POST /api/tulas", p(s.hAbrir))
	mux.HandleFunc("GET /api/tulas/{$}", p(s.hListar))
	mux.HandleFunc("GET /api/tulas", p(s.hListar))
	mux.HandleFunc("GET /api/tulas/base-del-dia", p(s.hBaseDelDia))
	mux.HandleFunc("GET /api/tulas/del-dia", p(s.hDelDia))
	mux.HandleFunc("GET /api/tulas/sin-leer", p(s.hSinLeer))
	mux.HandleFunc("GET /api/tulas/abierta", p(s.hAbierta))
	mux.HandleFunc("PATCH /api/tulas/{id}/total", p(s.hTotal))
	mux.HandleFunc("POST /api/tulas/{id}/seriales", p(s.hEscanear))
	mux.HandleFunc("POST /api/tulas/{id}/seriales/{serial}/reintentar-imile", p(s.hReintentar))
	mux.HandleFunc("POST /api/tulas/{id}/cerrar", p(s.hCerrar))
	mux.HandleFunc("GET /api/tulas/{id}", p(s.hDetalle))
}

func idDe(r *http.Request) (int64, error) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		return 0, httpx.Invalido("id de tula inválido")
	}
	return id, nil
}

func fechaDe(r *http.Request, obligatoria bool) (db.Fecha, error) {
	s := r.URL.Query().Get("fecha")
	if s == "" {
		if obligatoria {
			return db.Fecha{}, httpx.Invalido("falta fecha")
		}
		return db.Hoy(), nil
	}
	f, err := db.ParseFecha(s)
	if err != nil {
		return db.Fecha{}, httpx.Invalido("fecha inválida")
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

func (s *Servicio) hAbrir(w http.ResponseWriter, r *http.Request) {
	var body AbrirTula
	if err := httpx.LeerJSON(w, r, &body); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	body.LocalID = nil // solo por /api/flujo/sync
	t, err := s.Abrir(r.Context(), auth.DelContexto(r.Context()).Username, body)
	responder(w, r, http.StatusCreated, t, err)
}

func (s *Servicio) hListar(w http.ResponseWriter, r *http.Request) {
	f, err := fechaDe(r, true)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	ts, err := s.Listar(r.Context(), f)
	responder(w, r, http.StatusOK, ts, err)
}

func (s *Servicio) hBaseDelDia(w http.ResponseWriter, r *http.Request) {
	n, err := s.PaquetesHoy(r.Context())
	responder(w, r, http.StatusOK, map[string]int{"paquetes_hoy": n}, err)
}

func (s *Servicio) hDelDia(w http.ResponseWriter, r *http.Request) {
	d, err := s.DelDia(r.Context())
	responder(w, r, http.StatusOK, d, err)
}

func (s *Servicio) hSinLeer(w http.ResponseWriter, r *http.Request) {
	f, err := fechaDe(r, false)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	d, err := s.SinLeer(r.Context(), f)
	responder(w, r, http.StatusOK, d, err)
}

func (s *Servicio) hAbierta(w http.ResponseWriter, r *http.Request) {
	t, err := s.Abierta(r.Context(), auth.DelContexto(r.Context()).Username)
	responder(w, r, http.StatusOK, t, err)
}

func (s *Servicio) hTotal(w http.ResponseWriter, r *http.Request) {
	id, err := idDe(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	var body struct {
		TotalEsperado *int `json:"total_esperado"`
	}
	if err := httpx.LeerJSON(w, r, &body); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	t, err := s.FijarTotal(r.Context(), id, body.TotalEsperado)
	responder(w, r, http.StatusOK, t, err)
}

func (s *Servicio) hEscanear(w http.ResponseWriter, r *http.Request) {
	id, err := idDe(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	var body struct {
		Serial string `json:"serial"`
	}
	if err := httpx.LeerJSON(w, r, &body); err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	res, err := s.Escanear(r.Context(), id, body.Serial, auth.DelContexto(r.Context()).Username)
	responder(w, r, http.StatusOK, res, err)
}

func (s *Servicio) hReintentar(w http.ResponseWriter, r *http.Request) {
	id, err := idDe(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	res, err := s.ReintentarImile(r.Context(), id, r.PathValue("serial"), auth.DelContexto(r.Context()).Username)
	responder(w, r, http.StatusOK, res, err)
}

func (s *Servicio) hCerrar(w http.ResponseWriter, r *http.Request) {
	id, err := idDe(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	d, err := s.Cerrar(r.Context(), id)
	responder(w, r, http.StatusOK, d, err)
}

func (s *Servicio) hDetalle(w http.ResponseWriter, r *http.Request) {
	id, err := idDe(r)
	if err != nil {
		httpx.Fallar(w, r, err)
		return
	}
	d, err := s.Detalle(r.Context(), id)
	responder(w, r, http.StatusOK, d, err)
}
