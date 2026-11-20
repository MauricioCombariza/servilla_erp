package fuente

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Samba lee del SCO con smbclient. El Samba del SCO es antiguo: solo SMB1 por el puerto
// 139 (NetBIOS) y sin "extended security" (prueba del 2026-11-20). Ninguna librería de Go
// habla SMB1, por eso se usa smbclient.
//
// Para no escribir 1 GB en disco en cada pasada, smbclient descarga a una tubería con
// nombre (FIFO) y el replicador lee de ella en streaming.
type Samba struct {
	Binario  string            // "smbclient" por defecto
	Servidor string            // nombre NetBIOS: SCOSYSV
	IP       string            // 192.160.30.11
	Puerto   int               // 139
	Auth     string            // archivo con username/password/domain (smbclient -A), permisos 0600
	Recursos map[string]string // recurso lógico → nombre del recurso compartido en el SCO
	Opciones []string          // --option extra (p. ej. "client ntlmv2 auth = no")
	Espera   time.Duration     // tope para Info; 0 = 30 s
}

func (s Samba) args(recurso, comando string) ([]string, error) {
	nombre, ok := s.Recursos[recurso]
	if !ok {
		return nil, fmt.Errorf("recurso %q no configurado", recurso)
	}
	a := []string{"//" + s.Servidor + "/" + nombre, "-I", s.IP, "-p", strconv.Itoa(s.puerto()),
		"-A", s.Auth, "-m", "NT1", "--option=client min protocol=NT1"}
	for _, o := range s.Opciones {
		a = append(a, "--option="+o)
	}
	return append(a, "-c", comando), nil
}

func (s Samba) puerto() int {
	if s.Puerto == 0 {
		return 139
	}
	return s.Puerto
}

func (s Samba) binario() string {
	if s.Binario == "" {
		return "smbclient"
	}
	return s.Binario
}

// comillas para el comando de smbclient (las rutas del SCO no llevan comillas)
func citar(r string) string {
	return `"` + strings.ReplaceAll(r, "/", `\`) + `"`
}

// Línea de "ls": "  guia2601.his     A 103180288  Thu Nov 19 18:00:00 2026"
var lineaLs = regexp.MustCompile(`^\s+(.+?)\s+([A-Z]*)\s+(\d+)\s+(\w{3} \w{3}\s+\d+ \d\d:\d\d:\d\d \d{4})\s*$`)

func (s Samba) Info(ctx context.Context, recurso, ruta string) (Info, error) {
	espera := s.Espera
	if espera == 0 {
		espera = 30 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, espera)
	defer cancel()
	args, err := s.args(recurso, "ls "+citar(ruta))
	if err != nil {
		return Info{}, err
	}
	var out, errb bytes.Buffer
	cmd := exec.CommandContext(ctx, s.binario(), args...)
	cmd.Stdout, cmd.Stderr = &out, &errb
	if err := cmd.Run(); err != nil {
		return Info{}, fmt.Errorf("smbclient ls %s: %v: %s", ruta, err, strings.TrimSpace(errb.String()+" "+out.String()))
	}
	base := strings.ToLower(path.Base(ruta))
	for _, l := range strings.Split(out.String(), "\n") {
		m := lineaLs.FindStringSubmatch(l)
		if m == nil || strings.ToLower(m[1]) != base {
			continue
		}
		tam, _ := strconv.ParseInt(m[3], 10, 64)
		return Info{Tamano: tam, Marca: strings.Join(strings.Fields(m[4]), " ") + "/" + m[3]}, nil
	}
	return Info{}, fmt.Errorf("smbclient ls %s: %w", ruta, os.ErrNotExist)
}

// lectorSamba lee de la FIFO que llena smbclient.
type lectorSamba struct {
	f      *os.File
	dir    string
	fin    chan error
	cmd    *exec.Cmd
	errb    *bytes.Buffer
	cerrado bool
}

func (s Samba) Abrir(ctx context.Context, recurso, ruta string) (io.ReadCloser, error) {
	dir, err := os.MkdirTemp("", "replica-")
	if err != nil {
		return nil, err
	}
	fifo := filepath.Join(dir, "datos")
	if err := syscall.Mkfifo(fifo, 0o600); err != nil {
		os.RemoveAll(dir)
		return nil, fmt.Errorf("mkfifo: %w", err)
	}
	args, err := s.args(recurso, "get "+citar(ruta)+" "+fifo)
	if err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	errb := &bytes.Buffer{}
	cmd := exec.CommandContext(ctx, s.binario(), args...)
	cmd.Stdout, cmd.Stderr = errb, errb // smbclient escribe sus avisos en stdout
	if err := cmd.Start(); err != nil {
		os.RemoveAll(dir)
		return nil, fmt.Errorf("smbclient: %w", err)
	}
	fin := make(chan error, 1)
	go func() { fin <- cmd.Wait() }()

	type abierto struct {
		f   *os.File
		err error
	}
	ch := make(chan abierto, 1)
	go func() {
		f, err := os.Open(fifo) // se bloquea hasta que smbclient abra la FIFO para escribir
		ch <- abierto{f, err}
	}()

	select {
	case a := <-ch:
		if a.err != nil {
			_ = cmd.Process.Kill()
			<-fin
			os.RemoveAll(dir)
			return nil, a.err
		}
		return &lectorSamba{f: a.f, dir: dir, fin: fin, cmd: cmd, errb: errb}, nil
	case err := <-fin:
		// smbclient terminó sin abrir la FIFO (clave mala, archivo que no existe...):
		// se abre el lado de escritura para destrabar el Open y se devuelve el error.
		if w, e := os.OpenFile(fifo, os.O_WRONLY|syscall.O_NONBLOCK, 0); e == nil {
			w.Close()
		}
		if a := <-ch; a.f != nil {
			a.f.Close()
		}
		os.RemoveAll(dir)
		if err == nil {
			err = errors.New("terminó sin enviar datos")
		}
		return nil, fmt.Errorf("smbclient get %s: %v: %s", ruta, err, strings.TrimSpace(errb.String()))
	}
}

func (l *lectorSamba) Read(p []byte) (int, error) { return l.f.Read(p) }

// Close cierra la lectura. Si se cerró antes de terminar, smbclient muere por tubería rota;
// si se leyó todo y smbclient falló, se devuelve su error.
func (l *lectorSamba) Close() error {
	if l.cerrado {
		return nil
	}
	l.cerrado = true
	l.f.Close()
	var err error
	select {
	case err = <-l.fin:
	case <-time.After(10 * time.Second):
		_ = l.cmd.Process.Kill()
		err = <-l.fin
	}
	os.RemoveAll(l.dir)
	if err != nil {
		return fmt.Errorf("smbclient: %v: %s", err, strings.TrimSpace(l.errb.String()))
	}
	return nil
}
