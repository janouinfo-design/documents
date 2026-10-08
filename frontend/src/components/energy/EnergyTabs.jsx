import { NavLink } from "react-router-dom";
import { Fuel, CreditCard, Upload, AlertTriangle, Scale, FileCheck2 } from "lucide-react";
import { cn } from "@/lib/utils";

const TABS = [
  { to: "/energie", label: "Transactions", icon: Fuel, testId: "energy-tab-transactions", end: true },
  { to: "/energie/cartes", label: "Cartes", icon: CreditCard, testId: "energy-tab-cards" },
  { to: "/energie/imports", label: "Imports", icon: Upload, testId: "energy-tab-imports" },
  { to: "/energie/anomalies", label: "Anomalies", icon: AlertTriangle, testId: "energy-tab-anomalies" },
  { to: "/energie/rapprochements", label: "Rapprochements", icon: Scale, testId: "energy-reconciliations-tab" },
  { to: "/energie/releves", label: "Relevés / Décomptes", icon: FileCheck2, testId: "energy-statements-tab" },
];

// Sous-navigation du module Énergie (spec §2.10 : onglets d'Énergie, pas d'entrée principale ; Lot G ajoute Rapprochements + Relevés / Décomptes)
export default function EnergyTabs() {
  return (
    <nav className="flex gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-white p-1 shadow-sm" data-testid="energy-tabs">
      {TABS.map(({ to, label, icon: Icon, testId, end }) => (
        <NavLink key={to} to={to} end={end} data-testid={testId}
          className={({ isActive }) => cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
            isActive ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100")}>
          <Icon className="h-4 w-4" /> {label}
        </NavLink>
      ))}
    </nav>
  );
}
