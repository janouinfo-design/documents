import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Plus, ChevronRight, Truck, Loader2, FileDown, Database, Fuel } from "lucide-react";
import { getVehicles, conformityReportUrl, costsCsvUrl, photoSrc } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import StatusBadge from "@/components/StatusBadge";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import { useAuth } from "@/context/AuthContext";
import NewVehicleDialog from "@/components/NewVehicleDialog";
import SyncButton from "@/components/SyncButton";
import ConfigBanner from "@/components/ConfigBanner";
import AstraStatusDialog from "@/components/AstraStatusDialog";
import FleetEnrichDialog from "@/components/FleetEnrichDialog";
import FleetConsumptionDialog from "@/components/FleetConsumptionDialog";
import QueryErrorState from "@/components/QueryErrorState";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { lvl } from "@/lib/status";
import { cn } from "@/lib/utils";

export default function Vehicles() {
  const { openVehicle } = useVehicleDrawer();
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [q, setQ] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [astraOpen, setAstraOpen] = useState(false);
  const [fleetOpen, setFleetOpen] = useState(false);
  const [consoOpen, setConsoOpen] = useState(false);
  const { data: vehicles = [], isLoading, isError, error } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });

  const filtered = vehicles.filter((v) => {
    const hay = `${v.plaque} ${v.marque} ${v.modele} ${v.responsable} ${v.base} ${v.groupe}`.toLowerCase();
    return hay.includes(q.toLowerCase());
  });

  return (
    <div className="space-y-6 animate-fade-in" data-testid="vehicles-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Véhicules
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {vehicles.length} véhicule{vehicles.length > 1 ? "s" : ""} · cliquez sur une plaque pour ouvrir la fiche administrative.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              data-testid="vehicle-search"
              placeholder="Rechercher…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="w-full pl-9 sm:w-64"
            />
          </div>
          {!readOnly && (
            <Button data-testid="add-vehicle-btn" onClick={() => setCreateOpen(true)} className="gap-2 bg-slate-900 hover:bg-slate-800">
              <Plus className="h-4 w-4" /> Véhicule
            </Button>
          )}
          <Button
            data-testid="conso-open-btn"
            variant="outline"
            className="gap-2 border-slate-300 text-slate-700 hover:bg-slate-50"
            onClick={() => setConsoOpen(true)}
          >
            <Fuel className="h-4 w-4" /> Consommation
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button data-testid="astra-menu-btn" variant="outline" className="gap-2 border-slate-300 text-slate-700 hover:bg-slate-50">
                <Database className="h-4 w-4" /> Base technique
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem data-testid="fleet-enrich-menu-item" onClick={() => setFleetOpen(true)}>
                Enrichir la flotte (ASTRA)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="astra-status-menu-item" onClick={() => setAstraOpen(true)}>
                État des données officielles
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button data-testid="export-menu-btn" variant="outline" className="gap-2 border-slate-300 text-slate-700 hover:bg-slate-50">
                <FileDown className="h-4 w-4" /> Exporter
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem data-testid="report-pdf-btn" onClick={() => window.open(conformityReportUrl(), "_blank", "noopener")}>
                Rapport de conformité (PDF)
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="report-csv-btn" onClick={() => window.open(costsCsvUrl(), "_blank", "noopener")}>
                Coûts de la flotte (CSV)
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <SyncButton />
        </div>
      </div>

      <ConfigBanner />

      {isError && <QueryErrorState error={error} testId="vehicles-error" />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left">
                {["Véhicule", "Affectation", "Responsable", "Leasing", "Assurance", "Contrôle", ""].map((h) => (
                  <th key={h} className="px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading && (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">Chargement…</td></tr>
              )}
              {!isLoading && filtered.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-sm text-slate-400">Aucun véhicule trouvé.</td></tr>
              )}
              {filtered.map((v) => {
                const m = v.metrics || {};
                return (
                  <tr key={v.id} className="group transition-colors hover:bg-slate-50" data-testid={`vehicle-row-${v.plaque.replace(/\s/g, "")}`}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="h-11 w-16 shrink-0 overflow-hidden rounded-md border border-slate-200 bg-slate-100">
                          {v.photo_url ? (
                            <img src={photoSrc(v.photo_url)} alt={v.plaque} className="h-full w-full object-cover" />
                          ) : (
                            <div className="flex h-full w-full items-center justify-center text-slate-300">
                              <Truck className="h-5 w-5" />
                            </div>
                          )}
                        </div>
                        <div>
                          <button
                            onClick={() => openVehicle(v.id)}
                            data-testid={`vehicle-plate-link-${v.plaque.replace(/\s/g, "")}`}
                            className="font-semibold text-slate-900 underline decoration-slate-300 decoration-1 underline-offset-2 transition-colors hover:decoration-slate-900"
                          >
                            {v.plaque}
                          </button>
                          <p className="text-xs text-slate-500">{[v.marque, v.modele].filter(Boolean).join(" ")}{v.annee ? ` · ${v.annee}` : ""}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-700">{v.base}</p>
                      <p className="text-xs text-slate-400">{v.groupe} · {fmtKm(v.kilometrage)}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{v.responsable}</td>
                    <td className="px-4 py-3"><StatusBadge level={m.leasing?.level} days={m.leasing?.days_remaining} showDays /></td>
                    <td className="px-4 py-3"><StatusBadge level={m.assurance?.level} days={m.assurance?.days_remaining} showDays /></td>
                    <td className="px-4 py-3"><StatusBadge level={m.controle?.level} days={m.controle?.days_remaining} showDays /></td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => openVehicle(v.id)}
                        data-testid={`open-vehicle-${v.plaque.replace(/\s/g, "")}`}
                        className={cn("inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-900 hover:text-white", m.compliant ? "" : `ring-1 ${lvl(m.overall).ring}`)}
                        aria-label="Ouvrir la fiche"
                      >
                        <ChevronRight className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <NewVehicleDialog open={createOpen} onOpenChange={setCreateOpen} />
      <AstraStatusDialog open={astraOpen} onOpenChange={setAstraOpen} />
      <FleetEnrichDialog open={fleetOpen} onOpenChange={setFleetOpen} />
      <FleetConsumptionDialog open={consoOpen} onOpenChange={setConsoOpen} />
    </div>
  );
}
