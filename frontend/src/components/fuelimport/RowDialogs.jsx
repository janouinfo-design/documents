import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getVehicles, resolveFuelImportRow, acceptUniqueFuelImportRows, forceFuelImportRow } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";
import { REVIEW_REASON_LABELS } from "@/lib/fuelImport";

const KEEP = "__keep__";

// Résolution manuelle d'une ligne (véhicule et/ou carte) — décision humaine motivée, jamais automatique
export function RowResolveDialog({ job, row, open, onOpenChange, onDone }) {
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles, enabled: open });
  const [vehicleId, setVehicleId] = useState(KEEP);
  const [cardId, setCardId] = useState(KEEP);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setVehicleId(KEEP); setCardId(KEEP); setReason(""); } }, [open, row?.id]);
  if (!row) return null;
  const vres = row.resolution?.vehicle || {};
  const cres = row.resolution?.card || {};
  const candidates = vres.candidates || [];
  const submit = async () => {
    setBusy(true);
    try {
      const body = { reason: reason.trim() };
      if (vehicleId !== KEEP) body.vehicle_id = vehicleId;
      if (cardId !== KEEP) body.card_id = cardId;
      const res = await resolveFuelImportRow(job.id, row.id, body);
      toast.success(`Ligne ${row.row_index} → ${res.row.status}`);
      onDone?.(res);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-row-resolve-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Résoudre la ligne {row.row_index}</DialogTitle>
          <DialogDescription>
            {row.normalized?.date} · {row.normalized?.station || "—"} · {row.normalized?.montant} {row.normalized?.devise}
            {row.normalized?.plaque_hint ? ` · plaque fichier « ${row.normalized.plaque_hint} »` : ""}{row.normalized?.card_last4 ? ` · carte ••••${row.normalized.card_last4}` : ""}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {vres.review_reasons?.length > 0 && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="fuel-row-review-reasons">
              Revue requise : {vres.review_reasons.map((r) => REVIEW_REASON_LABELS[r] || r).join(" · ")}
            </p>
          )}
          {candidates.length > 0 && (
            <div className="space-y-1 text-xs text-slate-600" data-testid="fuel-row-candidates">
              <p className="font-semibold text-slate-700">Candidats proposés (aide à la décision, aucun choix automatique)</p>
              {candidates.map((c) => (
                <p key={c.vehicle_id}>• {c.label || c.vehicle_id} — {c.partial_score} pt · {c.sources.join(", ")}{c.proposed ? " · proposé" : ""}</p>
              ))}
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Véhicule</Label>
            <Select value={vehicleId} onValueChange={setVehicleId}>
              <SelectTrigger data-testid="fuel-row-vehicle-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={KEEP}>— inchangé —</SelectItem>
                {candidates.map((c) => <SelectItem key={`c-${c.vehicle_id}`} value={c.vehicle_id}>★ {c.label || c.vehicle_id}</SelectItem>)}
                {vehicles.filter((v) => !candidates.some((c) => c.vehicle_id === v.id)).map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}{v.marque ? ` · ${v.marque} ${v.modele || ""}` : ""}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {cres.status === "ambiguous" && (
            <div className="space-y-1">
              <Label className="text-xs text-slate-500">Carte (plusieurs cartes ••••{row.normalized?.card_last4} — identité non unique)</Label>
              <Select value={cardId} onValueChange={setCardId}>
                <SelectTrigger data-testid="fuel-row-card-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={KEEP}>— laisser non résolue (card_id vide) —</SelectItem>
                  {(cres.candidates || []).map((c) => <SelectItem key={c.id} value={c.id}>{c.label} · {c.statut_label}{c.assigned_plaque ? ` · ${c.assigned_plaque}` : ""}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
            <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-row-motif" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-row-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3 || (vehicleId === KEEP && cardId === KEEP)} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-row-confirm">Valider la décision</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Action groupée « Accepter les N propositions à candidat unique » : liste ligne → plaque → véhicule, désélection, motif global, audit par ligne
export function AcceptUniqueDialog({ job, rows, open, onOpenChange, onDone }) {
  const eligible = rows.filter((r) => r.status === "unknown_vehicle" && !r.imported && (r.resolution?.vehicle?.candidates || []).length === 1
    && r.resolution.vehicle.candidates[0].sources.includes("plate_candidate"));
  const [selected, setSelected] = useState(new Set());
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setSelected(new Set(eligible.map((r) => r.id))); setReason(""); } }, [open, rows.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const submit = async () => {
    setBusy(true);
    try {
      const res = await acceptUniqueFuelImportRows(job.id, { row_ids: [...selected], reason: reason.trim() });
      toast.success(`${res.accepted.length} ligne(s) acceptée(s)${res.refused.length ? `, ${res.refused.length} refusée(s)` : ""}`);
      onDone?.(res);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl" data-testid="fuel-bulk-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Accepter les propositions à candidat unique</DialogTitle>
          <DialogDescription>
            {eligible.length} ligne(s) éligible(s) : véhicule non résolu, exactement 1 véhicule correspondant à la plaque normalisée. Validation humaine explicite — ce n'est pas un rattachement automatique ; chaque ligne est auditée séparément.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2" data-testid="fuel-bulk-list">
          {eligible.length === 0 && <p className="py-4 text-center text-sm text-slate-400">Aucune ligne éligible.</p>}
          {eligible.map((r) => {
            const c = r.resolution.vehicle.candidates[0];
            return (
              <label key={r.id} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-slate-50" data-testid={`fuel-bulk-row-${r.id}`}>
                <Checkbox checked={selected.has(r.id)} onCheckedChange={(v) => setSelected((s) => { const n = new Set(s); if (v) n.add(r.id); else n.delete(r.id); return n; })} />
                <span className="w-14 text-xs text-slate-400">L.{r.row_index}</span>
                <span className="font-mono text-xs text-slate-600">{r.normalized?.plaque_hint}</span>
                <span className="text-slate-400">→</span>
                <span className="font-semibold text-slate-800">{c.label || c.vehicle_id}</span>
              </label>
            );
          })}
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif global (obligatoire, repris dans chaque audit)</Label>
          <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-bulk-motif" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-bulk-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3 || selected.size === 0} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-bulk-confirm">
            Accepter {selected.size} ligne(s)
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Forçage motivé d'une ligne « doublon »
export function ForceRowDialog({ job, row, open, onOpenChange, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setReason(""); }, [open]);
  if (!row) return null;
  const submit = async () => {
    setBusy(true);
    try {
      const res = await forceFuelImportRow(job.id, row.id, { reason: reason.trim() });
      toast.success(`Ligne ${row.row_index} importée (forcée)`);
      onDone?.(res);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-force-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Forcer l'import de la ligne {row.row_index}</DialogTitle>
          <DialogDescription>Doublon détecté ({row.duplicate_of?.kind}). L'import forcé conserve la référence au doublon d'origine et votre motif dans l'audit.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
          <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-force-motif" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-force-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3} className="bg-amber-600 hover:bg-amber-700" data-testid="fuel-force-confirm">Forcer l'import</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
