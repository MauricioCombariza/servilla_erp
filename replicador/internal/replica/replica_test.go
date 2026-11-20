package replica_test

import (
	"context"
	"errors"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgtype"

	"servilla/replicador/internal/dbf"
	"servilla/replicador/internal/dbf/dbftest"
	"servilla/replicador/internal/destino"
	"servilla/replicador/internal/fuente"
	"servilla/replicador/internal/replica"
)

// memoria: destino en memoria que se comporta como Postgres.
type fila struct {
	hash    int64
	borrado bool
	fecha   *time.Time
	valores []any
}

type memoria struct {
	tablas      map[string]map[uint32]fila
	estado      map[string]destino.Estado
	errores     map[string]string
	conciliados []destino.Conciliacion
	aplicadas   int // filas mandadas en total
	vaciados    int
	iFecha      int  // posición del campo de fecha del filtro
	perder      bool // simula que Postgres no guarda una fila (para el descuadre)
}

func nuevaMemoria() *memoria {
	return &memoria{tablas: map[string]map[uint32]fila{}, estado: map[string]destino.Estado{},
		errores: map[string]string{}, iFecha: 1}
}

func (m *memoria) AsegurarTabla(_ context.Context, t string, _ []dbf.Campo) error {
	if m.tablas[t] == nil {
		m.tablas[t] = map[uint32]fila{}
	}
	return nil
}
func (m *memoria) Estado(_ context.Context, t string) (destino.Estado, error) { return m.estado[t], nil }
func (m *memoria) Hashes(_ context.Context, t string) (map[uint32]int64, error) {
	h := map[uint32]int64{}
	for r, f := range m.tablas[t] {
		h[r] = f.hash
	}
	return h, nil
}
func (m *memoria) Aplicar(_ context.Context, t string, _ []dbf.Campo, filas []destino.Fila) error {
	for i, f := range filas {
		if m.perder && i == 0 {
			continue
		}
		var fecha *time.Time
		if d, ok := f.Valores[m.iFecha].(pgtype.Date); ok && d.Valid {
			tt := d.Time
			fecha = &tt
		}
		m.tablas[t][f.Recno] = fila{hash: f.Hash, borrado: f.Borrado, fecha: fecha, valores: f.Valores}
		m.aplicadas++
	}
	return nil
}
func (m *memoria) Borrar(_ context.Context, t string, recnos []uint32) error {
	for _, r := range recnos {
		delete(m.tablas[t], r)
	}
	return nil
}
func (m *memoria) Recortar(_ context.Context, t string, n uint32) error {
	for r := range m.tablas[t] {
		if r > n {
			delete(m.tablas[t], r)
		}
	}
	return nil
}
func (m *memoria) Vaciar(_ context.Context, t string) error {
	m.tablas[t] = map[uint32]fila{}
	m.vaciados++
	return nil
}
func (m *memoria) Contar(_ context.Context, t string, f *destino.Filtro) (int64, *big.Int, error) {
	var n int64
	s := new(big.Int)
	for _, fl := range m.tablas[t] {
		if f != nil && fl.fecha != nil && fl.fecha.Before(f.Desde) {
			continue
		}
		n++
		s.Add(s, big.NewInt(fl.hash))
	}
	return n, s, nil
}
func (m *memoria) GuardarEstado(_ context.Context, t, _, _, marca string, reg int64, fallo string) error {
	m.errores[t] = fallo
	if fallo == "" {
		m.estado[t] = destino.Estado{Marca: marca, Registros: reg}
	}
	return nil
}
func (m *memoria) GuardarConciliacion(_ context.Context, c destino.Conciliacion) error {
	m.conciliados = append(m.conciliados, c)
	return nil
}

var campos = []dbftest.Campo{
	{Nombre: "serial", Tipo: 'C', Largo: 10},
	{Nombre: "f_emi", Tipo: 'D', Largo: 8},
	{Nombre: "motivo", Tipo: 'C', Largo: 10},
}

