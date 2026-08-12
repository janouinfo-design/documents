import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Database, RefreshCw, CheckCircle2, XCircle, Clock } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getAstraStatus, astraImport } from "@/lib/api";

const fmtDate = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
};
const fmtNb = (n) => (n || 0).toLocaleString("fr-CH");

const RunBadge = ({ run }) => {
  if (!run) return <span className="text-xs text-slate-400">Jamais importé</span>;
  if (run.status === "done")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="h-3.5 w-3.5" /> {fmtDate(run.finished_at)}
      </span>
    );
  if (run.status === "running")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Import… {run.rows_read ? `${fmtNb(run.rows_read)} lignes` : ""}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
      <XCircle className="h-3.5 w-3.5" /> Échec
    </span>
  );
};

export default function AstraStatusDialog({ open, onOpenChange }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["astra-status"],
    queryFn: getAstraStatus,
    enabled: open,
    refetchInterval: (query) => (query.state.data?.import_running ? 3000 : false),
  });

  const startUpdate = async () => {
    try {
      await astraImport();
      toast.success("Mise à jour des données officielles lancée en arrière-plan");
      qc.invalidateQueries({ queryKey: ["astra-status"] });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de lancer la mise à jour");
    }
  };

  const datasets = data ? Object.entries(data.datasets || {}) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="astra-status-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-2xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Database className="h-5 w-5 text-slate-500" /> Données officielles ASTRA/OFROU
          </DialogTitle>
          <DialogDescription>
            Copie locale des registres d'homologation suisses — gratuite, sans clé API. Synchronisation mensuelle automatique.
          </DialogDescription>
        </DialogHeader>

        {isLoading && (
          <div className="flex justify-center py-10"><Loader2 className="h-7 w-7 animate-spin text-slate-400" /></div>
        )}

        {data && (
          <div className="space-y-4">
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-left">
                    {["Jeu de données", "Enregistrements", "Dernier import"].map((h) => (
                      <th key={h} className="px-3 py-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {datasets.map(([name, ds]) => (
                    <tr key={name} data-testid={`astra-dataset-row-${name}`}>
                      <td className="px-3 py-2.5 font-medium text-slate-800">{ds.label}</td>
                      <td className="px-3 py-2.5 tabular-nums text-slate-600">{fmtNb(ds.documents)}</td>
                      <td className="px-3 py-2.5"><RunBadge run={ds.last_run} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data.import_running && (
              <p data-testid="astra-import-running" className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                <Clock className="h-4 w-4" /> Un import est en cours — cette fenêtre se met à jour automatiquement.
              </p>
            )}
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-400">
                Source : opendata.astra.admin.ch · la mise à jour re-télécharge les fichiers récents puis ré-importe.
              </p>
              <Button
                data-testid="astra-update-btn"
                onClick={startUpdate}
                disabled={data.import_running}
                className="shrink-0 gap-2 bg-slate-900 hover:bg-slate-800"
              >
                {data.import_running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Mettre à jour les données
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
