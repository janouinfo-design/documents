import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setDocumentPaid } from "@/lib/api";
import { todayIso, errDetail } from "@/lib/fines";

export const FINE_QUERY_KEYS = ["fines", "fines-stats", "all-documents", "documents", "deadlines", "dashboard", "costs", "vehicle-costs"];

// Paiement : paid_on = DATE MÉTIER saisie (défaut aujourd'hui, modifiable) ; paid_at technique posé par le serveur ; réf. optionnelle.
export default function FinePaymentDialog({ doc, open, onOpenChange, onDone }) {
  const qc = useQueryClient();
  const [paidOn, setPaidOn] = useState(todayIso());
  const [ref, setRef] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setPaidOn(doc?.paid_on || todayIso()); setRef(doc?.payment_ref || ""); } }, [open, doc]);

  const submit = async () => {
    setBusy(true);
    try {
      await setDocumentPaid(doc.id, true, { paid_on: paidOn || null, payment_ref: ref.trim() || null });
      toast.success(`Amende marquée payée le ${paidOn}`);
      FINE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onDone?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(errDetail(e, "Paiement impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fine-payment-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Marquer l'amende comme payée</DialogTitle>
          <DialogDescription>La date saisie est la date métier du paiement ; l'horodatage technique est enregistré séparément.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Date de paiement (métier) *</Label>
            <Input type="date" value={paidOn} onChange={(e) => setPaidOn(e.target.value)} data-testid="fine-payment-paid-on" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Référence de paiement (optionnel)</Label>
            <Input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="N° de virement, QR, e-banking…" data-testid="fine-payment-ref" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fine-payment-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || !paidOn} className="bg-emerald-600 hover:bg-emerald-700" data-testid="fine-payment-confirm">
            {busy ? "Enregistrement…" : "Confirmer le paiement"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