type entorno struct {
	dir  string
	mem  *memoria
	rep  replica.Replicador
	arch replica.Archivo
	t    *testing.T
}

func nuevo(t *testing.T, filtro bool) *entorno {
	dir := t.TempDir()
	mem := nuevaMemoria()
	a := replica.Archivo{Recurso: "guias", Ruta: "guia2601.his", Tabla: "guia2601"}
	if filtro {
		a.Filtro = &destino.Filtro{Campo: "f_emi", Desde: time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)}
	}
	return &entorno{dir: dir, mem: mem, arch: a, t: t, rep: replica.Replicador{
		Fuente: fuente.Local{Carpetas: map[string]string{"guias": dir}}, Destino: mem, Lote: 2}}
}

// escribir deja el archivo con esas filas y una fecha de modificación distinta cada vez.
func (e *entorno) escribir(filas []dbftest.Fila, mod time.Time) {
	p := filepath.Join(e.dir, "guia2601.his")
	if err := os.WriteFile(p, dbftest.Armar(campos, filas), 0o644); err != nil {
		e.t.Fatal(err)
	}
	os.Chtimes(p, mod, mod)
}

func (e *entorno) pasada() replica.Resultado {
	e.t.Helper()
	r, err := e.rep.Pasada(context.Background(), e.arch)
	if err != nil {
		e.t.Fatal(err)
	}
	return r
}

func f(serial, fecha, motivo string) dbftest.Fila {
	return dbftest.Fila{Valores: []string{serial, fecha, motivo}}
}

var t0 = time.Date(2026, 11, 20, 8, 0, 0, 0, time.UTC)

func TestPrimeraCargaYSinCambios(t *testing.T) {
	e := nuevo(t, false)
	e.escribir([]dbftest.Fila{f("1", "20260105", "E"), f("2", "20260106", ""), f("3", "20260107", "D10")}, t0)
	r := e.pasada()
	c := r.Conciliacion
	if !c.OK() || c.Incluidos != 3 || c.Enviados != 3 || e.mem.aplicadas != 3 {
		t.Fatalf("primera carga: %+v", c)
	}
	// Misma marca: ni se abre el archivo
	if r := e.pasada(); !r.SinCambios {
		t.Fatalf("esperaba sin cambios: %+v", r)
	}
	// Otra fecha de modificación pero mismos datos: se lee y no se manda nada
	e.escribir([]dbftest.Fila{f("1", "20260105", "E"), f("2", "20260106", ""), f("3", "20260107", "D10")}, t0.Add(time.Minute))
	if r := e.pasada(); r.Conciliacion.Enviados != 0 || !r.Conciliacion.OK() {
		t.Fatalf("sin cambios reales no debe mandar filas: %+v", r.Conciliacion)
	}
}

func TestSoloMandaLoQueCambia(t *testing.T) {
	e := nuevo(t, false)
	e.escribir([]dbftest.Fila{f("1", "20260105", ""), f("2", "20260106", ""), f("3", "20260107", "")}, t0)
	e.pasada()
	borrada := f("2", "20260106", "")
	borrada.Borrada = true
	e.escribir([]dbftest.Fila{f("1", "20260105", "E"), borrada, f("3", "20260107", ""), f("4", "20260108", "")}, t0.Add(time.Minute))
	r := e.pasada()
	if r.Conciliacion.Enviados != 3 || !r.Conciliacion.OK() || r.Conciliacion.Borrados != 1 {
		t.Fatalf("debe mandar el cambiado, el borrado y el nuevo: %+v", r.Conciliacion)
	}
	if !e.mem.tablas["guia2601"][2].borrado {
		t.Fatal("el registro 2 debe quedar marcado como borrado")
	}
}

