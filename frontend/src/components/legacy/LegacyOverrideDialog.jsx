import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { legacyVehicleConfirm } from "@/lib/api";

const CONFLICT_LABEL = {
  legacy_already_confirmed: (c) => `Ce véhicule Journal est déjà confirmé vers le véhicule ${c.current_vehicle_id}`,
  vehicle_already_mapped: (c) => `Le véhicule Documents choisi est déjà rattaché au véhicule Journal ${c.legacy_vehicle_id}`,
};

// Remplacement explicite d'une correspondance en conflit — motif obligatoire, audité avec avant/après.
export default function LegacyOverrideDialog({ conflict, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  if (!conflict) return null;
  const submit = async () => {
    if (!reason.trim()) return toast.warning("Motif obligatoire pour remplacer une correspondance");
    setBusy(true);
    try {
      await legacyVehicleConfirm(conflict.row.legacy_vehicle_id,
        { vehicle_id: conflict.vehicleId, note: conflict.note || undefined, override: true, reason: reason.trim() },
        conflict.row.legacy_source);
      toast.success("Correspondance remplacée explicitement (auditée)");
      onDone?.();
      onClose();
    } catch (e) {
      toast.error(String(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Échec du remplacement"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="legacy-override-dialog">
        <DialogHeader>
          <DialogTitle>Conflit de correspondance</DialogTitle>
          <DialogDescription>Aucun écrasement silencieux : indiquez un motif pour remplacer explicitement.</DialogDescription>
        </DialogHeader>
        <ul className="list-disc space-y-1 pl-5 text-sm text-red-700" data-testid="legacy-override-conflicts">
          {conflict.conflicts.map((c, i) => <li key={i}>{(CONFLICT_LABEL[c.type] || (() => c.type))(c)}</li>)}
        </ul>
        <Textarea data-testid="legacy-override-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motif du remplacement (obligatoire)" rows={3} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="legacy-override-cancel-btn">Annuler</Button>
          <Button onClick={submit} disabled={busy} data-testid="legacy-override-confirm-btn" className="bg-red-600 hover:bg-red-700">
            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Remplacer avec motif
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
