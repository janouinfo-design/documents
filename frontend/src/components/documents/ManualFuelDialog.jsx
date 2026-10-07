import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createFuelNoFile } from "@/lib/api";
import { chfExact } from "@/lib/format";
import { CoherenceWarnings, DuplicateSuspectedBox } from "@/components/documents/BusinessCategoryPicker";
import { F, DeclarativeBanner, VehicleSelect, CurrencyFields, num, useNoFileSubmit } from "@/components/documents/nofileShared";

const EMPTY = { date: "", heure: "", station: "", montant: "", devise: "CHF", montant_chf: "", litres: "", prix_litre: "",
  energie_kwh: "", prix_kwh: "", type_carburant: "", kilometrage: "", carte_last4: "", motif: "" };

// « Plein / recharge sans justificatif » — 1 document sans fichier (= le coût) + 1 transaction énergie.
export default function ManualFuelDialog({ open, onOpenChange, vehicle, onCreated }) {
  const [vehicleId, setVehicleId] = useState(vehicle?.id || "");
  const [kind, setKind] = useState("CARBURANT");
  const [f, setF] = useState(EMPTY);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

  const s = useNoFileSubmit({
    submit: (override) => createFuelNoFile(vehicleId, {
      date: f.date, heure: f.heure || null, station: f.station || null, montant: num(f.montant), devise: f.devise,
      montant_chf: f.devise !== "CHF" ? num(f.montant_chf) : null, type_carburant: f.type_carburant || (kind === "ENERGIE_ELECTRIQUE" ? "Électricité" : null),
      litres: kind === "CARBURANT" ? num(f.litres) : null, prix_litre: kind === "CARBURANT" ? num(f.prix_litre) : null,
      energie_kwh: kind === "ENERGIE_ELECTRIQUE" ? num(f.energie_kwh) : null, prix_kwh: kind === "ENERGIE_ELECTRIQUE" ? num(f.prix_kwh) : null,
      kilometrage: num(f.kilometrage), carte_last4: f.carte_last4 || null, business_category: kind, motif: f.motif, source: "manual", duplicate_override: override,
    }),
    successLabel: (r) => `${kind === "ENERGIE_ELECTRIQUE" ? "Recharge" : "Plein"} enregistré sans justificatif — ${chfExact(r.cost?.montant, r.cost?.devise)}${r.cost?.pending_fx ? " (conversion en attente)" : ""} compté une seule fois`,
    onSuccess: (r) => { onCreated?.(r); onOpenChange(false); },
  });
  const { reset } = s;
  useEffect(() => { if (open) { setF(EMPTY); setKind("CARBURANT"); setVehicleId(vehicle?.id || ""); reset(); } }, [open, vehicle?.id, reset]);
  const canSubmit = vehicleId && f.date && f.montant !== "" && f.motif.trim().length >= 3 && !s.busy;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" data-testid="manual-fuel-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Plein / recharge sans justificatif</DialogTitle>
          <DialogDescription>Saisie manuelle d'une transaction énergie dont le ticket est absent ou perdu.</DialogDescription>
        </DialogHeader>
        <DeclarativeBanner />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {!vehicle && <div className="sm:col-span-2"><VehicleSelect value={vehicleId} onChange={setVehicleId} testId="manual-fuel-vehicle" /></div>}
          <F label="Type d'énergie" className="sm:col-span-2">
            <div className="flex gap-2">
              {[["CARBURANT", "Carburant (litres)"], ["ENERGIE_ELECTRIQUE", "Recharge électrique (kWh)"]].map(([v, l]) => (
                <Button key={v} type="button" size="sm" variant={kind === v ? "default" : "outline"} data-testid={`manual-fuel-kind-${v}`}
                  onClick={() => setKind(v)} className={kind === v ? "bg-slate-900 hover:bg-slate-800" : ""}>{l}</Button>
              ))}
            </div>
          </F>
          <F label="Date *"><Input data-testid="manual-fuel-date" type="date" value={f.date} onChange={set("date")} /></F>
          <F label="Heure (HH:MM, locale Zurich)"><Input data-testid="manual-fuel-heure" value={f.heure} onChange={set("heure")} placeholder="08:30" /></F>
          <F label="Station / borne"><Input data-testid="manual-fuel-station" value={f.station} onChange={set("station")} placeholder="Migrol Bern Wankdorf" /></F>
          <F label="Type (Diesel, Essence, Électricité…)"><Input data-testid="manual-fuel-type" value={f.type_carburant} onChange={set("type_carburant")} /></F>
          <F label="Montant total payé *"><Input data-testid="manual-fuel-montant" type="number" min="0" step="0.05" value={f.montant} onChange={set("montant")} /></F>
          <CurrencyFields devise={f.devise} montantChf={f.montant_chf} onDevise={set("devise")} onMontantChf={set("montant_chf")} idPrefix="manual-fuel" />
          {kind === "CARBURANT" ? (
            <>
              <F label="Litres"><Input data-testid="manual-fuel-litres" type="number" min="0" step="0.01" value={f.litres} onChange={set("litres")} /></F>
              <F label="Prix au litre"><Input data-testid="manual-fuel-prix-litre" type="number" min="0" step="0.001" value={f.prix_litre} onChange={set("prix_litre")} /></F>
            </>
          ) : (
            <>
              <F label="Énergie rechargée (kWh)"><Input data-testid="manual-fuel-kwh" type="number" min="0" step="0.01" value={f.energie_kwh} onChange={set("energie_kwh")} /></F>
              <F label="Prix au kWh"><Input data-testid="manual-fuel-prix-kwh" type="number" min="0" step="0.001" value={f.prix_kwh} onChange={set("prix_kwh")} /></F>
            </>
          )}
          <F label="Kilométrage au compteur"><Input data-testid="manual-fuel-km" type="number" min="0" step="1" value={f.kilometrage} onChange={set("kilometrage")} /></F>
          <F label="Carte (4 derniers chiffres)"><Input data-testid="manual-fuel-carte" maxLength={4} value={f.carte_last4} onChange={set("carte_last4")} /></F>
          <F label="Motif de la saisie sans justificatif *" className="sm:col-span-2">
            <Textarea data-testid="manual-fuel-motif" rows={2} value={f.motif} onChange={set("motif")} placeholder="Ticket perdu, relevé de carte carburant, borne sans reçu…" />
          </F>
        </div>
        <CoherenceWarnings warnings={s.warnings} />
        <DuplicateSuspectedBox info={s.dup} onConfirmAnyway={() => s.run(true)} busy={s.busy} />
        <DialogFooter>
          <Button variant="outline" data-testid="manual-fuel-cancel" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="manual-fuel-submit" onClick={() => s.run(false)} disabled={!canSubmit} className="bg-slate-900 hover:bg-slate-800">
            {s.busy ? "Enregistrement…" : "Enregistrer sans justificatif"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
