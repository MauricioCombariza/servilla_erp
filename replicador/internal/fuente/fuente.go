// Package fuente abre los archivos del FoxPro para leerlos: una carpeta local (pruebas, o
// un recurso ya montado) o el SCO por Samba con smbclient (SMB1, solo lectura).
package fuente

import (
	"context"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

// Info del archivo, para saber si cambió desde la última pasada sin leerlo.
type Info struct {
	Tamano int64
	// Marca: algo que cambia cuando el archivo cambia (tamaño + fecha de modificación).
	Marca string
}

// Fuente de archivos. Las rutas son relativas al recurso ("guia2601.his", "retorno/lote_apl.dbf").
type Fuente interface {
	Info(ctx context.Context, recurso, ruta string) (Info, error)
	Abrir(ctx context.Context, recurso, ruta string) (io.ReadCloser, error)
}

// Local lee de carpetas del disco: recurso → carpeta.
type Local struct {
	Carpetas map[string]string
}

func (l Local) camino(recurso, ruta string) string {
	return filepath.Join(l.Carpetas[recurso], filepath.FromSlash(ruta))
}

func (l Local) Info(_ context.Context, recurso, ruta string) (Info, error) {
	st, err := os.Stat(l.camino(recurso, ruta))
	if err != nil {
		return Info{}, err
	}
	return Info{Tamano: st.Size(), Marca: marca(st.Size(), st.ModTime())}, nil
}

func (l Local) Abrir(_ context.Context, recurso, ruta string) (io.ReadCloser, error) {
	return os.Open(l.camino(recurso, ruta))
}

func marca(tamano int64, mod time.Time) string {
	return mod.UTC().Format(time.RFC3339) + "/" + strconv.FormatInt(tamano, 10)
}
