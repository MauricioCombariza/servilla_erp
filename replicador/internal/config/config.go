// Package config lee la configuración del replicador (archivo JSON) y la URL de la base
// (variable REPLICADOR_DB_URL, nunca en el archivo).
package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"regexp"
	"time"

	"servilla/replicador/internal/destino"
	"servilla/replicador/internal/fuente"
	"servilla/replicador/internal/replica"
)

type Config struct {
	IntervaloMinutos int       `json:"intervalo_minutos"`
	Esquema          string    `json:"esquema"`
	Lote             int       `json:"lote"`
	Fuente           Fuente    `json:"fuente"`
	Archivos         []Archivo `json:"archivos"`
	DBURL            string    `json:"-"`
}

type Fuente struct {
	Tipo     string            `json:"tipo"` // "samba" o "local"
	Servidor string            `json:"servidor"`
	IP       string            `json:"ip"`
	Puerto   int               `json:"puerto"`
	Auth     string            `json:"auth"`
	Recursos map[string]string `json:"recursos"` // samba: recurso lógico → recurso del SCO; local: → carpeta
	Opciones []string          `json:"opciones"`
}

type Archivo struct {
	Recurso string `json:"recurso"`
	Ruta    string `json:"ruta"`
	Tabla   string `json:"tabla"`
	Desde   *struct {
		Campo string `json:"campo"`
		Fecha string `json:"fecha"`
	} `json:"desde"`
}

var nombreTabla = regexp.MustCompile(`^[a-z][a-z0-9_]{0,62}$`)

// Leer carga y valida la configuración.
func Leer(ruta string) (Config, error) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		return Config{}, err
	}
	var c Config
	if err := json.Unmarshal(b, &c); err != nil {
		return Config{}, fmt.Errorf("%s: %w", ruta, err)
	}
	c.DBURL = os.Getenv("REPLICADOR_DB_URL")
	if c.DBURL == "" {
		return Config{}, errors.New("falta REPLICADOR_DB_URL")
	}
	if c.IntervaloMinutos <= 0 {
		c.IntervaloMinutos = 10
	}
	if c.Esquema == "" {
		c.Esquema = "legacy"
	}
	if c.Fuente.Tipo != "samba" && c.Fuente.Tipo != "local" {
		return Config{}, fmt.Errorf("fuente.tipo debe ser samba o local, no %q", c.Fuente.Tipo)
	}
	vistas := map[string]bool{}
	for _, a := range c.Archivos {
		if !nombreTabla.MatchString(a.Tabla) || vistas[a.Tabla] {
			return Config{}, fmt.Errorf("tabla inválida o repetida: %q", a.Tabla)
		}
		vistas[a.Tabla] = true
		if _, ok := c.Fuente.Recursos[a.Recurso]; !ok {
			return Config{}, fmt.Errorf("%s: recurso %q no está en fuente.recursos", a.Tabla, a.Recurso)
		}
		if a.Desde != nil {
			if _, err := time.Parse("2006-01-02", a.Desde.Fecha); err != nil {
				return Config{}, fmt.Errorf("%s: fecha del filtro: %w", a.Tabla, err)
			}
		}
	}
	if len(c.Archivos) == 0 {
		return Config{}, errors.New("no hay archivos para replicar")
	}
	return c, nil
}

// LaFuente arma la fuente configurada.
func (c Config) LaFuente() fuente.Fuente {
	if c.Fuente.Tipo == "local" {
		return fuente.Local{Carpetas: c.Fuente.Recursos}
	}
	return fuente.Samba{Servidor: c.Fuente.Servidor, IP: c.Fuente.IP, Puerto: c.Fuente.Puerto,
		Auth: c.Fuente.Auth, Recursos: c.Fuente.Recursos, Opciones: c.Fuente.Opciones}
}

// LosArchivos devuelve la lista para el replicador.
func (c Config) LosArchivos() []replica.Archivo {
	out := make([]replica.Archivo, 0, len(c.Archivos))
	for _, a := range c.Archivos {
		r := replica.Archivo{Recurso: a.Recurso, Ruta: a.Ruta, Tabla: a.Tabla}
		if a.Desde != nil {
			d, _ := time.Parse("2006-01-02", a.Desde.Fecha)
			r.Filtro = &destino.Filtro{Campo: a.Desde.Campo, Desde: d}
		}
		out = append(out, r)
	}
	return out
}
