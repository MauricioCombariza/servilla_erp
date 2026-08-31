"""Sistema de roles y permisos por página (RBAC dinámico)

Crea las tablas `roles` y `rol_paginas`, siembra los 6 roles reales del
sistema (formalizando `contabilidad` y `operaciones`, ya usados por varios
routers pero antes bloqueados por el CHECK constraint), y convierte
`usuarios.rol` de string+CHECK a FK contra `roles.nombre`.

Revision ID: 023
Revises: 022
Create Date: 2026-08-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMINISTRADOR_PAGINAS = [
    "clientes", "personal", "ordenes",
    "facturacion_resumen", "facturacion_emitidas", "facturacion_recibidas",
    "facturacion_cxc", "facturacion_cxp",
    "reportes", "labores", "pagos_mensajeros", "facturas_transporte",
    "pagos_ciudades", "gastos", "flujo_caja", "nomina",
    "gestiones", "planillas", "buscar", "direcciones", "pendientes_entrega",
    "devoluciones", "escaneo_carryt", "imile_offload_scan",
]
LOGISTICA_PAGINAS = [
    "clientes", "personal", "ordenes",
    "facturacion_resumen", "facturacion_emitidas", "facturacion_recibidas",
    "facturacion_cxc", "facturacion_cxp",
    "reportes", "gestiones", "planillas", "buscar", "direcciones",
    "pendientes_entrega", "devoluciones", "escaneo_carryt", "imile_offload_scan",
]
MENSAJERO_PAGINAS = ["buscar", "escaneo_carryt", "imile_offload_scan"]
CONTABILIDAD_PAGINAS = [
    "labores", "pagos_mensajeros", "facturas_transporte", "pagos_ciudades",
    "gastos", "flujo_caja", "nomina",
]
OPERACIONES_PAGINAS = ["labores", "pagos_mensajeros", "facturas_transporte", "pagos_ciudades"]
PAQUETES_PAGINAS: list[str] = []

ROL_PAGINAS = {
    "administrador": ADMINISTRADOR_PAGINAS,
    "logistica": LOGISTICA_PAGINAS,
    "mensajero": MENSAJERO_PAGINAS,
    "contabilidad": CONTABILIDAD_PAGINAS,
    "operaciones": OPERACIONES_PAGINAS,
    "paquetes": PAQUETES_PAGINAS,
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE roles (
            nombre          VARCHAR(30) PRIMARY KEY,
            descripcion     VARCHAR(200),
            activo          BOOLEAN NOT NULL DEFAULT TRUE,
            fecha_creacion  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE rol_paginas (
            id        SERIAL PRIMARY KEY,
            rol       VARCHAR(30) NOT NULL REFERENCES roles(nombre) ON UPDATE CASCADE,
            page_key  VARCHAR(50) NOT NULL,
            CONSTRAINT uq_rol_paginas_rol_page UNIQUE (rol, page_key)
        )
    """)
    op.execute("CREATE INDEX ix_rol_paginas_rol ON rol_paginas(rol)")

    op.execute("""
        INSERT INTO roles (nombre, descripcion) VALUES
        ('administrador', 'Acceso total al sistema'),
        ('logistica', 'Operación logística diaria'),
        ('paquetes', 'Rol histórico sin páginas asignadas por defecto'),
        ('mensajero', 'Mensajeros de campo'),
        ('contabilidad', 'Área contable y financiera'),
        ('operaciones', 'Operaciones de labores y pagos')
    """)

    for rol, paginas in ROL_PAGINAS.items():
        if not paginas:
            continue
        valores = ", ".join(f"('{rol}', '{page_key}')" for page_key in paginas)
        op.execute(f"INSERT INTO rol_paginas (rol, page_key) VALUES {valores}")

    op.execute("ALTER TABLE usuarios ALTER COLUMN rol TYPE VARCHAR(30)")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT ck_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios ADD CONSTRAINT fk_usuarios_rol
        FOREIGN KEY (rol) REFERENCES roles(nombre)
        ON UPDATE CASCADE ON DELETE RESTRICT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT fk_usuarios_rol")
    op.execute("""
        ALTER TABLE usuarios ADD CONSTRAINT ck_usuarios_rol
        CHECK (rol IN ('administrador','logistica','paquetes','mensajero'))
    """)
    op.execute("ALTER TABLE usuarios ALTER COLUMN rol TYPE VARCHAR(15)")
    op.execute("DROP TABLE rol_paginas")
    op.execute("DROP TABLE roles")
