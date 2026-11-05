package imile

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/playwright-community/playwright-go"
	"golang.org/x/sync/singleflight"
)

// Paso 2.3: cuántos paquetes trae una tula según iMile. SOLO CONSULTA.
//
// POST .../unloading/search devuelve un renglón por paquete descargado en la estación con
// su tula (bagNo); no filtra por tula (visto 2026-10-16), así que se trae todo y se
// cuenta aquí. Como es la misma respuesta para todas las tulas, se guarda unos segundos
// y las consultas simultáneas comparten una sola petición a iMile (singleflight).
const (
	rutaDescargados = "/lm/express/ops/v1/biz/unloading/search"
	tamPagina       = 500
	maxPaginas      = 20 // tope de seguridad: 10.000 paquetes descargados
	esperaConsulta  = 20_000
)

type ConsultaTula struct {
	Encontrada bool
	Total      *int
	Seriales   []string
}

type filaDescargado struct {
	WaybillNo  string `json:"waybillNo"`
	BagNo      string `json:"bagNo"`
	ScanNumber string `json:"scanNumber"`
}

type Consultor struct {
	sesion *Sesion
	ttl    time.Duration

	grupo singleflight.Group
	mu    sync.Mutex
	filas []filaDescargado
	hora  time.Time
}

func NuevoConsultor(s *Sesion, ttl time.Duration) *Consultor { return &Consultor{sesion: s, ttl: ttl} }

func (c *Consultor) Consultar(ctx context.Context, codigo string) (ConsultaTula, error) {
	codigo = strings.TrimSpace(codigo)
	filas, edad, err := c.descargados(ctx, false)
	if err != nil {
		return ConsultaTula{}, err
	}
	r := contar(filas, codigo)
	// Una tula recién descargada puede no estar en lo guardado: se pregunta otra vez
	if !r.Encontrada && edad > 2*time.Second {
		if filas, _, err = c.descargados(ctx, true); err != nil {
			return ConsultaTula{}, err
		}
		r = contar(filas, codigo)
	}
	return r, nil
}

func contar(filas []filaDescargado, codigo string) ConsultaTula {
	vistos := map[string]bool{}
	for _, f := range filas {
		if f.WaybillNo != "" && (f.BagNo == codigo || f.ScanNumber == codigo) {
			vistos[f.WaybillNo] = true
		}
	}
	if len(vistos) == 0 {
		return ConsultaTula{}
	}
	seriales := make([]string, 0, len(vistos))
	for s := range vistos {
		seriales = append(seriales, s)
	}
	sort.Strings(seriales)
	total := len(seriales)
	return ConsultaTula{Encontrada: true, Total: &total, Seriales: seriales}
}

func (c *Consultor) descargados(ctx context.Context, fresco bool) ([]filaDescargado, time.Duration, error) {
	c.mu.Lock()
	if !fresco && c.filas != nil && time.Since(c.hora) < c.ttl {
		filas, edad := c.filas, time.Since(c.hora)
		c.mu.Unlock()
		return filas, edad, nil
	}
	c.mu.Unlock()

	ch := c.grupo.DoChan("descargados", func() (any, error) {
		var filas []filaDescargado
		vista := c.sesion.Generacion()
		err := c.sesion.Usar(func() error {
			var err error
			filas, err = c.pedir()
			return err
		})
		if errors.Is(err, ErrSinSesion) {
			if err = c.sesion.AsegurarSesion(vista, false); err == nil {
				err = c.sesion.Usar(func() error {
					var err error
					filas, err = c.pedir()
					return err
				})
			}
		}
		if err != nil {
			return nil, err
		}
		c.mu.Lock()
		c.filas, c.hora = filas, time.Now()
		c.mu.Unlock()
		return filas, nil
	})
	select {
	case <-ctx.Done():
		return nil, 0, ctx.Err()
	case r := <-ch:
		if r.Err != nil {
			return nil, 0, r.Err
		}
		return r.Val.([]filaDescargado), 0, nil
	}
}

func (c *Consultor) pedir() ([]filaDescargado, error) {
	token, err := c.sesion.Token()
	if err != nil {
		return nil, err
	}
	headers := map[string]string{"content-type": "application/json"}
	if token != "" {
		headers["authorization"] = token
	}
	var filas []filaDescargado
	for pagina := 1; pagina <= maxPaginas; pagina++ {
		datos, _ := json.Marshal(map[string]int{"pageNum": pagina, "pageSize": tamPagina})
		r, err := c.sesion.Request().Post(c.sesion.BaseURL()+rutaDescargados, playwright.APIRequestContextPostOptions{
			Headers: headers, Data: string(datos), Timeout: playwright.Float(esperaConsulta),
		})
		if err != nil {
			return nil, err
		}
		var body struct {
			Status       string `json:"status"`
			Message      string `json:"message"`
			ResultObject struct {
				Results []filaDescargado `json:"results"`
			} `json:"resultObject"`
		}
		if err := r.JSON(&body); err != nil {
			if r.Status() == 401 {
				return nil, ErrSinSesion
			}
			return nil, fmt.Errorf("iMile respondió HTTP %d sin JSON", r.Status())
		}
		if body.Status != "success" {
			if body.Message == "" {
				body.Message = fmt.Sprintf("iMile respondió HTTP %d", r.Status())
			}
			return nil, errors.New(body.Message)
		}
		filas = append(filas, body.ResultObject.Results...)
		if len(body.ResultObject.Results) < tamPagina {
			break
		}
	}
	return filas, nil
}
