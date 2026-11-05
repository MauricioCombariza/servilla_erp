package app

// Pruebas de punta a punta contra un PostgreSQL de pruebas con las migraciones de Alembic
// aplicadas. Se saltan si no está FLUJO_TEST_DATABASE_URL. BORRAN los datos de las
// tablas del flujo: nunca apuntar a la base de desarrollo ni a producción.
//
//	FLUJO_TEST_DATABASE_URL=postgresql://servilla:...@localhost:5440/flujo_test go test ./...

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/flujo/internal/config"
	"servilla/flujo/internal/db"
	"servilla/flujo/internal/imile"
	"servilla/flujo/internal/outbox"
)

const secreto = "secreto-de-pruebas"

type consultaFalsa struct{}

func (consultaFalsa) Consultar(_ context.Context, codigo string) (imile.ConsultaTula, error) {
	if codigo != "T1" {
		return imile.ConsultaTula{}, nil
	}
	n := 2
	return imile.ConsultaTula{Encontrada: true, Total: &n, Seriales: []string{"S0001", "S0002"}}, nil
}

type entorno struct {
	t     *testing.T
	pool  *pgxpool.Pool
	srv   *httptest.Server
	zonas []string
}

func preparar(t *testing.T) *entorno {
	url := os.Getenv("FLUJO_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("sin FLUJO_TEST_DATABASE_URL")
	}
	ctx := context.Background()
	pool, err := db.Conectar(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	ejecutar(t, pool, `
		TRUNCATE tulas, tula_seriales, imile_tareas, operaciones_cliente, asignaciones_zona, asignaciones_serial,
		         asignaciones_imile, paquetes_despacho, enlaces_vista RESTART IDENTITY CASCADE;
		DELETE FROM personal WHERE identificacion LIKE 'flujo-%';
		DELETE FROM usuarios WHERE username LIKE 'flujo_%';
		INSERT INTO usuarios (username, password_hash, nombre_completo, rol, activo) VALUES
			('flujo_admin', 'x', 'Admin', 'administrador', true),
			('flujo_esc', 'x', 'Escaneo', 'mensajero', true),
			('flujo_inactivo', 'x', 'Inactivo', 'administrador', false);
		INSERT INTO personal (codigo, nombre_completo, identificacion, tipo_personal, activo, nombre_imile) VALUES
			('9001', 'Juan Porras', 'flujo-1', 'mensajero', true, NULL),
			('9002', 'Ana Ruiz', 'flujo-2', 'mensajero', true, 'Ana Ruiz | D21000000001');
		INSERT INTO enlaces_vista (token, usuario, fecha, expira) VALUES
			('qr-valido', 'flujo_esc', CURRENT_DATE, now() + interval '1 day'),
			('qr-vencido', 'flujo_admin', CURRENT_DATE, now() - interval '1 minute');`)

	var zonas []string
	rows, err := pool.Query(ctx, `SELECT DISTINCT nombre FROM sectorizacion_limites WHERE tipo = 'zona' AND activo ORDER BY nombre LIMIT 2`)
	if err != nil {
		t.Fatal(err)
	}
	for rows.Next() {
		var z string
		_ = rows.Scan(&z)
		zonas = append(zonas, z)
	}
	if len(zonas) < 2 {
		t.Skip("la base de pruebas no tiene zonas en sectorizacion_limites")
	}
	hoy := db.Hoy()
	ejecutar(t, pool, `
		INSERT INTO paquetes_despacho (serial, direccion, direccion_estandarizada, localidad, zona, f_emi, estado) VALUES
			('S0001', 'Calle 1', 'CL 1', 'Chapinero', $1, $3, 'sin gestión'),
			('S0002', 'Calle 2', 'CL 2', 'Suba', $2, $3, 'sin gestión'),
			('S0003', 'Calle 3', NULL, NULL, NULL, $3, 'sin gestión')`, zonas[0], zonas[1], hoy)

	cfg := config.Config{JWTSecret: secreto, IngresoActivo: true, AsignacionActiva: true}
	a := Nueva(pool, cfg, imile.NuevaSesion(cfg), consultaFalsa{})
	srv := httptest.NewServer(a.Handler)
	t.Cleanup(srv.Close)
	return &entorno{t: t, pool: pool, srv: srv, zonas: zonas}
}

func ejecutar(t *testing.T, pool *pgxpool.Pool, sql string, args ...any) {
	t.Helper()
	if _, err := pool.Exec(context.Background(), sql, args...); err != nil {
		t.Fatalf("%v\n%s", err, sql)
	}
}

func token(usuario string) string {
	tk := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": usuario, "type": "access", "exp": time.Now().Add(time.Hour).Unix(),
	})
	s, _ := tk.SignedString([]byte(secreto))
	return s
}

