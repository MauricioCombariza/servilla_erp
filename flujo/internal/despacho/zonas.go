package despacho

import (
	"sort"
	"strconv"
	"strings"
)

// ordenarZonas: misma clave que en Python (orden de la serie, número dentro de la serie, nombre).
func ordenarZonas[T any](filas []T, campos func(T) (string, int)) []string {
	serieOrden := map[string]int{}
	for _, f := range filas {
		nombre, orden := campos(f)
		serie, _, _ := strings.Cut(nombre, "_")
		if o, ok := serieOrden[serie]; !ok || orden < o {
			serieOrden[serie] = orden
		}
	}
	type clave struct {
		serie, numero int
		nombre        string
	}
	claves := make([]clave, len(filas))
	for i, f := range filas {
		nombre, _ := campos(f)
		serie, numero, _ := strings.Cut(nombre, "_")
		n, err := strconv.Atoi(numero)
		if err != nil || numero == "" || strings.ContainsAny(numero, "+-") {
			n = 0
		}
		claves[i] = clave{serieOrden[serie], n, nombre}
	}
	sort.Slice(claves, func(i, j int) bool {
		a, b := claves[i], claves[j]
		if a.serie != b.serie {
			return a.serie < b.serie
		}
		if a.numero != b.numero {
			return a.numero < b.numero
		}
		return a.nombre < b.nombre
	})
	zonas := make([]string, len(claves))
	for i, c := range claves {
		zonas[i] = c.nombre
	}
	return zonas
}
