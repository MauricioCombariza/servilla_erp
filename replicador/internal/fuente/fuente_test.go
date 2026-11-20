package fuente_test

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"servilla/replicador/internal/fuente"
)

// smbclient falso: "ls" responde una línea como la del SCO y "get X destino" copia el
// archivo de la carpeta de datos al destino (la FIFO). Clave "mala" = error de acceso.
const falso = `#!/bin/sh
datos="$DATOS"
cmd=""
auth=""
while [ $# -gt 0 ]; do
  case "$1" in
    -c) cmd="$2"; shift ;;
    -A) auth="$2"; shift ;;
  esac
  shift
done
if grep -q mala "$auth"; then echo "session setup failed: NT_STATUS_LOGON_FAILURE"; exit 1; fi
archivo=$(echo "$cmd" | sed -E 's/^(ls|get) "([^"]+)".*/\2/')
case "$cmd" in
  ls*)
    [ -f "$datos/$archivo" ] || { echo "NT_STATUS_NO_SUCH_FILE listing \\$archivo"; exit 1; }
    tam=$(wc -c < "$datos/$archivo" | tr -d ' ')
    echo ""
    printf '  %s                      A %s  Thu Nov 19 18:00:00 2026\n' "$archivo" "$tam"
    echo ""
    echo "		123456 blocks of size 1024. 1234 blocks available" ;;
  get*)
    destino=$(echo "$cmd" | awk '{print $NF}')
    [ -f "$datos/$archivo" ] || { echo "NT_STATUS_OBJECT_NAME_NOT_FOUND opening remote file \\$archivo"; exit 1; }
    echo "getting file \\$archivo"
    cat "$datos/$archivo" > "$destino" ;;
esac
`

func preparar(t *testing.T, clave string) fuente.Samba {
	t.Helper()
	dir := t.TempDir()
	datos := filepath.Join(dir, "datos")
	os.Mkdir(datos, 0o755)
	os.WriteFile(filepath.Join(datos, "guia2601.his"), []byte(strings.Repeat("x", 300000)), 0o644)
	bin := filepath.Join(dir, "smbclient")
	os.WriteFile(bin, []byte(falso), 0o755)
	auth := filepath.Join(dir, "auth")
	os.WriteFile(auth, []byte("username = replica\npassword = "+clave+"\n"), 0o600)
	t.Setenv("DATOS", datos)
	return fuente.Samba{Binario: bin, Servidor: "SCOSYSV", IP: "192.0.2.1", Auth: auth,
		Recursos: map[string]string{"guias": "replica"}}
}

func TestSambaInfoYAbrir(t *testing.T) {
	s := preparar(t, "buena")
	ctx := context.Background()
	info, err := s.Info(ctx, "guias", "guia2601.his")
	if err != nil {
		t.Fatal(err)
	}
	if info.Tamano != 300000 || info.Marca != "Thu Nov 19 18:00:00 2026/300000" {
		t.Fatalf("info: %+v", info)
	}
	r, err := s.Abrir(ctx, "guias", "guia2601.his")
	if err != nil {
		t.Fatal(err)
	}
	b, err := io.ReadAll(r)
	if err != nil || len(b) != 300000 {
		t.Fatalf("leídos %d: %v", len(b), err)
	}
	if err := r.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestSambaCerrarAntesDeTerminar(t *testing.T) {
	s := preparar(t, "buena")
	r, err := s.Abrir(context.Background(), "guias", "guia2601.his")
	if err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 100)
	io.ReadFull(r, buf)
	r.Close() // smbclient muere por tubería rota: no debe quedar colgado
}

func TestSambaErrores(t *testing.T) {
	ctx := context.Background()
	s := preparar(t, "buena")
	if _, err := s.Info(ctx, "guias", "no_existe.his"); err == nil {
		t.Fatal("esperaba error para archivo inexistente")
	}
	if _, err := s.Abrir(ctx, "guias", "no_existe.his"); err == nil || !strings.Contains(err.Error(), "NOT_FOUND") {
		t.Fatalf("esperaba el error de smbclient: %v", err)
	}
	if _, err := s.Abrir(ctx, "otro", "x"); err == nil {
		t.Fatal("recurso sin configurar debe fallar")
	}
	m := preparar(t, "mala")
	if _, err := m.Abrir(ctx, "guias", "guia2601.his"); err == nil || !strings.Contains(err.Error(), "LOGON_FAILURE") {
		t.Fatalf("esperaba LOGON_FAILURE: %v", err)
	}
}

func TestLocal(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "a.dbf"), []byte("abc"), 0o644)
	l := fuente.Local{Carpetas: map[string]string{"x": dir}}
	info, err := l.Info(context.Background(), "x", "a.dbf")
	if err != nil || info.Tamano != 3 {
		t.Fatalf("%+v %v", info, err)
	}
	if _, err := l.Info(context.Background(), "x", "no.dbf"); !errors.Is(err, os.ErrNotExist) {
		t.Fatal(err)
	}
}