func (e *entorno) pedir(metodo, ruta, usuario string, body any, out any) int {
	e.t.Helper()
	var r *bytes.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		r = bytes.NewReader(b)
	} else {
		r = bytes.NewReader(nil)
	}
	req, _ := http.NewRequest(metodo, e.srv.URL+ruta, r)
	if usuario != "" {
		req.Header.Set("Authorization", "Bearer "+token(usuario))
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		e.t.Fatal(err)
	}
	defer resp.Body.Close()
	if out != nil {
		_ = json.NewDecoder(resp.Body).Decode(out)
	}
	return resp.StatusCode
}

func (e *entorno) contar(sql string, args ...any) int {
	e.t.Helper()
	var n int
	if err := e.pool.QueryRow(context.Background(), sql, args...).Scan(&n); err != nil {
		e.t.Fatal(err)
	}
	return n
}

func esperarEstado(t *testing.T, obtuve, quiero int, que string) {
	t.Helper()
	if obtuve != quiero {
		t.Fatalf("%s: HTTP %d, se esperaba %d", que, obtuve, quiero)
	}
}

type tulaJSON struct {
	ID         int64   `json:"id"`
	Estado     string  `json:"estado"`
	Leidos     int     `json:"leidos"`
	Contador   int     `json:"contador"`
	Diferencia *int    `json:"diferencia"`
	ImileTotal *string `json:"imile_total"`
}

