package dbf_test

import (
	"bytes"
	"errors"
	"io"
	"testing"
	"time"

	"servilla/replicador/internal/dbf"
	"servilla/replicador/internal/dbf/dbftest"
)

var campos = []dbftest.Campo{
	{Nombre: "serial", Tipo: 'C', Largo: 10},
	{Nombre: "f_emi", Tipo: 'D', Largo: 8},
	{Nombre: "nombred", Tipo: 'C', Largo: 20},
	{Nombre: "valor", Tipo: 'N', Largo: 8, Dec: 2},
	{Nombre: "activa", Tipo: 'L', Largo: 1},
}

func tabla() []byte {
	return dbftest.Armar(campos, []dbftest.Fila{
		{Valores: []string{"0000000001", "20260105", "PE\xd1A P\xc9REZ", "1500.50", "T"}},
		{Borrada: true, Valores: []string{"0000000002", "20250101", "BORRADO", "0", "F"}},
		{Valores: []string{"0000000003", "", "", "", " "}},
		{Valores: []string{"0000000004", "96201201", "MAL", "*****", "?"}},
	})
}

func TestEncabezadoYCampos(t *testing.T) {
	l, err := dbf.NuevoLector(bytes.NewReader(tabla()))
	if err != nil {
		t.Fatal(err)
	}
	if l.Enc.Registros != 4 || len(l.Enc.Campos) != 5 {
		t.Fatalf("encabezado: %+v", l.Enc)
	}
	if c := l.Enc.Campos[1]; c.Nombre != "f_emi" || c.Tipo != 'D' || c.Inicio != 11 {
		t.Fatalf("campo f_emi: %+v", c)
	}
	if !l.Enc.Actualizado.Equal(time.Date(2026, 11, 20, 0, 0, 0, 0, time.UTC)) {
		t.Fatalf("actualizado: %v", l.Enc.Actualizado)
	}
}

func TestRegistrosYValores(t *testing.T) {
	l, err := dbf.NuevoLector(bytes.NewReader(tabla()))
	if err != nil {
		t.Fatal(err)
	}
	c := l.Enc.Campos
	r, _ := l.Siguiente()
	if r.Recno != 1 || r.Borrado {
		t.Fatalf("registro 1: %+v", r)
	}
	if v := dbf.Leer(c[2], r.Crudo); v.Texto != "PEÑA PÉREZ" {
		t.Fatalf("Windows 1252: %q", v.Texto)
	}
	if v := dbf.Leer(c[1], r.Crudo); !v.Fecha.Equal(time.Date(2026, 1, 5, 0, 0, 0, 0, time.UTC)) {
		t.Fatalf("fecha: %+v", v)
	}
	if v := dbf.Leer(c[3], r.Crudo); v.Texto != "1500.50" {
		t.Fatalf("número: %+v", v)
	}
	if v := dbf.Leer(c[4], r.Crudo); !v.Logico || v.Nulo {
		t.Fatalf("lógico: %+v", v)
	}

	r, _ = l.Siguiente()
	if r.Recno != 2 || !r.Borrado {
		t.Fatalf("registro 2 debe estar borrado: %+v", r)
	}

	r, _ = l.Siguiente()
	for i := 1; i < 5; i++ {
		if v := dbf.Leer(c[i], r.Crudo); !v.Nulo {
			t.Fatalf("campo %s vacío debe ser nulo: %+v", c[i].Nombre, v)
		}
	}

	r, _ = l.Siguiente()
	if v := dbf.Leer(c[1], r.Crudo); !v.Invalido || v.Crudo != "96201201" {
		t.Fatalf("fecha del año 9620 debe ser inválida: %+v", v)
	}
	if v := dbf.Leer(c[3], r.Crudo); !v.Invalido {
		t.Fatalf("número desbordado (*****) debe ser inválido: %+v", v)
	}

	if _, err := l.Siguiente(); !errors.Is(err, io.EOF) {
		t.Fatalf("esperaba EOF: %v", err)
	}
}

func TestArchivoCortado(t *testing.T) {
	b := tabla()
	l, err := dbf.NuevoLector(bytes.NewReader(b[:len(b)-40]))
	if err != nil {
		t.Fatal(err)
	}
	var ultimo error
	for i := 0; i < 5; i++ {
		if _, ultimo = l.Siguiente(); ultimo != nil {
			break
		}
	}
	if !errors.Is(ultimo, io.ErrUnexpectedEOF) {
		t.Fatalf("esperaba ErrUnexpectedEOF: %v", ultimo)
	}
}

func TestNoEsDBF(t *testing.T) {
	if _, err := dbf.NuevoLector(bytes.NewReader([]byte("hola"))); !errors.Is(err, dbf.ErrFormato) {
		t.Fatalf("esperaba ErrFormato: %v", err)
	}
}
