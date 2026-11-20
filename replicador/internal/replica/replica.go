// Package replica hace una pasada por archivo: ¿cambió? → leer en streaming → mandar solo
// los registros nuevos, cambiados o borrados → conciliar contra Postgres.
package replica

import (
	"context"
	"errors"
	"fmt"
	"hash/fnv"
	"io"
	"log/slog"
	"math/big"
	"time"

	"servilla/replicador/internal/dbf"
	"servilla/replicador/internal/destino"
	"servilla/replicador/internal/fuente"
)

// Archivo a replicar.
type Archivo struct {
	Recurso string          // recurso de la fuente ("guias", "admin2", "retorno")
	Ruta    string          // "guia2601.his"
	Tabla   string          // tabla en el esquema legacy ("guia2601")
	Filtro  *destino.Filtro // solo filas con Campo >= Desde (p. ej. f_emi desde 2025)
}

// Destino: lo que el replicador necesita de Postgres (en pruebas, uno en memoria).
type Destino interface {
	AsegurarTabla(ctx context.Context, tabla string, campos []dbf.Campo) error
	Estado(ctx context.Context, tabla string) (destino.Estado, error)
	Hashes(ctx context.Context, tabla string) (map[uint32]int64, error)
	Aplicar(ctx context.Context, tabla string, campos []dbf.Campo, filas []destino.Fila) error
	Borrar(ctx context.Context, tabla string, recnos []uint32) error
	Recortar(ctx context.Context, tabla string, registros uint32) error
	Vaciar(ctx context.Context, tabla string) error
	Contar(ctx context.Context, tabla string, f *destino.Filtro) (int64, *big.Int, error)
	GuardarEstado(ctx context.Context, tabla, recurso, ruta, marca string, registros int64, fallo string) error
	GuardarConciliacion(ctx context.Context, c destino.Conciliacion) error
}

type Replicador struct {
	Fuente  fuente.Fuente
	Destino Destino
	Lote    int // filas por COPY; 0 = 5000
	Log     *slog.Logger
}

// Resultado de una pasada.
type Resultado struct {
	SinCambios   bool
	Conciliacion destino.Conciliacion
}

// ErrDescuadre: Postgres no quedó igual al DBF (se vuelve a intentar en la siguiente pasada).
var ErrDescuadre = errors.New("la conciliación no cuadra")

// Hash del registro crudo (incluye la marca de borrado): cambia si cambia cualquier byte.
func Hash(crudo []byte) int64 {
	h := fnv.New64a()
	h.Write(crudo)
	return int64(h.Sum64())
}

// Pasada replica un archivo. Guarda el estado (marca o error) y la conciliación.
func (r Replicador) Pasada(ctx context.Context, a Archivo) (Resultado, error) {
	inicio := time.Now()
	info, err := r.Fuente.Info(ctx, a.Recurso, a.Ruta)
	if err != nil {
		return Resultado{}, r.fallo(ctx, a, fmt.Errorf("info: %w", err))
	}
	previo, err := r.Destino.Estado(ctx, a.Tabla)
	if err != nil {
		return Resultado{}, err
	}
	if previo.Marca != "" && previo.Marca == info.Marca {
		return Resultado{SinCambios: true}, nil
	}

	con, err := r.copiar(ctx, a, previo)
	if err != nil {
		return Resultado{}, r.fallo(ctx, a, err)
	}
	con.Segundos = time.Since(inicio).Seconds()
	if err := r.Destino.GuardarConciliacion(ctx, con); err != nil {
		return Resultado{}, err
	}
	if !con.OK() {
		return Resultado{Conciliacion: con}, r.fallo(ctx, a, fmt.Errorf("%w: DBF %d filas / PG %d", ErrDescuadre, con.Incluidos, con.EnPG))
	}
	if err := r.Destino.GuardarEstado(ctx, a.Tabla, a.Recurso, a.Ruta, info.Marca, con.RegistrosDBF, ""); err != nil {
		return Resultado{}, err
	}
	return Resultado{Conciliacion: con}, nil
}

func (r Replicador) fallo(ctx context.Context, a Archivo, err error) error {
	if e := r.Destino.GuardarEstado(ctx, a.Tabla, a.Recurso, a.Ruta, "", 0, err.Error()); e != nil {
		return errors.Join(err, e)
	}
	return err
}

