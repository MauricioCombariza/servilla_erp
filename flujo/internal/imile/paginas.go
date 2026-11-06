package imile

import (
	"errors"
	"fmt"
	"log/slog"
	"path/filepath"
	"strings"

	"github.com/playwright-community/playwright-go"
)

const (
	rutaLlegada      = "/#/DSOperation/OperationManagement/arrivalScanAWB"
	rutaApiIngreso   = "/inbound/submit"
	rutaDescarga     = "/#/DSOperation/DSInbound/dsOffloadingScan"
	rutaApiDescarga  = "/unloading/submit"
	rutaAsignar      = "/#/DSOperation/DispatchManagement/assignDA"
	rutaApiAsignar   = "/bizAssignDaScan/submit"
	campoGuia        = "input[name='scanNumber']"
	selectorDA       = "#daCode .ImileSelect-root"
	etiquetaDA       = "#daCode .ImileSelect-trigger-label"
	desplegableDA    = ".MuiTooltip-popper:has(.ImileSelect-list)" // hay otros .MuiTooltip-popper (tooltips)
	opcionDA         = "li.ImileSelect-item"
	cargaPaginaMs    = 30_000
	esperaRespuesta  = 20_000
	esperaVentanaMs  = 3_000
	esperaBusquedaMs = 10_000
	pasoBusquedaMs   = 250
	esperaAbrirMs    = 3_000
	// Si algo tapa el selector DA (ventana o recorrido de iMile) el clic no entra nunca: se
	// corta antes de los 30 s por defecto para recargar la pantalla y reintentar
	clicDAMs = 8_000
)

// MensajeroNoEncontradoError: el nombre no está (o está repetido) en el selector DA de iMile.
type MensajeroNoEncontradoError struct{ Mensaje string }

func (e *MensajeroNoEncontradoError) Error() string { return e.Mensaje }

// abrirPantalla deja la página en `ruta` con el campo de guía visible. Si la página quedó
// en el login (p. ej. después de que otro worker volvió a entrar) navega de nuevo; si
// iMile la sigue mandando al login devuelve ErrSinSesion.
func (s *Sesion) abrirPantalla(page playwright.Page, ruta, marca string) error {
	if !s.EnLogin(page) && strings.Contains(page.URL(), marca) {
		if n, _ := page.Locator(campoGuia).Count(); n > 0 {
			return nil
		}
	}
	if _, err := page.Goto(s.BaseURL()+ruta, playwright.PageGotoOptions{Timeout: playwright.Float(navTimeoutMs)}); err != nil {
		return err
	}
	page.WaitForTimeout(s.esperaCargaMs / 3) // la página redirige al login con JS, no por HTTP
	if s.EnLogin(page) {
		return ErrSinSesion
	}
	if err := page.Locator(campoGuia).First().WaitFor(playwright.LocatorWaitForOptions{
		State: playwright.WaitForSelectorStateVisible, Timeout: playwright.Float(cargaPaginaMs),
	}); err != nil {
		if s.EnLogin(page) {
			return ErrSinSesion
		}
		return err
	}
	s.CerrarRecorrido(page)
	return nil
}

// cancelarVentanas cierra sin confirmar: el aviso "Excepción de impresión" (botón
// "cierre") y la ventana "bloquear" (botón "Cancelar"). Nunca presiona "Confirmar".
func cancelarVentanas(page playwright.Page, esperar bool) {
	exacto := playwright.PageGetByTextOptions{Exact: playwright.Bool(true)}
	if esperar {
		if err := page.GetByText("Cancelar", exacto).First().WaitFor(playwright.LocatorWaitForOptions{
			State: playwright.WaitForSelectorStateVisible, Timeout: playwright.Float(esperaVentanaMs),
		}); err != nil {
			return
		}
	}
	for _, t := range []string{"Cancelar", "cierre"} {
		botones := page.GetByText(t, exacto)
		n, _ := botones.Count()
		for i := 0; i < n; i++ {
			if v, _ := botones.Nth(i).IsVisible(); v {
				_ = botones.Nth(i).Click()
				page.WaitForTimeout(300)
			}
		}
	}
}

// escanear escribe el serial en Número de Guía, presiona Enter y lee la respuesta que
// la propia página recibe de iMile en `rutaApi`.
func escanear(page playwright.Page, serial, rutaApi string, bloqueos map[string]string) (Resultado, error) {
	r, _, err := escanearConCuerpo(page, serial, rutaApi, bloqueos)
	return r, err
}

