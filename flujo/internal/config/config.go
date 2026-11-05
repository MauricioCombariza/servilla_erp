// Package config lee la configuración del entorno, con los mismos nombres que usa el
// backend Python (backend/app/config.py) para poder compartir el mismo .env.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Puerto      string
	DatabaseURL string
	JWTSecret   string

	ImileUser        string
	ImilePass        string
	ImileBaseURL     string
	ImileLoginURL    string
	ImileStatePath   string
	ImileHeadless    bool
	ImileDriverDir   string
	IngresoActivo    bool
	ConsultaActiva   bool
	AsignacionActiva bool
	PoolIngreso      int
	PoolAsignar      int
	MaxIntentos      int
	ConsultaCacheTTL time.Duration
}

func Cargar() (Config, error) {
	c := Config{
		Puerto:      env("PORT", "8090"),
		DatabaseURL: pgxURL(os.Getenv("DATABASE_URL")),
		JWTSecret:   os.Getenv("JWT_SECRET"),

		ImileUser:      os.Getenv("IMILE_USER"),
		ImilePass:      os.Getenv("IMILE_PASS"),
		ImileBaseURL:   env("IMILE_BASE_URL", "https://ds.imile.com"),
		ImileLoginURL:  os.Getenv("IMILE_LOGIN_URL"), // vacío: ds-login.imile.com para iMile real, si no <base>/login
		ImileStatePath: env("IMILE_SESION_STATE_PATH", "/app/.secrets/imile_sesion.json"),
		ImileHeadless:  envBool("IMILE_HEADLESS", true),
		ImileDriverDir: os.Getenv("PLAYWRIGHT_DRIVER_PATH"),
		// Mismos valores por defecto que backend/app/config.py
		IngresoActivo:    envBool("IMILE_INGRESO_ACTIVO", false),
		ConsultaActiva:   envBool("IMILE_CONSULTA_TULA_ACTIVA", false),
		AsignacionActiva: envBool("IMILE_ASIGNACION_ACTIVA", true),
		PoolIngreso:      envInt("IMILE_POOL_INGRESO", 2),
		PoolAsignar:      envInt("IMILE_POOL_ASIGNAR", 1),
		MaxIntentos:      envInt("IMILE_MAX_INTENTOS", 5),
		ConsultaCacheTTL: time.Duration(envInt("IMILE_CONSULTA_CACHE_S", 15)) * time.Second,
	}
	if c.DatabaseURL == "" {
		return c, fmt.Errorf("falta DATABASE_URL")
	}
	if c.JWTSecret == "" {
		return c, fmt.Errorf("falta JWT_SECRET")
	}
	return c, nil
}

// pgxURL acepta la URL del backend Python ("postgresql+asyncpg://...") tal cual.
func pgxURL(u string) string {
	return strings.Replace(u, "postgresql+asyncpg://", "postgresql://", 1)
}

func env(nombre, defecto string) string {
	if v := strings.TrimSpace(os.Getenv(nombre)); v != "" {
		return v
	}
	return defecto
}

func envBool(nombre string, defecto bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(nombre)))
	switch v {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	}
	return defecto
}

func envInt(nombre string, defecto int) int {
	if n, err := strconv.Atoi(strings.TrimSpace(os.Getenv(nombre))); err == nil {
		return n
	}
	return defecto
}
