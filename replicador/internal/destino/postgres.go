// Package destino escribe en Postgres (esquema legacy): una tabla por archivo del FoxPro,
// creada sola a partir de los campos del DBF, más el estado y la conciliación de cada pasada.
package destino

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math/big"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"

	"servilla/replicador/internal/dbf"
)

// Fila lista para escribir: valores ya convertidos, en el orden de los campos.
type Fila struct {
	Recno   uint32
	Hash    int64
	Borrado bool
	Valores []any
	Crudo   map[string]string // valores que no se pudieron convertir
}

// Estado guardado de un archivo (legacy._archivos).
type Estado struct {
	Marca     string
	Registros int64
}

// Conciliacion de una pasada (legacy._conciliacion).
type Conciliacion struct {
	Tabla        string
	RegistrosDBF int64 // los que dice el encabezado
	Incluidos    int64 // los que pasan el filtro (borrados incluidos)
	Borrados     int64
	Enviados     int64 // nuevos o cambiados en esta pasada
	EnPG         int64
	SumaDBF      *big.Int
	SumaPG       *big.Int
	Segundos     float64
}

// OK si Postgres quedó igual al DBF (mismo conteo y misma suma de hashes).
func (c Conciliacion) OK() bool {
	return c.Incluidos == c.EnPG && c.SumaDBF.Cmp(c.SumaPG) == 0
}

// Filtro de fecha: solo filas con Campo >= Desde (o sin fecha válida, que no se pueden juzgar).
type Filtro struct {
	Campo string
	Desde time.Time
}

type Postgres struct {
	Pool    *pgxpool.Pool
	Esquema string // "legacy"
}

func (p Postgres) id(tabla string) string {
	return pgx.Identifier{p.Esquema, tabla}.Sanitize()
}

func tipoPG(c dbf.Campo) string {
	switch c.Tipo {
	case 'N', 'F', 'Y', 'B', 'I':
		return "numeric"
	case 'D':
		return "date"
	case 'T':
		return "timestamptz"
	case 'L':
		return "boolean"
	default:
		return "text"
	}
}

// AsegurarTabla crea la tabla del archivo si no existe y agrega las columnas que falten
// (si en el FoxPro le agregan un campo a la tabla).
func (p Postgres) AsegurarTabla(ctx context.Context, tabla string, campos []dbf.Campo) error {
	cols := []string{"_recno integer PRIMARY KEY", "_hash bigint NOT NULL", "_borrado boolean NOT NULL",
		"_crudo jsonb", "_visto_en timestamptz NOT NULL DEFAULT now()"}
	for _, c := range campos {
		cols = append(cols, pgx.Identifier{c.Nombre}.Sanitize()+" "+tipoPG(c))
	}
	if _, err := p.Pool.Exec(ctx, fmt.Sprintf("CREATE TABLE IF NOT EXISTS %s (%s)", p.id(tabla), strings.Join(cols, ", "))); err != nil {
		return fmt.Errorf("crear %s: %w", tabla, err)
	}
	for _, c := range campos {
		q := fmt.Sprintf("ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s", p.id(tabla), pgx.Identifier{c.Nombre}.Sanitize(), tipoPG(c))
		if _, err := p.Pool.Exec(ctx, q); err != nil {
			return fmt.Errorf("columna %s.%s: %w", tabla, c.Nombre, err)
		}
	}
	return nil
}

// Estado de la última pasada buena del archivo (marca vacía si nunca se replicó).
func (p Postgres) Estado(ctx context.Context, tabla string) (Estado, error) {
	var e Estado
	err := p.Pool.QueryRow(ctx, fmt.Sprintf("SELECT marca, registros FROM %s WHERE tabla = $1",
		pgx.Identifier{p.Esquema, "_archivos"}.Sanitize()), tabla).Scan(&e.Marca, &e.Registros)
	if errors.Is(err, pgx.ErrNoRows) {
		return Estado{}, nil
	}
	return e, err
}

