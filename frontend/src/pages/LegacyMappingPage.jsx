import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, GitMerge } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import { getLegacyVehicleMap, getVehicles } from "@/lib/api";
import QueryErrorState from "@/components/QueryErrorState";
import LegacyInputBox from "@/components/legacy/LegacyInputBox";
import LegacyRow from "@/components/legacy/LegacyRow";
import LegacyOverrideDialog from "@/components/legacy/LegacyOverrideDialog";
import { cn } from "@/lib/utils";

const FILTERS = [
  { key: "pending", label: "En attente" },
  { key: "confirmed", label: "Confirmées" },
  { key: "rejected", label: "Rejetées" },
  { key: "all", label: "Toutes" },
];

export default function LegacyMappingPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canWrite = can(user, "legacy.write");
  const [filter, setFilter] = useState("pending");
  const [conflict, setConflict] = useState(null);
  const params = filter === "all" ? {} : { status: filter };
  const { data, isLoading, error } = useQuery({ queryKey: ["legacy-vehicle-map", filter], queryFn: () => getLegacyVehicleMap(params) });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const refresh = () => qc.invalidateQueries({ queryKey: ["legacy-vehicle-map"] });
  const counts = data?.counts || {};

  return (
    <div className="space-y-6" data-testid="legacy-page">
      <div>
        <h1 className="flex items-center gap-3 font-display text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
          <GitMerge className="h-7 w-7 text-slate-400" /> Correspondances legacy
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          Journal de bord → Documents. Chaque véhicule Journal est rattaché à un véhicule Documents <strong>par confirmation humaine</strong> :
          jamais par plaque automatiquement, jamais par tracker comme identité historique. Aucune donnée métier n'est migrée ici.
        </p>
      </div>
      <LegacyInputBox canWrite={canWrite} onStaged={refresh} />
      <section className="rounded-2xl border border-slate-200 bg-white" data-testid="legacy-map-section">
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3" data-testid="legacy-counts">
          {FILTERS.map((f) => (
            <button key={f.key} data-testid={`legacy-filter-${f.key}`} onClick={() => setFilter(f.key)}
              className={cn("rounded-full border px-3 py-1 text-xs font-semibold transition-colors",
                filter === f.key ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-600 hover:border-slate-400")}>
              {f.label}{f.key !== "all" && counts[f.key] !== undefined ? ` · ${counts[f.key]}` : ""}
            </button>
          ))}
        </div>
        {error ? <div className="p-5"><QueryErrorState error={error} /></div>
          : isLoading ? <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
          : !data?.rows?.length ? (
            <p className="p-8 text-center text-sm text-slate-400" data-testid="legacy-empty">Aucune correspondance dans cette vue.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-left">
                <thead className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  <tr><th className="px-3 py-2">Véhicule Journal</th><th className="px-3 py-2">Statut</th><th className="px-3 py-2">Véhicule Documents</th><th className="px-3 py-2">Actions</th></tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <LegacyRow key={`${r.legacy_source}-${r.legacy_vehicle_id}`} row={r} vehicles={vehicles} canWrite={canWrite}
                      onChanged={refresh} onConflict={setConflict} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>
      <LegacyOverrideDialog conflict={conflict} onClose={() => setConflict(null)} onDone={refresh} />
    </div>
  );
}
