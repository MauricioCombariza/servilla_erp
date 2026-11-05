// Package httpx: respuestas JSON con el mismo formato de error que FastAPI
// ({"detail": ...}) y los middlewares comunes del servicio.
package httpx

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"runtime/debug"
	"time"
)

// Error es lo que devuelven los servicios cuando la operación no se puede hacer: el
// handler HTTP y la sincronización offline lo responden igual.
type Error struct {
	Status int
	Detail any
}

func (e *Error) Error() string {
	if s, ok := e.Detail.(string); ok {
		return s
	}
	b, _ := json.Marshal(e.Detail)
	return string(b)
}

func NoEncontrado(detalle string) *Error { return &Error{http.StatusNotFound, detalle} }
func Conflicto(detalle any) *Error      { return &Error{http.StatusConflict, detalle} }
func Invalido(detalle any) *Error       { return &Error{http.StatusUnprocessableEntity, detalle} }

func JSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if v != nil {
		_ = json.NewEncoder(w).Encode(v)
	}
}

// Fallar responde el error: un *Error con su estado; cualquier otro como 500 sin
// mostrar el detalle interno.
func Fallar(w http.ResponseWriter, r *http.Request, err error) {
	var e *Error
	if errors.As(err, &e) {
		JSON(w, e.Status, map[string]any{"detail": e.Detail})
		return
	}
	slog.ErrorContext(r.Context(), "error interno", "err", err, "ruta", r.URL.Path)
	JSON(w, http.StatusInternalServerError, map[string]any{"detail": "Error interno del servidor"})
}

// LeerJSON decodifica el cuerpo (máx. 1 MB); un cuerpo mal formado es 422 como en FastAPI.
func LeerJSON(w http.ResponseWriter, r *http.Request, v any) error {
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
	if err := json.NewDecoder(r.Body).Decode(v); err != nil {
		return Invalido("Cuerpo JSON inválido: " + err.Error())
	}
	return nil
}

type escritorConEstado struct {
	http.ResponseWriter
	estado int
}

func (e *escritorConEstado) WriteHeader(code int) {
	e.estado = code
	e.ResponseWriter.WriteHeader(code)
}

// Middleware: id de petición, log de cada petición y recuperación de pánicos.
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Request-Id")
		if id == "" {
			b := make([]byte, 8)
			_, _ = rand.Read(b)
			id = hex.EncodeToString(b)
		}
		w.Header().Set("X-Request-Id", id)
		ew := &escritorConEstado{ResponseWriter: w, estado: http.StatusOK}
		inicio := time.Now()
		defer func() {
			if p := recover(); p != nil {
				slog.Error("pánico", "valor", p, "ruta", r.URL.Path, "stack", string(debug.Stack()))
				JSON(ew, http.StatusInternalServerError, map[string]any{"detail": "Error interno del servidor"})
			}
			slog.Info("http", "id", id, "metodo", r.Method, "ruta", r.URL.Path, "estado", ew.estado,
				"ms", time.Since(inicio).Milliseconds())
		}()
		next.ServeHTTP(ew, r)
	})
}