func TestFiltroDeFecha(t *testing.T) {
	e := nuevo(t, true)
	e.escribir([]dbftest.Fila{f("1", "20240105", ""), f("2", "20250106", ""), f("3", "", ""), f("4", "96201201", "")}, t0)
	r := e.pasada()
	// 2024 queda fuera; sin fecha y fecha inválida entran (no se pueden juzgar)
	if r.Conciliacion.Incluidos != 3 || len(e.mem.tablas["guia2601"]) != 3 || !r.Conciliacion.OK() {
		t.Fatalf("filtro: %+v", r.Conciliacion)
	}
	if _, esta := e.mem.tablas["guia2601"][1]; esta {
		t.Fatal("la guía de 2024 no debe salir de la oficina")
	}
	if fl := e.mem.tablas["guia2601"][2]; fl.fecha == nil || fl.fecha.Year() != 2025 {
		t.Fatalf("la fecha debe llegar tipada: %+v", fl)
	}
	// La guía 2 cambia su fecha a 2024: deja de cumplir y se borra de Postgres
	e.escribir([]dbftest.Fila{f("1", "20240105", ""), f("2", "20241231", ""), f("3", "", ""), f("4", "96201201", "")}, t0.Add(time.Minute))
	r = e.pasada()
	if _, esta := e.mem.tablas["guia2601"][2]; esta || !r.Conciliacion.OK() {
		t.Fatalf("la guía que pasó a 2024 debe salir: %+v", r.Conciliacion)
	}
}

func TestPackRecargaTodo(t *testing.T) {
	e := nuevo(t, false)
	e.escribir([]dbftest.Fila{f("1", "20260105", ""), f("2", "20260106", ""), f("3", "20260107", "")}, t0)
	e.pasada()
	// PACK: se fue el 2 y el 3 pasó a ser el registro 2
	e.escribir([]dbftest.Fila{f("1", "20260105", ""), f("3", "20260107", "")}, t0.Add(time.Minute))
	r := e.pasada()
	if e.mem.vaciados != 1 || len(e.mem.tablas["guia2601"]) != 2 || !r.Conciliacion.OK() {
		t.Fatalf("PACK: vaciados=%d filas=%d %+v", e.mem.vaciados, len(e.mem.tablas["guia2601"]), r.Conciliacion)
	}
}

func TestDescuadreNoGuardaLaMarca(t *testing.T) {
	e := nuevo(t, false)
	e.mem.perder = true
	e.escribir([]dbftest.Fila{f("1", "20260105", ""), f("2", "20260106", "")}, t0)
	_, err := e.rep.Pasada(context.Background(), e.arch)
	if !errors.Is(err, replica.ErrDescuadre) {
		t.Fatalf("esperaba descuadre: %v", err)
	}
	if e.mem.estado["guia2601"].Marca != "" || e.mem.errores["guia2601"] == "" {
		t.Fatal("con descuadre no se guarda la marca (se reintenta) y queda el error")
	}
	// Siguiente pasada sin pérdida: completa lo que faltaba
	e.mem.perder = false
	if r := e.pasada(); !r.Conciliacion.OK() || r.Conciliacion.Enviados != 1 {
		t.Fatalf("debe completar el faltante: %+v", r.Conciliacion)
	}
}

func TestArchivoQueNoExiste(t *testing.T) {
	e := nuevo(t, false)
	if _, err := e.rep.Pasada(context.Background(), e.arch); err == nil || e.mem.errores["guia2601"] == "" {
		t.Fatal("debe fallar y dejar el error guardado")
	}
}

func TestFiltroConCampoQueNoExiste(t *testing.T) {
	e := nuevo(t, true)
	e.arch.Filtro.Campo = "f_rad"
	e.escribir([]dbftest.Fila{f("1", "20260105", "")}, t0)
	if _, err := e.rep.Pasada(context.Background(), e.arch); err == nil {
		t.Fatal("un filtro sobre un campo que no existe debe fallar")
	}
}