func TestTulaCompleta(t *testing.T) {
	e := preparar(t)
	var t1 tulaJSON
	esperarEstado(t, e.pedir("POST", "/api/tulas/", "flujo_esc", map[string]any{"codigo": " T1 "}, &t1), 201, "abrir")
	if t1.Contador != 2 || t1.ImileTotal == nil || *t1.ImileTotal != "iMile: la tula trae 2 paquetes" {
		t.Fatalf("la tula debe abrir con el total de iMile: %+v", t1)
	}

	var r struct {
		Tula        tulaJSON `json:"tula"`
		YaEscaneado bool     `json:"ya_escaneado"`
		Destino     struct {
			Zona     *string `json:"zona"`
			Ultimos4 string  `json:"ultimos_4"`
			Aviso    *string `json:"aviso"`
		} `json:"destino"`
		Imile struct {
			Estado *string `json:"estado"`
		} `json:"imile"`
	}
	ruta := fmt.Sprintf("/api/tulas/%d/seriales", t1.ID)
	esperarEstado(t, e.pedir("POST", ruta, "flujo_esc", map[string]string{"serial": " S0001 "}, &r), 200, "escanear")
	if r.Tula.Contador != 1 || r.YaEscaneado || r.Destino.Zona == nil || *r.Destino.Zona != e.zonas[0] ||
		r.Destino.Ultimos4 != "0001" || r.Imile.Estado == nil || *r.Imile.Estado != "pendiente" {
		t.Fatalf("lectura mal: %+v", r)
	}
	esperarEstado(t, e.pedir("POST", ruta, "flujo_esc", map[string]string{"serial": "S0001"}, &r), 200, "repetir")
	if !r.YaEscaneado || r.Tula.Leidos != 1 {
		t.Fatalf("un serial repetido no se cuenta dos veces: %+v", r)
	}
	if n := e.contar(`SELECT count(*) FROM imile_tareas WHERE serial = 'S0001'`); n != 1 {
		t.Fatalf("el ingreso en iMile se encola una sola vez, hay %d", n)
	}
	e.pedir("POST", ruta, "flujo_esc", map[string]string{"serial": "X9"}, &r)
	if r.Destino.Aviso == nil || *r.Destino.Aviso != "No está en la tabla" || r.Tula.Contador != 0 {
		t.Fatalf("serial fuera de la base: %+v", r)
	}

	var conflicto struct {
		Detail struct {
			TulaAbierta tulaJSON `json:"tula_abierta"`
		} `json:"detail"`
	}
	esperarEstado(t, e.pedir("POST", "/api/tulas/", "flujo_esc", map[string]any{"codigo": "T2"}, &conflicto), 409, "otra abierta")
	if conflicto.Detail.TulaAbierta.ID != t1.ID {
		t.Fatalf("el 409 debe traer la tula abierta: %+v", conflicto)
	}
	var mismo tulaJSON
	esperarEstado(t, e.pedir("POST", "/api/tulas/", "flujo_esc", map[string]any{"codigo": "T1"}, &mismo), 201, "misma tula")
	if mismo.ID != t1.ID {
		t.Fatal("volver a escanear la misma tula la deja abierta")
	}
	var t2 tulaJSON
	esperarEstado(t, e.pedir("POST", "/api/tulas/", "flujo_esc", map[string]any{"codigo": "T2", "cerrar_anterior": true}, &t2), 201, "cerrar y abrir")

	var d struct {
		Estado      string   `json:"estado"`
		Faltantes   []string `json:"faltantes"`
		NoEsperados []string `json:"no_esperados"`
		Seriales    []struct {
			Serial    string  `json:"serial"`
			Localidad *string `json:"localidad"`
		} `json:"seriales"`
	}
	esperarEstado(t, e.pedir("GET", fmt.Sprintf("/api/tulas/%d", t1.ID), "flujo_esc", nil, &d), 200, "detalle")
	if d.Estado != "cerrada" || len(d.Seriales) != 2 || fmt.Sprint(d.Faltantes) != "[S0002]" || fmt.Sprint(d.NoEsperados) != "[X9]" {
		t.Fatalf("detalle mal: %+v", d)
	}
	if d.Seriales[0].Localidad == nil || *d.Seriales[0].Localidad != "Chapinero" {
		t.Fatalf("la localidad sale de la base de despacho: %+v", d.Seriales[0])
	}
	esperarEstado(t, e.pedir("POST", ruta, "flujo_esc", map[string]string{"serial": "S0002"}, nil), 409, "escanear en tula cerrada")

	var sinLeer struct {
		Total int `json:"total"`
	}
	e.pedir("GET", "/api/tulas/sin-leer", "flujo_esc", nil, &sinLeer)
	if sinLeer.Total != 2 { // S0002 y S0003
		t.Fatalf("sin leer: %d", sinLeer.Total)
	}
	var delDia struct {
		Tulas, Paquetes int
	}
	e.pedir("GET", "/api/tulas/del-dia", "flujo_esc", nil, &delDia)
	if delDia.Tulas != 2 || delDia.Paquetes != 2 {
		t.Fatalf("del día: %+v", delDia)
	}
}

// Muchos celulares (o reintentos) leyendo a la vez en la misma tula: nada se cuenta dos veces.
func TestEscaneoConcurrente(t *testing.T) {
	e := preparar(t)
	var tula tulaJSON
	e.pedir("POST", "/api/tulas/", "flujo_esc", map[string]any{"codigo": nil}, &tula)
	var wg sync.WaitGroup
	errores := make(chan int, 100)
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			if c := e.pedir("POST", fmt.Sprintf("/api/tulas/%d/seriales", tula.ID), "flujo_esc",
				map[string]string{"serial": fmt.Sprintf("C%03d", i%40)}, nil); c != 200 {
				errores <- c
			}
		}(i)
	}
	wg.Wait()
	close(errores)
	for c := range errores {
		t.Errorf("escaneo concurrente respondió %d", c)
	}
	if n := e.contar(`SELECT count(*) FROM tula_seriales WHERE tula_id = $1`, tula.ID); n != 40 {
		t.Fatalf("se esperaban 40 paquetes, hay %d", n)
	}
	if n := e.contar(`SELECT count(*) FROM imile_tareas`); n != 40 {
		t.Fatalf("se esperaban 40 tareas de iMile, hay %d", n)
	}
}

