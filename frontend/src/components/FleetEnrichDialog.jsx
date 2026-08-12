import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Database, Check, AlertTriangle, RefreshCw } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { enrichFleet, applyTechnicalEnrichment } from "@/lib/api";

const STATUS_LABELS = {
  missing_homologation: "Sans n° d'homologation ni VIN exploitable",
  not_found: "Introuvable dans les données ASTRA",
  ambiguous_vin: "VIN trop ambigu — renseignez l'homologation",
  not_imported: "Données non importées",
};

export default function FleetEnrichDialog({ open, onOpenChange }) {
  const qc = useQueryClient();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({});
  const [applying, setApplying] = useState(false);
  const [progress, setProgress] = useState(0);

  const applicableFields = (r) => (r.fields || []).filter((f) => !f.conflict);
  const isApplicable = (r) => r.status === "found" && !r.requires_variant_choice && applicableFields(r).length > 0;

  const search = async () => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await enrichFleet();
      setData(res);
      setSelected(Object.fromEntries(res.results.filter(isApplicable).map((r) => [r.vehicle_id, true])));
    } catch (e) {
      setError(e?.response?.data?.detail || "Recherche impossible — réessayez plus tard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const selectedRows = (data?.results || []).filter((r) => isApplicable(r) && selected[r.vehicle_id]);

  const apply = async () => {
    setApplying(true);
    setProgress(0);
    let vehiclesUpdated = 0;
    let fieldsApplied = 0;
    try {
      for (const r of selectedRows) {
        const fields = Object.fromEntries(applicableFields(r).map((f) => [f.field, f.value]));
        const res = await applyTechnicalEnrichment(r.vehicle_id, {
          fields,
          matched_by: r.matched_by,
          retrieved_at: r.retrieved_at,
          provider: r.provider,
        });
        if (res.applied > 0) {
          vehiclesUpdated += 1;
          fieldsApplied += res.applied;
        }
        setProgress((p) => p + 1);
      }
      toast.success(
        vehiclesUpdated > 0
          ? `${vehiclesUpdated} véhicule(s) mis à jour — ${fieldsApplied} champ(s) appliqué(s)`
          : "Aucune modification nécessaire (fiches déjà à jour)"
      );
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur pendant l'application");
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !applying && onOpenChange(o)}>
      <DialogContent data-testid="fleet-enrich-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-3xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Database className="h-5 w-5 text-slate-500" /> Enrichir la flotte — Base officielle ASTRA/OFROU
          </DialogTitle>
          <DialogDescription>
            Recherche par n° d'homologation ou VIN pour chaque véhicule. Seuls les champs sans conflit sont appliqués — les conflits restent à arbitrer dans chaque fiche. Rien n'est enregistré sans votre validation.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex flex-col items-center gap-3 py-12" data-testid="fleet-loading">
            <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            <p className="text-sm font-medium text-slate-700">Recherche dans la base locale pour toute la flotte…</p>
          </div>
        )}

        {error && (
          <div className="space-y-4 py-4 text-center" data-testid="fleet-error">
            <AlertTriangle className="mx-auto h-8 w-8 text-red-400" />
            <p className="text-sm text-slate-600">{error}</p>
            <Button data-testid="fleet-retry-btn" onClick={search} variant="outline" className="gap-2">
              <RefreshCw className="h-4 w-4" /> Réessayer
            </Button>
          </div>
        )}

        {data && !loading && (
          <div className="space-y-4">
            <p className="text-sm text-slate-500" data-testid="fleet-summary">
              <span className="font-semibold text-slate-800">{data.found}</span> véhicule(s) trouvé(s) sur {data.total} dans les registres officiels.
            </p>
            <div className="max-h-[46vh] space-y-2 overflow-y-auto pr-1">
              {data.results.map((r) => {
                const app = applicableFields(r);
                const conflicts = (r.fields || []).filter((f) => f.conflict);
                const applicable = isApplicable(r);
                return (
                  <label
                    key={r.vehicle_id}
                    data-testid={`fleet-row-${(r.plaque || r.vehicle_id).replace(/\s/g, "")}`}
                    className={`flex items-start gap-3 rounded-xl border p-3 ${applicable ? "border-slate-200 bg-white" : "border-slate-100 bg-slate-50 opacity-80"}`}
                  >
                    <Checkbox
                      className="mt-0.5"
                      data-testid={`fleet-select-${(r.plaque || r.vehicle_id).replace(/\s/g, "")}`}
                      disabled={!applicable}
                      checked={applicable && !!selected[r.vehicle_id]}
                      onCheckedChange={(ch) => setSelected((s) => ({ ...s, [r.vehicle_id]: !!ch }))}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-baseline gap-x-2">
                        <span className="text-sm font-semibold text-slate-900">{r.plaque}</span>
                        <span className="text-xs text-slate-500">{[r.marque, r.modele].filter(Boolean).join(" ")}</span>
                        {r.match && (
                          <span className="text-xs text-slate-400">→ {[r.match.make, r.match.model].filter(Boolean).join(" ")}</span>
                        )}
                      </span>
                      {r.status === "found" ? (
                        <span className="mt-0.5 block text-xs text-slate-500">
                          {r.requires_variant_choice ? (
                            <span className="text-amber-700">Plusieurs variantes — choisissez dans la fiche (Carte grise → Base technique)</span>
                          ) : (
                            <>
                              {app.length > 0
                                ? `${app.length} champ(s) à appliquer : ${app.map((f) => f.label).join(", ")}`
                                : "Fiche déjà à jour"}
                              {conflicts.length > 0 && (
                                <span className="text-amber-700"> · {conflicts.length} conflit(s) à arbitrer dans la fiche</span>
                              )}
                            </>
                          )}
                        </span>
                      ) : (
                        <span className="mt-0.5 block text-xs text-slate-400">{STATUS_LABELS[r.status] || r.message}</span>
                      )}
                    </span>
                  </label>
                );
              })}
            </div>
            <p className="text-xs text-slate-400">
              Provenance et historique enregistrés pour chaque champ. Les valeurs mesurées via CAN/OBD ne sont jamais remplacées.
            </p>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
              {applying && (
                <span className="mr-auto text-xs text-slate-500" data-testid="fleet-progress">
                  {progress}/{selectedRows.length} véhicule(s) traité(s)…
                </span>
              )}
              <Button variant="outline" data-testid="fleet-cancel-btn" disabled={applying} onClick={() => onOpenChange(false)}>
                Annuler
              </Button>
              <Button
                data-testid="fleet-apply-btn"
                onClick={apply}
                disabled={applying || selectedRows.length === 0}
                className="gap-2 bg-emerald-600 hover:bg-emerald-700"
              >
                {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Appliquer à {selectedRows.length} véhicule(s)
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
