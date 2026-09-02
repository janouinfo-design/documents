import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, ShieldCheck, Building2, Hash, Phone, LifeBuoy } from "lucide-react";
import { updateVehicle } from "@/lib/api";
import { chf, dateFr, daysLabel } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { Label } from "@/components/ui/label";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import AlertChips from "@/components/AlertChips";
import StatusBadge from "@/components/StatusBadge";
import DocFolderSection from "@/components/DocFolderSection";
import DocumentScanCard from "@/components/DocumentScanCard";

const F = ["compagnie", "numero_police", "type_couverture", "prime_annuelle", "franchise", "assistance", "contact_sinistre", "date_debut", "date_echeance"];
const pick = (a = {}) => Object.fromEntries(F.map((k) => [k, a[k] ?? (k === "assistance" ? false : "")]));
const COVERAGES = ["RC", "Casco partielle", "Casco complète", "RC + Casco complète"];

export default function AssuranceTab({ vehicle, metrics, onSaved, docs, refetchDocs }) {
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const a = vehicle.assurance || {};
  const am = metrics.assurance || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(a));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        assurance: {
          ...form,
          prime_annuelle: Number(form.prime_annuelle) || 0,
          franchise: Number(form.franchise) || 0,
          date_debut: form.date_debut || null,
          date_echeance: form.date_echeance || null,
        },
      });
      toast.success("Assurance enregistrée");
      onSaved?.();
      setEdit(false);
    } catch {
      toast.error("Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">Renouvellement · {dateFr(a.date_echeance)}</span>
          <StatusBadge level={am.level} days={am.days_remaining} showDays />
        </div>
        <AlertChips days={am.days_remaining} thresholds={[90, 60, 30]} testId="assurance-alerts" />
      </div>

      {edit ? (
        <SectionCard title="Modifier l'assurance" testId="assurance-edit">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormRow label="Compagnie d'assurance"><Input data-testid="assurance-compagnie" value={form.compagnie} onChange={(e) => set("compagnie", e.target.value)} /></FormRow>
            <FormRow label="Numéro de police"><Input data-testid="assurance-numero_police" value={form.numero_police} onChange={(e) => set("numero_police", e.target.value)} /></FormRow>
            <FormRow label="Type de couverture">
              <Select value={form.type_couverture || undefined} onValueChange={(v) => set("type_couverture", v)}>
                <SelectTrigger data-testid="assurance-type_couverture"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                <SelectContent>{COVERAGES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Contact sinistre"><Input data-testid="assurance-contact_sinistre" value={form.contact_sinistre} onChange={(e) => set("contact_sinistre", e.target.value)} /></FormRow>
            <FormRow label="Prime annuelle (CHF)"><Input data-testid="assurance-prime_annuelle" type="number" value={form.prime_annuelle} onChange={(e) => set("prime_annuelle", e.target.value)} /></FormRow>
            <FormRow label="Franchise (CHF)"><Input data-testid="assurance-franchise" type="number" value={form.franchise} onChange={(e) => set("franchise", e.target.value)} /></FormRow>
            <FormRow label="Date de début" ><Input data-testid="assurance-date_debut" type="date" value={form.date_debut || ""} onChange={(e) => set("date_debut", e.target.value)} /></FormRow>
            <FormRow label="Date d'échéance"><Input data-testid="assurance-date_echeance" type="date" value={form.date_echeance || ""} onChange={(e) => set("date_echeance", e.target.value)} /></FormRow>
            <div className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-2.5 sm:col-span-2">
              <Label className="text-sm text-slate-700">Assistance incluse</Label>
              <Switch data-testid="assurance-assistance" checked={!!form.assistance} onCheckedChange={(v) => set("assistance", v)} />
            </div>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="assurance-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard
          title="Police d'assurance"
          description={a.compagnie || "Aucune compagnie renseignée"}
          testId="assurance-view"
          action={!readOnly && (<Button variant="outline" size="sm" onClick={() => { setForm(pick(a)); setEdit(true); }} data-testid="assurance-edit-btn" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Modifier</Button>)}
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="Compagnie" value={a.compagnie} icon={Building2} />
            <Stat label="N° police" value={a.numero_police} icon={Hash} />
            <Stat label="Couverture" value={a.type_couverture} icon={ShieldCheck} />
            <Stat label="Prime annuelle" value={chf(a.prime_annuelle)} />
            <Stat label="Franchise" value={chf(a.franchise)} />
            <Stat label="Assistance" value={a.assistance ? "Incluse" : "Non"} icon={LifeBuoy} />
            <Stat label="Contact sinistre" value={a.contact_sinistre} icon={Phone} />
            <Stat label="Début" value={dateFr(a.date_debut)} />
            <Stat label="Échéance" value={dateFr(a.date_echeance)} />
          </div>
        </SectionCard>
      )}

      <DocumentScanCard
        vehicle={vehicle}
        docType="assurance"
        testIdPrefix="assurance-scan"
        title="Scan intelligent — Police d'assurance"
        description="Photographiez ou importez la police : compagnie, n° de police, couverture, prime, dates… sont extraits puis soumis à votre validation."
        onValidated={() => { onSaved?.(); refetchDocs?.(); }}
      />

      <SectionCard title="Documents assurance" description="Police · Certificat · Conditions générales" testId="assurance-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Assurance" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>
    </div>
  );
}
