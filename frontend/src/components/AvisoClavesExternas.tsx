import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { clavesExternasApi } from "@/api/clavesExternas";
import { useAuthStore } from "@/store/authStore";

/** Franja para administradores cuando hay claves de otros sistemas vencidas o por vencer. */
export function AvisoClavesExternas() {
  const role = useAuthStore((s) => s.role);
  const { data } = useQuery({
    queryKey: ["admin", "claves-externas", "resumen"],
    queryFn: () => clavesExternasApi.resumen().then((r) => r.data),
    enabled: role === "administrador",
    refetchInterval: 30 * 60_000,
  });
  if (role !== "administrador" || !data) return null;
  const vencidas = data.vencidas + data.sin_registro;
  if (vencidas === 0 && data.por_vencer === 0) return null;

  const partes = [
    vencidas > 0 && `${vencidas} ${vencidas === 1 ? "clave vencida o sin registro" : "claves vencidas o sin registro"}`,
    data.por_vencer > 0 && `${data.por_vencer} por vencer`,
  ].filter(Boolean);
  return (
    <div className={`flex items-center gap-2 px-4 py-2 text-sm border-b ${vencidas > 0 ? "bg-red-50 text-red-800 border-red-200" : "bg-amber-50 text-amber-800 border-amber-200"}`}>
      <ShieldAlert size={15} className="flex-shrink-0" />
      <span className="flex-1">Claves de otros sistemas: {partes.join(" · ")}.</span>
      <Link to="/admin/usuarios-roles?tab=claves" className="font-medium underline">Ver</Link>
    </div>
  );
}
