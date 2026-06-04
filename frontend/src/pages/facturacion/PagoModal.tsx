import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { X } from "lucide-react";

const schema = z.object({
  fecha_pago: z.string().min(1, "Requerido"),
  monto: z.coerce.number().positive("Debe ser mayor a 0"),
  metodo_pago: z.enum(["efectivo", "transferencia", "cheque", "tarjeta", "otros"]),
  referencia: z.string().optional(),
  observaciones: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  titulo: string;
  saldoMaximo: number;
  onClose: () => void;
  onSave: (data: FormData) => Promise<void>;
}

export function PagoModal({ titulo, saldoMaximo, onClose, onSave }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      fecha_pago: new Date().toISOString().split("T")[0],
      monto: saldoMaximo,
      metodo_pago: "transferencia",
    },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      await onSave(data);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al registrar el pago");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">{titulo}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <p className="text-sm text-gray-500">
            Saldo pendiente: <strong className="text-gray-900">
              ${new Intl.NumberFormat("es-CO").format(saldoMaximo)}
            </strong>
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Fecha *</label>
              <input {...register("fecha_pago")} type="date"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              {errors.fecha_pago && <p className="text-xs text-red-600 mt-1">{errors.fecha_pago.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Monto *</label>
              <input {...register("monto")} type="number" step="1" min={1} max={saldoMaximo}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
              {errors.monto && <p className="text-xs text-red-600 mt-1">{errors.monto.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Método *</label>
              <select {...register("metodo_pago")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
                <option value="transferencia">Transferencia</option>
                <option value="efectivo">Efectivo</option>
                <option value="cheque">Cheque</option>
                <option value="tarjeta">Tarjeta</option>
                <option value="otros">Otros</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Referencia</label>
              <input {...register("referencia")}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Observaciones</label>
            <textarea {...register("observaciones")} rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none resize-none" />
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>}

          <div className="flex justify-end gap-3">
            <button type="button" onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="px-4 py-2 text-sm bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium disabled:opacity-60">
              {saving ? "Registrando..." : "Registrar pago"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
