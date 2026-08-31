import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { rolesAdminApi } from "@/api/usuariosAdmin";
import type { PaginaCatalogo, Rol } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  nombre: z.string().regex(/^[a-z][a-z0-9_]{2,29}$/, "minúsculas, números y _ (3-30 caracteres)"),
  descripcion: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

interface Props {
  initial: Rol | null;
  paginas: PaginaCatalogo[];
  onClose: () => void;
  onSaved: () => void;
}

export function RolForm({ initial, paginas, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? { nombre: initial.nombre, descripcion: initial.descripcion ?? "" }
      : { nombre: "", descripcion: "" },
  });
  const [selected, setSelected] = useState<Set<string>>(new Set(initial?.paginas ?? []));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      const paginasArr = Array.from(selected);
      if (initial) {
        await rolesAdminApi.update(initial.nombre, {
          descripcion: data.descripcion || undefined,
          paginas: paginasArr,
        });
      } else {
        await rolesAdminApi.create({
          nombre: data.nombre,
          descripcion: data.descripcion || undefined,
          paginas: paginasArr,
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">{initial ? "Editar rol" : "Nuevo rol"}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Nombre *</label>
            <input {...register("nombre")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none"
              disabled={!!initial}
            />
            {errors.nombre && <p className="text-xs text-red-600 mt-1">{errors.nombre.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Descripción</label>
            <input {...register("descripcion")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
          </div>

          <fieldset className="border border-gray-200 rounded-lg p-4">
            <legend className="text-xs font-medium text-gray-600 px-2">Páginas visibles</legend>
            <div className="grid grid-cols-2 gap-2 mt-2 max-h-64 overflow-y-auto">
              {paginas.map((p) => (
                <label key={p.key} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={selected.has(p.key)}
                    onChange={() => toggle(p.key)}
                    className="rounded border-gray-300 text-primary focus:ring-primary"
                  />
                  {p.label}
                </label>
              ))}
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
