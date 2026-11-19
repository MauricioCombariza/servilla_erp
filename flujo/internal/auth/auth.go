// Package auth: el mismo control de acceso que backend/app/auth/dependencies.py.
//
//   - JWT HS256 con el JWT_SECRET del backend; "sub" = usuario y "type" = "access".
//   - El usuario debe existir y estar activo; su rol debe tener alguna de las page_keys.
//   - /api/asignacion-qr/{token}: sin sesión, con el enlace del día (enlaces_vista);
//     queda registrado como "qr:<usuario del enlace>".
//
// Usuario y páginas del rol se guardan unos segundos en memoria: un escaneo no debe
// costar dos consultas extra a la base.
package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/httpx"
)

const cacheTTL = 30 * time.Second

type Usuario struct {
	Username string
	Rol      string
	pages    map[string]bool
}

func (u Usuario) TienePagina(keys ...string) bool {
	for _, k := range keys {
		if u.pages[k] {
			return true
		}
	}
	return false
}

type entrada[T any] struct {
	valor T
	vence time.Time
}

type Auth struct {
	pool    *pgxpool.Pool
	secreto []byte

	mu       sync.Mutex
	usuarios map[string]entrada[*Usuario] // nil = no existe o inactivo
}

func New(pool *pgxpool.Pool, secreto string) *Auth {
	return &Auth{pool: pool, secreto: []byte(secreto), usuarios: map[string]entrada[*Usuario]{}}
}

type ctxKey struct{}

func DelContexto(ctx context.Context) Usuario {
	u, _ := ctx.Value(ctxKey{}).(Usuario)
	return u
}

func ConUsuario(ctx context.Context, u Usuario) context.Context {
	return context.WithValue(ctx, ctxKey{}, u)
}

var (
	errNoAutenticado = &httpx.Error{Status: http.StatusForbidden, Detail: "Not authenticated"} // como HTTPBearer
	errToken         = &httpx.Error{Status: http.StatusUnauthorized, Detail: "Token inválido"}
	errInactivo      = &httpx.Error{Status: http.StatusUnauthorized, Detail: "Usuario inactivo o no existe"}
	ErrSinPermisos   = &httpx.Error{Status: http.StatusForbidden, Detail: "Sin permisos"}
)

// Usuario del token Bearer de la petición.
func (a *Auth) Autenticar(r *http.Request) (Usuario, error) {
	h := r.Header.Get("Authorization")
	esquema, token, ok := strings.Cut(h, " ")
	if !ok || !strings.EqualFold(esquema, "Bearer") || strings.TrimSpace(token) == "" {
		return Usuario{}, errNoAutenticado
	}
	claims := jwt.MapClaims{}
	_, err := jwt.ParseWithClaims(strings.TrimSpace(token), claims, func(*jwt.Token) (any, error) {
		return a.secreto, nil
	}, jwt.WithValidMethods([]string{"HS256"}))
	if err != nil {
		return Usuario{}, errToken
	}
	sub, _ := claims["sub"].(string)
	tipo, _ := claims["type"].(string)
	if sub == "" || tipo != "access" {
		return Usuario{}, errToken
	}
	u, err := a.usuario(r.Context(), sub)
	if err != nil {
		return Usuario{}, err
	}
	if u == nil {
		return Usuario{}, errInactivo
	}
	return *u, nil
}

func (a *Auth) usuario(ctx context.Context, username string) (*Usuario, error) {
	a.mu.Lock()
	e, ok := a.usuarios[username]
	a.mu.Unlock()
	if ok && time.Now().Before(e.vence) {
		return e.valor, nil
	}

	var u *Usuario
	var rol string
	var activo bool
	err := a.pool.QueryRow(ctx, `SELECT rol, activo FROM usuarios WHERE username = $1`, username).Scan(&rol, &activo)
	switch {
	case errors.Is(err, pgx.ErrNoRows):
	case err != nil:
		return nil, err
	case activo:
		pages, err := a.paginas(ctx, rol)
		if err != nil {
			return nil, err
		}
		u = &Usuario{Username: username, Rol: rol, pages: pages}
	}
	a.mu.Lock()
	a.usuarios[username] = entrada[*Usuario]{u, time.Now().Add(cacheTTL)}
	a.mu.Unlock()
	return u, nil
}

func (a *Auth) paginas(ctx context.Context, rol string) (map[string]bool, error) {
	rows, err := a.pool.Query(ctx, `
		SELECT rp.page_key FROM rol_paginas rp JOIN roles r ON r.nombre = rp.rol
		WHERE rp.rol = $1 AND r.activo = true`, rol)
	if err != nil {
		return nil, err
	}
	keys, err := pgx.CollectRows(rows, pgx.RowTo[string])
	if err != nil {
		return nil, err
	}
	m := make(map[string]bool, len(keys))
	for _, k := range keys {
		m[k] = true
	}
	return m, nil
}

// RequierePagina: como require_page(...) (semántica OR entre las page_keys).
func (a *Auth) RequierePagina(h http.HandlerFunc, keys ...string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u, err := a.Autenticar(r)
		if err != nil {
			httpx.Fallar(w, r, err)
			return
		}
		if !u.TienePagina(keys...) {
			httpx.Fallar(w, r, ErrSinPermisos)
			return
		}
		h(w, r.WithContext(ConUsuario(r.Context(), u)))
	}
}

// RequiereEnlaceQR: como _usuario_qr de routers/asignacion_zonas.py; el token va en {token}.
func (a *Auth) RequiereEnlaceQR(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var usuario string
		err := a.pool.QueryRow(r.Context(),
			`SELECT usuario FROM enlaces_vista WHERE token = $1 AND expira > now()`, r.PathValue("token"),
		).Scan(&usuario)
		if errors.Is(err, pgx.ErrNoRows) {
			httpx.Fallar(w, r, httpx.NoEncontrado("Enlace inválido o vencido"))
			return
		}
		if err != nil {
			httpx.Fallar(w, r, err)
			return
		}
		u := Usuario{Username: "qr:" + usuario, pages: map[string]bool{"asignacion_zonas": true}}
		h(w, r.WithContext(ConUsuario(r.Context(), u)))
	}
}