// El mismo lote llega dos veces (se cortó la red antes de la respuesta): nada se repite.
func TestSyncIdempotente(t *testing.T) {
	e := preparar(t)
	local := "11111111-2222-4333-8444-555555555555"
	ops := map[string]any{"ops": []map[string]any{
		{"op_id": "a0000000-0000-4000-8000-000000000001", "tipo": "abrir_tula", "tula_local_id": local, "datos": map[string]any{"codigo": "T1"}},
		{"op_id": "a0000000-0000-4000-8000-000000000002", "tipo": "serial", "tula_local_id": local, "datos": map[string]any{"serial": "S0001"}},
		{"op_id": "a0000000-0000-4000-8000-000000000003", "tipo": "serial", "tula_local_id": local, "datos": map[string]any{"serial": "S0002"}},
		{"op_id": "a0000000-0000-4000-8000-000000000004", "tipo": "asignar_zonas", "datos": map[string]any{"codigo": "9001", "zonas": []string{e.zonas[0]}}},
		{"op_id": "a0000000-0000-4000-8000-000000000005", "tipo": "cerrar_tula", "tula_local_id": local},
	}}
	type resp struct {
		Resultados []struct {
			Status int `json:"status"`
		} `json:"resultados"`
		Tulas      map[string]int64 `json:"tulas"`
		Pendientes int              `json:"pendientes"`
	}
	var r1, r2 resp
	esperarEstado(t, e.pedir("POST", "/api/flujo/sync", "flujo_esc", ops, &r1), 200, "sync")
	esperarEstado(t, e.pedir("POST", "/api/flujo/sync", "flujo_esc", ops, &r2), 200, "sync otra vez")
	quiero := []int{200, 200, 200, 403, 200} // el rol mensajero no puede asignar zonas
	for i, q := range quiero {
		if r1.Resultados[i].Status != q || r2.Resultados[i].Status != q {
			t.Fatalf("op %d: %d / %d, se esperaba %d", i, r1.Resultados[i].Status, r2.Resultados[i].Status, q)
		}
	}
	if r1.Tulas[local] == 0 || r1.Tulas[local] != r2.Tulas[local] {
		t.Fatalf("la tula local debe mapear al mismo id: %v %v", r1.Tulas, r2.Tulas)
	}
	if n := e.contar(`SELECT count(*) FROM tulas`); n != 1 {
		t.Fatalf("una sola tula, hay %d", n)
	}
	if n := e.contar(`SELECT count(*) FROM tula_seriales`); n != 2 {
		t.Fatalf("dos lecturas, hay %d", n)
	}
	if n := e.contar(`SELECT count(*) FROM tulas WHERE estado = 'cerrada'`); n != 1 {
		t.Fatal("la tula debe quedar cerrada")
	}
}