func (r Replicador) copiar(ctx context.Context, a Archivo, previo destino.Estado) (destino.Conciliacion, error) {
	con := destino.Conciliacion{Tabla: a.Tabla, SumaDBF: new(big.Int), SumaPG: new(big.Int)}
	lectura, err := r.Fuente.Abrir(ctx, a.Recurso, a.Ruta)
	if err != nil {
		return con, fmt.Errorf("abrir: %w", err)
	}
	cerrada := false
	defer func() {
		if !cerrada {
			lectura.Close()
		}
	}()
	l, err := dbf.NuevoLector(lectura)
	if err != nil {
		return con, err
	}
	campos := l.Enc.Campos
	con.RegistrosDBF = int64(l.Enc.Registros)

	iFiltro := -1
	if a.Filtro != nil {
		for i, c := range campos {
			if c.Nombre == a.Filtro.Campo {
				iFiltro = i
			}
		}
		if iFiltro < 0 || campos[iFiltro].Tipo != 'D' {
			return con, fmt.Errorf("el filtro usa %q, que no es un campo de fecha de %s", a.Filtro.Campo, a.Ruta)
		}
	}

	if err := r.Destino.AsegurarTabla(ctx, a.Tabla, campos); err != nil {
		return con, err
	}
	// Menos registros que la vez pasada: hubo PACK y se renumeró todo → se recarga.
	if previo.Registros > int64(l.Enc.Registros) {
		r.log().Info("el archivo quedó más corto: recarga completa", "tabla", a.Tabla,
			"antes", previo.Registros, "ahora", l.Enc.Registros)
		if err := r.Destino.Vaciar(ctx, a.Tabla); err != nil {
			return con, err
		}
	}
	guardados, err := r.Destino.Hashes(ctx, a.Tabla)
	if err != nil {
		return con, err
	}

	lote := r.Lote
	if lote <= 0 {
		lote = 5000
	}
	var filas []destino.Fila
	var fuera []uint32
	for {
		reg, err := l.Siguiente()
		if err != nil {
			if errors.Is(err, io.EOF) { // io.ErrUnexpectedEOF (archivo cortado) no es fin
				break
			}
			return con, fmt.Errorf("registro %d: %w", reg.Recno, err)
		}
		if iFiltro >= 0 {
			v := dbf.Leer(campos[iFiltro], reg.Crudo)
			if !v.Nulo && !v.Invalido && v.Fecha.Before(a.Filtro.Desde) {
				if _, estaba := guardados[reg.Recno]; estaba {
					fuera = append(fuera, reg.Recno) // dejó de cumplir el filtro
				}
				continue
			}
		}
		h := Hash(reg.Crudo)
		con.Incluidos++
		con.SumaDBF.Add(con.SumaDBF, big.NewInt(h))
		if reg.Borrado {
			con.Borrados++
		}
		if prev, ok := guardados[reg.Recno]; ok && prev == h {
			continue
		}
		filas = append(filas, convertir(campos, reg, h))
		if len(filas) >= lote {
			if err := r.Destino.Aplicar(ctx, a.Tabla, campos, filas); err != nil {
				return con, err
			}
			con.Enviados += int64(len(filas))
			filas = filas[:0]
		}
	}
	if err := r.Destino.Aplicar(ctx, a.Tabla, campos, filas); err != nil {
		return con, err
	}
	con.Enviados += int64(len(filas))
	if err := r.Destino.Borrar(ctx, a.Tabla, fuera); err != nil {
		return con, err
	}
	if err := r.Destino.Recortar(ctx, a.Tabla, l.Enc.Registros); err != nil {
		return con, err
	}
	cerrada = true
	if err := lectura.Close(); err != nil {
		return con, fmt.Errorf("cerrar: %w", err)
	}
	con.EnPG, con.SumaPG, err = r.Destino.Contar(ctx, a.Tabla, a.Filtro)
	return con, err
}

func convertir(campos []dbf.Campo, reg dbf.Registro, h int64) destino.Fila {
	f := destino.Fila{Recno: reg.Recno, Hash: h, Borrado: reg.Borrado, Valores: make([]any, len(campos))}
	for i, c := range campos {
		v := dbf.Leer(c, reg.Crudo)
		if v.Invalido {
			if f.Crudo == nil {
				f.Crudo = map[string]string{}
			}
			f.Crudo[c.Nombre] = v.Crudo
		}
		f.Valores[i] = destino.Valor(c, v)
	}
	return f
}

func (r Replicador) log() *slog.Logger {
	if r.Log != nil {
		return r.Log
	}
	return slog.Default()
}
