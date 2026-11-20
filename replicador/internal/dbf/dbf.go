// Package dbf lee tablas FoxPro (.dbf y .his del SCO) en streaming, sin cargarlas en
// memoria: encabezado, campos y registro por registro con su marca de borrado.
//
// Los textos del SCO están en Windows 1252 (perfil de datos del 2026-11-20); las fechas
// van como AAAAMMDD. Las fechas imposibles (años 0025, 5201, 9620 que se digitaron mal)
// se devuelven como inválidas para que quien llama las guarde aparte.
package dbf

import (
	"bufio"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
	"strconv"
	"strings"
	"time"

	"golang.org/x/text/encoding/charmap"
)

// Campo de la tabla, tal como lo describe el encabezado.
type Campo struct {
	Nombre  string // en minúscula
	Tipo    byte   // C, N, F, D, L, M, I, T, Y, B
	Largo   int
	Decimal int
	Inicio  int // posición dentro del registro (0 es la marca de borrado)
}

// Encabezado de la tabla.
type Encabezado struct {
	Version     byte
	Registros   uint32
	LargoCab    int
	LargoReg    int
	Codepage    byte
	Actualizado time.Time // fecha de última modificación que guarda el propio archivo
	Campos      []Campo
}

// Registro crudo: los bytes tal cual (sirven para el hash) y la marca de borrado.
type Registro struct {
	Recno   uint32 // desde 1, como RECNO() en FoxPro
	Borrado bool
	Crudo   []byte // incluye el byte de borrado; se reutiliza: copiar si se guarda
}

// Lector en streaming.
type Lector struct {
	Enc   Encabezado
	r     *bufio.Reader
	buf   []byte
	leido uint32
}

var ErrFormato = errors.New("no es una tabla FoxPro válida")

// NuevoLector lee el encabezado y deja el lector listo en el primer registro.
func NuevoLector(r io.Reader) (*Lector, error) {
	br := bufio.NewReaderSize(r, 1<<20)
	cab := make([]byte, 32)
	if _, err := io.ReadFull(br, cab); err != nil {
		return nil, fmt.Errorf("%w: encabezado: %v", ErrFormato, err)
	}
	enc := Encabezado{
		Version:   cab[0],
		Registros: binary.LittleEndian.Uint32(cab[4:8]),
		LargoCab:  int(binary.LittleEndian.Uint16(cab[8:10])),
		LargoReg:  int(binary.LittleEndian.Uint16(cab[10:12])),
		Codepage:  cab[29],
	}
	anio := int(cab[1])
	if anio < 50 {
		anio += 2000
	} else {
		anio += 1900
	}
	if cab[2] >= 1 && cab[2] <= 12 && cab[3] >= 1 && cab[3] <= 31 {
		enc.Actualizado = time.Date(anio, time.Month(cab[2]), int(cab[3]), 0, 0, 0, 0, time.UTC)
	}
	if enc.LargoCab < 33 || enc.LargoReg < 1 {
		return nil, fmt.Errorf("%w: largos %d/%d", ErrFormato, enc.LargoCab, enc.LargoReg)
	}

	leidos := 32
	pos := 1
	for {
		d := make([]byte, 32)
		if _, err := io.ReadFull(br, d[:1]); err != nil {
			return nil, fmt.Errorf("%w: campos: %v", ErrFormato, err)
		}
		leidos++
		if d[0] == 0x0D {
			break
		}
		if _, err := io.ReadFull(br, d[1:]); err != nil {
			return nil, fmt.Errorf("%w: campos: %v", ErrFormato, err)
		}
		leidos += 31
		nombre := strings.ToLower(strings.TrimRight(string(d[:11]), "\x00 "))
		if i := strings.IndexByte(nombre, 0); i >= 0 {
			nombre = nombre[:i]
		}
		c := Campo{Nombre: nombre, Tipo: d[11], Largo: int(d[16]), Decimal: int(d[17]), Inicio: pos}
		if c.Tipo == 'C' { // textos de más de 255: el byte de decimales es la parte alta
			c.Largo += c.Decimal * 256
			c.Decimal = 0
		}
		pos += c.Largo
		enc.Campos = append(enc.Campos, c)
		if leidos >= enc.LargoCab {
			break
		}
	}
	if pos != enc.LargoReg {
		return nil, fmt.Errorf("%w: los campos suman %d y el registro mide %d", ErrFormato, pos, enc.LargoReg)
	}
	// Lo que sobre del encabezado (VFP guarda 263 bytes del .dbc después del 0x0D)
	if resto := enc.LargoCab - leidos; resto > 0 {
		if _, err := br.Discard(resto); err != nil {
			return nil, fmt.Errorf("%w: fin del encabezado: %v", ErrFormato, err)
		}
	}
	return &Lector{Enc: enc, r: br, buf: make([]byte, enc.LargoReg)}, nil
}

