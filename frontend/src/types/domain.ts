export interface Cliente {
  id: number;
  nombre_empresa: string;
  nit: string;
  contacto_nombre: string | null;
  contacto_telefono: string | null;
  contacto_email: string | null;
  direccion: string | null;
  ciudad: string | null;
  plazo_pago_dias: number;
  activo: boolean;
  notas: string | null;
  fecha_creacion: string | null;
  fecha_modificacion: string | null;
}

export interface PrecioCliente {
  id: number;
  cliente_id: number;
  tipo_servicio: "sobre" | "paquete";
  ambito: "bogota" | "nacional";
  precio_entrega: number;
  precio_devolucion: number;
  costo_mensajero_entrega: number;
  costo_mensajero_devolucion: number;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
  notas: string | null;
}

export interface ClienteWithPrecios extends Cliente {
  precios: PrecioCliente[];
}

export type TipoPersonal =
  | "mensajero"
  | "alistamiento"
  | "conductor"
  | "courier_externo"
  | "transportadora";

export interface Personal {
  id: number;
  codigo: string;
  nombre_completo: string;
  identificacion: string;
  telefono: string | null;
  email: string | null;
  tipo_personal: TipoPersonal;
  banco: string | null;
  numero_cuenta: string | null;
  tipo_cuenta: "ahorros" | "corriente" | null;
  dia_pago: number;
  activo: boolean;
  observaciones: string | null;
  fecha_ingreso: string | null;
  precio_local: number | null;
  precio_nacional: number | null;
}

export interface PersonalCiudad {
  id: number;
  personal_id: number;
  ciudad_id: number;
  tarifa_entrega: number | null;
  tarifa_devolucion: number | null;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
}

export interface Orden {
  id: number;
  numero_orden: string;
  cliente_id: number;
  cliente: { id: number; nombre_empresa: string; nit: string };
  ciudad_destino_id: number | null;
  ciudad_destino: { id: number; nombre: string; ambito: string } | null;
  fecha_recepcion: string;
  tipo_servicio: "sobre" | "paquete";
  cantidad_total: number;
  cantidad_recibido: number;
  cantidad_en_cajoneras: number;
  cantidad_en_lleva: number;
  cantidad_entregados: number;
  cantidad_devolucion: number;
  precio_unitario: number | null;
  valor_total: number;
  costo_total: number;
  utilidad_total: number;
  estado: "activa" | "finalizada" | "anulada";
  facturado: boolean;
  fecha_finalizacion: string | null;
  observaciones: string | null;
  fecha_creacion: string | null;
  fecha_modificacion: string | null;
}

export interface Ciudad {
  id: number;
  nombre: string;
  departamento: string | null;
  codigo: string | null;
  es_bogota: boolean;
  ambito: "bogota" | "nacional";
  activa: boolean;
}

export interface SerialGestion {
  id: number;
  serial: string;
  orden: string | null;
  f_emi: string | null;
  f_esc: string;
  planilla: string;
  cod_men: string;
  mensajero_id: number | null;
  mensajero: {
    id: number;
    codigo: string;
    nombre_completo: string;
    tipo_personal: string | null;
    precio_local: number | null;
    precio_nacional: number | null;
  } | null;
  cliente_id: number | null;
  cliente: { id: number; nombre_empresa: string } | null;
  tipo_gestion: "Entrega" | "Devolucion";
  tipo_envio: "sobre" | "paquete";
  ambito: "bogota" | "nacional";
  precio_cliente: number;
  precio_mensajero: number;
  estado: string;
  liquidacion_id: number | null;
  factura_id: number | null;
  editado_manualmente: boolean;
  observaciones: string | null;
  fecha_creacion: string | null;
  fecha_modificacion: string | null;
}

// ── Gastos ────────────────────────────────────────────────────────────────────

export interface GastoAdmin {
  id: number;
  fecha: string;
  categoria: string;
  descripcion: string;
  monto: number;
  proveedor: string | null;
  numero_factura: string | null;
  estado: "pendiente" | "pagado";
  fecha_pago: string | null;
  observaciones: string | null;
  fecha_creacion: string | null;
}

export interface GastoAdminResumen {
  categoria: string;
  total: number;
  cantidad: number;
}

export interface GastoFijo {
  id: number;
  categoria: string;
  descripcion: string;
  monto: number;
  dia_pago: number;
  activo: boolean;
  observaciones: string | null;
  created_at: string | null;
  pagos: PagoGastoFijo[];
}

export interface PagoGastoFijo {
  id: number;
  gasto_fijo_id: number;
  mes: number;
  anio: number;
  monto_pagado: number;
  fecha_pago: string;
  observaciones: string | null;
  created_at: string | null;
}

// ── Nómina ────────────────────────────────────────────────────────────────────

export interface NominaEmpleado {
  id: number;
  nombre_completo: string;
  identificacion: string | null;
  cargo: string | null;
  salario_mensual: number;
  tiene_auxilio_transporte: boolean;
  auxilio_no_salarial: number;
  fecha_ingreso: string | null;
  activo: boolean;
  fecha_creacion: string | null;
}

