// Package dbftest arma tablas FoxPro en memoria para las pruebas (sin datos reales).
package dbftest

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"strings"
)

// Campo de la tabla de prueba.
type Campo struct {
	Nombre string
	Tipo   byte
	Largo  int
	Dec    int
}

// Fila: valores en el mismo orden que los campos, ya como texto del DBF
// (fechas AAAAMMDD, lógicos T/F). Borrada = marca '*'.
type Fila struct {
	Borrada bool
	Valores []string
}

// Armar devuelve los bytes de un .dbf FoxPro 2.x con esos campos y filas. Los textos se
// escriben tal cual (pasar bytes Windows 1252 en el string si se quieren tildes).
func Armar(campos []Campo, filas []Fila) []byte {
	largoReg := 1
	for _, c := range campos {
		largoReg += c.Largo
	}
	largoCab := 32 + 32*len(campos) + 1
	var out bytes.Buffer
	cab := make([]byte, 32)
	cab[0] = 0x03
	cab[1], cab[2], cab[3] = 126, 11, 20
	binary.LittleEndian.PutUint32(cab[4:8], uint32(len(filas)))
	binary.LittleEndian.PutUint16(cab[8:10], uint16(largoCab))
	binary.LittleEndian.PutUint16(cab[10:12], uint16(largoReg))
	cab[29] = 0x03
	out.Write(cab)
	for _, c := range campos {
		d := make([]byte, 32)
		copy(d, strings.ToUpper(c.Nombre))
		d[11] = c.Tipo
		d[16] = byte(c.Largo)
		d[17] = byte(c.Dec)
		out.Write(d)
	}
	out.WriteByte(0x0D)
	for _, f := range filas {
		if f.Borrada {
			out.WriteByte('*')
		} else {
			out.WriteByte(' ')
		}
		for i, c := range campos {
			v := ""
			if i < len(f.Valores) {
				v = f.Valores[i]
			}
			if len(v) > c.Largo {
				v = v[:c.Largo]
			}
			if c.Tipo == 'N' || c.Tipo == 'F' {
				out.WriteString(fmt.Sprintf("%*s", c.Largo, v))
			} else {
				out.WriteString(v + strings.Repeat(" ", c.Largo-len(v)))
			}
		}
	}
	out.WriteByte(0x1A)
	return out.Bytes()
}