func TestAsignacion(t *testing.T) {
	e := preparar(t)
	z1, z2 := e.zonas[0], e.zonas[1]
	base := "/api/asignacion-zonas"
	var m struct {
		Nombre string   `json:"nombre"`
		Zonas  []string `json:"zonas"`
	}
	esperarEstado(t, e.pedir("PUT", base+"/mensajero/9001", "flujo_admin", map[string]any{"zonas": []string{z1, " " + z1, z2}}, &m), 200, "asignar")
	if m.Nombre != "Juan Porras" || len(m.Zonas) != 2 {
		t.Fatalf("zonas sin repetir: %+v", m)
	}
	var choque struct {
		Detail struct {
			Choques []struct{ Zona, Codigo string } `json:"choques"`
		} `json:"detail"`
	}
	esperarEstado(t, e.pedir("PUT", base+"/mensajero/9002", "flujo_admin", map[string]any{"zonas": []string{z1}}, &choque), 409, "choque")
	if len(choque.Detail.Choques) != 1 || choque.Detail.Choques[0].Codigo != "9001" {
		t.Fatalf("choque mal: %+v", choque)
	}
	esperarEstado(t, e.pedir("PUT", base+"/mensajero/9002", "flujo_admin", map[string]any{"zonas": []string{z1}, "reasignar": true}, nil), 200, "reasignar")
	esperarEstado(t, e.pedir("PUT", base+"/mensajero/9002", "flujo_admin", map[string]any{"zonas": []string{"NO_EXISTE"}}, nil), 400, "zona inválida")
	esperarEstado(t, e.pedir("GET", base+"/mensajero/0000", "flujo_admin", nil, nil), 404, "mensajero inexistente")

	// S0001 (z1) y S0002 (z2) leídos hoy
	var tula tulaJSON
	e.pedir("POST", "/api/tulas/", "flujo_admin", map[string]any{"codigo": "TX"}, &tula)
	for _, s := range []string{"S0001", "S0002"} {
		e.pedir("POST", fmt.Sprintf("/api/tulas/%d/seriales", tula.ID), "flujo_admin", map[string]string{"serial": s}, nil)
	}
	var seriales []struct{ Serial, Origen string }
	e.pedir("GET", base+"/mensajero/9002/seriales", "flujo_admin", nil, &seriales)
	if len(seriales) != 1 || seriales[0].Serial != "S0001" || seriales[0].Origen != "zona" {
		t.Fatalf("a Ana le toca S0001 por su zona: %+v", seriales)
	}

	var as struct {
		MensajeroAnterior *struct{ Codigo string } `json:"mensajero_anterior"`
		YaEraSuyo         bool                     `json:"ya_era_suyo"`
	}
	esperarEstado(t, e.pedir("POST", base+"/mensajero/9001/seriales", "flujo_admin", map[string]string{"serial": "S0001"}, &as), 200, "asignar serial")
	if as.MensajeroAnterior == nil || as.MensajeroAnterior.Codigo != "9002" || as.YaEraSuyo {
		t.Fatalf("S0001 lo tenía Ana: %+v", as)
	}
	var totales []struct {
		Codigo      string
		Paquetes    int
		Reasignados int
	}
	e.pedir("GET", base+"/mensajeros", "flujo_admin", nil, &totales)
	if len(totales) != 2 || totales[0].Codigo != "9001" || totales[0].Paquetes != 2 || totales[0].Reasignados != 1 || totales[1].Paquetes != 0 {
		t.Fatalf("totales mal: %+v", totales)
	}

	var envio struct {
		NombreImile string `json:"nombre_imile"`
		Total       int    `json:"total"`
		EnCurso     bool   `json:"en_curso"`
	}
	esperarEstado(t, e.pedir("POST", base+"/mensajero/9001/imile", "flujo_admin", nil, &envio), 202, "envío iMile")
	if envio.Total != 2 || !envio.EnCurso || envio.NombreImile != "Juan Porras" {
		t.Fatalf("envío mal: %+v", envio)
	}
	esperarEstado(t, e.pedir("POST", base+"/mensajero/9001/imile", "flujo_admin", nil, nil), 409, "envío en curso")
	esperarEstado(t, e.pedir("GET", base+"/mensajero/9001/imile", "flujo_admin", nil, &envio), 200, "avance")
	if envio.Total != 2 || !envio.EnCurso {
		t.Fatalf("avance mal: %+v", envio)
	}
	esperarEstado(t, e.pedir("DELETE", base+"/mensajero/9001/seriales/S0001", "flujo_admin", nil, nil), 204, "quitar serial")
	esperarEstado(t, e.pedir("DELETE", base+"/mensajero/9001/seriales/S0001", "flujo_admin", nil, nil), 404, "quitar dos veces")

	// El mismo tablero por el enlace QR, sin sesión
	esperarEstado(t, e.pedir("GET", "/api/asignacion-qr/qr-valido/", "", nil, nil), 200, "QR")
	esperarEstado(t, e.pedir("GET", "/api/asignacion-qr/qr-vencido/", "", nil, nil), 404, "QR vencido")
}

