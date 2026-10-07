import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createFineNoFile } from "@/lib/api";
import { chfExact } from "@/lib/format";
import { CoherenceWarnings, DuplicateSuspectedBox } from "@/components/documents/BusinessCategoryPicker";
import { F, DeclarativeBanner, VehicleSelect, CurrencyFields, num, useNoFileSubmit } from "@/components/documents/nofileShared";

const EMPTY = { autorite: "", numero_amende: "", date_infraction: "", montant: "", devise: "CHF", montant_chf: "", delai_paiement: "", plaque: "", motif: "" };

// « Nouvelle amende sans fichier » — document validé (coût + échéance de paiement), règles Phase 3.
export default function ManualFineDialog({ open, onOpenChange, vehicle, onCreated }) {
  const [vehicleId, setVehicleId] = useState(vehicle?.id || "");
  const [f, setF] = useState(EMPTY);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

  const s = useNoFileSubmit({
    submit: (override) => createFineNoFile(vehicleId, {
      autorite: f.autorite, numero_amende: f.numero_amende || null, date_infraction: f.date_infraction || null,
      montant: num(f.montant), devise: f.devise, montant_chf: f.devise !== "CHF" ? num(f.montant_chf) : null,
      delai_paiement: f.delai_paiement || null, plaque: f.plaque || null, motif: f.motif, source: "manual", duplicate_override: override,
    }),
    successLabel: (r) => `Amende enregistrée sans fichier — ${chfExact(r.cost?.montant, r.cost?.devise)}${r.cost?.pending_fx ? " (conversion en attente)" : ""} · à payer`,
    onSuccess: (r) => { onCreated?.(r); onOpenChange(false); },
  });
  const { reset } = s;
  useEffect(() => { if (open) { setF(EMPTY); setVehicleId(vehicle?.id || ""); reset(); } }, [open, vehicle?.id, reset]);
  const canSubmit = vehicleId && f.autorite.trim() && f.montant !== "" && f.motif.trim().length >= 3 && !s.busy;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" data-testid="manual-fine-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Nouvelle amende sans fichier</DialogTitle>
          <DialogDescription>Amende reçue sans pièce numérisée : elle entre dans Coûts et Échéances, statut « À payer ».</DialogDescription>
        </DialogHeader>
        <DeclarativeBanner />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {!vehicle && <div className="sm:col-span-2"><VehicleSelect value={vehicleId} onChange={setVehicleId} testId="manual-fine-vehicle" /></div>}
          <F label="Autorité *"><Input data-testid="manual-fine-autorite" value={f.autorite} onChange={set("autorite")} placeholder="Police cantonale vaudoise" /></F>
          <F label="N° de l'amende"><Input data-testid="manual-fine-numero" value={f.numero_amende} onChange={set("numero_amende")} /></F>
          <F label="Date de l'infraction"><Input data-testid="manual-fine-date-infraction" type="date" value={f.date_infraction} onChange={set("date_infraction")} /></F>
          <F label="Délai de paiement"><Input data-testid="manual-fine-delai" type="date" value={f.delai_paiement} onChange={set("delai_paiement")} /></F>
          <F label="Montant à payer (frais inclus) *"><Input data-testid="manual-fine-montant" type="number" min="0" step="0.05" value={f.montant} onChange={set("montant")} /></F>
          <CurrencyFields devise={f.devise} montantChf={f.montant_chf} onDevise={set("devise")} onMontantChf={set("montant_chf")} idPrefix="manual-fine" />
          <F label="Plaque mentionnée"><Input data-testid="manual-fine-plaque" value={f.plaque} onChange={set("plaque")} placeholder={vehicle?.plaque || ""} /></F>
          <F label="Motif de la saisie sans fichier *" className="sm:col-span-2">
            <Textarea data-testid="manual-fine-motif" rows={2} value={f.motif} onChange={set("motif")} placeholder="Courrier papier non scanné, amende reprise d'un ancien système…" />
          </F>
        </div>
        <CoherenceWarnings warnings={s.warnings} />
        <DuplicateSuspectedBox info={s.dup} onConfirmAnyway={() => s.run(true)} busy={s.busy} />
        <DialogFooter>
          <Button variant="outline" data-testid="manual-fine-cancel" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="manual-fine-submit" onClick={() => s.run(false)} disabled={!canSubmit} className="bg-slate-900 hover:bg-slate-800">
            {s.busy ? "Enregistrement…" : "Enregistrer sans fichier"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
