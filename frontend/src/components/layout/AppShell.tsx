import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Users, UserCheck, ShoppingCart, FileText, BarChart2,
  Clock, DollarSign, Truck, Receipt, Wallet, Calculator, List, ClipboardCheck,
  LogOut, Menu, X, ArrowDownCircle, ArrowUpCircle, Search, Building2, MapPin, PackageCheck,
  ScanLine, Radio, ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { useAuthStore } from "@/store/authStore";

const navItems = [
  { to: "/clientes", label: "Clientes y Precios", icon: Users, pageKey: "clientes" },
  { to: "/personal", label: "Personal", icon: UserCheck, pageKey: "personal" },
  { to: "/ordenes", label: "Órdenes", icon: ShoppingCart, pageKey: "ordenes" },
  { to: "/facturacion", label: "Resumen Financiero", icon: FileText, pageKey: "facturacion_resumen" },
  { to: "/facturacion/emitidas", label: "Facturas Emitidas", icon: FileText, pageKey: "facturacion_emitidas" },
  { to: "/facturacion/recibidas", label: "Facturas Recibidas", icon: FileText, pageKey: "facturacion_recibidas" },
  { to: "/facturacion/cobrar", label: "CxC — Por Cobrar", icon: ArrowDownCircle, pageKey: "facturacion_cxc" },
  { to: "/facturacion/pagar", label: "CxP — Por Pagar", icon: ArrowUpCircle, pageKey: "facturacion_cxp" },
  { to: "/reportes", label: "Reportes", icon: BarChart2, pageKey: "reportes" },
  { to: "/labores", label: "Registro Labores", icon: Clock, pageKey: "labores" },
  { to: "/pagos-mensajeros", label: "Gestión Pagos", icon: DollarSign, pageKey: "pagos_mensajeros" },
  { to: "/facturas-transporte", label: "Facturas Transporte", icon: Truck, pageKey: "facturas_transporte" },
  { to: "/pagos-ciudades", label: "Pagos Ciudades", icon: Building2, pageKey: "pagos_ciudades" },
  { to: "/gastos", label: "Gastos Admin", icon: Receipt, pageKey: "gastos" },
  { to: "/flujo-caja", label: "Flujo de Caja", icon: Wallet, pageKey: "flujo_caja" },
  { to: "/nomina", label: "Nómina", icon: Calculator, pageKey: "nomina" },
  { to: "/gestiones", label: "Detalle Gestiones", icon: List, pageKey: "gestiones" },
  { to: "/planillas", label: "Planillas", icon: ClipboardCheck, pageKey: "planillas" },
  { to: "/buscar", label: "Buscar Paquete", icon: Search, pageKey: "buscar" },
  { to: "/direcciones", label: "Ajuste Direcciones", icon: MapPin, pageKey: "direcciones" },
  { to: "/pendientes-entrega", label: "Pendientes Entrega", icon: PackageCheck, pageKey: "pendientes_entrega" },
  { to: "/escaneo-carryt", label: "Escaneo Carryt", icon: ScanLine, pageKey: "escaneo_carryt" },
  { to: "/imile-offload-scan", label: "Escaneo Offloading iMile", icon: Radio, pageKey: "imile_offload_scan" },
  { to: "/admin/usuarios-roles", label: "Administración", icon: ShieldCheck, adminOnly: true },
];

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { nombreCompleto, role, pageKeys, logout } = useAuthStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  const visibleItems = navItems.filter((item) =>
    item.adminOnly ? role === "administrador" : role === "administrador" || pageKeys.includes(item.pageKey ?? "")
  );

  return (
    <div className="flex h-screen bg-surface">
      {/* Sidebar */}
      <aside
        className={`${
          sidebarOpen ? "w-56" : "w-0 overflow-hidden"
        } transition-all duration-200 bg-gray-900 text-gray-100 flex flex-col flex-shrink-0`}
      >
        <div className="px-4 py-5 border-b border-gray-700">
          <p className="font-semibold text-white text-sm">Servilla ERP</p>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{nombreCompleto}</p>
          <span className="text-xs text-gray-500 capitalize">{role}</span>
        </div>

        <nav className="flex-1 overflow-y-auto py-2">
          {visibleItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? "bg-primary text-white"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                }`
              }
            >
              <Icon size={16} className="flex-shrink-0" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 text-sm text-gray-400 hover:text-white hover:bg-gray-800 border-t border-gray-700"
        >
          <LogOut size={16} />
          Cerrar sesión
        </button>
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="h-12 bg-white border-b border-gray-200 flex items-center px-4 gap-3 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-gray-500 hover:text-gray-900"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <span className="text-sm font-medium text-gray-700">Logística</span>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
