import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { personalApi } from "@/api/personal";
import type { Personal } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  codigo: z.string().length(4, "Debe tener exactamente 4 caracteres"),
  nombre_completo: z.string().min(1, "Requerido"),
  identificacion: z.string().min(1, "Requerido"),
  tipo_personal: z.enum(["mensajero","alistamiento","conductor","courier_externo","transportadora"]),
  telefono: z.string().optional(),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  banco: z.string().optional(),
  numero_cuenta: z.string().optional(),
  tipo_cuenta: z.enum(["ahorros","corriente"]).optional(),
  dia_pago: z.coerce.number().int().min(1).max(28).default(8),
  precio_local: z.coerce.number().min(0).optional(),
  precio_nacional: z.coerce.number().min(0).optional(),
  observaciones: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  initial: Personal | null;
  onClose: () => void;
  onSaved: () => void;
}

export function PersonalForm({ initial, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          codigo: initial.codigo,
          nombre_completo: initial.nombre_completo,
          identificacion: initial.identificacion,
          tipo_personal: initial.tipo_personal,
          telefono: initial.telefono ?? "",
          email: initial.email ?? "",
          banco: initial.banco ?? "",
          numero_cuenta: initial.numero_cuenta ?? "",
          tipo_cuenta: initial.tipo_cuenta ?? undefined,
          dia_pago: initial.dia_pago,
          precio_local: initial.precio_local ?? undefined,
          precio_nacional: initial.precio_nacional ?? undefined,
          observaciones: initial.observaciones ?? "",
        }
      : { dia_pago: 8, tipo_personal: "mensajero" },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      if (initial) {
        await personalApi.update(initial.id, data);
      } else {
        await personalApi.create(data as Parameters<typeof personalApi.create>[0]);
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">
            {initial ? "Editar personal" : "Nuevo personal"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Código (4 dígitos) *</label>
              <input {...register("codigo")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none"
                maxLength={4} disabled={!!initial}
              />
              {errors.codigo && <p className="text-xs text-red-600 mt-1">{errors.codigo.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Tipo *</label>
              <select {...register("tipo_personal")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                <option value="mensajero">Mensajero</option>
                <option value="alistamiento">Alistamiento</option>
                <option value="conductor">Conductor</option>
                <option value="courier_externo">Courier externo</option>
                <option value="transportadora">Transportadora</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Nombre completo *</label>
              <input {...register("nombre_completo")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              {errors.nombre_completo && <p className="text-xs text-red-600 mt-1">{errors.nombre_completo.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Identificación *</label>
              <input {...register("identificacion")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Teléfono</label>
              <input {...register("telefono")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>
          </div>

          <fieldset className="border border-gray-200 rounded-lg p-4">
            <legend className="text-xs font-medium text-gray-600 px-2">Precios por gestión</legend>
            <div className="grid grid-cols-2 gap-4 mt-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Precio local (Bogotá)</label>
                <input {...register("precio_local")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Precio nacional</label>
                <input {...register("precio_nacional")} type="number" step="1"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
            </div>
          </fieldset>

          <fieldset className="border border-gray-200 rounded-lg p-4">
            <legend className="text-xs font-medium text-gray-600 px-2">Datos bancarios</legend>
            <div className="grid grid-cols-2 gap-4 mt-2">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Banco</label>
                <input {...register("banco")}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Nro. cuenta</label>
                <input {...register("numero_cuenta")}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Tipo cuenta</label>
                <select {...register("tipo_cuenta")}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                  <option value="">—</option>
                  <option value="ahorros">Ahorros</option>
                  <option value="corriente">Corriente</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Día de pago</label>
                <input {...register("dia_pago")} type="number" min={1} max={28}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              </div>
            </div>
          </fieldset>

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
