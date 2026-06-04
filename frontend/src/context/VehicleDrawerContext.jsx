import { createContext, useContext, useState, useCallback } from "react";
import VehicleDrawer from "@/components/VehicleDrawer";

const VehicleDrawerCtx = createContext(null);

export const useVehicleDrawer = () => {
  const ctx = useContext(VehicleDrawerCtx);
  if (!ctx) return { openVehicle: () => {}, close: () => {} };
  return ctx;
};

export function VehicleDrawerProvider({ children }) {
  const [vehicleId, setVehicleId] = useState(null);
  const [open, setOpen] = useState(false);
  const [initialTab, setInitialTab] = useState("general");

  const openVehicle = useCallback((id, tab = "general") => {
    setVehicleId(id);
    setInitialTab(tab);
    setOpen(true);
  }, []);

  const close = useCallback(() => setOpen(false), []);

  return (
    <VehicleDrawerCtx.Provider value={{ openVehicle, close }}>
      {children}
      <VehicleDrawer
        open={open}
        onOpenChange={setOpen}
        vehicleId={vehicleId}
        initialTab={initialTab}
      />
    </VehicleDrawerCtx.Provider>
  );
}
