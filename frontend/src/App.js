import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { VehicleDrawerProvider } from "@/context/VehicleDrawerContext";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Vehicles from "@/pages/Vehicles";
import TimelinePage from "@/pages/TimelinePage";
import AlertsPage from "@/pages/AlertsPage";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <VehicleDrawerProvider>
          <Layout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/vehicules" element={<Vehicles />} />
              <Route path="/timeline" element={<TimelinePage />} />
              <Route path="/alertes" element={<AlertsPage />} />
            </Routes>
          </Layout>
          <Toaster position="top-right" richColors closeButton />
        </VehicleDrawerProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
