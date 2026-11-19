package offline

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
)

func TestEsErrorDeDatos(t *testing.T) {
	casos := []struct {
		err  error
		dato bool
	}{
		{&pgconn.PgError{Code: "22001"}, true}, // value too long (lo que trabó la cola el 2026-11-06)
		{fmt.Errorf("abrir: %w", &pgconn.PgError{Code: "23514"}), true},
		{&pgconn.PgError{Code: "40001"}, false}, // serialización: sí vale reintentar
		{&pgconn.PgError{Code: "57P01"}, false},
		{context.DeadlineExceeded, false},
		{errors.New("conexión cerrada"), false},
	}
	for _, c := range casos {
		if got := esErrorDeDatos(c.err); got != c.dato {
			t.Errorf("%v: %v, se esperaba %v", c.err, got, c.dato)
		}
	}
}
