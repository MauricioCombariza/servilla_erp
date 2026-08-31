import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { usuariosAdminApi, rolesAdminApi } from "@/api/usuariosAdmin";
import { Badge } from "@/components/ui/Badge";
import { useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { UsuarioForm } from "./UsuarioForm";
import type { Usuario } from "@/types/domain";

export function UsuariosTable() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Usuario | null>(null);

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ["admin", "usuarios"],
    queryFn: () => usuariosAdminApi.list().then((r) => r.data),
  });

  const { data: roles = [] } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => rolesAdminApi.list().then((r) => r.data),
  });

  const toggleActivo = useMutation({
    mutationFn: (u: Usuario) => usuariosAdminApi.update(u.id, { activo: !u.activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "usuarios"] }),
  });

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">{usuarios.length} usuarios</p>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Nuevo usuario
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {["Usuario", "Nombre", "Email", "Rol", "Último acceso", "Estado", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-3 font-medium text-gray-600 text-xs uppercase tracking-wide">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {usuarios.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-700">{u.username}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{u.nombre_completo}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">
                    <span className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full">{u.rol}</span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {u.ultimo_acceso ? new Date(u.ultimo_acceso).toLocaleString("es-CO") : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggleActivo.mutate(u)}>
                      <Badge active={u.activo} />
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => { setEditing(u); setShowForm(true); }}
                      className="text-gray-400 hover:text-primary transition-colors"
                    >
                      <Pencil size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <UsuarioForm
          initial={editing}
          roles={roles}
          onClose={closeForm}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["admin", "usuarios"] });
            closeForm();
          }}
        />
      )}
    </div>
  );
}
