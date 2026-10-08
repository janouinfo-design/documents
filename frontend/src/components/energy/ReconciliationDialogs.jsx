import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { justifyFuelReconciliation, updateReconciliationSettings } from "@/lib/api";
import { apiError, FormError } from "@/lib/fuelStatements";

// Justification humaine motivée d'un écart : explique, ne corrige jamais (achats / CAN / ASTRA / écart inchangés)
export function JustifyDialog({ item, open, onOpenChange }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setReason(""); setError(null); } }, [open, item?.vehicle_id]);
  if (!item) return null;
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await justifyFuelReconciliation(item.vehicle_id, item.period_month, { reason: reason.trim() });
      toast.success("Justification enregistrée (l'écart reste affiché tel quel)");
      qc.invalidateQueries({ queryKey: ["fuel-reconciliations"] });
      onOpenChange(false);
    } catch (e) { const m = apiError(e); setError(m); toast.error(m); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-reconciliation-justify-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Justifier l'écart — {item.plaque || item.vehicle_id} · {item.period_month}</DialogTitle>
          <DialogDescription>
            Écart achats − consommation CAN : <b>{item.ecart_l ?? "N/A"} L</b> ({item.ecart_pct ?? "N/A"} %) · statut {item.status}. La justification explique l'écart et reste visible ; elle ne modifie ni les achats, ni la mesure CAN, ni la référence ASTRA.
            {item.justification?.reason ? <> Justification actuelle : « {item.justification.reason} » ({item.justification.by}).</> : null}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif (obligatoire, ≥ 3 caractères)</Label>
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-reconciliation-justify-motif" />
        </div>
        <FormError error={error} testId="fuel-reconciliation-justify-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-reconciliation-justify-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-reconciliation-justify-confirm">Confirmer la justification</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Seuils tenant de rapprochement : null par défaut (aucune valeur métier injectée) ; vide = seuil désactivé
export function ThresholdsDialog({ settings, rule, open, onOpenChange }) {
  const qc = useQueryClient();
  const [pct, setPct] = useState("");
  const [litres, setLitres] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setPct(settings?.threshold_pct ?? ""); setLitres(settings?.threshold_l ?? ""); setError(null); } }, [open, settings]);
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      await updateReconciliationSettings({ threshold_pct: pct === "" ? null : Number(pct), threshold_l: litres === "" ? null : Number(litres) });
      toast.success("Seuils de rapprochement enregistrés");
      qc.invalidateQueries({ queryKey: ["fuel-reconciliation-settings"] });
      qc.invalidateQueries({ queryKey: ["fuel-reconciliations"] });
      onOpenChange(false);
    } catch (e) { const m = apiError(e); setError(m); toast.error(m); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-reconciliation-thresholds-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Seuils de rapprochement</DialogTitle>
          <DialogDescription>Aucun seuil n'est pré-rempli : tant qu'ils sont vides, les rapprochements restent <b>INDICATIF</b>. {rule?.label}</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1"><Label className="text-xs text-slate-500">Seuil % (vide = désactivé)</Label><Input type="number" min="0" step="0.1" value={pct} onChange={(e) => setPct(e.target.value)} data-testid="fuel-reconciliation-threshold-pct" /></div>
          <div className="space-y-1"><Label className="text-xs text-slate-500">Seuil litres (vide = désactivé)</Label><Input type="number" min="0" step="0.1" value={litres} onChange={(e) => setLitres(e.target.value)} data-testid="fuel-reconciliation-threshold-l" /></div>
        </div>
        <FormError error={error} testId="fuel-reconciliation-thresholds-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-reconciliation-thresholds-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-reconciliation-thresholds-save">Enregistrer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