// Hashes guardados: recno → hash.
func (p Postgres) Hashes(ctx context.Context, tabla string) (map[uint32]int64, error) {
	rows, err := p.Pool.Query(ctx, fmt.Sprintf("SELECT _recno, _hash FROM %s", p.id(tabla)))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	m := make(map[uint32]int64)
	for rows.Next() {
		var r int32
		var h int64
		if err := rows.Scan(&r, &h); err != nil {
			return nil, err
		}
		m[uint32(r)] = h
	}
	return m, rows.Err()
}

// Aplicar escribe las filas nuevas o cambiadas (COPY a una tabla temporal + upsert).
func (p Postgres) Aplicar(ctx context.Context, tabla string, campos []dbf.Campo, filas []Fila) error {
	if len(filas) == 0 {
		return nil
	}
	tx, err := p.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	tmp := "_tmp_" + tabla
	if _, err := tx.Exec(ctx, fmt.Sprintf("CREATE TEMP TABLE %s (LIKE %s INCLUDING DEFAULTS) ON COMMIT DROP",
		pgx.Identifier{tmp}.Sanitize(), p.id(tabla))); err != nil {
		return err
	}
	nombres := []string{"_recno", "_hash", "_borrado", "_crudo", "_visto_en"}
	for _, c := range campos {
		nombres = append(nombres, c.Nombre)
	}
	ahora := time.Now()
	datos := make([][]any, len(filas))
	for i, f := range filas {
		var crudo any
		if len(f.Crudo) > 0 {
			b, _ := json.Marshal(f.Crudo)
			crudo = b
		}
		datos[i] = append([]any{int32(f.Recno), f.Hash, f.Borrado, crudo, ahora}, f.Valores...)
	}
	if _, err := tx.CopyFrom(ctx, pgx.Identifier{tmp}, nombres, pgx.CopyFromRows(datos)); err != nil {
		return fmt.Errorf("copy %s: %w", tabla, err)
	}
	sets := make([]string, 0, len(nombres)-1)
	cols := make([]string, len(nombres))
	for i, n := range nombres {
		cols[i] = pgx.Identifier{n}.Sanitize()
		if n != "_recno" {
			sets = append(sets, cols[i]+" = EXCLUDED."+cols[i])
		}
	}
	q := fmt.Sprintf("INSERT INTO %s (%s) SELECT %s FROM %s ON CONFLICT (_recno) DO UPDATE SET %s",
		p.id(tabla), strings.Join(cols, ", "), strings.Join(cols, ", "), pgx.Identifier{tmp}.Sanitize(), strings.Join(sets, ", "))
	if _, err := tx.Exec(ctx, q); err != nil {
		return fmt.Errorf("upsert %s: %w", tabla, err)
	}
	return tx.Commit(ctx)
}

// Borrar quita filas por recno (las que dejaron de pasar el filtro).
func (p Postgres) Borrar(ctx context.Context, tabla string, recnos []uint32) error {
	if len(recnos) == 0 {
		return nil
	}
	ids := make([]int32, len(recnos))
	for i, r := range recnos {
		ids[i] = int32(r)
	}
	_, err := p.Pool.Exec(ctx, fmt.Sprintf("DELETE FROM %s WHERE _recno = ANY($1)", p.id(tabla)), ids)
	return err
}

// Recortar quita los recno que ya no existen en el DBF (quedó más corto).
func (p Postgres) Recortar(ctx context.Context, tabla string, registros uint32) error {
	_, err := p.Pool.Exec(ctx, fmt.Sprintf("DELETE FROM %s WHERE _recno > $1", p.id(tabla)), int32(registros))
	return err
}

// Vaciar borra todo (después de un PACK del FoxPro los recno se renumeran).
func (p Postgres) Vaciar(ctx context.Context, tabla string) error {
	_, err := p.Pool.Exec(ctx, fmt.Sprintf("TRUNCATE %s", p.id(tabla)))
	return err
}

