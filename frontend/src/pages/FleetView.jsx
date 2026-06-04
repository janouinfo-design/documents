import { useQuery } from "@tanstack/react-query";
import { Radio, History, FileText, Truck } from "lucide-react";
import { getVehicles } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { Button } from "@/components/ui/button";
import StatusBadge from "@/components/StatusBadge";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

export default function FleetView({ mode = "live" }) {
  const { openVehicle } = useVehicleDrawer();
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });

  const isLive = mode === "live";
  const Icon = isLive ? Radio : History;

  return (
    <div className="space-y-6 animate-fade-in" data-testid={`fleet-view-${mode}`}>
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-900 text-white">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            {isLive ? "Suivi Live" : "Historique"}
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Depuis chaque véhicule, ouvrez instantanément l'onglet{" "}
            <span className="font-semibold text-slate-700">Administration</span> pour accéder à tous
            ses documents et coûts administratifs.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {vehicles.map((v) => {
          const m = v.metrics || {};
          return (
            <div key={v.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" data-testid={`fleet-card-${v.plaque.replace(/\s/g, "")}`}>
              <div className="relative h-36 bg-slate-100">
                {v.photo_url ? (
                  <img src={v.photo_url} alt={v.plaque} className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full items-center justify-center text-slate-300"><Truck className="h-8 w-8" /></div>
                )}
                {isLive && (
                  <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-emerald-500 px-2.5 py-1 text-[11px] font-semibold text-white">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> En ligne
                  </span>
                )}
              </div>
              <div className="space-y-3 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-slate-900">{v.plaque}</p>
                    <p className="text-xs text-slate-500">{v.marque} {v.modele} · {fmtKm(v.kilometrage)}</p>
                  </div>
                  <StatusBadge level={m.overall} />
                </div>
                <Button
                  variant="outline"
                  className="w-full justify-center gap-2 border-slate-200"
                  onClick={() => openVehicle(v.id)}
                  data-testid={`admin-btn-${v.plaque.replace(/\s/g, "")}`}
                >
                  <FileText className="h-4 w-4" /> Administration
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
