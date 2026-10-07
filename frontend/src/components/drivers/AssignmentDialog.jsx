import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { createVehicleAssignment } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { F } from "@/components/documents/nofileShared";
import DriverPicker from "@/components/drivers/DriverPicker";

export const ASSIGN_KEYS = ["assignments", "driver-at", "drivers"];
const today = () => new Date().toISOString().slice(0, 10);

// Affecter un conducteur à un véhicule (période datée). Chevauchement → 409 : remplacement EXPLICITE avec motif.
export default function AssignmentDialog({ open, onOpenChange, vehicle, onCreated }) {
  const qc = useQueryClient();
  const [driverId, setDriverId] = useState(null);
  const [f, setF] = useState({ valid_from: today(), valid_to: "", principal: true, motif: "" });
  const [conflict, setConflict] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

  useEffect(() => { if (open) { setDriverId(null); setF({ valid_from: today(), valid_to: "", principal: true, motif: "" }); setConflict(null); } }, [open]);

  const submit = async (replace = false) => {
    setBusy(true);
    try {
      const r = await createVehicleAssignment(vehicle.id, { driver_id: driverId, valid_from: f.valid_from, valid_to: f.valid_to || null,
        principal: f.principal, motif: f.motif || null, replace, source: "manual" });
      toast.success(`${r.driver_nom} affecté à ${vehicle.plaque} dès le ${dateFr(r.valid_from)}${r.replaced?.length ? ` — ${r.replaced.length} affectation(s) clôturée(s)` : ""}`);
      ASSIGN_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onCreated?.(r);
      onOpenChange(false);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d?.code === "ASSIGNMENT_OVERLAP") {
        setConflict(d);
        if (replace) toast.error(d.message || "Remplacement impossible", { duration: 9000 });
      } else toast.error((typeof d === "string" && d) || d?.message || "Affectation impossible");
    } finally {
      setBusy(false);
    }
  };
  const canReplace = conflict && f.motif.trim().length >= 3;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="assignment-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Affecter un conducteur — {vehicle?.plaque}</DialogTitle>
          <DialogDescription>Affectation datée, historique conservé. Aucun conducteur n'est déduit automatiquement.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <F label="Conducteur *"><DriverPicker value={driverId} onChange={(v) => { setDriverId(v); setConflict(null); }} testId="assignment-driver" allowEmpty={false} placeholder="Choisir un conducteur" /></F>
          <div className="grid grid-cols-2 gap-4">
            <F label="Du *"><Input data-testid="assignment-valid-from" type="date" value={f.valid_from} onChange={(e) => { set("valid_from")(e); setConflict(null); }} /></F>
            <F label="Au (vide = en cours)"><Input data-testid="assignment-valid-to" type="date" value={f.valid_to} onChange={set("valid_to")} /></F>
          </div>
          <F label="Affectation principale">
            <div className="flex h-9 items-center gap-2">
              <Switch checked={f.principal} onCheckedChange={set("principal")} data-testid="assignment-principal" />
              <span className="text-sm text-slate-600">{f.principal ? "Conducteur principal du véhicule" : "Conducteur secondaire (peut cohabiter)"}</span>
            </div>
          </F>
          <F label={conflict ? "Motif du remplacement *" : "Motif (optionnel)"}>
            <Textarea data-testid="assignment-motif" rows={2} value={f.motif} onChange={set("motif")} placeholder="Changement de chauffeur, remplacement congé…" />
          </F>
          {conflict && (
            <div data-testid="assignment-conflict" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-3.5 w-3.5" /> Affectation principale en conflit</p>
              <ul className="mt-1 list-disc pl-5">
                {conflict.conflicts.map((c) => <li key={c.id}>{c.driver_nom} — du {dateFr(c.valid_from)}{c.valid_to ? ` au ${dateFr(c.valid_to)}` : " (en cours)"}</li>)}
              </ul>
              <p className="mt-1">{conflict.message}</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" data-testid="assignment-cancel" onClick={() => onOpenChange(false)}>Annuler</Button>
          {conflict ? (
            <Button data-testid="assignment-replace" onClick={() => submit(true)} disabled={busy || !canReplace} className="bg-amber-700 hover:bg-amber-800">
              {busy ? "…" : "Clôturer l'affectation en cours et remplacer"}
            </Button>
          ) : (
            <Button data-testid="assignment-submit" onClick={() => submit(false)} disabled={busy || !driverId || !f.valid_from} className="bg-slate-900 hover:bg-slate-800">
              {busy ? "Enregistrement…" : "Affecter"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
