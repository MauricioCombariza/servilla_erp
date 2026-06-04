import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { clientesApi } from "@/api/clientes";
import type { Cliente } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  nombre_empresa: z.string().min(1, "Requerido"),
  nit: z.string().min(1, "Requerido"),
  contacto_nombre: z.string().optional(),
  contacto_telefono: z.string().optional(),
  contacto_email: z.string().email("Email inválido").optional().or(z.literal("")),
  ciudad: z.string().optional(),
  plazo_pago_dias: z.coerce.number().int().min(1).default(30),
  notas: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  initial: Cliente | null;
  onClose: () => void;
  onSaved: () => void;
}

export function ClienteForm({ initial, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          nombre_empresa: initial.nombre_empresa,
          nit: initial.nit,
          contacto_nombre: initial.contacto_nombre ?? "",
          contacto_telefono: initial.contacto_telefono ?? "",
          contacto_email: initial.contacto_email ?? "",
          ciudad: initial.ciudad ?? "",
          plazo_pago_dias: initial.plazo_pago_dias,
          notas: initial.notas ?? "",
        }
      : { plazo_pago_dias: 30 },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      if (initial) {
        await clientesApi.update(initial.id, data);
      } else {
        await clientesApi.create(data as Parameters<typeof clientesApi.create>[0]);
      }
      onSaved();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "Error al guardar");
    } finally {
      setSaving(false);
    }
  }

  const Field = ({ label, name, type = "text" }: { label: string; name: keyof FormData; type?: string }) => (
    <div>
      <label className="block text-xs font-medium text-gray-700 mb-1">{label}</label>
      <input
        {...register(name)}
        type={type}
        className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none"
      />
      {errors[name] && <p className="text-xs text-red-600 mt-1">{errors[name]?.message as string}</p>}
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">
            {initial ? "Editar cliente" : "Nuevo cliente"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <Field label="Razón social *" name="nombre_empresa" />
            </div>
            <Field label="NIT *" name="nit" />
            <Field label="Ciudad" name="ciudad" />
            <Field label="Contacto nombre" name="contacto_nombre" />
            <Field label="Teléfono" name="contacto_telefono" />
            <Field label="Email" name="contacto_email" type="email" />
            <Field label="Plazo pago (días)" name="plazo_pago_dias" type="number" />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Notas</label>
            <textarea
              {...register("notas")}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary focus:border-primary outline-none resize-none"
            />
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
