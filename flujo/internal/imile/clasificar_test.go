package imile

import (
	"testing"
)

func respuesta(ro map[string]any) map[string]any {
	base := map[string]any{"status": 2, "repeat": false, "voiceType": "success"}
	for k, v := range ro {
		base[k] = v
	}
	return map[string]any{"status": "success", "resultCode": "", "message": "Successful operation!", "resultObject": base}
}

func s(v string) *string { return &v }

func igual(a, b *string) bool { return (a == nil && b == nil) || (a != nil && b != nil && *a == *b) }

// Los mismos casos de backend/tests/test_imile_ingreso.py::test_clasificar_respuesta
func TestClasificarIngreso(t *testing.T) {
	casos := []struct {
		nombre          string
		body            map[string]any
		estado          string
		codigo, mensaje *string
	}{
		{"1121 repetido", respuesta(map[string]any{"blockInfo": "No registrar Motivo Problema", "blockCode": "1121", "msgCode": "1121", "voiceType": "fail"}),
			Repetido, s("1121"), s("No registrar Motivo Problema")},
		{"1119 no existe", respuesta(map[string]any{"blockInfo": "Sin información de pedido()", "blockCode": "1119", "msgCode": "1119", "voiceType": "fail"}),
			Error, s("1119"), s("Sin información de pedido()")},
		{"31000 repetido", respuesta(map[string]any{"blockInfo": "Escaneo repetido", "blockCode": "31000", "voiceType": "fail"}),
			Repetido, s("31000"), s("Escaneo repetido")},
		{"desconocido bloqueado", respuesta(map[string]any{"blockInfo": "Otro motivo", "blockCode": "9999", "voiceType": "fail"}),
			Bloqueado, s("9999"), s("Otro motivo")},
		{"repeat", respuesta(map[string]any{"repeat": true, "warnMsg": "Ya escaneado"}), Repetido, nil, s("Ya escaneado")},
		{"fail", respuesta(map[string]any{"voiceType": "fail", "warnMsg": "Algo falló"}), Error, nil, s("Algo falló")},
		{"ok", respuesta(nil), OK, nil, nil},
		{"status fail", map[string]any{"status": "fail", "message": "Token inválido", "resultCode": "401"}, Error, s("401"), s("Token inválido")},
		{"sin respuesta", nil, SinConfirmar, nil, s("iMile no devolvió respuesta")},
	}
	for _, c := range casos {
		r := Clasificar(c.body, BloqueosIngreso)
		if r.Estado != c.estado || !igual(r.Codigo, c.codigo) || !igual(r.Mensaje, c.mensaje) {
			t.Errorf("%s: obtuve (%s, %v, %v)", c.nombre, r.Estado, deref(r.Codigo), deref(r.Mensaje))
		}
	}
}

func TestClasificarAsignacionCerrada(t *testing.T) {
	r := Clasificar(respuesta(map[string]any{"blockInfo": "Guía ya cerrada", "blockCode": "1118"}), BloqueosAsignacion)
	if r.Estado != Cerrada {
		t.Fatalf("1118 debe quedar cerrada, quedó %s", r.Estado)
	}
}

// blockCode numérico (sin comillas) en el JSON debe leerse igual que el texto
func TestBlockCodeNumerico(t *testing.T) {
	body := DecodificarCuerpo([]byte(`{"status":"success","resultObject":{"blockCode":1121,"blockInfo":"x"}}`))
	r := Clasificar(body, BloqueosIngreso)
	if r.Estado != Repetido || *r.Codigo != "1121" {
		t.Fatalf("obtuve %s %v", r.Estado, deref(r.Codigo))
	}
}

func deref(p *string) any {
	if p == nil {
		return nil
	}
	return *p
}

func TestElegirOpcionDA(t *testing.T) {
	m, ok := opcionDe("Juan Porras | D21043330501")
	if !ok || m.nombre != "Juan Porras" || m.codigo != "D21043330501" {
		t.Fatalf("opción mal leída: %+v", m)
	}
	if !m.esElBuscado(buscadoDe("  juan   porras ")) {
		t.Error("el nombre debe coincidir sin importar mayúsculas ni espacios")
	}
	if m.esElBuscado(buscadoDe("Juan Porras | D99")) {
		t.Error("con código solo vale ese código")
	}
	if _, ok := opcionDe("Sin código"); ok {
		t.Error("una opción sin '|' no es mensajero")
	}
}
