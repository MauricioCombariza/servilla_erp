package tulas

import (
	"reflect"
	"testing"
)

func TestContador(t *testing.T) {
	sinTotal := leer(Tula{}, 3)
	if sinTotal.Contador != 3 || sinTotal.Diferencia != nil {
		t.Errorf("sin total el contador sube: %+v", sinTotal)
	}
	n := 2
	sobran := leer(Tula{TotalEsperado: &n}, 3)
	if sobran.Contador != -1 || *sobran.Diferencia != -1 {
		t.Errorf("con total baja y puede quedar negativo: %+v", sobran)
	}
}

func TestComparar(t *testing.T) {
	f, ne := Comparar([]string{"A", "B", "C"}, []string{"C", "D", "A"})
	if !reflect.DeepEqual(f, []string{"B"}) || !reflect.DeepEqual(ne, []string{"D"}) {
		t.Errorf("faltantes %v no esperados %v", f, ne)
	}
	f, ne = Comparar([]string{"A"}, []string{"A"})
	if f == nil || ne == nil || len(f)+len(ne) != 0 {
		t.Error("sin diferencias deben ser listas vacías (no null)")
	}
}
