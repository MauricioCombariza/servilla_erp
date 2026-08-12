import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { clientesApi } from "@/api/clientes";
import type { PrecioCliente } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  tipo_servicio: z.enum(["sobre", "paquete"]),
  ambito: z.enum(["bogota", "nacional"]),
  precio_entrega: z.coerce.number().min(0),
  precio_devolucion: z.coerce.number().min(0),
  costo_mensajero_entrega: z.coerce.number().min(0),
  costo_mensajero_devolucion: z.coerce.number().min(0),
  vigencia_desde: z.string().min(1, "Requerido"),
  vigencia_hasta: z.string().optional(),
  notas: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  clienteId: number;
  initial: PrecioCliente | null;
  onClose: () => void;
  onSaved: () => void;
}

export function PrecioClienteForm({ clienteId, initial, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          tipo_servicio: initial.tipo_servicio,
          ambito: initial.ambito,
          precio_entrega: initial.precio_entrega,
          precio_devolucion: initial.precio_devolucion,
          costo_mensajero_entrega: initial.costo_mensajero_entrega,
          costo_mensajero_devolucion: initial.costo_mensajero_devolucion,
          vigencia_desde: initial.vigencia_desde,
          vigencia_hasta: initial.vigencia_hasta ?? "",
          notas: initial.notas ?? "",
        }
      : {
          tipo_servicio: "sobre",
          ambito: "bogota",
          precio_entrega: 0,
          precio_devolucion: 0,
          costo_mensajero_entrega: 0,
          costo_mensajero_devolucion: 0,
          vigencia_desde: new Date().toISOString().slice(0, 10),
        },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      const payload = { ...data, vigencia_hasta: data.vigencia_hasta || null };
      if (initial) {
        await clientesApi.updatePrecio(clienteId, initial.id, payload);
      } else {
        await clientesApi.createPrecio(clienteId, payload as Parameters<typeof clientesApi.createPrecio>[1]);
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">
            {initial ? "Editar precio" : "Nuevo precio"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tipo de servicio *</label>
              <select {...register("tipo_servicio")} disabled={!!initial}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none disabled:bg-gray-100">
                <option value="sobre">Sobre</option>
                <option value="paquete">Paquete</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Ámbito *</label>
              <select {...register("ambito")} disabled={!!initial}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none disabled:bg-gray-100">
                <option value="bogota">Bogotá</option>
                <option value="nacional">Nacional</option>
              </select>
            </div>
          </div>

          <fieldset className="border border-gray-200 rounded-lg p-4">
            <legend className="text-xs font-medium text-gray-600 px-2">Precio al cliente</legend>
            <div className="grid grid-cols-2 gap-4 mt-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Entrega</label>
                <input {...register("precio_entrega")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Devolución</label>
                <input {...register("precio_devolucion")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
            </div>
          </fieldset>

          <fieldset className="border border-gray-200 rounded-lg p-4">
            <legend className="text-xs font-medium text-gray-600 px-2">Costo mensajero</legend>
            <div className="grid grid-cols-2 gap-4 mt-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Entrega</label>
                <input {...register("costo_mensajero_entrega")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Devolución</label>
                <input {...register("costo_mensajero_devolucion")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
            </div>
          </fieldset>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Vigente desde *</label>
              <input {...register("vigencia_desde")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              {errors.vigencia_desde && <p className="text-xs text-red-600 mt-1">{errors.vigencia_desde.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Vigente hasta</label>
              <input {...register("vigencia_hasta")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas</label>
            <textarea {...register("notas")} rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none resize-none" />
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
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
