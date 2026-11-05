// Package imile automatiza iMile con Playwright (playwright-go), como lo hacía
// backend/app/services/imile_*.py, pero con varias páginas trabajando a la vez.
//
// Un solo navegador y un solo BrowserContext (la sesión y las cookies se comparten) y
// varias páginas: cada página es de una sola goroutine (worker), así que el ingreso de
// paquetes, la asignación al mensajero y la consulta de tulas ya no hacen fila en un
// único candado. Cuando una página cae en el login, la sesión se vuelve a abrir una sola
// vez para todas: los workers trabajan con RLock y el re-login toma el Lock.
package imile

import (
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/playwright-community/playwright-go"

	"servilla/flujo/internal/config"
)

const (
	usuarioSelector         = "input[name='userCode']"
	claveSelector           = "input[name='password']"
	botonAccesoSelector     = "button:has-text('Acceso'), button:has-text('Login'), button[type='submit']"
	recorridoCerrarSelector = ".fireWrap .close-icon"
	idiomaObjetivo          = "Español"

	navTimeoutMs        = 30_000
	loginTimeoutMs      = 30_000
	accionTimeoutMs     = 5_000
	esperaEnterMs       = 3_000
	imileBaseURL        = "https://ds.imile.com"
	// Desde oct. 2026 el ingreso está en otro dominio: ds.imile.com/login redirige aquí
	imileLoginURL       = "https://ds-login.imile.com/"
	esperaCargaMs       = 3_000
	cambioIdiomaMs      = 15_000
	recorridoQuietoMs   = 4_000
	recorridoMaxMs      = 20_000
	pasoRecorridoMs     = 250
	cookieToken         = "IMILE_ACCESS_TOKEN"
)

// Etiquetas del selector de idioma del encabezado (orden del menú de iMile).
var idiomasImile = []string{"English", "简体中文", "Português", "Español", "Italian", "Macedonian", "German"}

var (
	ErrCredencialesFaltantes = errors.New("Faltan IMILE_USER e IMILE_PASS en el .env del servidor")
	ErrLogin                 = errors.New("No se pudo iniciar sesión en iMile: usuario o contraseña incorrectos, o iMile no respondió")
	// ErrSinSesion: la página cayó en el login. El worker suelta la página, pide
	// AsegurarSesion y reintenta.
	ErrSinSesion = errors.New("la sesión de iMile se cerró")
)

type EstadoSesion struct {
	CredencialesConfiguradas bool       `json:"credenciales_configuradas"`
	NavegadorAbierto         bool       `json:"navegador_abierto"`
	Conectado                bool       `json:"conectado"`
	Idioma                   *string    `json:"idioma"`
	UltimoIngreso            *time.Time `json:"ultimo_ingreso"`
}

type Sesion struct {
	cfg config.Config
	// Tiempos del recorrido de bienvenida y de la carga (las pruebas los acortan)
	esperaCargaMs, recorridoQuietoMs, recorridoMaxMs float64

	mu      sync.RWMutex // páginas trabajando: RLock · re-login: Lock
	abrirMu sync.Mutex
	pw      *playwright.Playwright
	browser playwright.Browser
	bctx    playwright.BrowserContext
	control playwright.Page // página propia para iniciar sesión y revisar el estado

	generacion    atomic.Int64 // sube con cada inicio de sesión exitoso
	conectado     atomic.Bool
	idioma        atomic.Pointer[string]
	ultimoIngreso atomic.Pointer[time.Time]
}

func NuevaSesion(cfg config.Config) *Sesion {
	return &Sesion{cfg: cfg, esperaCargaMs: esperaCargaMs, recorridoQuietoMs: recorridoQuietoMs, recorridoMaxMs: recorridoMaxMs}
}

func (s *Sesion) BaseURL() string { return strings.TrimRight(s.cfg.ImileBaseURL, "/") }

func (s *Sesion) loginURL() string {
	if s.cfg.ImileLoginURL != "" {
		return s.cfg.ImileLoginURL
	}
	if s.BaseURL() == imileBaseURL {
		return imileLoginURL
	}
	return s.BaseURL() + "/login"
}

func (s *Sesion) credenciales() (string, string, error) {
	if s.cfg.ImileUser == "" || s.cfg.ImilePass == "" {
		return "", "", ErrCredencialesFaltantes
	}
	return s.cfg.ImileUser, s.cfg.ImilePass, nil
}

