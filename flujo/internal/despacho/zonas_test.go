package despacho

import (
	"reflect"
	"testing"
)

func TestOrdenarZonas(t *testing.T) {
	type f struct {
		n string
		o int
	}
	filas := []f{{"10_2", 50}, {"60_10", 1}, {"60_2", 3}, {"10_1", 51}, {"70_1", 10}}
	got := ordenarZonas(filas, func(x f) (string, int) { return x.n, x.o })
	want := []string{"60_2", "60_10", "70_1", "10_1", "10_2"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("obtuve %v", got)
	}
}

func TestUltimos4(t *testing.T) {
	if Ultimos4("3671050719461") != "9461" || Ultimos4("12") != "12" {
		t.Error("últimos 4 mal")
	}
}
