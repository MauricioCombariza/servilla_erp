import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ClavesExternasTable } from "./ClavesExternasTable";
import { UsuariosTable } from "./UsuariosTable";
import { RolesTable } from "./RolesTable";

export function UsuariosRolesPage() {
  type Tab = "usuarios" | "roles" | "claves";
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) ?? "usuarios");

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Administración</h1>
          <p className="text-sm text-gray-500 mt-0.5">Usuarios, roles, páginas visibles por rol y claves de otros sistemas</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-6">
        {[
          { key: "usuarios" as const, label: "Usuarios" },
          { key: "roles" as const, label: "Roles" },
          { key: "claves" as const, label: "Claves de otros sistemas" },
        ].map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? "border-primary text-primary"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "usuarios" ? <UsuariosTable /> : tab === "roles" ? <RolesTable /> : <ClavesExternasTable />}
    </div>
  );
}