// abrir arranca Playwright, el navegador y el contexto (con la sesión guardada) la
// primera vez que alguien los necesita.
func (s *Sesion) abrir() error {
	s.abrirMu.Lock()
	defer s.abrirMu.Unlock()
	if s.bctx != nil {
		return nil
	}
	if _, _, err := s.credenciales(); err != nil {
		return err
	}
	pw, err := playwright.Run(&playwright.RunOptions{DriverDirectory: s.cfg.ImileDriverDir, SkipInstallBrowsers: true})
	if err != nil {
		return fmt.Errorf("no se pudo arrancar Playwright: %w", err)
	}
	browser, err := pw.Chromium.Launch(playwright.BrowserTypeLaunchOptions{Headless: playwright.Bool(s.cfg.ImileHeadless)})
	if err != nil {
		_ = pw.Stop()
		return fmt.Errorf("no se pudo abrir Chromium: %w", err)
	}
	opts := playwright.BrowserNewContextOptions{Viewport: &playwright.Size{Width: 1400, Height: 900}}
	if _, err := os.Stat(s.cfg.ImileStatePath); err == nil {
		opts.StorageStatePath = playwright.String(s.cfg.ImileStatePath)
	}
	bctx, err := browser.NewContext(opts)
	if err != nil {
		_ = browser.Close()
		_ = pw.Stop()
		return err
	}
	control, err := bctx.NewPage()
	if err != nil {
		_ = browser.Close()
		_ = pw.Stop()
		return err
	}
	s.pw, s.browser, s.bctx, s.control = pw, browser, bctx, control
	return nil
}

// NuevaPagina para un worker; la página es solo suya mientras viva el worker.
func (s *Sesion) NuevaPagina() (playwright.Page, error) {
	if err := s.abrir(); err != nil {
		return nil, err
	}
	return s.bctx.NewPage()
}

func (s *Sesion) Generacion() int64 { return s.generacion.Load() }

// Usar corre fn mientras nadie esté volviendo a iniciar sesión. Varias a la vez.
func (s *Sesion) Usar(fn func() error) error {
	if err := s.abrir(); err != nil {
		return err
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	err := fn()
	if errors.Is(err, ErrSinSesion) {
		s.conectado.Store(false)
	}
	return err
}

// AsegurarSesion deja la sesión iniciada y en español. `vista` es la Generacion() que
// tenía el worker cuando falló: si otro ya volvió a entrar después, no se repite.
// Nunca se llama desde dentro de Usar (se bloquearía esperando su propio RLock).
func (s *Sesion) AsegurarSesion(vista int64, forzar bool) error {
	if err := s.abrir(); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if !forzar && s.generacion.Load() != vista && s.conectado.Load() {
		return nil
	}
	page := s.control
	if forzar {
		if err := s.iniciarSesion(page); err != nil {
			return err
		}
	} else {
		if !strings.HasPrefix(page.URL(), s.BaseURL()) {
			if _, err := page.Goto(s.BaseURL()+"/#", playwright.PageGotoOptions{Timeout: playwright.Float(navTimeoutMs)}); err != nil {
				return err
			}
			page.WaitForTimeout(s.esperaCargaMs)
		}
		if s.EnLogin(page) {
			if err := s.iniciarSesion(page); err != nil {
				return err
			}
		}
	}
	s.CerrarRecorrido(page)
	if err := s.ponerEnEspanol(page); err != nil {
		return err
	}
	s.conectado.Store(true)
	s.generacion.Add(1)
	return nil
}

func (s *Sesion) EnLogin(page playwright.Page) bool {
	u := page.URL()
	if strings.HasPrefix(u, s.loginURL()) || strings.Contains(u, "/login") {
		return true
	}
	n, _ := page.Locator(claveSelector).Count()
	return n > 0
}

func (s *Sesion) iniciarSesion(page playwright.Page) error {
	usuario, clave, err := s.credenciales()
	if err != nil {
		return err
	}
	if _, err := page.Goto(s.loginURL(), playwright.PageGotoOptions{Timeout: playwright.Float(navTimeoutMs)}); err != nil {
		return fmt.Errorf("%w (%v)", ErrLogin, err)
	}
	campo := page.Locator(usuarioSelector).First()
	if err := campo.WaitFor(playwright.LocatorWaitForOptions{Timeout: playwright.Float(navTimeoutMs)}); err != nil {
		return fmt.Errorf("%w (%v)", ErrLogin, err)
	}
	if err := campo.Fill(usuario); err != nil {
		return err
	}
	if err := page.Locator(claveSelector).First().Fill(clave); err != nil {
		return err
	}
	if err := page.Locator(claveSelector).First().Press("Enter"); err != nil {
		return err
	}
	// Entró cuando vuelve a la página de iMile (el formulario nuevo vive en
	// ds-login.imile.com, cuya URL no dice "/login")
	entro := "base => location.href.startsWith(base) && !location.href.includes('/login')"
	if _, err := page.WaitForFunction(entro, s.BaseURL(), playwright.PageWaitForFunctionOptions{Timeout: playwright.Float(esperaEnterMs)}); err != nil {
		boton := page.Locator(botonAccesoSelector)
		if n, _ := boton.Count(); n > 0 {
			_ = boton.First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(accionTimeoutMs)})
		}
		if _, err := page.WaitForFunction(entro, s.BaseURL(), playwright.PageWaitForFunctionOptions{Timeout: playwright.Float(loginTimeoutMs)}); err != nil {
			return ErrLogin
		}
	}
	page.WaitForTimeout(s.esperaCargaMs)
	ahora := time.Now().UTC()
	s.ultimoIngreso.Store(&ahora)
	s.guardarEstado()
	slog.Info("imile: sesión iniciada")
	return nil
}

