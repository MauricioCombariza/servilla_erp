import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { rolesAdminApi, paginasAdminApi } from "@/api/usuariosAdmin";
import { Badge } from "@/components/ui/Badge";
import { useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { RolForm } from "./RolForm";
import type { Rol } from "@/types/domain";

export function RolesTable() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Rol | null>(null);

  const { data: roles = [], isLoading } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: () => rolesAdminApi.list().then((r) => r.data),
  });

  const { data: paginas = [] } = useQuery({
    queryKey: ["admin", "paginas"],
    queryFn: () => paginasAdminApi.list().then((r) => r.data),
  });

  const toggleActivo = useMutation({
    mutationFn: (r: Rol) => rolesAdminApi.update(r.nombre, { activo: !r.activo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "roles"] }),
  });

  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  const labelByKey = Object.fromEntries(paginas.map((p) => [p.key, p.label]));

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">{roles.length} roles</p>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Nuevo rol
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-16 text-gray-500">Cargando...</div>
      ) : (
        <div className="space-y-3">
          {roles.map((r) => (
            <div key={r.nombre} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className="font-medium text-gray-900">{r.nombre}</p>
                  {r.descripcion && <p className="text-xs text-gray-500 mt-0.5">{r.descripcion}</p>}
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={() => toggleActivo.mutate(r)}>
                    <Badge active={r.activo} />
                  </button>
                  <button
                    onClick={() => { setEditing(r); setShowForm(true); }}
                    className="text-gray-400 hover:text-primary transition-colors"
                  >
                    <Pencil size={15} />
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {r.paginas.length === 0 ? (
                  <span className="text-xs text-gray-400">Sin páginas asignadas</span>
                ) : (
                  r.paginas.map((key) => (
                    <span key={key} className="bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded-full">
                      {labelByKey[key] ?? key}
                    </span>
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <RolForm
          initial={editing}
          paginas={paginas}
          onClose={closeForm}
          onSaved={() => {
            qc.invalidateQueries({ queryKey: ["admin", "roles"] });
            closeForm();
          }}
        />
      )}
    </div>
  );
}
