import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, Database, AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { suggestConso, applyConso } from "@/lib/api";

export default function ConsoSuggestDialog({ vehicle, open, onOpenChange, onSaved }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [suggestion, setSuggestion] = useState(null);
  const [value, setValue] = useState("");
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!open || !vehicle?.id) return;
    setLoading(true);
    setError(null);
    setSuggestion(null);
    suggestConso(vehicle.id)
      .then((s) => { setSuggestion(s); setValue(String(s.value_l_100km)); })
      .catch((e) => setError(e?.response?.data?.detail || "Donnée indisponible"))
      .finally(() => setLoading(false));
  }, [open, vehicle?.id]);

  const isAstra = suggestion?.source === "ASTRA_OFROU";

  const apply = async () => {
    const v = Number(value);
    if (!v || v < 1 || v > 40) {
      toast.error("Valeur hors plage plausible (1–40 L/100 km)");
      return;
    }
    setApplying(true);
    try {
      await applyConso(vehicle.id, {
        value_l_100km: v,
        norme: suggestion?.norme || null,
        source: suggestion?.source,
        matched_by: suggestion?.matched_by || null,
        retrieved_at: suggestion?.retrieved_at || null,
      });
      toast.success(`Conso officielle enregistrée : ${v} L/100 km`);
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'enregistrement");
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="conso-suggest-dialog" className="w-[calc(100vw-1rem)] max-w-md rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Database className="h-5 w-5 text-slate-500" /> Conso officielle — base ASTRA puis IA
          </DialogTitle>
          <DialogDescription>
            {vehicle?.marque} {vehicle?.modele} · {vehicle?.plaque} — base officielle ASTRA/OFROU en priorité,
            estimation IA en dernier recours. Rien n'est écrit sans votre validation.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500" data-testid="conso-loading">
            <Loader2 className="h-4 w-4 animate-spin" /> Recherche base officielle puis estimation…
          </div>
        )}
        {error && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="conso-error">
            {error}
          </p>
        )}

        {suggestion && (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Valeur proposée</p>
                {isAstra ? (
                  <span data-testid="conso-source-badge" className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                    Base officielle ASTRA/OFROU
                  </span>
                ) : (
                  <span data-testid="conso-source-badge" className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
                    Estimation IA{suggestion.confidence != null ? ` · ${Math.round(suggestion.confidence * 100)} %` : ""}
                  </span>
                )}
              </div>
              <p className="mt-1 font-display text-3xl font-bold text-slate-900" data-testid="conso-suggested-value">
                {suggestion.value_l_100km} L/100 km{suggestion.norme ? <span className="text-base font-semibold text-slate-400"> · {suggestion.norme}{isAstra ? "" : " (est.)"}</span> : null}
              </p>
              {suggestion.rationale && <p className="mt-1.5 text-xs text-slate-500">{suggestion.rationale}</p>}
              {suggestion.current_value ? (
                <p className="mt-1.5 text-xs font-medium text-amber-700">
                  Valeur actuelle sur la fiche : {suggestion.current_value} L/100 km — elle sera remplacée si vous appliquez.
                </p>
              ) : null}
            </div>
            {!isAstra && (
              <p className="flex items-start gap-1.5 text-xs text-slate-500">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                Aucune correspondance dans la base officielle (homologation/VIN manquants ou introuvables) —
                estimation IA marquée « (est.) ». Corrigez si besoin, puis appliquez.
              </p>
            )}
            <div className="flex items-center gap-2">
              <Input
                type="number"
                step="0.1"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="h-9 w-28"
                data-testid="conso-value-input"
              />
              <span className="text-sm text-slate-500">L/100 km</span>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <Button variant="outline" data-testid="conso-cancel-btn" onClick={() => onOpenChange(false)}>Annuler</Button>
          {suggestion && (
            <Button data-testid="conso-apply-btn" onClick={apply} disabled={applying}
                    className="gap-2 bg-emerald-600 hover:bg-emerald-700">
              {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Appliquer {Number(value) > 0 ? `${Number(value)} L/100 km` : ""}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
