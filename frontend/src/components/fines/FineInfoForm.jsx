import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import DriverPicker from "@/components/drivers/DriverPicker";
import { updateDocument } from "@/lib/api";
import { INFRACTION_TYPES, PRIORITIES, errDetail } from "@/lib/fines";
import { FINE_QUERY_KEYS } from "@/components/fines/FinePaymentDialog";

const F = ({ label, children, className = "" }) => (
  <div className={`space-y-1 ${className}`}><Label className="text-xs text-slate-500">{label}</Label>{children}</div>
);
const pick = (d) => ({
  numero: d?.numero || "", dossier_interne: d?.dossier_interne || "", fournisseur: d?.fournisseur || "",
  type_infraction: d?.type_infraction || "other", priorite: d?.priorite || "normal",
  date_debut: (d?.date_debut || "").slice(0, 10), date_expiration: (d?.date_expiration || "").slice(0, 10),
  date_reception: (d?.date_reception || "").slice(0, 10), heure_infraction: d?.heure_infraction || "",
  montant_amende: d?.montant_amende ?? "", frais_admin: d?.frais_admin ?? "",
  ville: d?.lieu_infraction?.ville || "", lieu: d?.lieu_infraction?.lieu || "", canton: d?.lieu_infraction?.canton || "",
  notes_internes: d?.notes_internes || "", driver_id: d?.driver_id || null,
});
const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

// Champs métier de l'amende (PATCH /documents) — conducteur via le DriverPicker Lot C (tenant courant, « Non identifié » possible).
export default function FineInfoForm({ doc, canEdit, isAdmin }) {
  const qc = useQueryClient();
  const [f, setF] = useState(pick(doc));
  const [busy, setBusy] = useState(false);
  useEffect(() => { setF(pick(doc)); }, [doc]);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

  const save = async () => {
    setBusy(true);
    try {
      await updateDocument(doc.id, {
        numero: f.numero || null, dossier_interne: f.dossier_interne || null, fournisseur: f.fournisseur || null,
        type_infraction: f.type_infraction, priorite: f.priorite,
        date_debut: f.date_debut || null, date_expiration: f.date_expiration || null, date_reception: f.date_reception || null,
        heure_infraction: f.heure_infraction || null, montant_amende: num(f.montant_amende), frais_admin: num(f.frais_admin),
        lieu_infraction: { ville: f.ville || null, lieu: f.lieu || null, canton: f.canton || null, pays: doc?.lieu_infraction?.pays || null },
        driver_id: f.driver_id || "",
        ...(isAdmin ? { notes_internes: f.notes_internes || null } : {}),
      });
      toast.success("Fiche amende mise à jour");
      FINE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      qc.invalidateQueries({ queryKey: ["fine-history", doc.id] });
    } catch (e) { toast.error(errDetail(e, "Enregistrement impossible")); } finally { setBusy(false); }
  };

  return (
    <section className="space-y-3" data-testid="fine-info-form">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <F label="Référence autorité"><Input value={f.numero} onChange={set("numero")} disabled={!canEdit} data-testid="fine-field-numero" /></F>
        <F label="Dossier interne"><Input value={f.dossier_interne} onChange={set("dossier_interne")} disabled={!canEdit} data-testid="fine-field-dossier" /></F>
        <F label="Autorité"><Input value={f.fournisseur} onChange={set("fournisseur")} disabled={!canEdit} data-testid="fine-field-autorite" /></F>
        <F label="Type d'infraction">
          <Select value={f.type_infraction} onValueChange={set("type_infraction")} disabled={!canEdit}>
            <SelectTrigger data-testid="fine-field-type"><SelectValue /></SelectTrigger>
            <SelectContent>{INFRACTION_TYPES.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}
              {!INFRACTION_TYPES.some(([c]) => c === f.type_infraction) && f.type_infraction && <SelectItem value={f.type_infraction}>{f.type_infraction}</SelectItem>}
            </SelectContent>
          </Select>
        </F>
        <F label="Priorité">
          <Select value={f.priorite} onValueChange={set("priorite")} disabled={!canEdit}>
            <SelectTrigger data-testid="fine-field-priorite"><SelectValue /></SelectTrigger>
            <SelectContent>{PRIORITIES.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}</SelectContent>
          </Select>
        </F>
        <F label="Conducteur">
          <DriverPicker value={f.driver_id} onChange={(v) => setF((p) => ({ ...p, driver_id: v }))} disabled={!canEdit} testId="fine-driver-picker" />
        </F>
        <F label="Date infraction"><Input type="date" value={f.date_debut} onChange={set("date_debut")} disabled={!canEdit} data-testid="fine-field-date-infraction" /></F>
        <F label="Heure"><Input value={f.heure_infraction} onChange={set("heure_infraction")} placeholder="HH:MM" disabled={!canEdit} data-testid="fine-field-heure" /></F>
        <F label="Échéance de paiement"><Input type="date" value={f.date_expiration} onChange={set("date_expiration")} disabled={!canEdit} data-testid="fine-field-echeance" /></F>
        <F label="Reçue le"><Input type="date" value={f.date_reception} onChange={set("date_reception")} disabled={!canEdit} data-testid="fine-field-reception" /></F>
        <F label="Amende (hors frais)"><Input type="number" step="0.05" min="0" value={f.montant_amende} onChange={set("montant_amende")} disabled={!canEdit} data-testid="fine-field-montant-amende" /></F>
        <F label="Frais administratifs"><Input type="number" step="0.05" min="0" value={f.frais_admin} onChange={set("frais_admin")} disabled={!canEdit} data-testid="fine-field-frais" /></F>
        <F label="Ville"><Input value={f.ville} onChange={set("ville")} disabled={!canEdit} data-testid="fine-field-ville" /></F>
        <F label="Lieu"><Input value={f.lieu} onChange={set("lieu")} disabled={!canEdit} data-testid="fine-field-lieu" /></F>
        <F label="Canton"><Input value={f.canton} onChange={set("canton")} disabled={!canEdit} data-testid="fine-field-canton" /></F>
        {isAdmin && (
          <F label="Notes internes (admin uniquement)" className="col-span-2 sm:col-span-3">
            <Textarea rows={2} value={f.notes_internes} onChange={set("notes_internes")} disabled={!canEdit} data-testid="fine-field-notes-internes" />
          </F>
        )}
      </div>
      {canEdit && (
        <div className="flex justify-end">
          <Button size="sm" onClick={save} disabled={busy} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fine-info-save">
            <Save className="h-4 w-4" /> {busy ? "Enregistrement…" : "Enregistrer la fiche"}
          </Button>
        </div>
      )}
    </section>
  );
}
