// Package db: conexión a PostgreSQL (la misma base del backend Python) y fechas en hora de Bogotá.
package db

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"
	_ "time/tzdata" // la imagen del contenedor puede no traer la base de zonas horarias

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

// DBTX lo cumplen tanto *pgxpool.Pool como pgx.Tx: los servicios corren igual dentro o
// fuera de una transacción.
type DBTX interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// El servidor corre en UTC: después de las 7 p. m. en Bogotá la fecha UTC ya es mañana.
var Bogota = mustLoad("America/Bogota")

func mustLoad(nombre string) *time.Location {
	loc, err := time.LoadLocation(nombre)
	if err != nil {
		panic(err)
	}
	return loc
}

func Conectar(ctx context.Context, url string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, err
	}
	cfg.MaxConns = 20
	cfg.MinConns = 2
	cfg.MaxConnIdleTime = 5 * time.Minute
	cfg.HealthCheckPeriod = 30 * time.Second
	return pgxpool.NewWithConfig(ctx, cfg)
}

// EsperarMigracion: el backend Python aplica las migraciones de Alembic al arrancar; este
// servicio no atiende hasta que la base tenga al menos `minima` (p. ej. "049").
func EsperarMigracion(ctx context.Context, pool *pgxpool.Pool, minima string, cada time.Duration) error {
	for {
		var v string
		err := pool.QueryRow(ctx, `SELECT version_num FROM alembic_version`).Scan(&v)
		if err == nil && len(v) == len(minima) && v >= minima {
			return nil
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("la base no llegó a la migración %s (va en %q): %w", minima, v, ctx.Err())
		case <-time.After(cada):
		}
	}
}

// EnTx corre fn en una transacción: commit si devuelve nil, rollback si no.
func EnTx(ctx context.Context, pool *pgxpool.Pool, fn func(pgx.Tx) error) error {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx) //nolint:errcheck // tras un commit no hace nada
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Fecha es un día sin hora, en JSON "2006-01-02" como lo manda Pydantic.
type Fecha struct{ time.Time }

func Hoy() Fecha {
	n := time.Now().In(Bogota)
	return Fecha{time.Date(n.Year(), n.Month(), n.Day(), 0, 0, 0, 0, time.UTC)}
}

func ParseFecha(s string) (Fecha, error) {
	t, err := time.Parse(time.DateOnly, s)
	return Fecha{t}, err
}

func (f Fecha) String() string { return f.Format(time.DateOnly) }

func (f Fecha) MarshalJSON() ([]byte, error) { return json.Marshal(f.String()) }

func (f *Fecha) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	t, err := time.Parse(time.DateOnly, s)
	f.Time = t
	return err
}

// ScanDate y DateValue: pgx lee y escribe columnas DATE directamente en Fecha.
func (f *Fecha) ScanDate(v pgtype.Date) error {
	if !v.Valid {
		f.Time = time.Time{}
		return nil
	}
	f.Time = time.Date(v.Time.Year(), v.Time.Month(), v.Time.Day(), 0, 0, 0, 0, time.UTC)
	return nil
}

func (f Fecha) DateValue() (pgtype.Date, error) {
	return pgtype.Date{Time: f.Time, Valid: !f.IsZero()}, nil
}

// FechaOpcional: para cuerpos con "fecha": null u omitida (por defecto hoy).
func FechaOpcional(f *Fecha) Fecha {
	if f == nil || f.IsZero() {
		return Hoy()
	}
	return *f
}

// InicioDelDia en Bogotá, como instante: para comparar contra columnas TIMESTAMPTZ.
func (f Fecha) InicioDelDia() time.Time {
	return time.Date(f.Year(), f.Month(), f.Day(), 0, 0, 0, 0, Bogota)
}

func EsUnicaViolada(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
