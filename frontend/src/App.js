import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { VehicleDrawerProvider } from "@/context/VehicleDrawerContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import ErrorBoundary from "@/components/ErrorBoundary";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import TimelinePage from "@/pages/TimelinePage";
import AlertsPage from "@/pages/AlertsPage";
import Login from "@/pages/Login";
import IntegrityPage from "@/pages/IntegrityPage";
import AdminPage from "@/pages/AdminPage";

function Protected({ children }) {
  const { user, ssoPending } = useAuth();
  if (user === undefined || ssoPending)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" data-testid="auth-loading" />
        {ssoPending && <p className="text-sm text-slate-500" data-testid="sso-pending">Ouverture de Documents…</p>}
      </div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return children;
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
                        <Routes>
                          <Route path="/" element={<Dashboard />} />
                          <Route path="/vehicules" element={<Vehicles />} />
                          <Route path="/timeline" element={<TimelinePage />} />
                          <Route path="/alertes" element={<AlertsPage />} />
                          <Route path="/integrite" element={<IntegrityPage />} />
                          <Route path="/admin" element={<AdminPage />} />
                        </Routes>
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
