import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { suggestReservoir, applyReservoir } from "@/lib/api";
import { notifyNavixyPush } from "@/lib/navixyFeedback";

export default function ReservoirSuggestDialog({ vehicle, open, onOpenChange, onSaved }) {
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
    suggestReservoir(vehicle.id)
      .then((s) => { setSuggestion(s); setValue(String(s.value_l)); })
      .catch((e) => setError(e?.response?.data?.detail || "Estimation indisponible"))
      .finally(() => setLoading(false));
  }, [open, vehicle?.id]);

  const apply = async () => {
    const v = Number(value);
    if (!v || v < 10 || v > 500) {
      toast.error("Valeur hors plage plausible (10–500 L)");
      return;
    }
    setApplying(true);
    try {
      const r = await applyReservoir(vehicle.id, v);
      toast.success(`Capacité réservoir enregistrée : ${v} L`);
      notifyNavixyPush(r?.navixy_push, vehicle.id);
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
      <DialogContent data-testid="reservoir-suggest-dialog" className="w-[calc(100vw-1rem)] max-w-md rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Sparkles className="h-5 w-5 text-slate-500" /> Capacité réservoir — suggestion IA
          </DialogTitle>
          <DialogDescription>
            {vehicle?.marque} {vehicle?.modele} · {vehicle?.plaque} — estimation constructeur, rien n'est écrit sans votre validation.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-500" data-testid="reservoir-loading">
            <Loader2 className="h-4 w-4 animate-spin" /> Recherche de la donnée constructeur…
          </div>
        )}
        {error && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="reservoir-error">
            {error}
          </p>
        )}

        {suggestion && (
          <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Valeur estimée</p>
                {suggestion.confidence != null && (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                    Confiance {Math.round(suggestion.confidence * 100)} %
                  </span>
                )}
              </div>
              <p className="mt-1 font-display text-3xl font-bold text-slate-900" data-testid="reservoir-suggested-value">
                {suggestion.value_l} L
              </p>
              {suggestion.rationale && <p className="mt-1.5 text-xs text-slate-500">{suggestion.rationale}</p>}
              {suggestion.current_value ? (
                <p className="mt-1.5 text-xs font-medium text-amber-700">
                  Valeur actuelle sur la fiche : {suggestion.current_value} L — elle sera remplacée si vous appliquez.
                </p>
              ) : null}
            </div>
            <p className="flex items-start gap-1.5 text-xs text-slate-500">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
              Estimation IA (la capacité ne figure pas sur la carte grise). Corrigez si besoin, puis appliquez.
            </p>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                step="0.5"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                className="h-9 w-28"
                data-testid="reservoir-value-input"
              />
              <span className="text-sm text-slate-500">L</span>
            </div>
          </div>
        )}

        <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
          <Button variant="outline" data-testid="reservoir-cancel-btn" onClick={() => onOpenChange(false)}>Annuler</Button>
          {suggestion && (
            <Button data-testid="reservoir-apply-btn" onClick={apply} disabled={applying}
                    className="gap-2 bg-emerald-600 hover:bg-emerald-700">
              {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Appliquer {Number(value) > 0 ? `${Number(value)} L` : ""}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
