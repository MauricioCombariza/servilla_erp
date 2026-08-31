import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { AppShell } from "@/components/layout/AppShell";
import { Login } from "@/pages/Login";
import { Forbidden } from "@/pages/Forbidden";
import { ClientesPage } from "@/pages/clientes/ClientesPage";
import { ClienteDetailPage } from "@/pages/clientes/ClienteDetailPage";
import { PersonalPage } from "@/pages/personal/PersonalPage";
import { OrdenesPage } from "@/pages/ordenes/OrdenesPage";
import { CargaMasivaPage } from "@/pages/ordenes/CargaMasivaPage";
import { ResumenPage } from "@/pages/facturacion/ResumenPage";
import { FacturasEmitidasPage } from "@/pages/facturacion/FacturasEmitidasPage";
import { PlanillasPage } from "@/pages/planillas/PlanillasPage";
import { DetalleGestionesPage } from "@/pages/gestiones/DetalleGestionesPage";
import { ReportesPage } from "@/pages/reportes/ReportesPage";
import { GastosPage } from "@/pages/gastos/GastosPage";
import { NominaPage } from "@/pages/nomina/NominaPage";
import { LaboresPage } from "@/pages/labores/LaboresPage";
import { FlujoCajaPage } from "@/pages/flujo/FlujoCajaPage";
import { FacturasRecibidasPage } from "@/pages/facturacion/FacturasRecibidasPage";
import { CuentasCobrarPage } from "@/pages/facturacion/CuentasCobrarPage";
import { CuentasPagarPage } from "@/pages/facturacion/CuentasPagarPage";
import { LiquidacionesPage } from "@/pages/pagos/LiquidacionesPage";
import { FacturasTransportePage } from "@/pages/transporte/FacturasTransportePage";
import { PagosCiudadesPage } from "@/pages/pagos-ciudades/PagosCiudadesPage";
import { BuscarPaquetePage } from "@/pages/buscar/BuscarPaquetePage";
import { AjusteDireccionesPage } from "@/pages/direcciones/AjusteDireccionesPage";
import { PendientesEntregaPage } from "@/pages/pendientes-entrega/PendientesEntregaPage";
import { DevolucionesPage } from "@/pages/devoluciones/DevolucionesPage";
import { EscaneoDevolucionesPage } from "@/pages/devoluciones/EscaneoDevolucionesPage";
import { EscaneoCarrytPage } from "@/pages/carryt/EscaneoCarrytPage";
import { EscaneoOffloadPage } from "@/pages/imile/EscaneoOffloadPage";
import { UsuariosRolesPage } from "@/pages/admin/UsuariosRolesPage";
import { Placeholder } from "@/pages/Placeholder";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

function PageGuard({ pageKey, children }: { pageKey: string | string[]; children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role);
  const pageKeys = useAuthStore((s) => s.pageKeys);
  const keys = Array.isArray(pageKey) ? pageKey : [pageKey];
  const allowed = role === "administrador" || keys.some((k) => pageKeys.includes(k));
  return allowed ? <>{children}</> : <Navigate to="/sin-permiso" replace />;
}

function AdminOnlyRoute({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role);
  return role === "administrador" ? <>{children}</> : <Navigate to="/sin-permiso" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/escaneo-carryt"
            element={
              <ProtectedRoute>
                <PageGuard pageKey="escaneo_carryt">
                  <EscaneoCarrytPage />
                </PageGuard>
              </ProtectedRoute>
            }
          />
          <Route
            path="/imile-offload-scan"
            element={
              <ProtectedRoute>
                <PageGuard pageKey="imile_offload_scan">
                  <EscaneoOffloadPage />
                </PageGuard>
              </ProtectedRoute>
            }
          />
          <Route
            path="/escaneo-devoluciones"
            element={
              <ProtectedRoute>
                <PageGuard pageKey="devoluciones_scan">
                  <EscaneoDevolucionesPage />
                </PageGuard>
              </ProtectedRoute>
            }
          />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/clientes" replace />} />
            <Route path="/sin-permiso" element={<Forbidden />} />
            <Route path="/clientes" element={<PageGuard pageKey="clientes"><ClientesPage /></PageGuard>} />
            <Route path="/clientes/:id" element={<PageGuard pageKey="clientes"><ClienteDetailPage /></PageGuard>} />
            <Route path="/personal" element={<PageGuard pageKey="personal"><PersonalPage /></PageGuard>} />
            <Route path="/ordenes" element={<PageGuard pageKey="ordenes"><OrdenesPage /></PageGuard>} />
            <Route path="/ordenes/carga-masiva" element={<PageGuard pageKey="ordenes"><CargaMasivaPage /></PageGuard>} />
            <Route path="/facturacion" element={<PageGuard pageKey="facturacion_resumen"><ResumenPage /></PageGuard>} />
            <Route path="/facturacion/emitidas" element={<PageGuard pageKey="facturacion_emitidas"><FacturasEmitidasPage /></PageGuard>} />
            <Route path="/facturacion/recibidas" element={<PageGuard pageKey="facturacion_recibidas"><FacturasRecibidasPage /></PageGuard>} />
            <Route path="/facturacion/cobrar" element={<PageGuard pageKey="facturacion_cxc"><CuentasCobrarPage /></PageGuard>} />
            <Route path="/facturacion/pagar" element={<PageGuard pageKey="facturacion_cxp"><CuentasPagarPage /></PageGuard>} />
            <Route path="/reportes" element={<PageGuard pageKey="reportes"><ReportesPage /></PageGuard>} />
            <Route path="/labores" element={<PageGuard pageKey="labores"><LaboresPage /></PageGuard>} />
            <Route path="/pagos-mensajeros" element={<PageGuard pageKey="pagos_mensajeros"><LiquidacionesPage /></PageGuard>} />
            <Route path="/facturas-transporte" element={<PageGuard pageKey="facturas_transporte"><FacturasTransportePage /></PageGuard>} />
            <Route path="/pagos-ciudades" element={<PageGuard pageKey="pagos_ciudades"><PagosCiudadesPage /></PageGuard>} />
            <Route path="/gastos" element={<PageGuard pageKey="gastos"><GastosPage /></PageGuard>} />
            <Route path="/flujo-caja" element={<PageGuard pageKey="flujo_caja"><FlujoCajaPage /></PageGuard>} />
            <Route path="/nomina" element={<PageGuard pageKey="nomina"><NominaPage /></PageGuard>} />
            <Route path="/gestiones" element={<PageGuard pageKey="gestiones"><DetalleGestionesPage /></PageGuard>} />
            <Route path="/planillas" element={<PageGuard pageKey="planillas"><PlanillasPage /></PageGuard>} />
            <Route path="/buscar" element={<PageGuard pageKey="buscar"><BuscarPaquetePage /></PageGuard>} />
            <Route path="/direcciones" element={<PageGuard pageKey="direcciones"><AjusteDireccionesPage /></PageGuard>} />
            <Route path="/pendientes-entrega" element={<PageGuard pageKey="pendientes_entrega"><PendientesEntregaPage /></PageGuard>} />
            <Route path="/devoluciones" element={<PageGuard pageKey="devoluciones"><DevolucionesPage /></PageGuard>} />
            <Route path="/admin/usuarios-roles" element={<AdminOnlyRoute><UsuariosRolesPage /></AdminOnlyRoute>} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