// escanearConCuerpo: como escanear, y además devuelve el cuerpo que respondió iMile.
func escanearConCuerpo(page playwright.Page, serial, rutaApi string, bloqueos map[string]string) (Resultado, []byte, error) {
	campo := page.Locator(campoGuia).First()
	if err := campo.Fill(serial); err != nil {
		return Resultado{}, nil, err
	}
	var crudo []byte
	var body map[string]any
	resp, err := page.ExpectResponse(func(u string) bool { return strings.Contains(u, rutaApi) },
		func() error { return campo.Press("Enter") },
		playwright.PageExpectResponseOptions{Timeout: playwright.Float(esperaRespuesta)})
	var tiempo *playwright.Error
	switch {
	case err == nil:
		if b, errBody := resp.Body(); errBody == nil {
			crudo, body = b, DecodificarCuerpo(b)
		}
	case errors.As(err, &tiempo) || errors.Is(err, playwright.ErrTimeout):
		// sin respuesta a tiempo: queda sin_confirmar
	default:
		return Resultado{}, nil, err
	}
	if AbreVentanaBloqueo(body) {
		cancelarVentanas(page, true)
	}
	return Clasificar(body, bloqueos), crudo, nil
}

// Descargar: "Descarga de escaneo" de una tula (dsOffloadingScan). Es una acción real en
// iMile: después de esto la consulta (unloading/search) ya sabe qué paquetes trae. Se
// escribe el código y Enter; si sale una ventana se cancela, nunca se confirma nada.
// Devuelve también la respuesta de iMile para dejarla en el log (aún no se ha visto la
// de una tula real descargada con éxito: la grabación del 2026-10-26 fue con "21").
func (s *Sesion) Descargar(page playwright.Page, codigo string) (Resultado, []byte, error) {
	if err := s.abrirPantalla(page, rutaDescarga, "dsOffloadingScan"); err != nil {
		return Resultado{}, nil, err
	}
	cancelarVentanas(page, false)
	r, crudo, err := escanearConCuerpo(page, strings.TrimSpace(codigo), rutaApiDescarga, BloqueosDescarga)
	if err == nil && !AbreVentanaBloqueo(DecodificarCuerpo(crudo)) && verdadero(objeto(DecodificarCuerpo(crudo))["popup"]) {
		cancelarVentanas(page, true) // iMile pidió ventana sin bloqueo: se cierra sin confirmar
	}
	return r, crudo, err
}

// Ingresar: Paso 2.5, "Llegada (Waybill No)". El peso no se llena y la fecha se deja como está.
func (s *Sesion) Ingresar(page playwright.Page, serial string) (Resultado, error) {
	if err := s.abrirPantalla(page, rutaLlegada, "arrivalScanAWB"); err != nil {
		return Resultado{}, err
	}
	cancelarVentanas(page, false)
	return escanear(page, strings.TrimSpace(serial), rutaApiIngreso, BloqueosIngreso)
}

// Asignar: Paso 3.3, "Asignar repartidor". Elige al mensajero en el selector DA (si la
// página no lo tenía ya elegido) y escanea el serial.
func (s *Sesion) Asignar(page playwright.Page, nombre, serial string) (Resultado, error) {
	if err := s.abrirPantalla(page, rutaAsignar, "assignDA"); err != nil {
		return Resultado{}, err
	}
	cancelarVentanas(page, false)
	if err := elegirMensajero(page, nombre); err != nil {
		if !errors.Is(err, playwright.ErrTimeout) {
			return Resultado{}, err
		}
		// La página quedó trabada (2026-10-26: todos los seriales de un lote fallaban al
		// hacer clic en el selector DA): se recarga la pantalla y se reintenta una vez
		if err := s.reintentarMensajero(page, nombre); err != nil {
			if errors.Is(err, playwright.ErrTimeout) {
				s.guardarPantalla(page)
			}
			return Resultado{}, err
		}
	}
	return escanear(page, strings.TrimSpace(serial), rutaApiAsignar, BloqueosAsignacion)
}

func (s *Sesion) reintentarMensajero(page playwright.Page, nombre string) error {
	_ = page.Keyboard().Press("Escape")
	cancelarVentanas(page, false)
	// Goto a la misma ruta con # no recarga el documento
	if _, err := page.Reload(playwright.PageReloadOptions{Timeout: playwright.Float(navTimeoutMs)}); err != nil {
		return err
	}
	if err := s.abrirPantalla(page, rutaAsignar, "assignDA"); err != nil {
		return err
	}
	s.CerrarRecorrido(page) // abrirPantalla no lo cierra si el campo ya cargó tras recargar
	cancelarVentanas(page, false)
	return elegirMensajero(page, nombre)
}

