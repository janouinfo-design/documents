import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Plus, Upload, FileCheck2, AlertTriangle, Layers } from "lucide-react";
import { getFuelImports } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import EnergyTabs from "@/components/energy/EnergyTabs";
import ImportJobsTable from "@/components/fuelimport/ImportJobsTable";
import ImportWizard from "@/components/fuelimport/ImportWizard";
import { Button } from "@/components/ui/button";

// Énergie › Importations : wizard CSV/XLSX (upload → mapping → preview → confirmation) + historique des imports
export default function FuelImportsPage() {
  const { user } = useAuth();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job");
  const mode = params.get("new") === "1";
  const setJob = (id, isNew = false) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("job", id); else n.delete("job"); if (isNew) n.set("new", "1"); else n.delete("new"); return n; }, { replace: true });
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fuel-imports"], queryFn: getFuelImports });
  const jobs = data?.items || [];
  const stats = {
    total: jobs.length, confirmed: jobs.filter((j) => j.status === "confirmed").length, pending: jobs.filter((j) => j.status !== "confirmed").length,
    imported: jobs.reduce((a, j) => a + (j.counts?.imported || 0), 0), review: jobs.reduce((a, j) => a + (j.counts?.unknown_vehicle || 0) + (j.counts?.unknown_card || 0), 0),
  };
  return (
    <div className="space-y-6 animate-fade-in" data-testid="fuel-imports-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Importations carburant</h2>
          <p className="mt-1 text-sm text-slate-500">Relevés fournisseurs CSV/XLSX → mapping explicite → preview (lecture) → confirmation. Chaque ligne importée devient un document sans justificatif (source du coût) et une transaction énergie.</p>
        </div>
        {isAdmin && (
          <Button size="sm" onClick={() => setJob(null, true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-import-new-btn">
            <Plus className="h-4 w-4" /> Nouvel import
          </Button>
        )}
      </div>
      <EnergyTabs />
      {isError && <QueryErrorState error={error} testId="fuel-imports-error" />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="fuel-imports-kpis">
        <KpiCard testId="fuel-imports-kpi-total" label="Imports" value={isLoading ? "—" : stats.total} icon={Layers} accent="slate" sub={`${stats.confirmed} confirmé(s)`} />
        <KpiCard testId="fuel-imports-kpi-pending" label="En attente" value={isLoading ? "—" : stats.pending} icon={Upload} accent="amber" sub="Mapping / preview non confirmés" />
        <KpiCard testId="fuel-imports-kpi-imported" label="Lignes importées" value={isLoading ? "—" : stats.imported} icon={FileCheck2} accent="emerald" sub="Transactions créées" />
        <KpiCard testId="fuel-imports-kpi-review" label="À vérifier" value={isLoading ? "—" : stats.review} icon={AlertTriangle} accent="rose" sub="Véhicule / carte non résolus" />
      </div>
      {(mode || jobId) && <ImportWizard jobId={jobId} isAdmin={isAdmin} onJobChange={(id) => setJob(id, !id)} />}
      <ImportJobsTable jobs={jobs} isLoading={isLoading} selectedId={jobId} onSelect={(id) => setJob(id)} />
    </div>
  );
}
