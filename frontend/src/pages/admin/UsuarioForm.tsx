import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useState } from "react";
import { usuariosAdminApi } from "@/api/usuariosAdmin";
import type { Rol, Usuario } from "@/types/domain";
import { X } from "lucide-react";

const schema = z.object({
  username: z.string().min(3, "Mínimo 3 caracteres"),
  password: z.string().min(6, "Mínimo 6 caracteres").optional().or(z.literal("")),
  nombre_completo: z.string().min(1, "Requerido"),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  rol: z.string().min(1, "Requerido"),
});
type FormData = z.infer<typeof schema>;

interface Props {
  initial: Usuario | null;
  roles: Rol[];
  onClose: () => void;
  onSaved: () => void;
}

export function UsuarioForm({ initial, roles, onClose, onSaved }: Props) {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: initial
      ? {
          username: initial.username,
          nombre_completo: initial.nombre_completo,
          email: initial.email ?? "",
          rol: initial.rol,
          password: "",
        }
      : { rol: roles.find((r) => r.activo)?.nombre ?? "" },
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(data: FormData) {
    setSaving(true);
    setError("");
    try {
      if (initial) {
        await usuariosAdminApi.update(initial.id, {
          nombre_completo: data.nombre_completo,
          email: data.email || undefined,
          rol: data.rol,
        });
        if (data.password) {
          await usuariosAdminApi.resetPassword(initial.id, data.password);
        }
      } else {
        await usuariosAdminApi.create({
          username: data.username,
          password: data.password || "",
          nombre_completo: data.nombre_completo,
          email: data.email || undefined,
          rol: data.rol,
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
      <div className="bg-white rounded-xl shadow-lg w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-900">
            {initial ? "Editar usuario" : "Nuevo usuario"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Usuario *</label>
            <input {...register("username")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-primary outline-none"
              disabled={!!initial}
            />
            {errors.username && <p className="text-xs text-red-600 mt-1">{errors.username.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              {initial ? "Nueva contraseña (opcional)" : "Contraseña *"}
            </label>
            <input {...register("password")} type="password"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            {errors.password && <p className="text-xs text-red-600 mt-1">{errors.password.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Nombre completo *</label>
            <input {...register("nombre_completo")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            {errors.nombre_completo && <p className="text-xs text-red-600 mt-1">{errors.nombre_completo.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Email</label>
            <input {...register("email")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary outline-none" />
            {errors.email && <p className="text-xs text-red-600 mt-1">{errors.email.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">Rol *</label>
            <select {...register("rol")}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-primary outline-none">
              {roles.filter((r) => r.activo || r.nombre === initial?.rol).map((r) => (
                <option key={r.nombre} value={r.nombre}>{r.nombre}</option>
              ))}
            </select>
            {errors.rol && <p className="text-xs text-red-600 mt-1">{errors.rol.message}</p>}
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
