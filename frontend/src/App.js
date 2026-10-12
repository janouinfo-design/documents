import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { VehicleDrawerProvider } from "@/context/VehicleDrawerContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { can, isDriver, isConsoleMode, moduleOn, DRIVER_HOME } from "@/lib/rbac";
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
import AdminToolsPage from "@/pages/AdminToolsPage";
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
// Modules : route absente si le module est désactivé pour le client (le serveur répond 403 MODULE_DISABLED de toute façon).
function RoleRoutes() {
  const { user } = useAuth();
  const on = (key) => moduleOn(user, key);
  if (isDriver(user)) {
    return (
      <Routes>
        {on("energy") && <Route path="/mes-pleins" element={<MyFuelPage />} />}
        {on("fines") && <Route path="/mes-amendes" element={<MyFinesPage />} />}
        <Route path="/mes-vehicules" element={<MyVehiclesPage />} />
        <Route path="*" element={<Navigate to={on("energy") ? DRIVER_HOME : "/mes-vehicules"} replace />} />
      </Routes>
    );
  }
  if (isConsoleMode(user)) {
    return (
      <Routes>
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/admin/outils" element={<AdminToolsPage />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    );
  }
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      {on("vehicles") && <Route path="/vehicules" element={<Vehicles />} />}
      {on("vehicles") && can(user, "pages.archives") && <Route path="/archives" element={<ArchivesPage />} />}
      {on("documents") && <Route path="/scan/:vehicleId" element={<ScanPage />} />}
      {on("documents") && <Route path="/documents" element={<DocumentsPage />} />}
      {on("deadlines") && <Route path="/timeline" element={<TimelinePage />} />}
      {on("costs") && <Route path="/couts" element={<CostsPage />} />}
      {on("energy") && <Route path="/energie" element={<EnergyPage />} />}
      {on("energy") && <Route path="/energie/cartes" element={<FuelCardsPage />} />}
      {on("energy") && can(user, "pages.imports") && <Route path="/energie/imports" element={<FuelImportsPage />} />}
      {on("energy") && <Route path="/energie/anomalies" element={<FuelAnomaliesPage />} />}
      {on("energy") && <Route path="/energie/rapprochements" element={<FuelReconciliationsPage />} />}
      {on("energy") && can(user, "pages.statements") && <Route path="/energie/releves" element={<FuelStatementsPage />} />}
      {on("drivers") && <Route path="/conducteurs" element={<DriversPage />} />}
      {on("fines") && <Route path="/amendes" element={<FinesPage />} />}
      {on("ai") && can(user, "ai.use") && <Route path="/assistant" element={<AiAssistantPage />} />}
      {on("alerts") && <Route path="/alertes" element={<AlertsPage />} />}
      {on("integrity") && can(user, "pages.integrity") && <Route path="/integrite" element={<IntegrityPage />} />}
      {can(user, "console") && <Route path="/admin" element={<AdminPage />} />}
      {can(user, "console") && <Route path="/admin/outils" element={<AdminToolsPage />} />}
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