// guardarPantalla: para ver después qué tapaba el selector DA.
func (s *Sesion) guardarPantalla(page playwright.Page) {
	ruta := filepath.Join(filepath.Dir(s.cfg.ImileStatePath), "imile_asignar_error.png")
	if _, err := page.Screenshot(playwright.PageScreenshotOptions{Path: playwright.String(ruta), FullPage: playwright.Bool(true)}); err != nil {
		slog.Warn("imile: no se pudo guardar la pantalla del selector DA tapado", "err", err)
		return
	}
	slog.Warn("imile: selector DA tapado", "pantalla", ruta)
}

type mensajeroImile struct{ nombre, codigo string }

// opcionDe: "Juan Porras | D21043330501" → nombre y código de iMile.
func opcionDe(t string) (mensajeroImile, bool) {
	i := strings.LastIndex(t, "|")
	if i < 0 {
		return mensajeroImile{}, false
	}
	return mensajeroImile{strings.TrimSpace(t[:i]), strings.TrimSpace(t[i+1:])}, true
}

func normalizar(s string) string { return strings.ToLower(strings.Join(strings.Fields(s), " ")) }

// buscadoDe: "Mariela Pabon" o "Mariela Pabon | D21026309101" (con código se elige
// exactamente esa opción, aunque el nombre esté repetido).
func buscadoDe(t string) mensajeroImile {
	t = strings.Join(strings.Fields(t), " ")
	if m, ok := opcionDe(t); ok {
		return m
	}
	return mensajeroImile{nombre: t}
}

func (m mensajeroImile) esElBuscado(b mensajeroImile) bool {
	if b.codigo != "" {
		return strings.EqualFold(m.codigo, b.codigo)
	}
	return normalizar(m.nombre) == normalizar(b.nombre)
}

func coincidencias(opciones playwright.Locator, buscado mensajeroImile) []int {
	var idx []int
	n, _ := opciones.Count()
	for i := 0; i < n; i++ {
		t, err := opciones.Nth(i).InnerText()
		if err != nil {
			continue
		}
		if m, ok := opcionDe(t); ok && m.esElBuscado(buscado) {
			idx = append(idx, i)
		}
	}
	return idx
}

func elegirMensajero(page playwright.Page, nombre string) error {
	buscado := buscadoDe(nombre)
	// Si ya está elegido (serial anterior del mismo mensajero) no se toca el selector
	if t, err := page.Locator(etiquetaDA).First().InnerText(); err == nil {
		if actual, ok := opcionDe(t); ok && actual.esElBuscado(buscado) {
			return nil
		}
	}

	desplegable := page.Locator(desplegableDA).Last()
	if err := page.Locator(selectorDA).First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(clicDAMs)}); err != nil {
		return err
	}
	visible := func(ms float64) error {
		return desplegable.WaitFor(playwright.LocatorWaitForOptions{
			State: playwright.WaitForSelectorStateVisible, Timeout: playwright.Float(ms)})
	}
	if visible(esperaAbrirMs) != nil {
		// Si ya estaba abierto, ese clic lo cerró: se vuelve a abrir
		if err := page.Locator(selectorDA).First().Click(playwright.LocatorClickOptions{Timeout: playwright.Float(clicDAMs)}); err != nil {
			return err
		}
		if err := visible(cargaPaginaMs); err != nil {
			return err
		}
	}
	if err := desplegable.Locator("input").First().Fill(buscado.nombre); err != nil {
		return err
	}

	// La lista la trae iMile al escribir y puede tardar varios segundos
	opciones := desplegable.Locator(opcionDA)
	var encontradas []int
	for i := 0; i < esperaBusquedaMs/pasoBusquedaMs; i++ {
		page.WaitForTimeout(pasoBusquedaMs)
		if encontradas = coincidencias(opciones, buscado); len(encontradas) > 0 {
			page.WaitForTimeout(pasoBusquedaMs) // por si la lista sigue llegando (nombres repetidos)
			encontradas = coincidencias(opciones, buscado)
			break
		}
	}
	if len(encontradas) != 1 {
		_ = page.Keyboard().Press("Escape")
		motivo := "no está"
		if len(encontradas) > 1 {
			motivo = fmt.Sprintf("aparece %d veces", len(encontradas))
		}
		return &MensajeroNoEncontradoError{fmt.Sprintf("%q %s en la lista de mensajeros de iMile", nombre, motivo)}
	}
	return opciones.Nth(encontradas[0]).Click()
}
