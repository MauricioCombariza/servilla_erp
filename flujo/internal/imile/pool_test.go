package imile

// Prueba del pool de páginas Playwright contra el iMile FALSO de backend/tests/fake_imile.py
// (mismo JSON que iMile real; nunca toca iMile). Necesita el driver de playwright-go,
// Chromium, el iMile falso corriendo y una base de pruebas con las migraciones:
//
//	FAKE_IMILE_URL=http://127.0.0.1:NNNN FLUJO_TEST_DATABASE_URL=postgresql://.../flujo_test go test -run Pool ./internal/imile/

import (
	"context"
	"os"
	"testing"
	"time"

	"servilla/flujo/internal/config"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/outbox"
)

func TestPoolContraImileFalso(t *testing.T) {
	url, dbURL := os.Getenv("FAKE_IMILE_URL"), os.Getenv("FLUJO_TEST_DATABASE_URL")
	if url == "" || dbURL == "" {
		t.Skip("sin FAKE_IMILE_URL / FLUJO_TEST_DATABASE_URL")
	}
	ctx := context.Background()
	pool, err := db.Conectar(ctx, dbURL)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	exec := func(sql string, args ...any) {
		t.Helper()
		if _, err := pool.Exec(ctx, sql, args...); err != nil {
			t.Fatal(err)
		}
	}
	exec(`TRUNCATE imile_tareas, asignaciones_imile RESTART IDENTITY CASCADE`)
	exec(`DELETE FROM personal WHERE identificacion LIKE 'pool-%'`)
	var juan, ana int64
	if err := pool.QueryRow(ctx, `INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal)
		VALUES ('8001', 'Juan Porras', 'pool-1', 'mensajero') RETURNING id`).Scan(&juan); err != nil {
		t.Fatal(err)
	}
	if err := pool.QueryRow(ctx, `INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal)
		VALUES ('8002', 'Ana Ruiz', 'pool-2', 'mensajero') RETURNING id`).Scan(&ana); err != nil {
		t.Fatal(err)
	}

	hoy := db.Hoy()
	ingresos := map[string]string{ // serial → estado esperado
		"IM200001": OK, "IM200002": OK, "IM200003": OK, "IM200004": OK,
		"NOEXISTE-9": Error, "BLOQ-9": Repetido,
	}
	for s := range ingresos {
		if _, err := outbox.Encolar(ctx, pool, outbox.Tarea{Tipo: outbox.TipoIngreso, Serial: s, Fecha: hoy, Usuario: "t"}); err != nil {
			t.Fatal(err)
		}
	}
	envioJuan, envioAna := "00000000-0000-4000-8000-00000000000a", "00000000-0000-4000-8000-00000000000b"
	for _, s := range []string{"IM300001", "IM300002", "NOEXISTE-8"} {
		_, _ = outbox.Encolar(ctx, pool, outbox.Tarea{Tipo: outbox.TipoAsignar, Serial: s, Fecha: hoy, PersonalID: &juan, EnvioID: &envioJuan, Usuario: "t"})
	}
	for _, s := range []string{"IM300003", "IM300004"} {
		_, _ = outbox.Encolar(ctx, pool, outbox.Tarea{Tipo: outbox.TipoAsignar, Serial: s, Fecha: hoy, PersonalID: &ana, EnvioID: &envioAna, Usuario: "t"})
	}

	cfg := config.Config{ImileUser: "operador", ImilePass: "clave-secreta", ImileBaseURL: url,
		ImileStatePath: t.TempDir() + "/sesion.json", ImileHeadless: true, ImileDriverDir: os.Getenv("PLAYWRIGHT_DRIVER_PATH")}
	sesion := NuevaSesion(cfg)
	sesion.esperaCargaMs, sesion.recorridoQuietoMs, sesion.recorridoMaxMs = 200, 1_000, 5_000
	defer sesion.Cerrar()

	ctxW, parar := context.WithCancel(ctx)
	w := &Workers{Pool: pool, Sesion: sesion, Ingreso: 3, Asignar: 2, MaxIntentos: 3}
	inicio := time.Now()
	w.Arrancar(ctxW)
	esperarCola := func() {
		t.Helper()
		limite := time.Now().Add(3 * time.Minute)
		for time.Now().Before(limite) {
			var n int
			_ = pool.QueryRow(ctx, `SELECT count(*) FROM imile_tareas WHERE estado IN ('pendiente', 'en_proceso')`).Scan(&n)
			if n == 0 {
				return
			}
			time.Sleep(300 * time.Millisecond)
		}
		t.Fatal("la cola no se vació a tiempo")
	}
	esperarCola()
	t.Logf("11 tareas con 3+2 páginas en %s", time.Since(inicio).Round(time.Millisecond))

	resultado := func(tipo, serial string) (string, string) {
		var estado string
		var res *string
		if err := pool.QueryRow(ctx, `SELECT estado, resultado FROM imile_tareas WHERE tipo = $1 AND serial = $2`, tipo, serial).Scan(&estado, &res); err != nil {
			t.Fatal(serial, err)
		}
		if res == nil {
			return estado, ""
		}
		return estado, *res
	}
	for s, quiero := range ingresos {
		if estado, r := resultado(outbox.TipoIngreso, s); estado != outbox.EstadoHecha || r != quiero {
			t.Errorf("ingreso %s: %s/%s, se esperaba hecha/%s", s, estado, r, quiero)
		}
	}
	for s, quiero := range map[string]string{"IM300001": OK, "IM300002": OK, "NOEXISTE-8": Error} {
		if estado, r := resultado(outbox.TipoAsignar, s); estado != outbox.EstadoHecha || r != quiero {
			t.Errorf("asignar %s: %s/%s, se esperaba hecha/%s", s, estado, r, quiero)
		}
	}
	// "Ana Ruiz" está dos veces en el selector DA de iMile: el envío se detiene y se avisa
	var canceladas int
	var motivo string
	_ = pool.QueryRow(ctx, `SELECT count(*), max(ultimo_error) FROM imile_tareas WHERE envio_id = $1 AND estado = 'cancelada'`, envioAna).Scan(&canceladas, &motivo)
	if canceladas != 2 || motivo == "" {
		t.Errorf("el envío de Ana debía cancelarse: %d %q", canceladas, motivo)
	}
	var guardadas int
	_ = pool.QueryRow(ctx, `SELECT count(*) FROM asignaciones_imile WHERE personal_id = $1`, juan).Scan(&guardadas)
	if guardadas != 3 {
		t.Errorf("las 3 asignaciones de Juan deben quedar en asignaciones_imile, hay %d", guardadas)
	}

	// La sesión se cae (iMile borra la cookie): el worker vuelve a entrar solo y sigue
	if err := sesion.bctx.ClearCookies(); err != nil {
		t.Fatal(err)
	}
	for _, p := range sesion.bctx.Pages() { // la cola está vacía: ningún worker usa su página
		if _, err := p.Reload(); err != nil {
			t.Fatal(err)
		}
	}
	gen := sesion.Generacion()
	_, _ = outbox.Encolar(ctx, pool, outbox.Tarea{Tipo: outbox.TipoIngreso, Serial: "IM200001", Fecha: hoy, Usuario: "t"})
	_, _ = outbox.Encolar(ctx, pool, outbox.Tarea{Tipo: outbox.TipoIngreso, Serial: "IM200099", Fecha: hoy, Usuario: "t"})
	esperarCola()
	var repetido, nuevo string
	_ = pool.QueryRow(ctx, `SELECT resultado FROM imile_tareas WHERE serial = 'IM200001' ORDER BY id DESC LIMIT 1`).Scan(&repetido)
	_ = pool.QueryRow(ctx, `SELECT resultado FROM imile_tareas WHERE serial = 'IM200099'`).Scan(&nuevo)
	if repetido != Repetido || nuevo != OK {
		t.Errorf("tras volver a entrar: IM200001=%s (repetido) IM200099=%s (ok)", repetido, nuevo)
	}
	if sesion.Generacion() == gen {
		t.Error("se esperaba un nuevo inicio de sesión")
	}
	parar()
	w.Esperar()
}