// Contar devuelve cuántas filas hay en Postgres y la suma de sus hashes, con el mismo filtro.
func (p Postgres) Contar(ctx context.Context, tabla string, f *Filtro) (int64, *big.Int, error) {
	q := fmt.Sprintf("SELECT count(*), coalesce(sum(_hash::numeric), 0)::text FROM %s", p.id(tabla))
	var args []any
	if f != nil {
		col := pgx.Identifier{f.Campo}.Sanitize()
		q += fmt.Sprintf(" WHERE %s >= $1 OR %s IS NULL", col, col)
		args = append(args, f.Desde)
	}
	var n int64
	var s string
	if err := p.Pool.QueryRow(ctx, q, args...).Scan(&n, &s); err != nil {
		return 0, nil, err
	}
	suma, ok := new(big.Int).SetString(s, 10)
	if !ok {
		return 0, nil, fmt.Errorf("suma de hashes inválida: %q", s)
	}
	return n, suma, nil
}

// GuardarEstado deja la marca y el resultado de la pasada (error vacío = bien).
func (p Postgres) GuardarEstado(ctx context.Context, tabla, recurso, ruta, marca string, registros int64, fallo string) error {
	q := fmt.Sprintf(`INSERT INTO %s (tabla, recurso, ruta, marca, registros, ultima_pasada, ultimo_error)
		VALUES ($1, $2, $3, $4, $5, now(), NULLIF($6, ''))
		ON CONFLICT (tabla) DO UPDATE SET recurso = EXCLUDED.recurso, ruta = EXCLUDED.ruta,
		  marca = CASE WHEN EXCLUDED.ultimo_error IS NULL THEN EXCLUDED.marca ELSE %s.marca END,
		  registros = CASE WHEN EXCLUDED.ultimo_error IS NULL THEN EXCLUDED.registros ELSE %s.registros END,
		  ultima_pasada = now(), ultimo_error = EXCLUDED.ultimo_error,
		  ultima_buena = CASE WHEN EXCLUDED.ultimo_error IS NULL THEN now() ELSE %s.ultima_buena END`,
		pgx.Identifier{p.Esquema, "_archivos"}.Sanitize(), "_archivos", "_archivos", "_archivos")
	_, err := p.Pool.Exec(ctx, q, tabla, recurso, ruta, marca, registros, fallo)
	return err
}

// GuardarConciliacion registra el resultado de la pasada.
func (p Postgres) GuardarConciliacion(ctx context.Context, c Conciliacion) error {
	q := fmt.Sprintf(`INSERT INTO %s (tabla, registros_dbf, incluidos, borrados, enviados, en_pg, suma_dbf, suma_pg, ok, segundos)
		VALUES ($1, $2, $3, $4, $5, $6, $7::numeric, $8::numeric, $9, $10)`,
		pgx.Identifier{p.Esquema, "_conciliacion"}.Sanitize())
	_, err := p.Pool.Exec(ctx, q, c.Tabla, c.RegistrosDBF, c.Incluidos, c.Borrados, c.Enviados, c.EnPG,
		c.SumaDBF.String(), c.SumaPG.String(), c.OK(), c.Segundos)
	return err
}

// Valor convierte un valor del DBF al tipo de la columna (nil = NULL).
func Valor(c dbf.Campo, v dbf.Valor) any {
	if v.Nulo || v.Invalido {
		return nil
	}
	switch tipoPG(c) {
	case "numeric":
		var n pgtype.Numeric
		if err := n.Scan(v.Texto); err != nil {
			return nil
		}
		return n
	case "date":
		return pgtype.Date{Time: v.Fecha, Valid: true}
	case "timestamptz":
		return v.Fecha
	case "boolean":
		return v.Logico
	default:
		return strings.ReplaceAll(v.Texto, "\x00", "") // Postgres no acepta nulos en text
	}
}