func TestPermisos(t *testing.T) {
	e := preparar(t)
	esperarEstado(t, e.pedir("GET", "/api/tulas/abierta", "", nil, nil), 403, "sin token")
	req, _ := http.NewRequest("GET", e.srv.URL+"/api/tulas/abierta", nil)
	req.Header.Set("Authorization", "Bearer basura")
	resp, _ := http.DefaultClient.Do(req)
	resp.Body.Close()
	esperarEstado(t, resp.StatusCode, 401, "token inválido")
	esperarEstado(t, e.pedir("GET", "/api/tulas/abierta", "flujo_inactivo", nil, nil), 401, "usuario inactivo")
	esperarEstado(t, e.pedir("GET", "/api/asignacion-zonas/", "flujo_esc", nil, nil), 403, "rol sin la página")
	esperarEstado(t, e.pedir("GET", "/api/tulas/abierta", "flujo_esc", nil, nil), 200, "con permiso")
}

// Dos workers reclamando a la vez nunca toman la misma tarea.
func TestOutboxSinPisarse(t *testing.T) {
	e := preparar(t)
	ctx := context.Background()
	for i := 0; i < 20; i++ {
		if _, err := outbox.Encolar(ctx, e.pool, outbox.Tarea{Tipo: outbox.TipoIngreso, Serial: fmt.Sprint(i), Fecha: db.Hoy(), Usuario: "t"}); err != nil {
			t.Fatal(err)
		}
	}
	var mu sync.Mutex
	vistas := map[int64]bool{}
	var wg sync.WaitGroup
	for w := 0; w < 5; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				tarea, err := outbox.Reclamar(ctx, e.pool, outbox.TipoIngreso, nil)
				if err != nil {
					t.Error(err)
					return
				}
				if tarea == nil {
					return
				}
				mu.Lock()
				if vistas[tarea.ID] {
					t.Errorf("tarea %d tomada dos veces", tarea.ID)
				}
				vistas[tarea.ID] = true
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	if len(vistas) != 20 {
		t.Fatalf("se reclamaron %d de 20", len(vistas))
	}
	// Un lease vencido devuelve la tarea a la cola
	ejecutar(t, e.pool, `UPDATE imile_tareas SET lease_hasta = now() - interval '1 second' WHERE id = 1`)
	if n, _ := outbox.RecuperarVencidas(ctx, e.pool); n != 1 {
		t.Fatalf("se esperaba recuperar 1, se recuperaron %d", n)
	}
}

func TestBaseDelDiaConETag(t *testing.T) {
	e := preparar(t)
	req, _ := http.NewRequest("GET", e.srv.URL+"/api/paquetes-despacho/base", nil)
	req.Header.Set("Authorization", "Bearer "+token("flujo_esc"))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	var base struct {
		Paquetes []struct{ S string } `json:"paquetes"`
		Personal []struct{ Codigo string }
		Zonas    []string
	}
	_ = json.NewDecoder(resp.Body).Decode(&base)
	resp.Body.Close()
	etag := resp.Header.Get("ETag")
	if resp.StatusCode != 200 || len(base.Paquetes) != 3 || etag == "" || len(base.Zonas) == 0 {
		t.Fatalf("base mal: %d %+v %q", resp.StatusCode, base, etag)
	}
	req.Header.Set("If-None-Match", etag)
	resp, _ = http.DefaultClient.Do(req)
	resp.Body.Close()
	esperarEstado(t, resp.StatusCode, 304, "sin cambios")
	ejecutar(t, e.pool, `UPDATE paquetes_despacho SET zona = NULL, fecha_modificacion = now() + interval '1 second' WHERE serial = 'S0001'`)
	resp, _ = http.DefaultClient.Do(req)
	resp.Body.Close()
	esperarEstado(t, resp.StatusCode, 200, "con cambios")
}
