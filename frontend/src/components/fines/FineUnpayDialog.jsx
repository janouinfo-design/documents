import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { setDocumentPaid } from "@/lib/api";
import { errDetail } from "@/lib/fines";
import { FINE_QUERY_KEYS } from "@/components/fines/FinePaymentDialog";
import { dateFr } from "@/lib/format";

// Dé-paiement = correction métier : motif obligatoire, audit `fine_payment_reverted` (anciens paid_on/paid_at/payment_ref conservés dans l'historique).
export default function FineUnpayDialog({ doc, open, onOpenChange, onDone }) {
  const qc = useQueryClient();
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setMotif(""); }, [open]);

  const submit = async () => {
    setBusy(true);
    try {
      await setDocumentPaid(doc.id, false, { motif: motif.trim() });
      toast.success("Paiement annulé — l'amende est à nouveau à payer (correction auditée)");
      FINE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      qc.invalidateQueries({ queryKey: ["fine-history", doc.id] });
      onDone?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(errDetail(e, "Annulation du paiement impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fine-unpay-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Annuler le paiement</DialogTitle>
          <DialogDescription>
            Correction métier : l'amende repasse « À payer » ; la date de paiement{doc?.paid_on ? ` (${dateFr(doc.paid_on)})` : ""}, l'horodatage et la référence
            sont effacés de la fiche mais conservés dans l'historique.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif de la correction *</Label>
          <Textarea rows={2} value={motif} onChange={(e) => setMotif(e.target.value)} placeholder="Ex. : paiement saisi sur la mauvaise amende, virement rejeté…" data-testid="fine-unpay-motif" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fine-unpay-cancel">Fermer</Button>
          <Button onClick={submit} disabled={busy || motif.trim().length < 3} className="bg-amber-600 hover:bg-amber-700" data-testid="fine-unpay-confirm">
            {busy ? "Enregistrement…" : "Confirmer la correction"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
