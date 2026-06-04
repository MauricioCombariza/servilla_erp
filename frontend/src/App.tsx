import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { AppShell } from "@/components/layout/AppShell";
import { Login } from "@/pages/Login";
import { ClientesPage } from "@/pages/clientes/ClientesPage";
import { PersonalPage } from "@/pages/personal/PersonalPage";
import { OrdenesPage } from "@/pages/ordenes/OrdenesPage";
import { CargaMasivaPage } from "@/pages/ordenes/CargaMasivaPage";
import { ResumenPage } from "@/pages/facturacion/ResumenPage";
import { FacturasEmitidasPage } from "@/pages/facturacion/FacturasEmitidasPage";
import { PlanillasPage } from "@/pages/planillas/PlanillasPage";
import { DetalleGestionesPage } from "@/pages/gestiones/DetalleGestionesPage";
import { ReportesPage } from "@/pages/reportes/ReportesPage";
import { Placeholder } from "@/pages/Placeholder";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  return token ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<Navigate to="/clientes" replace />} />
            <Route path="/clientes" element={<ClientesPage />} />
            <Route path="/personal" element={<PersonalPage />} />
            <Route path="/ordenes" element={<OrdenesPage />} />
            <Route path="/ordenes/carga-masiva" element={<CargaMasivaPage />} />
            <Route path="/facturacion" element={<ResumenPage />} />
            <Route path="/facturacion/emitidas" element={<FacturasEmitidasPage />} />
            <Route path="/facturacion/*" element={<Placeholder />} />
            <Route path="/reportes" element={<ReportesPage />} />
            <Route path="/labores" element={<Placeholder />} />
            <Route path="/pagos-mensajeros" element={<Placeholder />} />
            <Route path="/facturas-transporte" element={<Placeholder />} />
            <Route path="/gastos" element={<Placeholder />} />
            <Route path="/flujo-caja" element={<Placeholder />} />
            <Route path="/nomina" element={<Placeholder />} />
            <Route path="/gestiones" element={<DetalleGestionesPage />} />
            <Route path="/planillas" element={<PlanillasPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
