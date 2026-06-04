import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { X } from "lucide-react";
import { facturacionApi } from "@/api/facturacion";
import type { Cliente } from "@/types/domain";

const schema = z.object({
  numero_factura: z.string().min(1, "Requerido"),
  cliente_id: z.coerce.number().int().positive("Selecciona cliente"),
  fecha_emision: z.string().min(1, "Requerido"),
  fecha_vencimiento: z.string().min(1, "Requerido"),
  periodo_mes: z.coerce.number().int().min(1).max(12),
  periodo_anio: z.coerce.number().int().min(2020),
  cantidad_items: z.coerce.number().int().min(1),
  subtotal: z.coerce.number().min(0),
  descuento: z.coerce.number().min(0).default(0),
  total: z.coerce.number().min(0),
  observaciones: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  clientes: Cliente[];
  onClose: () => void;
  onSaved: () => void;
}

export function FacturaEmitidaForm({ clientes, onClose, onSaved }: Props) {
  const today = new Date();
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      fecha_emision: today.toISOString().split("T")[0],
      periodo_mes: today.getMonth() + 1,
      periodo_anio: today.getFullYear(),
      cantidad_items: 1,
      subtotal: 0,
      descuento: 0,
      total: 0,
    },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const subtotal = watch("subtotal");
  const descuento = watch("descuento");

  function handleSubtotalChange(val: number) {
    setValue("total", Math.max(0, val - (descuento || 0)));
  }

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      await facturacionApi.createEmitida(data);
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">Nueva factura emitida</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
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
              <label className="block text-xs font-medium text-gray-700 mb-1">Número de factura *</label>
              <input {...register("numero_factura")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none" />
              {errors.numero_factura && <p className="text-xs text-red-600 mt-1">{errors.numero_factura.message}</p>}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cantidad ítems *</label>
              <input {...register("cantidad_items")} type="number" min={1}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha emisión *</label>
              <input {...register("fecha_emision")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha vencimiento *</label>
              <input {...register("fecha_vencimiento")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Período mes</label>
              <select {...register("periodo_mes")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                {Array.from({length: 12}, (_, i) => i + 1).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Año</label>
              <input {...register("periodo_anio")} type="number" min={2020}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Subtotal *</label>
              <input {...register("subtotal")} type="number" step="1" min={0}
                onChange={(e) => { register("subtotal").onChange(e); handleSubtotalChange(Number(e.target.value)); }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Descuento</label>
              <input {...register("descuento")} type="number" step="1" min={0}
                onChange={(e) => { register("descuento").onChange(e); setValue("total", Math.max(0, (subtotal || 0) - Number(e.target.value))); }}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>

            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Total *</label>
              <input {...register("total")} type="number" step="1" min={0}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-semibold focus:ring-2 focus:ring-primary outline-none" />
              {errors.total && <p className="text-xs text-red-600 mt-1">{errors.total.message}</p>}
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
              {saving ? "Guardando..." : "Crear factura"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
