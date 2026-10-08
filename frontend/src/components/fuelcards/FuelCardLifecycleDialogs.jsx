import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { setFuelCardStatus, archiveFuelCard, restoreFuelCard } from "@/lib/api";
import { CARD_STATUSES, CARD_STATUS_META, cardStatusLabel, errDetail } from "@/lib/fuelCards";

export const CARD_QUERY_KEYS = [["fuel-cards"], ["deadlines"]];
const refresh = (qc, id) => { CARD_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: k })); if (id) qc.invalidateQueries({ queryKey: ["fuel-card-history", id] }); };

// Statut déclaré : changement explicite, motif obligatoire, audité avant/après — jamais automatique (l'expiration par date est dérivée à part)
export function FuelCardStatusDialog({ card, open, onOpenChange }) {
  const qc = useQueryClient();
  const [statut, setStatut] = useState(card?.statut || "active");
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setStatut(card?.statut || "active"); setMotif(""); } }, [open, card]);
  const submit = async () => {
    setBusy(true);
    try {
      await setFuelCardStatus(card.id, { statut, motif: motif.trim() });
      toast.success(`Statut → ${cardStatusLabel(statut)}`);
      refresh(qc, card.id);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-card-status-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Changer le statut — {card?.label}</DialogTitle>
          <DialogDescription>Statut actuel : {cardStatusLabel(card?.statut)}. Le statut n'est jamais modifié automatiquement ; la date d'expiration reste inchangée.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Nouveau statut</Label>
            <Select value={statut} onValueChange={setStatut}>
              <SelectTrigger data-testid="fuel-card-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{CARD_STATUSES.map((s) => <SelectItem key={s} value={s} data-testid={`fuel-card-status-option-${s}`}>{CARD_STATUS_META[s].label}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Motif *</Label>
            <Textarea rows={2} value={motif} onChange={(e) => setMotif(e.target.value)} data-testid="fuel-card-status-motif" placeholder="Ex. : carte perdue, remplacée par la carte ••••5678, fin de contrat…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-card-status-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || motif.trim().length < 3 || statut === card?.statut} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-card-status-confirm">
            {busy ? "Enregistrement…" : "Confirmer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Archivage = soft-delete `is_deleted` (motif obligatoire) ; restauration. Aucune suppression physique, statut métier conservé.
export function FuelCardArchiveDialog({ card, open, onOpenChange, onDone }) {
  const qc = useQueryClient();
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  const restoring = !!card?.is_deleted;
  const tid = restoring ? "fuel-card-restore" : "fuel-card-archive"; // testids distincts archivage / restauration
  useEffect(() => { if (open) setMotif(""); }, [open]);
  const submit = async () => {
    setBusy(true);
    try {
      if (restoring) await restoreFuelCard(card.id, { motif: motif.trim() || null });
      else await archiveFuelCard(card.id, { motif: motif.trim() });
      toast.success(restoring ? "Carte restaurée" : "Carte archivée (historique conservé)");
      refresh(qc, card.id);
      onDone?.();
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid={`${tid}-dialog`}>
        <DialogHeader>
          <DialogTitle className="font-display text-lg">{restoring ? "Restaurer" : "Archiver"} — {card?.label}</DialogTitle>
          <DialogDescription>
            {restoring ? "La carte redevient visible dans la liste principale ; son statut métier est inchangé."
              : "La carte est masquée par défaut (filtre « Archivées »). Historique, affectations et statut métier sont conservés — aucune suppression."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif{restoring ? "" : " *"}</Label>
          <Textarea rows={2} value={motif} onChange={(e) => setMotif(e.target.value)} data-testid={`${tid}-motif`} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${tid}-cancel`}>Annuler</Button>
          <Button onClick={submit} disabled={busy || (!restoring && motif.trim().length < 3)} className={restoring ? "bg-emerald-600 hover:bg-emerald-700" : "bg-slate-900 hover:bg-slate-800"} data-testid={`${tid}-confirm`}>
            {busy ? "Enregistrement…" : restoring ? "Restaurer" : "Archiver"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
