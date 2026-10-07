import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { setFineStatus } from "@/lib/api";
import { FINE_STATUSES, FINE_STATUS_META, PAID_STATUSES, fineStatusLabel, todayIso, errDetail } from "@/lib/fines";
import { FINE_QUERY_KEYS } from "@/components/fines/FinePaymentDialog";

// Changement de statut (10 valeurs, transitions libres, auditées) — motif obligatoire pour « Annulée » (D9).
export default function FineStatusControl({ doc, disabled }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState(null);
  const [motif, setMotif] = useState("");
  const [paidOn, setPaidOn] = useState(todayIso());
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  const current = doc?.fine_status;
  const isPaidTarget = PAID_STATUSES.includes(target);
  const reverting = !!target && PAID_STATUSES.includes(current) && !isPaidTarget && target !== "cloturee";
  const needsMotif = target === "annulee" || reverting;

  const open = (code) => { if (code === current) return; setTarget(code); setMotif(""); setPaidOn(doc?.paid_on || todayIso()); setRef(doc?.payment_ref || ""); };
  const confirm = async () => {
    setBusy(true);
    try {
      await setFineStatus(doc.id, { fine_status: target, motif: motif.trim() || null,
        ...(isPaidTarget ? { paid_on: paidOn || null, payment_ref: ref.trim() || null } : {}) });
      toast.success(`Statut : ${fineStatusLabel(current)} → ${fineStatusLabel(target)}`);
      FINE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      setTarget(null);
    } catch (e) {
      toast.error(errDetail(e, "Changement de statut impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Select value={current || ""} onValueChange={open} disabled={disabled}>
        <SelectTrigger data-testid="fine-status-select" className="h-9 w-full sm:w-64"><SelectValue placeholder="Statut" /></SelectTrigger>
        <SelectContent>
          {FINE_STATUSES.map((s) => (
            <SelectItem key={s} value={s} data-testid={`fine-status-option-${s}`}>
              <span className={`mr-2 inline-block h-2 w-2 rounded-full border ${FINE_STATUS_META[s].cls}`} />{FINE_STATUS_META[s].label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Dialog open={!!target} onOpenChange={(o) => !o && setTarget(null)}>
        <DialogContent className="max-w-md" data-testid="fine-status-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-lg">Passer en « {fineStatusLabel(target)} »</DialogTitle>
            <DialogDescription>
              {target === "annulee"
                ? "Amende annulée : exclue des coûts et des échéances actives, montant et document conservés. Motif obligatoire (D9)."
                : reverting ? "Dé-paiement (correction métier) : date, horodatage et référence de paiement effacés de la fiche, conservés dans l'historique. Motif obligatoire."
                : isPaidTarget ? "Statut payé : indiquez la date métier du paiement (jamais déduite de l'horodatage technique)."
                : "Transition auditée avec statut avant / après."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {isPaidTarget && (
              <>
                <div className="space-y-1"><Label className="text-xs text-slate-500">Date de paiement (métier)</Label>
                  <Input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} data-testid="fine-status-paid-on" /></div>
                <div className="space-y-1"><Label className="text-xs text-slate-500">Référence de paiement (optionnel)</Label>
                  <Input value={ref} onChange={(e) => setRef(e.target.value)} data-testid="fine-status-payment-ref" /></div>
              </>
            )}
            <div className="space-y-1">
              <Label className="text-xs text-slate-500">Motif {needsMotif ? "*" : "(optionnel)"}</Label>
              <Textarea rows={2} value={motif} onChange={(e) => setMotif(e.target.value)} data-testid="fine-status-motif"
                placeholder={target === "annulee" ? "Ex. : amende retirée par l'autorité, doublon, erreur de plaque…" : reverting ? "Ex. : paiement saisi par erreur, virement rejeté…" : "Contexte de la transition"} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)} data-testid="fine-status-cancel">Annuler</Button>
            <Button onClick={confirm} disabled={busy || (needsMotif && motif.trim().length < 3)} data-testid="fine-status-confirm"
              className={target === "annulee" ? "bg-red-600 hover:bg-red-700" : reverting ? "bg-amber-600 hover:bg-amber-700" : "bg-slate-900 hover:bg-slate-800"}>
              {busy ? "Enregistrement…" : "Confirmer"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
