import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { VehicleDrawerProvider } from "@/context/VehicleDrawerContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { can, isDriver, DRIVER_HOME } from "@/lib/rbac";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import TimelinePage from "@/pages/TimelinePage";
import CostsPage from "@/pages/CostsPage";
import EnergyPage from "@/pages/EnergyPage";
import AlertsPage from "@/pages/AlertsPage";
import Login from "@/pages/Login";
import IntegrityPage from "@/pages/IntegrityPage";
import AdminPage from "@/pages/AdminPage";
import DocumentsPage from "@/pages/DocumentsPage";
import ScanPage from "@/pages/ScanPage";
import ArchivesPage from "@/pages/ArchivesPage";
import LegacyMappingPage from "@/pages/LegacyMappingPage";
import DriversPage from "@/pages/DriversPage";
import FinesPage from "@/pages/FinesPage";
import FuelCardsPage from "@/pages/FuelCardsPage";
import FuelImportsPage from "@/pages/FuelImportsPage";
import FuelAnomaliesPage from "@/pages/FuelAnomaliesPage";
import FuelReconciliationsPage from "@/pages/FuelReconciliationsPage";
import FuelStatementsPage from "@/pages/FuelStatementsPage";
import MyFuelPage from "@/pages/MyFuelPage";
import MyFinesPage from "@/pages/MyFinesPage";
import MyVehiclesPage from "@/pages/MyVehiclesPage";
import AiAssistantPage from "@/pages/AiAssistantPage";
import SsoNotConfigured from "@/pages/SsoNotConfigured";
import { useLocation } from "react-router-dom";

function Protected({ children }) {
  const { user, ssoPending, ssoUnconfigured } = useAuth();
  const location = useLocation();
  if (ssoUnconfigured) return <SsoNotConfigured />;
  if (user === undefined || ssoPending)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" data-testid="auth-loading" />
        {ssoPending && <p className="text-sm text-slate-500" data-testid="sso-pending">Ouverture de Documents…</p>}
      </div>
    );
  if (!user) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return children;
}

// Lot H — routage par rôle (l'UI redirige, le serveur reste la seule protection : 403 / 404 indépendants de la navigation).
function RoleRoutes() {
  const { user } = useAuth();
  if (isDriver(user)) {
    return (
      <Routes>
        <Route path="/mes-pleins" element={<MyFuelPage />} />
        <Route path="/mes-amendes" element={<MyFinesPage />} />
        <Route path="/mes-vehicules" element={<MyVehiclesPage />} />
        <Route path="*" element={<Navigate to={DRIVER_HOME} replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/vehicules" element={<Vehicles />} />
      {can(user, "pages.archives") && <Route path="/archives" element={<ArchivesPage />} />}
      <Route path="/scan/:vehicleId" element={<ScanPage />} />
      <Route path="/documents" element={<DocumentsPage />} />
      <Route path="/timeline" element={<TimelinePage />} />
      <Route path="/couts" element={<CostsPage />} />
      <Route path="/energie" element={<EnergyPage />} />
      <Route path="/energie/cartes" element={<FuelCardsPage />} />
      {can(user, "pages.imports") && <Route path="/energie/imports" element={<FuelImportsPage />} />}
      <Route path="/energie/anomalies" element={<FuelAnomaliesPage />} />
      <Route path="/energie/rapprochements" element={<FuelReconciliationsPage />} />
      {can(user, "pages.statements") && <Route path="/energie/releves" element={<FuelStatementsPage />} />}
      <Route path="/conducteurs" element={<DriversPage />} />
      <Route path="/amendes" element={<FinesPage />} />
      {can(user, "ai.use") && <Route path="/assistant" element={<AiAssistantPage />} />}
      <Route path="/alertes" element={<AlertsPage />} />
      {can(user, "pages.integrity") && <Route path="/integrite" element={<IntegrityPage />} />}
      {can(user, "console") && <Route path="/admin" element={<AdminPage />} />}
      {can(user, "pages.legacy") && <Route path="/admin/correspondances" element={<LegacyMappingPage />} />}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <Protected>
                  <VehicleDrawerProvider>
                    <Layout>
                      <ErrorBoundary>
                        <RoleRoutes />
                      </ErrorBoundary>
                    </Layout>
                  </VehicleDrawerProvider>
                </Protected>
              }
            />
          </Routes>
          <Toaster position="top-right" richColors closeButton />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
