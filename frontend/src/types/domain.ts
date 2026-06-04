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
  f_emi: string | null;
  f_esc: string;
  planilla: string;
  cod_men: string;
  mensajero_id: number | null;
  mensajero: { id: number; codigo: string; nombre_completo: string } | null;
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

export interface PlanillaResumen {
  planilla: string;
  cod_men: string;
  mensajero_nombre: string | null;
  mensajero_id: number | null;
  fecha_escaner: string | null;
  entregas: number;
  devoluciones: number;
  total_seriales: number;
  total_cliente: number;
  total_mensajero: number;
  precio_promedio_mensajero: number;
  estados: Record<string, number>;
  bloqueada: boolean;
  con_precio_cero: number;
}
