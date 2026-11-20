package destino_test

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/replicador/internal/dbf/dbftest"
	"servilla/replicador/internal/destino"
	"servilla/replicador/internal/fuente"
	"servilla/replicador/internal/replica"
)

// Prueba contra un Postgres real. Solo corre con REPLICADOR_TEST_DB (p. ej. la base
// ci_prueba local); usa un esquema propio que borra al terminar.
func conectar(t *testing.T) (*pgxpool.Pool, string) {
	url := os.Getenv("REPLICADOR_TEST_DB")
	if url == "" {
		t.Skip("sin REPLICADOR_TEST_DB")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	esquema := "legacy_prueba"
	for _, q := range []string{
		"DROP SCHEMA IF EXISTS " + esquema + " CASCADE",
		"CREATE SCHEMA " + esquema,
		`CREATE TABLE ` + esquema + `._archivos (tabla varchar(64) PRIMARY KEY, recurso varchar(30) NOT NULL,
		  ruta varchar(200) NOT NULL, marca varchar(100) NOT NULL DEFAULT '', registros bigint NOT NULL DEFAULT 0,
		  ultima_pasada timestamptz, ultima_buena timestamptz, ultimo_error text)`,
		`CREATE TABLE ` + esquema + `._conciliacion (id bigserial PRIMARY KEY, fecha timestamptz NOT NULL DEFAULT now(),
		  tabla varchar(64) NOT NULL, registros_dbf bigint NOT NULL, incluidos bigint NOT NULL, borrados bigint NOT NULL,
		  enviados bigint NOT NULL, en_pg bigint NOT NULL, suma_dbf numeric NOT NULL, suma_pg numeric NOT NULL,
		  ok boolean NOT NULL, segundos double precision NOT NULL)`,
	} {
		if _, err := pool.Exec(ctx, q); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() {
		pool.Exec(context.Background(), "DROP SCHEMA IF EXISTS "+esquema+" CASCADE")
		pool.Close()
	})
	return pool, esquema
}

var campos = []dbftest.Campo{
	{Nombre: "serial", Tipo: 'C', Largo: 10},
	{Nombre: "f_emi", Tipo: 'D', Largo: 8},
	{Nombre: "nombred", Tipo: 'C', Largo: 20},
	{Nombre: "valor", Tipo: 'N', Largo: 8, Dec: 2},
	{Nombre: "orden", Tipo: 'C', Largo: 6}, // palabra reservada de SQL: debe ir entre comillas
}

func TestReplicaContraPostgres(t *testing.T) {
	pool, esquema := conectar(t)
	ctx := context.Background()
	dir := t.TempDir()
	archivo := filepath.Join(dir, "guia2601.his")
	escribir := func(filas []dbftest.Fila, mod time.Time) {
		os.WriteFile(archivo, dbftest.Armar(campos, filas), 0o644)
		os.Chtimes(archivo, mod, mod)
	}
	rep := replica.Replicador{
		Fuente:  fuente.Local{Carpetas: map[string]string{"guias": dir}},
		Destino: destino.Postgres{Pool: pool, Esquema: esquema},
		Lote:    2,
	}
	a := replica.Archivo{Recurso: "guias", Ruta: "guia2601.his", Tabla: "guia2601",
		Filtro: &destino.Filtro{Campo: "f_emi", Desde: time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)}}
	t0 := time.Date(2026, 11, 20, 8, 0, 0, 0, time.UTC)

	escribir([]dbftest.Fila{
		{Valores: []string{"0000000001", "20260105", "PE\xd1A", "1500.50", "OR1"}},
		{Valores: []string{"0000000002", "20240105", "VIEJA", "1", "OR1"}}, // 2024: no sube
		{Valores: []string{"0000000003", "52010925", "FECHA MAL", "", "OR2"}},
	}, t0)
	r, err := rep.Pasada(ctx, a)
	if err != nil {
		t.Fatal(err)
	}
	if !r.Conciliacion.OK() || r.Conciliacion.Incluidos != 2 {
		t.Fatalf("conciliación: %+v", r.Conciliacion)
	}

	var nombre, valor, orden, crudo string
	var fecha time.Time
	err = pool.QueryRow(ctx, `SELECT nombred, valor::text, "orden", f_emi FROM `+esquema+`.guia2601 WHERE _recno = 1`).
		Scan(&nombre, &valor, &orden, &fecha)
	if err != nil || nombre != "PEÑA" || valor != "1500.50" || orden != "OR1" || fecha.Year() != 2026 {
		t.Fatalf("fila 1: %q %q %q %v %v", nombre, valor, orden, fecha, err)
	}
	err = pool.QueryRow(ctx, `SELECT _crudo->>'f_emi' FROM `+esquema+`.guia2601 WHERE _recno = 3 AND f_emi IS NULL`).Scan(&crudo)
	if err != nil || crudo != "52010925" {
		t.Fatalf("la fecha inválida debe quedar en _crudo: %q %v", crudo, err)
	}

	// Cambia una fila y se agrega otra columna en el FoxPro
	campos = append(campos, dbftest.Campo{Nombre: "nuevo", Tipo: 'C', Largo: 3})
	escribir([]dbftest.Fila{
		{Valores: []string{"0000000001", "20260105", "PEÑA", "1500.50", "OR1", "SI"}},
		{Valores: []string{"0000000002", "20240105", "VIEJA", "1", "OR1", ""}},
		{Valores: []string{"0000000003", "52010925", "FECHA MAL", "", "OR2", ""}},
	}, t0.Add(time.Minute))
	r, err = rep.Pasada(ctx, a)
	if err != nil || !r.Conciliacion.OK() {
		t.Fatalf("segunda pasada: %+v %v", r.Conciliacion, err)
	}

	var marca, fallo *string
	if err := pool.QueryRow(ctx, `SELECT marca, ultimo_error FROM `+esquema+`._archivos WHERE tabla = 'guia2601'`).
		Scan(&marca, &fallo); err != nil || marca == nil || *marca == "" || fallo != nil {
		t.Fatalf("estado: %v %v %v", marca, fallo, err)
	}
	var n int
	pool.QueryRow(ctx, `SELECT count(*) FROM `+esquema+`._conciliacion WHERE ok`).Scan(&n)
	if n != 2 {
		t.Fatalf("esperaba 2 conciliaciones buenas, hay %d", n)
	}

	// Sin cambios: no hace nada
	if r, err := rep.Pasada(ctx, a); err != nil || !r.SinCambios {
		t.Fatalf("esperaba sin cambios: %+v %v", r, err)
	}
}