func (s *Sesion) guardarEstado() {
	if err := os.MkdirAll(filepath.Dir(s.cfg.ImileStatePath), 0o700); err != nil {
		slog.Warn("imile: no se pudo crear la carpeta de la sesión", "err", err)
		return
	}
	if _, err := s.bctx.StorageState(s.cfg.ImileStatePath); err != nil {
		slog.Warn("imile: no se pudo guardar la sesión", "err", err)
	}
}

// CerrarRecorrido: el recorrido de bienvenida aparece unos segundos DESPUÉS de cargar
// la página y tapa los clics. Se cierra cada vez que aparece y se sigue cuando lleva
// recorridoQuietoMs sin aparecer (o se agotó recorridoMaxMs).
func (s *Sesion) CerrarRecorrido(page playwright.Page) {
	quieto, transcurrido := 0.0, 0.0
	for quieto < s.recorridoQuietoMs && transcurrido < s.recorridoMaxMs {
		cerrar := page.Locator(recorridoCerrarSelector)
		if n, _ := cerrar.Count(); n > 0 {
			_ = cerrar.First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(accionTimeoutMs)})
			quieto = 0
		} else {
			quieto += pasoRecorridoMs
		}
		page.WaitForTimeout(pasoRecorridoMs)
		transcurrido += pasoRecorridoMs
	}
}

// etiquetaIdioma: la etiqueta VISIBLE del selector (el menú puede estar en el DOM oculto).
func etiquetaIdioma(page playwright.Page) (string, playwright.Locator) {
	for _, idioma := range idiomasImile {
		candidatos := page.GetByText(idioma, playwright.PageGetByTextOptions{Exact: playwright.Bool(true)})
		n, _ := candidatos.Count()
		for i := 0; i < n; i++ {
			if v, _ := candidatos.Nth(i).IsVisible(); v {
				return idioma, candidatos.Nth(i)
			}
		}
	}
	return "", nil
}

func (s *Sesion) ponerEnEspanol(page playwright.Page) error {
	idioma, etiqueta := etiquetaIdioma(page)
	if etiqueta == nil || idioma == idiomaObjetivo {
		if idioma != "" {
			s.idioma.Store(&idioma)
		}
		return nil
	}
	s.CerrarRecorrido(page)
	if err := etiqueta.Click(playwright.LocatorClickOptions{Timeout: playwright.Float(accionTimeoutMs)}); err != nil {
		return err
	}
	opcion := page.Locator(fmt.Sprintf(
		"li:has-text('%[1]s'), [role='option']:has-text('%[1]s'), [role='menuitem']:has-text('%[1]s')", idiomaObjetivo))
	if err := opcion.First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(accionTimeoutMs)}); err != nil {
		return err
	}
	// iMile recarga la página al cambiar el idioma y tarda en pintar el encabezado
	for i := 0; i < cambioIdiomaMs/500; i++ {
		if actual, _ := etiquetaIdioma(page); actual == idiomaObjetivo {
			objetivo := idiomaObjetivo
			s.idioma.Store(&objetivo)
			s.CerrarRecorrido(page)
			s.guardarEstado()
			return nil
		}
		page.WaitForTimeout(500)
	}
	return fmt.Errorf("iMile no quedó en %s después de cambiar el idioma", idiomaObjetivo)
}

// Token: el que la página manda en Authorization (sale de la cookie IMILE_ACCESS_TOKEN).
// Vacío si no hay cookie: se pregunta igual y iMile dirá si la sesión no sirve.
func (s *Sesion) Token() (string, error) {
	cookies, err := s.bctx.Cookies()
	if err != nil {
		return "", err
	}
	for _, c := range cookies {
		if c.Name == cookieToken && c.Value != "" {
			if strings.HasPrefix(strings.ToLower(c.Value), "bearer ") {
				return c.Value, nil
			}
			return "Bearer " + c.Value, nil
		}
	}
	return "", nil
}

func (s *Sesion) Request() playwright.APIRequestContext { return s.bctx.Request() }

func (s *Sesion) Estado() EstadoSesion {
	_, _, errCred := s.credenciales()
	s.abrirMu.Lock()
	abierto := s.bctx != nil
	s.abrirMu.Unlock()
	e := EstadoSesion{
		CredencialesConfiguradas: errCred == nil,
		NavegadorAbierto:         abierto,
		Conectado:                abierto && s.conectado.Load(),
		UltimoIngreso:            s.ultimoIngreso.Load(),
	}
	if e.Conectado {
		e.Idioma = s.idioma.Load()
	}
	return e
}

func (s *Sesion) Cerrar() {
	s.abrirMu.Lock()
	defer s.abrirMu.Unlock()
	if s.bctx != nil {
		_ = s.bctx.Close()
	}
	if s.browser != nil {
		_ = s.browser.Close()
	}
	if s.pw != nil {
		_ = s.pw.Stop()
	}
	s.pw, s.browser, s.bctx, s.control = nil, nil, nil, nil
}
