package imile

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// Estados con que queda un paquete en iMile (mismos valores que guarda el backend Python).
const (
	OK           = "ok"
	Repetido     = "repetido"
	Bloqueado    = "bloqueado"
	Error        = "error"
	SinConfirmar = "sin_confirmar"
	Cerrada      = "cerrada" // Asignar repartidor: "Guía ya cerrada", iMile no deja asignarla
	Omitido      = "omitido" // el interruptor de esa automatización está apagado
	Pendiente    = "pendiente"
)

// Significado de cada blockCode en la pantalla de Llegada (confirmado por el usuario
// 2026-10-08/09): 1121 y 31000 = ya estaba ingresado; 1119 = el serial no existe en iMile.
var BloqueosIngreso = map[string]string{"1121": Repetido, "1119": Error, "31000": Repetido}

// En Asignar repartidor: 1119 no existe; 1118 "Guía ya cerrada" (2026-10-23).
var BloqueosAsignacion = map[string]string{"1119": Error, "1118": Cerrada}

type Resultado struct {
	Estado  string
	Mensaje *string
	Codigo  *string // blockCode / msgCode de iMile
}

// Definitivo: no vale la pena volver a mandarlo (reintentar daría lo mismo).
func (r Resultado) Definitivo() bool { return r.Estado != SinConfirmar }

func DecodificarCuerpo(b []byte) map[string]any {
	d := json.NewDecoder(bytes.NewReader(b))
	d.UseNumber() // blockCode puede venir como número: 1121 y no 1121.0
	var body map[string]any
	if d.Decode(&body) != nil {
		return nil
	}
	return body
}

func objeto(body map[string]any) map[string]any {
	ro, _ := body["resultObject"].(map[string]any)
	return ro
}

// texto: como `x or None` en Python (vacío, false, 0 y null → nil).
func texto(v any) *string {
	switch x := v.(type) {
	case nil:
		return nil
	case string:
		if x == "" {
			return nil
		}
		return &x
	case bool:
		if !x {
			return nil
		}
	case json.Number:
		if x.String() == "0" {
			return nil
		}
	}
	s := fmt.Sprint(v)
	return &s
}

func verdadero(v any) bool { return texto(v) != nil }

func primero(vs ...any) *string {
	for _, v := range vs {
		if s := texto(v); s != nil {
			return s
		}
	}
	return nil
}

func AbreVentanaBloqueo(body map[string]any) bool {
	ro := objeto(body)
	return verdadero(ro["blockCode"]) || verdadero(ro["blockInfo"])
}

// Clasificar: port de clasificar_respuesta (backend/app/services/imile_ingreso.py).
// La respuesta de iMile siempre trae status "success"; lo que importa está en resultObject.
func Clasificar(body map[string]any, bloqueos map[string]string) Resultado {
	if body == nil {
		return Resultado{Estado: SinConfirmar, Mensaje: texto("iMile no devolvió respuesta")}
	}
	if body["status"] != "success" {
		return Resultado{Estado: Error, Mensaje: texto(body["message"]), Codigo: texto(body["resultCode"])}
	}
	ro := objeto(body)
	codigo := primero(ro["blockCode"], ro["msgCode"])
	if AbreVentanaBloqueo(body) {
		estado, ok := bloqueos[fmt.Sprint(ro["blockCode"])]
		if !ok {
			estado = Bloqueado
		}
		return Resultado{Estado: estado, Mensaje: texto(ro["blockInfo"]), Codigo: codigo}
	}
	if verdadero(ro["repeat"]) {
		return Resultado{Estado: Repetido, Mensaje: primero(ro["warnMsg"], "Ya ingresado"), Codigo: codigo}
	}
	if ro["voiceType"] == "fail" {
		return Resultado{Estado: Error, Mensaje: primero(ro["warnMsg"], body["message"]), Codigo: codigo}
	}
	return Resultado{Estado: OK, Mensaje: texto(ro["warnMsg"]), Codigo: codigo}
}
