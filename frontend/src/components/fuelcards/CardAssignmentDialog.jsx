import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { F, VehicleSelect } from "@/components/documents/nofileShared";
import DriverPicker from "@/components/drivers/DriverPicker";
import { createFuelCardAssignment } from "@/lib/api";
import { ASSIGNMENT_TYPES, assignmentTypeLabel, todayIso, errDetail, errCode } from "@/lib/fuelCards";
import { dateFr } from "@/lib/format";
import { CARD_QUERY_KEYS } from "@/components/fuelcards/FuelCardLifecycleDialogs";

// Affectation datée carte → véhicule | conducteur | pool | autre (même tenant, pickers existants, aucune résolution par plaque/nom).
// Chevauchement du même type → 409 : l'utilisateur confirme explicitement le remplacement avec un motif (clôture auditée).
export default function CardAssignmentDialog({ card, open, onOpenChange }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ type: "vehicule", vehicle_id: "", driver_id: null, valid_from: todayIso(), valid_to: "", motif: "" });
  const [conflict, setConflict] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v?.target ? v.target.value : v }));
  useEffect(() => {
    if (open) { setF({ type: card?.type_affectation || "vehicule", vehicle_id: "", driver_id: null, valid_from: todayIso(), valid_to: "", motif: "" }); setConflict(null); }
  }, [open, card]);

  const submit = async (replace = false) => {
    setBusy(true);
    try {
      const r = await createFuelCardAssignment(card.id, {
        type: f.type, vehicle_id: f.type === "vehicule" ? f.vehicle_id : null, driver_id: f.type === "conducteur" ? f.driver_id : null,
        valid_from: f.valid_from, valid_to: f.valid_to || null, motif: f.motif.trim() || null, replace,
      });
      toast.success(`Affectation ${assignmentTypeLabel(f.type)} → ${r.cible} enregistrée${r.replaced?.length ? ` (${r.replaced.length} affectation clôturée)` : ""}`);
      CARD_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      qc.invalidateQueries({ queryKey: ["fuel-card-history", card.id] });
      onOpenChange(false);
    } catch (e) {
      if (errCode(e) === "ASSIGNMENT_OVERLAP") setConflict(e.response.data.detail);
      else toast.error(errDetail(e, "Affectation impossible"));
    } finally { setBusy(false); }
  };
  const targetOk = f.type === "vehicule" ? !!f.vehicle_id : f.type === "conducteur" ? !!f.driver_id : true;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="card-assignment-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Affecter la carte {card?.label}</DialogTitle>
          <DialogDescription>Une seule affectation ouverte par type ; véhicule et conducteur peuvent coexister. L'historique daté est conservé.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <F label="Type" className="sm:col-span-2">
            <Select value={f.type} onValueChange={(v) => { setConflict(null); setF((p) => ({ ...p, type: v, vehicle_id: "", driver_id: null })); }}>
              <SelectTrigger data-testid="card-assignment-type"><SelectValue /></SelectTrigger>
              <SelectContent>{ASSIGNMENT_TYPES.map(([c, l]) => <SelectItem key={c} value={c} data-testid={`card-assignment-type-${c}`}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </F>
          {f.type === "vehicule" && <div className="sm:col-span-2"><VehicleSelect value={f.vehicle_id} onChange={set("vehicle_id")} testId="card-assignment-vehicle" /></div>}
          {f.type === "conducteur" && (
            <F label="Conducteur" className="sm:col-span-2">
              <DriverPicker value={f.driver_id} onChange={set("driver_id")} testId="card-assignment-driver" allowEmpty={false} placeholder="Choisir un conducteur" />
            </F>
          )}
          <F label="Début (valid_from) *"><Input type="date" value={f.valid_from} onChange={set("valid_from")} data-testid="card-assignment-valid-from" /></F>
          <F label="Fin (valid_to, optionnel)"><Input type="date" value={f.valid_to} onChange={set("valid_to")} data-testid="card-assignment-valid-to" /></F>
          <F label={conflict ? "Motif du remplacement *" : "Motif"} className="sm:col-span-2">
            <Textarea rows={2} value={f.motif} onChange={set("motif")} data-testid="card-assignment-motif" placeholder="Contexte de l'affectation" />
          </F>
        </div>
        {conflict && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="card-assignment-conflict-box">
            <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-4 w-4" /> Chevauchement avec une affectation du même type</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {conflict.conflicts.map((c) => <li key={c.id}>{assignmentTypeLabel(c.type)} → {c.driver_nom || c.vehicle_id || "—"} · du {c.valid_from ? dateFr(c.valid_from) : "toujours"}{c.valid_to ? ` au ${dateFr(c.valid_to)}` : " (en cours)"}</li>)}
            </ul>
            <p className="mt-1 text-xs">{conflict.message}</p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="card-assignment-cancel">Annuler</Button>
          {conflict ? (
            <Button onClick={() => submit(true)} disabled={busy || f.motif.trim().length < 3} className="bg-amber-600 hover:bg-amber-700" data-testid="card-assignment-replace">
              {busy ? "Enregistrement…" : "Remplacer l'affectation en cours"}
            </Button>
          ) : (
            <Button onClick={() => submit(false)} disabled={busy || !targetOk || !f.valid_from} className="bg-slate-900 hover:bg-slate-800" data-testid="card-assignment-submit">
              {busy ? "Enregistrement…" : "Affecter"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