export interface NominaProvision {
  id: number;
  empleado_id: number;
  periodo_mes: number;
  periodo_anio: number;
  salario_base: number | null;
  auxilio_transporte: number | null;
  auxilio_no_salarial: number | null;
  arl: number | null;
  eps: number | null;
  afp: number | null;
  caja_compensacion: number | null;
  prima: number | null;
  cesantias: number | null;
  int_cesantias: number | null;
  vacaciones: number | null;
  fecha_creacion: string | null;
}

export interface ResumenNomina {
  periodo_mes: number;
  periodo_anio: number;
  total_empleados: number;
  total_salarios: number;
  total_seguridad_social: number;
  total_provisiones: number;
  costo_total: number;
}

export interface NominaParametro {
  id: number;
  parametro: string;
  valor: number;
  descripcion: string | null;
  vigencia_desde: string;
  activo: boolean;
}

export interface EmpleadoResumen {
  id: number;
  nombre_completo: string;
  cargo: string | null;
  salario_mensual: number;
  auxilio_no_salarial: number;
  auxilio_transporte: number;
  arl: number;
  eps: number;
  afp: number;
  caja_compensacion: number;
  prima: number;
  cesantias: number;
  int_cesantias: number;
  vacaciones: number;
  total_seguridad_social: number;
  total_provisiones: number;
  costo_total: number;
}

export interface ResumenNominaDetallado {
  total_empleados: number;
  empleados: EmpleadoResumen[];
  total_salarios: number;
  total_aux_no_salarial: number;
  total_aux_transporte: number;
  total_nomina_base: number;
  total_arl: number;
  total_eps: number;
  total_afp: number;
  total_caja: number;
  total_seguridad_social: number;
  total_prima: number;
  total_cesantias: number;
  total_int_cesantias: number;
  total_vacaciones: number;
  total_provisiones: number;
  costo_total: number;
}

export interface PeriodoHistorico {
  periodo_mes: number;
  periodo_anio: number;
  total_empleados: number;
  costo_total: number;
}

export interface RosterEntry {
  id: number;
  empleado_id: number;
  periodo_mes: number;
  periodo_anio: number;
  fecha_creacion: string | null;
  empleado: NominaEmpleado;
}

export interface NominaResumenPeriodo {
  anio: number;
  mes: number | null;
  total_empleados: number;
  costo_total: number;
}

// ── Labores ───────────────────────────────────────────────────────────────────

export interface RegistroHoras {
  id: number;
  personal_id: number;
  orden_id: number | null;
  fecha: string;
  horas_trabajadas: number;
  tarifa_hora: number;
  total: number | null;
  tipo_trabajo: string;
  aprobado: boolean;
  aprobado_por: number | null;
  fecha_aprobacion: string | null;
  liquidado: boolean;
  observaciones: string | null;
  fecha_creacion: string | null;
}

export interface RegistroLabores {
  id: number;
  personal_id: number;
  orden_id: number | null;
  fecha: string;
  tipo_labor: string;
  cantidad: number;
  tarifa_unitaria: number;
  total: number | null;
  aprobado: boolean;
  aprobado_por: number | null;
  fecha_aprobacion: string | null;
  liquidado: boolean;
  observaciones: string | null;
  fecha_creacion: string | null;
}

export interface ResumenLabores {
  personal_id: number;
  nombre_completo: string;
  total_horas: number;
  total_horas_monto: number;
  total_labores: number;
  total_labores_monto: number;
  total_general: number;
}

// ── Flujo de caja ─────────────────────────────────────────────────────────────

export interface FlujoCaja60Dias {
  fecha: string;
  tipo: "ingreso" | "egreso";
  descripcion: string;
  monto: number;
  categoria: string;
  dias_hasta_fecha: number;
  periodo: "VENCIDO" | "ESTA SEMANA" | "ESTE MES" | "PROXIMO MES";
}

export interface ResumenMensualFlujo {
  anio: number;
  mes: number;
  total_facturado: number;
  cobrado: number;
  por_cobrar: number;
  ingreso_bruto_seriales: number;
  costo_mensajero: number;
  gastos_admin: number;
  costo_nomina: number;
  flujo_neto: number;
}

export interface PlanillaResumen {
  planilla: string;
  cod_men: string;
  mensajero_nombre: string | null;
  mensajero_id: number | null;
  tipo_personal: string | null;
  fecha_escaner: string | null;
  entregas: number;
  devoluciones: number;
  total_seriales: number;
  total_cliente: number;
  total_mensajero: number;
  precio_promedio_mensajero: number;
  precio_promedio_cliente: number;
  estados: Record<string, number>;
  bloqueada: boolean;
  con_precio_cero: number;
  revisada: boolean;
  precio_local_mensajero?: number | null;
  precio_nacional_mensajero?: number | null;
}
