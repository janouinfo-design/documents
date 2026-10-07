import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CalendarX2 } from "lucide-react";
import { closeAssignment } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { F } from "@/components/documents/nofileShared";
import { ASSIGN_KEYS } from "@/components/drivers/AssignmentDialog";

function CloseDialog({ assignment, onOpenChange, onClosed }) {
  const qc = useQueryClient();
  const [validTo, setValidTo] = useState(new Date().toISOString().slice(0, 10));
  const [motif, setMotif] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const r = await closeAssignment(assignment.id, { valid_to: validTo, motif: motif || null });
      toast.success(`Affectation de ${r.driver_nom} clôturée au ${dateFr(r.valid_to)}`);
      ASSIGN_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onClosed?.(r);
      onOpenChange(false);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((typeof d === "string" && d) || d?.message || "Clôture impossible");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={!!assignment} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="assignment-close-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Clôturer l'affectation</DialogTitle>
          <DialogDescription>{assignment?.driver_nom} — {assignment?.plaque} depuis le {dateFr(assignment?.valid_from)}. L'historique est conservé.</DialogDescription>
        </DialogHeader>
        <F label="Date de fin *"><Input data-testid="assignment-close-date" type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} /></F>
        <F label="Motif (optionnel)"><Textarea data-testid="assignment-close-motif" rows={2} value={motif} onChange={(e) => setMotif(e.target.value)} /></F>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="assignment-close-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || !validTo} data-testid="assignment-close-confirm" className="bg-slate-900 hover:bg-slate-800">{busy ? "…" : "Clôturer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Historique des affectations (véhicule ou conducteur) — lecture ; clôture explicite pour l'admin.
export default function AssignmentHistory({ rows = [], readOnly = false, showVehicle = false, showDriver = true, emptyText = "Aucune affectation enregistrée." }) {
  const [closing, setClosing] = useState(null);
  if (!rows.length) return <p className="py-4 text-center text-xs text-slate-400" data-testid="assignments-empty">{emptyText}</p>;
  return (
    <>
      <ul className="divide-y divide-slate-100" data-testid="assignments-history">
        {rows.map((a) => (
          <li key={a.id} data-testid={`assignment-row-${a.id}`} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-800">
                {showDriver && (a.driver_nom || "—")}{showDriver && showVehicle && " → "}{showVehicle && (a.plaque || a.vehicle_id)}
                {a.principal === false && <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">secondaire</span>}
                {a.source === "legacy_import" && <span className="ml-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">import</span>}
              </p>
              <p className="text-[11px] text-slate-500">
                du {dateFr(a.valid_from)} {a.valid_to ? `au ${dateFr(a.valid_to)}` : "— en cours"}
                {a.replaced && " · remplacée"}{a.close_motif ? ` · ${a.close_motif}` : a.motif ? ` · ${a.motif}` : ""}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span data-testid={`assignment-state-${a.id}`} className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${a.active && !a.valid_to ? "bg-emerald-50 text-emerald-700" : a.active ? "bg-sky-50 text-sky-700" : "bg-slate-100 text-slate-500"}`}>
                {!a.valid_to ? "En cours" : a.active ? "Jusqu'au " + dateFr(a.valid_to) : "Terminée"}
              </span>
              {!readOnly && !a.valid_to && (
                <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" data-testid={`assignment-close-${a.id}`} onClick={() => setClosing(a)}>
                  <CalendarX2 className="h-3.5 w-3.5" /> Clôturer
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {closing && <CloseDialog assignment={closing} onOpenChange={(o) => !o && setClosing(null)} />}
    </>
  );
}
