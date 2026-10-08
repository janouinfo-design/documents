import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getVehicles, getFuelCards, matchFuelTransaction, setFuelTransactionCard } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";
import { REVIEW_REASON_LABELS } from "@/lib/fuelImport";
import { cn } from "@/lib/utils";

const NONE = "__none__";

const invalidate = (qc, id) => {
  qc.invalidateQueries({ queryKey: ["energy"] });
  qc.invalidateQueries({ queryKey: ["fuel-tx", id] });
  qc.invalidateQueries({ queryKey: ["fuel-anomalies"] });
};

// Correction individuelle du véhicule d'une transaction : candidats (plaque source, score, raisons) → choix humain + motif obligatoire → `manual`
export function VehicleCorrectionDialog({ tx, open, onOpenChange }) {
  const qc = useQueryClient();
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles, enabled: open });
  const [vehicleId, setVehicleId] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setVehicleId(""); setReason(""); } }, [open, tx?.id]);
  if (!tx) return null;
  const match = tx.match || {};
  const candidates = (match.candidates || []).filter((c) => c.vehicle_id !== tx.vehicle_id);
  const submit = async () => {
    setBusy(true);
    try {
      const res = await matchFuelTransaction(tx.id, { vehicle_id: vehicleId, reason: reason.trim() });
      toast.success(`Transaction rattachée manuellement${res.warnings?.length ? ` — ${res.warnings.length} avertissement(s)` : ""}`);
      invalidate(qc, tx.id);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-vehicle-correction-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Corriger le véhicule</DialogTitle>
          <DialogDescription>
            Véhicule actuel : <b>{tx.plaque || tx.vehicle_id}</b> · rattachement {tx.match_label || tx.match_status || "—"}{match.score != null ? ` (${match.score} pt)` : ""}.
            {tx.vehicle_hint ? <> Plaque du fichier : <span className="font-mono">{tx.vehicle_hint}</span>.</> : null} Décision humaine motivée — la transaction et son document sont déplacés ; aucune correction automatique.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {(match.review_reasons || []).length > 0 && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="fuel-vehicle-correction-reasons">
              Raisons de revue : {match.review_reasons.map((r) => REVIEW_REASON_LABELS[r] || r).join(" · ")}
            </p>
          )}
          {candidates.length > 0 && (
            <div className="space-y-1" data-testid="fuel-vehicle-candidates">
              <p className="text-xs font-semibold text-slate-700">Candidats proposés (aide à la décision)</p>
              {candidates.map((c) => (
                <button key={c.vehicle_id} type="button" onClick={() => setVehicleId(c.vehicle_id)} data-testid={`fuel-vehicle-candidate-${c.vehicle_id}`}
                  className={cn("flex w-full items-center justify-between rounded-lg border px-3 py-1.5 text-left text-sm transition-colors", vehicleId === c.vehicle_id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:bg-slate-50")}>
                  <span className="font-semibold">{c.label || c.vehicle_id}</span>
                  <span className="text-xs opacity-80">{c.partial_score} pt · {(c.sources || []).join(", ")}</span>
                </button>
              ))}
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Véhicule cible</Label>
            <Select value={vehicleId || NONE} onValueChange={(v) => setVehicleId(v === NONE ? "" : v)}>
              <SelectTrigger data-testid="fuel-vehicle-correction-select"><SelectValue placeholder="Choisir…" /></SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>— choisir —</SelectItem>
                {vehicles.filter((v) => v.id !== tx.vehicle_id).map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}{v.marque ? ` · ${v.marque} ${v.modele || ""}` : ""}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-vehicle-correction-motif" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-vehicle-correction-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || !vehicleId || reason.trim().length < 3} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-vehicle-correction-confirm">Valider la correction</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Choix humain de la carte (ambiguë / introuvable) ou retrait — jamais automatique
export function CardChoiceDialog({ tx, open, onOpenChange }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["fuel-cards", "list", { archived: "false" }], queryFn: () => getFuelCards({ archived: "false" }), enabled: open });
  const [cardId, setCardId] = useState(NONE);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setCardId(NONE); setReason(""); } }, [open, tx?.id]);
  if (!tx) return null;
  const candidates = tx.card_resolution?.candidates || [];
  const cards = data?.items || [];
  const submit = async () => {
    setBusy(true);
    try {
      await setFuelTransactionCard(tx.id, { card_id: cardId === NONE ? null : cardId, reason: reason.trim() });
      toast.success(cardId === NONE ? "Carte retirée de la transaction" : "Carte choisie manuellement");
      invalidate(qc, tx.id);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-card-choice-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Carte de la transaction</DialogTitle>
          <DialogDescription>Carte lue : {tx.carte_last4 ? <span className="font-mono">••••{tx.carte_last4}</span> : "aucune"} · résolution {tx.card_resolution?.status || "—"}. L'identité (fournisseur, 4 chiffres) n'est pas unique : le choix est humain et motivé.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Select value={cardId} onValueChange={setCardId}>
            <SelectTrigger data-testid="fuel-card-choice-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>— aucune carte (card_id vide) —</SelectItem>
              {candidates.map((c) => <SelectItem key={`c-${c.id}`} value={c.id}>★ {c.label} · {c.statut}{c.assigned_plaque ? ` · ${c.assigned_plaque}` : ""}</SelectItem>)}
              {cards.filter((c) => !candidates.some((x) => x.id === c.id)).map((c) => <SelectItem key={c.id} value={c.id}>{c.label} · {c.statut_label || c.statut}</SelectItem>)}
            </SelectContent>
          </Select>
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-card-choice-motif" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-card-choice-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-card-choice-confirm">Valider</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
