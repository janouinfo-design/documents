import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { decideFuelAnomaly } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";
import { DECISIONS, ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";
import { chfExact, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";

// Décision humaine motivée sur une anomalie : justifier / corriger / rejeter — l'anomalie reste visible dans l'historique
export default function AnomalyDecisionDialog({ anomaly, open, onOpenChange, onDone }) {
  const qc = useQueryClient();
  const [decision, setDecision] = useState("justify");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setDecision("justify"); setReason(""); } }, [open, anomaly?.id]);
  if (!anomaly) return null;
  const tx = anomaly.transaction || {};
  const submit = async () => {
    setBusy(true);
    try {
      const res = await decideFuelAnomaly(anomaly.id, { decision, reason: reason.trim() });
      toast.success(`Anomalie ${res.status_label?.toLowerCase() || res.status}`);
      qc.invalidateQueries({ queryKey: ["fuel-anomalies"] });
      qc.invalidateQueries({ queryKey: ["fuel-tx"] });
      qc.invalidateQueries({ queryKey: ["energy"] });
      onDone?.(res);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-anomaly-justify-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Décider — {ANOMALY_TYPE_LABELS[anomaly.type] || anomaly.label}</DialogTitle>
          <DialogDescription>
            {tx.date ? `${dateFr(tx.date)}${tx.heure ? ` ${tx.heure}` : ""}` : ""} · {tx.station || "—"} · {tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : "—"}{anomaly.plaque ? ` · ${anomaly.plaque}` : ""}{anomaly.card_label ? ` · ${anomaly.card_label}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" data-testid="fuel-anomaly-justify-explanation">{anomaly.explanation}</p>
          <div className="grid grid-cols-3 gap-2" data-testid="fuel-anomaly-decision-options">
            {DECISIONS.map((d) => (
              <button key={d.code} type="button" onClick={() => setDecision(d.code)} data-testid={`fuel-anomaly-decision-${d.code}`}
                className={cn("rounded-lg border px-2 py-2 text-left transition-colors", decision === d.code ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:bg-slate-50")}>
                <p className="text-sm font-bold">{d.label}</p>
                <p className="text-[11px] opacity-80">{d.hint}</p>
              </button>
            ))}
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Motif (obligatoire — conservé avec l'acteur et la date)</Label>
            <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-anomaly-justify-motif" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-anomaly-justify-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-anomaly-justify-confirm">Confirmer la décision</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
