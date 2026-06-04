import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { ordenesApi } from "@/api/ordenes";
import type { Cliente, Orden } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  numero_orden: z.string().min(1, "Requerido"),
  cliente_id: z.coerce.number().int().positive("Selecciona un cliente"),
  fecha_recepcion: z.string().min(1, "Requerido"),
  tipo_servicio: z.enum(["sobre", "paquete"]),
  cantidad_total: z.coerce.number().int().min(0).default(0),
  precio_unitario: z.coerce.number().min(0).optional(),
  observaciones: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  initial: Orden | null;
  clientes: Cliente[];
  onClose: () => void;
  onSaved: () => void;
}

export function OrdenForm({ initial, clientes, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          numero_orden: initial.numero_orden,
          cliente_id: initial.cliente_id,
          fecha_recepcion: initial.fecha_recepcion,
          tipo_servicio: initial.tipo_servicio,
          cantidad_total: initial.cantidad_total,
          precio_unitario: initial.precio_unitario ?? undefined,
          observaciones: initial.observaciones ?? "",
        }
      : { tipo_servicio: "sobre", cantidad_total: 0 },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      if (initial) {
        await ordenesApi.update(initial.id, data);
      } else {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await (ordenesApi.create as any)({
          ...data,
          ciudad_destino_id: null,
          cantidad_recibido: data.cantidad_total,
          quantidade_en_cajoneras: 0,
          cantidad_en_lleva: 0,
          cantidad_entregados: 0,
          cantidad_devolucion: 0,
          valor_total: 0,
          estado: "activa",
          facturado: false,
        });
      }
      onSaved();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">
            {initial ? "Editar orden" : "Nueva orden"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Número de orden *</label>
              <input {...register("numero_orden")} disabled={!!initial}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none disabled:bg-gray-50" />
              {errors.numero_orden && <p className="text-xs text-red-600 mt-1">{errors.numero_orden.message}</p>}
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Cliente *</label>
              <select {...register("cliente_id")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                <option value="">Seleccionar...</option>
                {clientes.map((c) => (
                  <option key={c.id} value={c.id}>{c.nombre_empresa}</option>
                ))}
              </select>
              {errors.cliente_id && <p className="text-xs text-red-600 mt-1">{errors.cliente_id.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha recepción *</label>
              <input {...register("fecha_recepcion")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              {errors.fecha_recepcion && <p className="text-xs text-red-600 mt-1">{errors.fecha_recepcion.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tipo *</label>
              <select {...register("tipo_servicio")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                <option value="sobre">Sobre</option>
                <option value="paquete">Paquete</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cantidad total</label>
              <input {...register("cantidad_total")} type="number" min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Precio unitario</label>
              <input {...register("precio_unitario")} type="number" step="0.01" min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
              <textarea {...register("observaciones")} rows={2}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none resize-none" />
            </div>
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-primary hover:bg-primary-hover text-white rounded-lg font-medium disabled:opacity-60">
              {saving ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
