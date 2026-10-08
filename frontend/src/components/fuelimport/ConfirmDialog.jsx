import { useState } from "react";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { confirmFuelImport } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";
import { IMPORTABLE } from "@/lib/fuelImport";

// Étape 4 — confirmation explicite : résumé (importées / mises de côté) → seule écriture métier. Protégée contre le double clic ; idempotente côté serveur.
export default function ConfirmDialog({ job, rows, open, onOpenChange, onDone }) {
  const [busy, setBusy] = useState(false);
  const pending = rows.filter((r) => !r.imported);
  const toImport = pending.filter((r) => IMPORTABLE.includes(r.status));
  const aside = { duplicate: 0, invalid: 0, unknown_vehicle: 0 };
  pending.forEach((r) => { if (r.status in aside) aside[r.status] += 1; });
  const submit = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await confirmFuelImport(job.id);
      toast.success(`${res.imported} ligne(s) importée(s)${res.already_imported ? ` (${res.already_imported} déjà importée(s))` : ""}`);
      onDone(res);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e, "Confirmation refusée")); } finally { setBusy(false); }
  };
  return (
    <AlertDialog open={open} onOpenChange={(o) => { if (!busy) onOpenChange(o); }}>
      <AlertDialogContent data-testid="fuel-import-confirm-step">
        <AlertDialogHeader>
          <AlertDialogTitle className="font-display">Confirmer l'import — {job.filename}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2 text-sm text-slate-600">
              <p><b className="text-slate-900" data-testid="fuel-import-confirm-to-import">{toImport.length}</b> ligne(s) seront importées : chacune crée un document sans justificatif (source du coût) et une transaction énergie, avec rattachement et détection d'anomalies.</p>
              <ul className="list-inside list-disc text-xs">
                <li>{toImport.filter((r) => r.status === "ok").length} valide(s)</li>
                <li>{toImport.filter((r) => r.status === "amount_mismatch").length} montant(s) incohérent(s) — importé(s) avec anomalie</li>
                <li>{toImport.filter((r) => r.status === "unknown_card").length} carte(s) non résolue(s) — importée(s) sans card_id</li>
              </ul>
              <p>Mises de côté (non importées) : <b data-testid="fuel-import-confirm-set-aside">{aside.duplicate + aside.invalid + aside.unknown_vehicle}</b> — {aside.duplicate} doublon(s), {aside.invalid} invalide(s), {aside.unknown_vehicle} véhicule(s) non résolu(s).</p>
              {toImport.length === 0 && <p className="font-semibold text-amber-700">Aucune ligne importable : résolvez les véhicules ou forcez les doublons avant de confirmer.</p>}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy} data-testid="fuel-import-cancel-btn">Annuler</AlertDialogCancel>
          <Button onClick={submit} disabled={busy || toImport.length === 0} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-import-confirm-final-btn">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Importer {toImport.length} ligne(s)
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