// Siguiente devuelve el próximo registro, o io.EOF cuando se leyeron todos los que dice
// el encabezado (lo que haya después, como el 0x1A final, se ignora). Un archivo que se
// corta antes devuelve io.ErrUnexpectedEOF.
func (l *Lector) Siguiente() (Registro, error) {
	if l.leido >= l.Enc.Registros {
		return Registro{}, io.EOF
	}
	if _, err := io.ReadFull(l.r, l.buf); err != nil {
		if errors.Is(err, io.EOF) {
			err = io.ErrUnexpectedEOF
		}
		return Registro{}, err
	}
	l.leido++
	return Registro{Recno: l.leido, Borrado: l.buf[0] == '*', Crudo: l.buf}, nil
}

var win1252 = charmap.Windows1252.NewDecoder()

// Texto decodifica Windows 1252 a UTF-8 y quita espacios y nulos de relleno.
func Texto(b []byte) string {
	b = recortar(b)
	for _, c := range b {
		if c >= 0x80 {
			s, err := win1252.Bytes(b)
			if err != nil {
				return string(b)
			}
			return string(s)
		}
	}
	return string(b)
}

func recortar(b []byte) []byte {
	ini, fin := 0, len(b)
	for ini < fin && (b[ini] == ' ' || b[ini] == 0) {
		ini++
	}
	for fin > ini && (b[fin-1] == ' ' || b[fin-1] == 0) {
		fin--
	}
	return b[ini:fin]
}

// Valor tipado de un campo. Nulo = vacío. Invalido = había algo pero no se pudo convertir
// (fecha imposible, número con basura): Crudo trae el texto original para revisarlo.
type Valor struct {
	Nulo     bool
	Invalido bool
	Texto    string    // C, M, y N/F/Y como texto exacto (para numeric de Postgres)
	Fecha    time.Time // D, T
	Logico   bool      // L
	Crudo    string
}

// Desde y Hasta limitan las fechas aceptadas: fuera de ese rango se marcan inválidas.
var (
	FechaDesde = time.Date(1900, 1, 1, 0, 0, 0, 0, time.UTC)
	FechaHasta = time.Date(2100, 12, 31, 0, 0, 0, 0, time.UTC)
)

// Leer convierte el campo c del registro crudo.
func Leer(c Campo, reg []byte) Valor {
	b := reg[c.Inicio : c.Inicio+c.Largo]
	switch c.Tipo {
	case 'C':
		s := Texto(b)
		return Valor{Nulo: s == "", Texto: s}
	case 'M': // número de bloque en el .fpt: no se lee el memo (no hay memos en las tablas vivas)
		s := strings.TrimSpace(string(b))
		return Valor{Nulo: s == "" || s == "0", Texto: s}
	case 'N', 'F':
		s := strings.TrimSpace(string(recortar(b)))
		if s == "" {
			return Valor{Nulo: true}
		}
		if s[0] == '.' {
			s = "0" + s
		} else if strings.HasPrefix(s, "-.") {
			s = "-0" + s[1:]
		}
		if _, err := strconv.ParseFloat(s, 64); err != nil || strings.ContainsAny(s, "*") {
			return Valor{Invalido: true, Crudo: s}
		}
		return Valor{Texto: s}
	case 'D':
		s := string(recortar(b))
		if s == "" || s == "00000000" {
			return Valor{Nulo: true}
		}
		t, err := time.Parse("20060102", s)
		if err != nil || t.Before(FechaDesde) || t.After(FechaHasta) {
			return Valor{Invalido: true, Crudo: s}
		}
		return Valor{Fecha: t}
	case 'L':
		switch b[0] {
		case 'T', 't', 'Y', 'y', 'S', 's':
			return Valor{Logico: true}
		case 'F', 'f', 'N', 'n':
			return Valor{Logico: false}
		default:
			return Valor{Nulo: true}
		}
	case 'I':
		return Valor{Texto: strconv.FormatInt(int64(int32(binary.LittleEndian.Uint32(b))), 10)}
	case 'B':
		f := math.Float64frombits(binary.LittleEndian.Uint64(b))
		if math.IsNaN(f) || math.IsInf(f, 0) {
			return Valor{Invalido: true, Crudo: fmt.Sprint(f)}
		}
		return Valor{Texto: strconv.FormatFloat(f, 'f', -1, 64)}
	case 'Y': // moneda: entero de 64 bits con 4 decimales
		v := int64(binary.LittleEndian.Uint64(b))
		return Valor{Texto: strconv.FormatFloat(float64(v)/10000, 'f', 4, 64)}
	case 'T': // fecha juliana + milisegundos
		dia := int64(binary.LittleEndian.Uint32(b[:4]))
		ms := int64(binary.LittleEndian.Uint32(b[4:8]))
		if dia == 0 {
			return Valor{Nulo: true}
		}
		t := time.Unix((dia-2440588)*86400, 0).UTC().Add(time.Duration(ms) * time.Millisecond)
		if t.Before(FechaDesde) || t.After(FechaHasta) {
			return Valor{Invalido: true, Crudo: t.String()}
		}
		return Valor{Fecha: t}
	default:
		s := Texto(b)
		return Valor{Nulo: s == "", Texto: s}
	}
}
