import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Users, UserCheck, ShoppingCart, FileText, BarChart2,
  Clock, DollarSign, Truck, Receipt, Wallet, Calculator, List, ClipboardCheck,
  LogOut, Menu, X
} from "lucide-react";
import { useState } from "react";
import { useAuthStore } from "@/store/authStore";

const navItems = [
  { to: "/clientes", label: "Clientes y Precios", icon: Users },
  { to: "/personal", label: "Personal", icon: UserCheck },
  { to: "/ordenes", label: "Órdenes", icon: ShoppingCart },
  { to: "/facturacion", label: "Resumen Financiero", icon: FileText },
  { to: "/facturacion/emitidas", label: "Facturas Emitidas", icon: FileText },
  { to: "/reportes", label: "Reportes", icon: BarChart2 },
  { to: "/labores", label: "Registro Labores", icon: Clock },
  { to: "/pagos-mensajeros", label: "Gestión Pagos", icon: DollarSign },
  { to: "/facturas-transporte", label: "Facturas Transporte", icon: Truck },
  { to: "/gastos", label: "Gastos Admin", icon: Receipt },
  { to: "/flujo-caja", label: "Flujo de Caja", icon: Wallet },
  { to: "/nomina", label: "Nómina", icon: Calculator },
  { to: "/gestiones", label: "Detalle Gestiones", icon: List },
  { to: "/planillas", label: "Planillas", icon: ClipboardCheck },
];

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { nombreCompleto, role, logout } = useAuthStore();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

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
          {navItems.map(({ to, label, icon: Icon }) => (
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
