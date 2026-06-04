-- ============================================================
-- SERVILLA ERP — SCHEMA PostgreSQL
-- 38 tablas + 5 vistas
-- Migrado y simplificado desde MySQL logistica
-- ============================================================

-- ============================================================
-- TRIGGER: actualiza fecha_modificacion en UPDATE
-- ============================================================

CREATE OR REPLACE FUNCTION update_fecha_modificacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_modificacion = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 1. USUARIOS
-- ============================================================

CREATE TABLE usuarios (
    id                  BIGSERIAL PRIMARY KEY,
    username            VARCHAR(50) UNIQUE NOT NULL,
    password_hash       VARCHAR(255) NOT NULL,
    nombre_completo     VARCHAR(100) NOT NULL,
    email               VARCHAR(100),
    rol                 VARCHAR(15) NOT NULL CHECK (rol IN ('administrador','contabilidad','operaciones','ventas')),
    activo              BOOLEAN DEFAULT TRUE,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ultimo_acceso       TIMESTAMPTZ
);

CREATE INDEX idx_usuarios_username ON usuarios(username);
CREATE INDEX idx_usuarios_rol ON usuarios(rol);

-- ============================================================
-- 2. CLIENTES
-- ============================================================

CREATE TABLE clientes (
    id                  BIGSERIAL PRIMARY KEY,
    nombre_empresa      VARCHAR(150) NOT NULL,
    nit                 VARCHAR(20) UNIQUE NOT NULL,
    contacto_nombre     VARCHAR(100),
    contacto_telefono   VARCHAR(20),
    contacto_email      VARCHAR(100),
    direccion           TEXT,
    ciudad              VARCHAR(50),
    plazo_pago_dias     INT DEFAULT 30,
    activo              BOOLEAN DEFAULT TRUE,
    notas               TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_clientes_nit ON clientes(nit);
CREATE INDEX idx_clientes_activo ON clientes(activo);
CREATE TRIGGER trg_clientes_mod BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 3. CIUDADES  (absorbe ciudad_tipo: añade columna ambito)
-- ============================================================

CREATE TABLE ciudades (
    id              BIGSERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    departamento    VARCHAR(100),
    codigo          VARCHAR(10),
    es_bogota       BOOLEAN DEFAULT FALSE,
    ambito          VARCHAR(8) DEFAULT 'nacional' CHECK (ambito IN ('bogota','nacional')),
    activa          BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_ciudades_nombre ON ciudades(nombre);
CREATE INDEX idx_ciudades_bogota ON ciudades(es_bogota);
CREATE INDEX idx_ciudades_ambito ON ciudades(ambito);

-- ============================================================
-- 4. PERSONAL
-- ============================================================

CREATE TABLE personal (
    id                  BIGSERIAL PRIMARY KEY,
    codigo              CHAR(4) UNIQUE NOT NULL,
    nombre_completo     VARCHAR(150) NOT NULL,
    identificacion      VARCHAR(20) UNIQUE NOT NULL,
    telefono            VARCHAR(20),
    email               VARCHAR(100),
    tipo_personal       VARCHAR(20) NOT NULL CHECK (tipo_personal IN ('mensajero','alistamiento','conductor','courier_externo','transportadora')),
    banco               VARCHAR(100),
    numero_cuenta       VARCHAR(50),
    tipo_cuenta         VARCHAR(10) CHECK (tipo_cuenta IN ('ahorros','corriente')),
    dia_pago            INT DEFAULT 8,
    activo              BOOLEAN DEFAULT TRUE,
    observaciones       TEXT,
    fecha_ingreso       DATE,
    precio_local        DECIMAL(10,0),
    precio_nacional     DECIMAL(10,0),
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_personal_codigo ON personal(codigo);
CREATE INDEX idx_personal_tipo ON personal(tipo_personal);
CREATE INDEX idx_personal_activo ON personal(activo);
CREATE TRIGGER trg_personal_mod BEFORE UPDATE ON personal
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 5. PRECIOS CLIENTE  (simplificado: entrega+devolucion en 1 fila)
-- ============================================================

CREATE TABLE precios_cliente (
    id                          BIGSERIAL PRIMARY KEY,
    cliente_id                  BIGINT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    tipo_servicio               VARCHAR(8) NOT NULL CHECK (tipo_servicio IN ('sobre','paquete')),
    ambito                      VARCHAR(8) NOT NULL CHECK (ambito IN ('bogota','nacional')),
    precio_entrega              DECIMAL(10,2) NOT NULL DEFAULT 0,
    precio_devolucion           DECIMAL(10,2) NOT NULL DEFAULT 0,
    costo_mensajero_entrega     DECIMAL(10,2) DEFAULT 0,
    costo_mensajero_devolucion  DECIMAL(10,2) DEFAULT 0,
    vigencia_desde              DATE NOT NULL,
    vigencia_hasta              DATE,
    activo                      BOOLEAN DEFAULT TRUE,
    notas                       TEXT,
    fecha_creacion              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (cliente_id, tipo_servicio, ambito, vigencia_desde)
);

CREATE INDEX idx_precios_cliente ON precios_cliente(cliente_id, tipo_servicio, ambito);
CREATE INDEX idx_precios_vigencia ON precios_cliente(vigencia_desde);

-- ============================================================
-- 6. PERSONAL CIUDADES (tarifas por ciudad)
-- ============================================================

CREATE TABLE personal_ciudades (
    id                  BIGSERIAL PRIMARY KEY,
    personal_id         BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    ciudad_id           BIGINT NOT NULL REFERENCES ciudades(id) ON DELETE CASCADE,
    tarifa_entrega      DECIMAL(10,2),
    tarifa_devolucion   DECIMAL(10,2),
    vigencia_desde      DATE NOT NULL,
    vigencia_hasta      DATE,
    activo              BOOLEAN DEFAULT TRUE,
    UNIQUE (personal_id, ciudad_id)
);

CREATE INDEX idx_personal_ciudades_ciudad ON personal_ciudades(ciudad_id);

-- ============================================================
-- 7. TARIFAS DE SERVICIOS INTERNOS
-- ============================================================

CREATE TABLE tarifas_servicios (
    id              BIGSERIAL PRIMARY KEY,
    tipo_servicio   VARCHAR(25) NOT NULL CHECK (tipo_servicio IN ('alistamiento_hora','transporte_completo','medio_transporte','pegado_guia')),
    descripcion     VARCHAR(200),
    tarifa          DECIMAL(10,2) NOT NULL,
    vigencia_desde  DATE NOT NULL,
    vigencia_hasta  DATE,
    activo          BOOLEAN DEFAULT TRUE,
    fecha_creacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tarifas_tipo ON tarifas_servicios(tipo_servicio);
CREATE INDEX idx_tarifas_vigencia ON tarifas_servicios(vigencia_desde);

-- ============================================================
-- 8. ÓRDENES
-- ============================================================

CREATE TABLE ordenes (
    id                          BIGSERIAL PRIMARY KEY,
    numero_orden                VARCHAR(50) UNIQUE NOT NULL,
    cliente_id                  BIGINT NOT NULL REFERENCES clientes(id),
    ciudad_destino_id           BIGINT REFERENCES ciudades(id) ON DELETE SET NULL,
    fecha_recepcion             DATE NOT NULL,
    tipo_servicio               VARCHAR(8) NOT NULL CHECK (tipo_servicio IN ('sobre','paquete')),

    -- Contadores de estado (flujo: recibido → cajoneras → lleva → finalizado)
    cantidad_total              INT NOT NULL DEFAULT 0,
    cantidad_recibido           INT NOT NULL DEFAULT 0,
    cantidad_en_cajoneras       INT NOT NULL DEFAULT 0,
    cantidad_en_lleva           INT NOT NULL DEFAULT 0,
    cantidad_entregados         INT NOT NULL DEFAULT 0,
    cantidad_devolucion         INT NOT NULL DEFAULT 0,

    -- Valores financieros
    precio_unitario             DECIMAL(10,2),
    valor_total                 DECIMAL(12,2) DEFAULT 0,
    costo_mensajero_total       DECIMAL(12,2) DEFAULT 0,
    costo_alistamiento_total    DECIMAL(12,2) DEFAULT 0,
    costo_pegado_total          DECIMAL(12,2) DEFAULT 0,
    costo_transporte_total      DECIMAL(12,2) DEFAULT 0,
    costo_flete_total           DECIMAL(12,2) DEFAULT 0,

    -- Columnas calculadas (PostgreSQL 12+ GENERATED ALWAYS ... STORED)
    costo_total     DECIMAL(12,2) GENERATED ALWAYS AS (
        COALESCE(costo_mensajero_total,0) + COALESCE(costo_alistamiento_total,0) +
        COALESCE(costo_pegado_total,0) + COALESCE(costo_transporte_total,0) +
        COALESCE(costo_flete_total,0)
    ) STORED,
    utilidad_total  DECIMAL(12,2) GENERATED ALWAYS AS (
        COALESCE(valor_total,0) - (
            COALESCE(costo_mensajero_total,0) + COALESCE(costo_alistamiento_total,0) +
            COALESCE(costo_pegado_total,0) + COALESCE(costo_transporte_total,0) +
            COALESCE(costo_flete_total,0)
        )
    ) STORED,

    estado                      VARCHAR(10) DEFAULT 'activa' CHECK (estado IN ('activa','finalizada','anulada')),
    facturado                   BOOLEAN DEFAULT FALSE,
    fecha_finalizacion          DATE,
    observaciones               TEXT,
    fecha_creacion              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ordenes_cliente ON ordenes(cliente_id);
CREATE INDEX idx_ordenes_fecha ON ordenes(fecha_recepcion);
CREATE INDEX idx_ordenes_estado ON ordenes(estado);
CREATE INDEX idx_ordenes_facturado ON ordenes(facturado);
CREATE INDEX idx_ordenes_numero ON ordenes(numero_orden);
CREATE INDEX idx_ordenes_ciudad ON ordenes(ciudad_destino_id);
CREATE TRIGGER trg_ordenes_mod BEFORE UPDATE ON ordenes
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 9. ORDEN PERSONAL (asignaciones de órdenes a mensajeros)
-- ============================================================

CREATE TABLE orden_personal (
    id                  BIGSERIAL PRIMARY KEY,
    orden_id            BIGINT NOT NULL REFERENCES ordenes(id) ON DELETE CASCADE,
    personal_id         BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    cantidad_asignada   INT NOT NULL,
    cantidad_entregada  INT DEFAULT 0,
    cantidad_devolucion INT DEFAULT 0,
    tarifa_unitaria     DECIMAL(10,2),
    total_pagar         DECIMAL(10,2) GENERATED ALWAYS AS (
        (COALESCE(cantidad_entregada,0) + COALESCE(cantidad_devolucion,0)) * COALESCE(tarifa_unitaria,0)
    ) STORED,
    fecha_asignacion    DATE,
    observaciones       TEXT
);

CREATE INDEX idx_orden_personal_orden ON orden_personal(orden_id);
CREATE INDEX idx_orden_personal_personal ON orden_personal(personal_id);

-- ============================================================
-- 10. SERIALES GESTION  (reemplaza gestiones_mensajero — desde enero)
-- ============================================================

CREATE TABLE seriales_gestion (
    id                  BIGSERIAL PRIMARY KEY,
    serial              VARCHAR(50) NOT NULL UNIQUE,
    f_emi               DATE,               -- fecha emisión del serial (de bases_web.histo)
    f_esc               DATE NOT NULL,      -- fecha escáner → determina el período de costo
    planilla            VARCHAR(50) NOT NULL,
    cod_men             VARCHAR(4) NOT NULL,
    mensajero_id        BIGINT REFERENCES personal(id) ON DELETE SET NULL,
    cliente_id          BIGINT REFERENCES clientes(id) ON DELETE SET NULL,
    tipo_gestion        VARCHAR(10) NOT NULL CHECK (tipo_gestion IN ('Entrega','Devolucion')),
    tipo_envio          VARCHAR(8) DEFAULT 'sobre' CHECK (tipo_envio IN ('sobre','paquete')),
    ambito              VARCHAR(8) DEFAULT 'bogota' CHECK (ambito IN ('bogota','nacional')),
    precio_cliente      DECIMAL(10,2) NOT NULL DEFAULT 0,
    precio_mensajero    DECIMAL(10,2) NOT NULL DEFAULT 0,
    estado              VARCHAR(12) NOT NULL DEFAULT 'pendiente'
                        CHECK (estado IN ('pendiente','liquidado','facturado','anulado','en_revision')),
    liquidacion_id      BIGINT,
    factura_id          BIGINT,
    origen              VARCHAR(8) NOT NULL DEFAULT 'scanner' CHECK (origen IN ('scanner','imile','manual')),
    editado_manualmente BOOLEAN NOT NULL DEFAULT FALSE,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sg_planilla ON seriales_gestion(planilla);
CREATE INDEX idx_sg_cod_men ON seriales_gestion(cod_men);
CREATE INDEX idx_sg_f_esc ON seriales_gestion(f_esc);
CREATE INDEX idx_sg_f_emi ON seriales_gestion(f_emi);
CREATE INDEX idx_sg_estado ON seriales_gestion(estado);
CREATE INDEX idx_sg_mensajero ON seriales_gestion(mensajero_id);
CREATE INDEX idx_sg_cliente ON seriales_gestion(cliente_id);
CREATE INDEX idx_sg_liquidacion ON seriales_gestion(liquidacion_id);
CREATE INDEX idx_sg_factura ON seriales_gestion(factura_id);
CREATE TRIGGER trg_sg_mod BEFORE UPDATE ON seriales_gestion
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 11. MAPEO CLIENTES (nombre CSV → cliente en BD)
-- ============================================================

CREATE TABLE mapeo_clientes (
    id          BIGSERIAL PRIMARY KEY,
    nombre_csv  VARCHAR(200) NOT NULL UNIQUE,
    nombre_bd   VARCHAR(200),
    cliente_id  BIGINT REFERENCES clientes(id) ON DELETE SET NULL
);

-- ============================================================
-- 14. MAPEO DA (distribuidoras de área → mensajero)
-- ============================================================

CREATE TABLE mapeo_da (
    nombre_da       VARCHAR(200) PRIMARY KEY,
    cod_mensajero   VARCHAR(20) NOT NULL
);

-- ============================================================
-- 15. REGISTRO DE HORAS (alistamiento)
-- ============================================================

CREATE TABLE registro_horas (
    id                  BIGSERIAL PRIMARY KEY,
    personal_id         BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    orden_id            BIGINT REFERENCES ordenes(id) ON DELETE SET NULL,
    fecha               DATE NOT NULL,
    horas_trabajadas    DECIMAL(5,2) NOT NULL,
    tarifa_hora         DECIMAL(10,2) NOT NULL,
    total               DECIMAL(10,2) GENERATED ALWAYS AS (horas_trabajadas * tarifa_hora) STORED,
    tipo_trabajo        VARCHAR(25) NOT NULL CHECK (tipo_trabajo IN ('alistamiento_sobres','alistamiento_paquetes')),
    aprobado            BOOLEAN DEFAULT FALSE,
    aprobado_por        BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_aprobacion    TIMESTAMPTZ,
    liquidado           BOOLEAN DEFAULT FALSE,
    liquidacion_id      BIGINT,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reg_horas_personal ON registro_horas(personal_id);
CREATE INDEX idx_reg_horas_fecha ON registro_horas(fecha);
CREATE INDEX idx_reg_horas_aprobado ON registro_horas(aprobado);
CREATE INDEX idx_reg_horas_liquidado ON registro_horas(liquidado);

-- ============================================================
-- 16. REGISTRO DE LABORES (pegado guía, transporte)
-- ============================================================

CREATE TABLE registro_labores (
    id                  BIGSERIAL PRIMARY KEY,
    personal_id         BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    orden_id            BIGINT REFERENCES ordenes(id) ON DELETE SET NULL,
    fecha               DATE NOT NULL,
    tipo_labor          VARCHAR(25) NOT NULL CHECK (tipo_labor IN ('pegado_guia','transporte_completo','medio_transporte')),
    cantidad            INT NOT NULL,
    tarifa_unitaria     DECIMAL(10,2) NOT NULL,
    total               DECIMAL(10,2) GENERATED ALWAYS AS (cantidad * tarifa_unitaria) STORED,
    aprobado            BOOLEAN DEFAULT FALSE,
    aprobado_por        BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_aprobacion    TIMESTAMPTZ,
    liquidado           BOOLEAN DEFAULT FALSE,
    liquidacion_id      BIGINT,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reg_labores_personal ON registro_labores(personal_id);
CREATE INDEX idx_reg_labores_fecha ON registro_labores(fecha);
CREATE INDEX idx_reg_labores_tipo ON registro_labores(tipo_labor);
CREATE INDEX idx_reg_labores_aprobado ON registro_labores(aprobado);
CREATE INDEX idx_reg_labores_liquidado ON registro_labores(liquidado);

-- ============================================================
-- 17. SUBSIDIO DE TRANSPORTE
-- ============================================================

CREATE TABLE subsidio_transporte (
    id                  BIGSERIAL PRIMARY KEY,
    personal_id         BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    fecha               DATE NOT NULL,
    horas_totales       DECIMAL(5,2) NOT NULL DEFAULT 0,
    tipo_subsidio       VARCHAR(25) NOT NULL CHECK (tipo_subsidio IN ('transporte_completo','medio_transporte')),
    tarifa              DECIMAL(10,2) NOT NULL,
    total               DECIMAL(10,2) GENERATED ALWAYS AS (tarifa) STORED,
    origen              VARCHAR(12) DEFAULT 'automatico' CHECK (origen IN ('automatico','manual','recalculado')),
    aprobado            BOOLEAN DEFAULT FALSE,
    aprobado_por        BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_aprobacion    TIMESTAMPTZ,
    liquidado           BOOLEAN DEFAULT FALSE,
    liquidacion_id      BIGINT,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (personal_id, fecha)
);

CREATE INDEX idx_subsidio_fecha ON subsidio_transporte(fecha);
CREATE INDEX idx_subsidio_personal ON subsidio_transporte(personal_id);
CREATE INDEX idx_subsidio_aprobado ON subsidio_transporte(aprobado);
CREATE INDEX idx_subsidio_liquidado ON subsidio_transporte(liquidado);
CREATE TRIGGER trg_subsidio_mod BEFORE UPDATE ON subsidio_transporte
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 18. LIQUIDACIONES (pago a personal)
-- ============================================================

CREATE TABLE liquidaciones (
    id                      BIGSERIAL PRIMARY KEY,
    numero_liquidacion      VARCHAR(50) UNIQUE NOT NULL,
    personal_id             BIGINT NOT NULL REFERENCES personal(id) ON DELETE CASCADE,
    periodo_mes             INT NOT NULL,
    periodo_anio            INT NOT NULL,
    fecha_generacion        DATE NOT NULL,
    fecha_pago_programada   DATE NOT NULL,
    total_entregas          DECIMAL(12,2) DEFAULT 0,
    cantidad_entregas       INT DEFAULT 0,
    total_horas             DECIMAL(12,2) DEFAULT 0,
    cantidad_horas          DECIMAL(5,2) DEFAULT 0,
    total_labores           DECIMAL(12,2) DEFAULT 0,
    cantidad_labores        INT DEFAULT 0,
    bonificaciones          DECIMAL(12,2) DEFAULT 0,
    descuentos              DECIMAL(12,2) DEFAULT 0,
    total_a_pagar           DECIMAL(12,2) NOT NULL,
    estado                  VARCHAR(10) DEFAULT 'generada' CHECK (estado IN ('generada','aprobada','pagada')),
    fecha_pago_real         DATE,
    metodo_pago             VARCHAR(12) DEFAULT 'transferencia' CHECK (metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')),
    referencia_pago         VARCHAR(100),
    observaciones           TEXT,
    generado_por            BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    aprobado_por            BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_creacion          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_liquidaciones_personal ON liquidaciones(personal_id);
CREATE INDEX idx_liquidaciones_periodo ON liquidaciones(periodo_anio, periodo_mes);
CREATE INDEX idx_liquidaciones_fecha_pago ON liquidaciones(fecha_pago_programada);
CREATE INDEX idx_liquidaciones_estado ON liquidaciones(estado);

-- ============================================================
-- 19. FACTURAS EMITIDAS (a clientes)
-- ============================================================

CREATE TABLE facturas_emitidas (
    id                  BIGSERIAL PRIMARY KEY,
    numero_factura      VARCHAR(50) UNIQUE NOT NULL,
    cliente_id          BIGINT NOT NULL REFERENCES clientes(id),
    fecha_emision       DATE NOT NULL,
    fecha_vencimiento   DATE NOT NULL,
    periodo_mes         INT NOT NULL,
    periodo_anio        INT NOT NULL,
    cantidad_items      INT DEFAULT 0,
    subtotal            DECIMAL(12,2) NOT NULL,
    descuento           DECIMAL(12,2) DEFAULT 0,
    total               DECIMAL(12,2) NOT NULL,
    saldo_pendiente     DECIMAL(12,2) NOT NULL,
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','parcial','pagada','vencida','anulada')),
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fact_emit_numero ON facturas_emitidas(numero_factura);
CREATE INDEX idx_fact_emit_cliente ON facturas_emitidas(cliente_id);
CREATE INDEX idx_fact_emit_fecha ON facturas_emitidas(fecha_emision);
CREATE INDEX idx_fact_emit_vence ON facturas_emitidas(fecha_vencimiento);
CREATE INDEX idx_fact_emit_estado ON facturas_emitidas(estado);
CREATE INDEX idx_fact_emit_periodo ON facturas_emitidas(periodo_anio, periodo_mes);
CREATE TRIGGER trg_fact_emit_mod BEFORE UPDATE ON facturas_emitidas
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 20. DETALLE FACTURAS EMITIDAS
-- ============================================================

CREATE TABLE detalle_facturas_emitidas (
    id                  BIGSERIAL PRIMARY KEY,
    factura_id          BIGINT NOT NULL REFERENCES facturas_emitidas(id) ON DELETE CASCADE,
    orden_id            BIGINT REFERENCES ordenes(id) ON DELETE SET NULL,
    descripcion         TEXT NOT NULL,
    cantidad            INT NOT NULL DEFAULT 1,
    precio_unitario     DECIMAL(10,2) NOT NULL,
    subtotal            DECIMAL(10,2) NOT NULL
);

CREATE INDEX idx_det_emit_factura ON detalle_facturas_emitidas(factura_id);
CREATE INDEX idx_det_emit_orden ON detalle_facturas_emitidas(orden_id);

-- ============================================================
-- 21. FACTURAS RECIBIDAS (de couriers/transportadoras)
-- ============================================================

CREATE TABLE facturas_recibidas (
    id                  BIGSERIAL PRIMARY KEY,
    numero_factura      VARCHAR(50) NOT NULL,
    personal_id         BIGINT NOT NULL REFERENCES personal(id),
    tipo                VARCHAR(15) NOT NULL CHECK (tipo IN ('courier','transportadora','materiales','otros')),
    fecha_recepcion     DATE NOT NULL,
    fecha_vencimiento   DATE NOT NULL,
    periodo_mes         INT,
    periodo_anio        INT,
    cantidad_items      INT DEFAULT 0,
    subtotal            DECIMAL(12,2) NOT NULL,
    descuento           DECIMAL(12,2) DEFAULT 0,
    total               DECIMAL(12,2) NOT NULL,
    saldo_pendiente     DECIMAL(12,2) NOT NULL,
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','parcial','pagada','anulada')),
    observaciones       TEXT,
    archivo_adjunto     VARCHAR(255),
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    fecha_modificacion  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fact_rec_numero ON facturas_recibidas(numero_factura, personal_id);
CREATE INDEX idx_fact_rec_personal ON facturas_recibidas(personal_id);
CREATE INDEX idx_fact_rec_fecha ON facturas_recibidas(fecha_recepcion);
CREATE INDEX idx_fact_rec_vence ON facturas_recibidas(fecha_vencimiento);
CREATE INDEX idx_fact_rec_estado ON facturas_recibidas(estado);
CREATE INDEX idx_fact_rec_tipo ON facturas_recibidas(tipo);
CREATE TRIGGER trg_fact_rec_mod BEFORE UPDATE ON facturas_recibidas
    FOR EACH ROW EXECUTE FUNCTION update_fecha_modificacion();

-- ============================================================
-- 22. DETALLE FACTURAS RECIBIDAS
-- ============================================================

CREATE TABLE detalle_facturas_recibidas (
    id                  BIGSERIAL PRIMARY KEY,
    factura_id          BIGINT NOT NULL REFERENCES facturas_recibidas(id) ON DELETE CASCADE,
    descripcion         TEXT NOT NULL,
    cantidad            INT NOT NULL DEFAULT 1,
    precio_unitario     DECIMAL(10,2) NOT NULL,
    subtotal            DECIMAL(10,2) NOT NULL
);

CREATE INDEX idx_det_rec_factura ON detalle_facturas_recibidas(factura_id);

-- ============================================================
-- 23. FACTURAS TRANSPORTE (couriers externos — ciudades)
-- ============================================================

CREATE TABLE facturas_transporte (
    id                  BIGSERIAL PRIMARY KEY,
    numero_factura      VARCHAR(100) NOT NULL,
    fecha_factura       DATE NOT NULL,
    courrier_id         BIGINT NOT NULL REFERENCES personal(id),
    monto_total         DECIMAL(15,2) NOT NULL,
    total_sobres        INT DEFAULT 0,
    observaciones       TEXT,
    fecha_vencimiento   DATE,
    monto_pagado        DECIMAL(15,2) DEFAULT 0,
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','pagada','anulada')),
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (numero_factura, courrier_id)
);

CREATE INDEX idx_fact_transp_courrier ON facturas_transporte(courrier_id);
CREATE INDEX idx_fact_transp_fecha ON facturas_transporte(fecha_factura);
CREATE INDEX idx_fact_transp_estado ON facturas_transporte(estado);

-- ============================================================
-- 24. DETALLE FACTURAS TRANSPORTE
-- ============================================================

CREATE TABLE detalle_facturas_transporte (
    id                  BIGSERIAL PRIMARY KEY,
    factura_id          BIGINT NOT NULL REFERENCES facturas_transporte(id) ON DELETE CASCADE,
    orden_id            BIGINT REFERENCES ordenes(id) ON DELETE SET NULL,
    cantidad_sobres     INT DEFAULT 0,
    costo_asignado      DECIMAL(12,2) DEFAULT 0
);

CREATE INDEX idx_det_transp_factura ON detalle_facturas_transporte(factura_id);
CREATE INDEX idx_det_transp_orden ON detalle_facturas_transporte(orden_id);

-- ============================================================
-- 25. PAGOS RECIBIDOS (de clientes)
-- ============================================================

CREATE TABLE pagos_recibidos (
    id                      BIGSERIAL PRIMARY KEY,
    factura_id              BIGINT NOT NULL REFERENCES facturas_emitidas(id) ON DELETE CASCADE,
    fecha_pago              DATE NOT NULL,
    monto                   DECIMAL(12,2) NOT NULL,
    metodo_pago             VARCHAR(12) NOT NULL CHECK (metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')),
    referencia              VARCHAR(100),
    observaciones           TEXT,
    usuario_registro_id     BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_creacion          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pagos_rec_factura ON pagos_recibidos(factura_id);
CREATE INDEX idx_pagos_rec_fecha ON pagos_recibidos(fecha_pago);

-- ============================================================
-- 26. PAGOS REALIZADOS (a personal/couriers)
-- ============================================================

CREATE TABLE pagos_realizados (
    id                      BIGSERIAL PRIMARY KEY,
    factura_id              BIGINT REFERENCES facturas_recibidas(id) ON DELETE CASCADE,
    liquidacion_id          BIGINT REFERENCES liquidaciones(id) ON DELETE CASCADE,
    fecha_pago              DATE NOT NULL,
    monto                   DECIMAL(12,2) NOT NULL,
    metodo_pago             VARCHAR(12) NOT NULL CHECK (metodo_pago IN ('efectivo','transferencia','cheque','tarjeta','otros')),
    referencia              VARCHAR(100),
    observaciones           TEXT,
    usuario_registro_id     BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    fecha_creacion          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pagos_real_factura ON pagos_realizados(factura_id);
CREATE INDEX idx_pagos_real_liquidacion ON pagos_realizados(liquidacion_id);
CREATE INDEX idx_pagos_real_fecha ON pagos_realizados(fecha_pago);

-- ============================================================
-- 27. COSTOS ADICIONALES
-- ============================================================

CREATE TABLE costos_adicionales (
    id                  BIGSERIAL PRIMARY KEY,
    tipo                VARCHAR(10) NOT NULL CHECK (tipo IN ('flete','materiales','otros')),
    descripcion         TEXT NOT NULL,
    ciudad_id           BIGINT REFERENCES ciudades(id) ON DELETE SET NULL,
    fecha               DATE NOT NULL,
    monto               DECIMAL(10,2) NOT NULL,
    proveedor           VARCHAR(150),
    factura_referencia  VARCHAR(50),
    orden_id            BIGINT REFERENCES ordenes(id) ON DELETE SET NULL,
    pagado              BOOLEAN DEFAULT FALSE,
    fecha_pago          DATE,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_costos_tipo ON costos_adicionales(tipo);
CREATE INDEX idx_costos_fecha ON costos_adicionales(fecha);
CREATE INDEX idx_costos_pagado ON costos_adicionales(pagado);

-- ============================================================
-- 28. GASTOS ADMINISTRATIVOS
-- ============================================================

CREATE TABLE gastos_administrativos (
    id                  BIGSERIAL PRIMARY KEY,
    fecha               DATE NOT NULL,
    categoria           VARCHAR(50) NOT NULL,
    descripcion         VARCHAR(255) NOT NULL,
    monto               DECIMAL(15,2) NOT NULL,
    proveedor           VARCHAR(150),
    numero_factura      VARCHAR(50),
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','pagado')),
    fecha_pago          DATE,
    observaciones       TEXT,
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_gastos_admin_fecha ON gastos_administrativos(fecha);
CREATE INDEX idx_gastos_admin_categoria ON gastos_administrativos(categoria);
CREATE INDEX idx_gastos_admin_estado ON gastos_administrativos(estado);

-- ============================================================
-- 29. RESERVAS DE DINERO (flujo de caja)
-- ============================================================

CREATE TABLE reservas_dinero (
    id                  BIGSERIAL PRIMARY KEY,
    fecha_creacion_reg  DATE NOT NULL,
    fecha_programada    DATE,
    categoria           VARCHAR(50) NOT NULL,
    descripcion         VARCHAR(255) NOT NULL,
    monto               DECIMAL(15,2) NOT NULL,
    estado              VARCHAR(10) DEFAULT 'activa' CHECK (estado IN ('activa','liberada','ejecutada')),
    fecha_liberacion    DATE,
    observaciones       TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_reservas_estado ON reservas_dinero(estado);
CREATE INDEX idx_reservas_fecha ON reservas_dinero(fecha_programada);

-- ============================================================
-- 30. GASTOS FIJOS MENSUALES
-- ============================================================

CREATE TABLE gastos_fijos_mensuales (
    id              BIGSERIAL PRIMARY KEY,
    categoria       VARCHAR(50) NOT NULL,
    descripcion     VARCHAR(255) NOT NULL,
    monto           DECIMAL(15,2) NOT NULL,
    dia_pago        INT DEFAULT 1,
    activo          BOOLEAN DEFAULT TRUE,
    observaciones   TEXT,
    created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 31. PAGOS GASTOS FIJOS
-- ============================================================

CREATE TABLE pagos_gastos_fijos (
    id                  BIGSERIAL PRIMARY KEY,
    gasto_fijo_id       BIGINT NOT NULL REFERENCES gastos_fijos_mensuales(id),
    mes                 INT NOT NULL,
    anio                INT NOT NULL,
    monto_pagado        DECIMAL(15,2) NOT NULL,
    fecha_pago          DATE NOT NULL,
    observaciones       TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (gasto_fijo_id, mes, anio)
);

-- ============================================================
-- 32. NÓMINA EMPLEADOS
-- ============================================================

CREATE TABLE nomina_empleados (
    id                          BIGSERIAL PRIMARY KEY,
    nombre_completo             VARCHAR(150) NOT NULL,
    identificacion              VARCHAR(20) UNIQUE,
    cargo                       VARCHAR(100),
    salario_mensual             DECIMAL(15,2) NOT NULL DEFAULT 0,
    tiene_auxilio_transporte    BOOLEAN DEFAULT FALSE,
    auxilio_no_salarial         DECIMAL(15,2) DEFAULT 0,
    fecha_ingreso               DATE,
    activo                      BOOLEAN DEFAULT TRUE,
    fecha_creacion              TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 33. NÓMINA PROVISIONES
-- ============================================================

CREATE TABLE nomina_provisiones (
    id                  BIGSERIAL PRIMARY KEY,
    empleado_id         BIGINT NOT NULL REFERENCES nomina_empleados(id),
    periodo_mes         INT NOT NULL,
    periodo_anio        INT NOT NULL,
    salario_base        DECIMAL(15,2),
    auxilio_transporte  DECIMAL(15,2),
    auxilio_no_salarial DECIMAL(15,2),
    arl                 DECIMAL(15,2),
    eps                 DECIMAL(15,2),
    afp                 DECIMAL(15,2),
    caja_compensacion   DECIMAL(15,2),
    prima               DECIMAL(15,2),
    cesantias           DECIMAL(15,2),
    int_cesantias       DECIMAL(15,2),
    vacaciones          DECIMAL(15,2),
    fecha_creacion      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (empleado_id, periodo_mes, periodo_anio)
);

-- ============================================================
-- 34. NÓMINA PARÁMETROS
-- ============================================================

CREATE TABLE nomina_parametros (
    id              BIGSERIAL PRIMARY KEY,
    parametro       VARCHAR(100) NOT NULL,
    valor           DECIMAL(15,4) NOT NULL,
    descripcion     VARCHAR(255),
    vigencia_desde  DATE NOT NULL,
    activo          BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_nomina_params_activo ON nomina_parametros(activo);

-- ============================================================
-- 35. PAGOS OPERATIVOS MENSUALES
-- ============================================================

CREATE TABLE pagos_operativos_mensuales (
    id                  BIGSERIAL PRIMARY KEY,
    tipo                VARCHAR(15) NOT NULL CHECK (tipo IN ('mensajeros','alistamiento')),
    periodo_mes         INT NOT NULL,
    periodo_anio        INT NOT NULL,
    monto_total         DECIMAL(15,2) NOT NULL,
    fecha_vencimiento   DATE NOT NULL,
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','pagado')),
    fecha_pago          DATE,
    observaciones       TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tipo, periodo_mes, periodo_anio)
);

-- ============================================================
-- 36. PREFACTURAS COURIER (facturación por ciudades)
-- ============================================================

CREATE TABLE prefacturas_courier (
    id                  BIGSERIAL PRIMARY KEY,
    cod_mensajero       VARCHAR(4) NOT NULL,
    fecha_generacion    DATE NOT NULL,
    periodo_desde       DATE,
    periodo_hasta       DATE,
    cantidad_planillas  INT DEFAULT 0,
    cantidad_local      INT DEFAULT 0,
    cantidad_nacional   INT DEFAULT 0,
    valor_local         DECIMAL(15,2) DEFAULT 0,
    valor_nacional      DECIMAL(15,2) DEFAULT 0,
    valor_total         DECIMAL(15,2) DEFAULT 0,
    estado              VARCHAR(10) DEFAULT 'borrador' CHECK (estado IN ('borrador','aprobada','facturada')),
    notas               TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_prefact_cod_men ON prefacturas_courier(cod_mensajero);
CREATE INDEX idx_prefact_estado ON prefacturas_courier(estado);

-- ============================================================
-- 37. PREFACTURA PLANILLAS
-- ============================================================

CREATE TABLE prefactura_planillas (
    id                  BIGSERIAL PRIMARY KEY,
    prefactura_id       BIGINT NOT NULL REFERENCES prefacturas_courier(id) ON DELETE CASCADE,
    planilla            VARCHAR(50) NOT NULL,
    fecha_escaner       DATE,
    cantidad_local      INT DEFAULT 0,
    cantidad_nacional   INT DEFAULT 0,
    precio_local        DECIMAL(10,2) DEFAULT 0,
    precio_nac          DECIMAL(10,2) DEFAULT 0,
    valor_local         DECIMAL(12,2) DEFAULT 0,
    valor_nac           DECIMAL(12,2) DEFAULT 0,
    valor_total         DECIMAL(12,2) DEFAULT 0
);

CREATE INDEX idx_prefact_planillas_id ON prefactura_planillas(prefactura_id);

-- ============================================================
-- 38. FACTURAS COURIER CXP (cuentas por pagar couriers)
-- ============================================================

CREATE TABLE facturas_courier_cxp (
    id                  BIGSERIAL PRIMARY KEY,
    prefactura_id       BIGINT NOT NULL REFERENCES prefacturas_courier(id),
    cod_mensajero       VARCHAR(4) NOT NULL,
    numero_factura      VARCHAR(100) NOT NULL,
    fecha_emision       DATE,
    fecha_vencimiento   DATE NOT NULL,
    valor_total         DECIMAL(15,2) NOT NULL,
    estado              VARCHAR(10) DEFAULT 'pendiente' CHECK (estado IN ('pendiente','pagada','vencida')),
    notas               TEXT,
    fecha_pago          DATE,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cxp_estado ON facturas_courier_cxp(estado);
CREATE INDEX idx_cxp_vencimiento ON facturas_courier_cxp(fecha_vencimiento);

-- ============================================================
-- 39. AUDITORÍA
-- ============================================================

CREATE TABLE auditoria (
    id                  BIGSERIAL PRIMARY KEY,
    usuario_id          BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    tabla               VARCHAR(50) NOT NULL,
    registro_id         BIGINT,
    accion              VARCHAR(6) NOT NULL CHECK (accion IN ('INSERT','UPDATE','DELETE')),
    datos_anteriores    JSONB,
    datos_nuevos        JSONB,
    fecha_accion        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    ip_address          VARCHAR(45)
);

CREATE INDEX idx_auditoria_tabla ON auditoria(tabla, registro_id);
CREATE INDEX idx_auditoria_usuario ON auditoria(usuario_id);
CREATE INDEX idx_auditoria_fecha ON auditoria(fecha_accion);

-- ============================================================
-- VISTAS
-- ============================================================

CREATE VIEW vista_estado_ordenes AS
SELECT
    o.id, o.numero_orden,
    c.nombre_empresa AS cliente,
    ci.nombre AS ciudad_destino,
    o.tipo_servicio, o.fecha_recepcion,
    o.cantidad_total, o.cantidad_recibido, o.cantidad_en_cajoneras,
    o.cantidad_en_lleva, o.cantidad_entregados, o.cantidad_devolucion,
    (o.cantidad_entregados + o.cantidad_devolucion) AS finalizados,
    CASE WHEN o.cantidad_total > 0
        THEN ROUND((o.cantidad_entregados + o.cantidad_devolucion)::NUMERIC / o.cantidad_total * 100, 2)
        ELSE 0 END AS porcentaje_completado,
    o.valor_total, o.costo_total, o.utilidad_total,
    CASE WHEN o.valor_total > 0
        THEN ROUND(o.utilidad_total / o.valor_total * 100, 2)
        ELSE 0 END AS margen_porcentaje,
    o.estado, o.facturado
FROM ordenes o
JOIN clientes c ON o.cliente_id = c.id
LEFT JOIN ciudades ci ON o.ciudad_destino_id = ci.id;

CREATE VIEW vista_rentabilidad_cliente AS
SELECT
    c.id, c.nombre_empresa,
    COUNT(DISTINCT o.id)        AS total_ordenes,
    SUM(o.cantidad_total)       AS total_items,
    SUM(o.cantidad_entregados)  AS total_entregados,
    SUM(o.cantidad_devolucion)  AS total_devoluciones,
    SUM(o.valor_total)          AS ingresos_totales,
    SUM(o.costo_total)          AS costos_totales,
    SUM(o.utilidad_total)       AS utilidad_total,
    CASE WHEN SUM(o.valor_total) > 0
        THEN ROUND(SUM(o.utilidad_total) / SUM(o.valor_total) * 100, 2)
        ELSE 0 END AS margen_porcentaje
FROM clientes c
LEFT JOIN ordenes o ON c.id = o.cliente_id AND o.estado = 'finalizada'
GROUP BY c.id, c.nombre_empresa;

CREATE VIEW vista_cuentas_por_cobrar AS
SELECT
    fe.id, fe.numero_factura,
    c.nombre_empresa AS cliente,
    fe.fecha_emision, fe.fecha_vencimiento,
    fe.total, fe.saldo_pendiente, fe.estado,
    (CURRENT_DATE - fe.fecha_vencimiento)           AS dias_vencidos,
    CASE
        WHEN (CURRENT_DATE - fe.fecha_vencimiento) > 0      THEN 'VENCIDA'
        WHEN (fe.fecha_vencimiento - CURRENT_DATE) <= 7     THEN 'POR VENCER'
        ELSE 'VIGENTE'
    END AS clasificacion
FROM facturas_emitidas fe
JOIN clientes c ON fe.cliente_id = c.id
WHERE fe.estado IN ('pendiente','parcial','vencida')
ORDER BY fe.fecha_vencimiento;

CREATE VIEW vista_cuentas_por_pagar AS
SELECT 'factura'::TEXT AS tipo, fr.id, fr.numero_factura AS referencia,
    p.codigo, p.nombre_completo AS acreedor,
    fr.fecha_vencimiento, fr.saldo_pendiente AS monto, fr.estado,
    (fr.fecha_vencimiento - CURRENT_DATE)               AS dias_hasta_vencimiento,
    CASE
        WHEN (CURRENT_DATE - fr.fecha_vencimiento) > 0     THEN 'VENCIDA'
        WHEN (fr.fecha_vencimiento - CURRENT_DATE) <= 7    THEN 'POR VENCER'
        ELSE 'VIGENTE'
    END AS clasificacion
FROM facturas_recibidas fr
JOIN personal p ON fr.personal_id = p.id
WHERE fr.estado IN ('pendiente','parcial')

UNION ALL

SELECT 'liquidacion'::TEXT AS tipo, l.id, l.numero_liquidacion AS referencia,
    p.codigo, p.nombre_completo AS acreedor,
    l.fecha_pago_programada AS fecha_vencimiento, l.total_a_pagar AS monto, l.estado,
    (l.fecha_pago_programada - CURRENT_DATE)            AS dias_hasta_vencimiento,
    CASE
        WHEN (CURRENT_DATE - l.fecha_pago_programada) > 0  THEN 'VENCIDA'
        WHEN (l.fecha_pago_programada - CURRENT_DATE) <= 7 THEN 'POR VENCER'
        ELSE 'VIGENTE'
    END AS clasificacion
FROM liquidaciones l
JOIN personal p ON l.personal_id = p.id
WHERE l.estado IN ('generada','aprobada')

ORDER BY fecha_vencimiento;

CREATE VIEW vista_flujo_caja_60dias AS
SELECT fecha, tipo, descripcion, monto, categoria, dias_hasta_fecha,
    CASE
        WHEN dias_hasta_fecha < 0   THEN 'VENCIDO'
        WHEN dias_hasta_fecha <= 7  THEN 'ESTA SEMANA'
        WHEN dias_hasta_fecha <= 30 THEN 'ESTE MES'
        ELSE 'PROXIMO MES'
    END AS periodo
FROM (
    SELECT fe.fecha_vencimiento AS fecha, 'ingreso'::TEXT AS tipo,
        c.nombre_empresa || ' - ' || fe.numero_factura AS descripcion,
        fe.saldo_pendiente AS monto, 'cliente'::TEXT AS categoria,
        (fe.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_fecha
    FROM facturas_emitidas fe JOIN clientes c ON fe.cliente_id = c.id
    WHERE fe.estado IN ('pendiente','parcial','vencida')
      AND fe.fecha_vencimiento <= CURRENT_DATE + INTERVAL '60 days'

    UNION ALL

    SELECT fr.fecha_vencimiento AS fecha, 'egreso'::TEXT AS tipo,
        p.nombre_completo || ' - ' || fr.numero_factura AS descripcion,
        fr.saldo_pendiente AS monto, fr.tipo AS categoria,
        (fr.fecha_vencimiento - CURRENT_DATE) AS dias_hasta_fecha
    FROM facturas_recibidas fr JOIN personal p ON fr.personal_id = p.id
    WHERE fr.estado IN ('pendiente','parcial')
      AND fr.fecha_vencimiento <= CURRENT_DATE + INTERVAL '60 days'

    UNION ALL

    SELECT l.fecha_pago_programada AS fecha, 'egreso'::TEXT AS tipo,
        p.nombre_completo || ' - ' || l.numero_liquidacion AS descripcion,
        l.total_a_pagar AS monto, p.tipo_personal AS categoria,
        (l.fecha_pago_programada - CURRENT_DATE) AS dias_hasta_fecha
    FROM liquidaciones l JOIN personal p ON l.personal_id = p.id
    WHERE l.estado IN ('generada','aprobada')
      AND l.fecha_pago_programada <= CURRENT_DATE + INTERVAL '60 days'
) AS flujo
ORDER BY fecha, tipo DESC;

-- ============================================================
-- DATOS INICIALES
-- ============================================================

-- Usuario admin (password: admin123 — cambiar en producción)
INSERT INTO usuarios (username, password_hash, nombre_completo, email, rol) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7RXVdgxEgi', 'Administrador', 'admin@servilla.co', 'administrador');

-- Bogotá
INSERT INTO ciudades (nombre, departamento, codigo, es_bogota, ambito) VALUES
('Bogotá D.C.', 'Cundinamarca', 'BOG', TRUE, 'bogota');

-- Tarifas vigentes 2025
INSERT INTO tarifas_servicios (tipo_servicio, descripcion, tarifa, vigencia_desde) VALUES
('alistamiento_hora',   'Hora de alistamiento',   7960.90, '2025-01-01'),
('transporte_completo', 'Transporte completo',     8333.33, '2025-01-01'),
('medio_transporte',    'Medio transporte',        4166.67, '2025-01-01'),
('pegado_guia',         'Pegado de guía',            11.54, '2025-01-01');
