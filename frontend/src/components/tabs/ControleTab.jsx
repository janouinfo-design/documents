import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, ClipboardCheck, Calendar, Building2, CheckCircle2 } from "lucide-react";
import { updateVehicle } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import AlertChips from "@/components/AlertChips";
import StatusBadge from "@/components/StatusBadge";
import DocFolderSection from "@/components/DocFolderSection";
import DocumentScanCard from "@/components/DocumentScanCard";

const F = ["date_dernier", "date_prochain", "centre", "resultat"];
const pick = (c = {}) => Object.fromEntries(F.map((k) => [k, c[k] ?? ""]));
const RESULTS = ["Conforme", "Conforme avec remarques", "Non conforme"];

export default function ControleTab({ vehicle, metrics, onSaved, docs, refetchDocs }) {
  const c = vehicle.controle_technique || {};
  const cm = metrics.controle || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(c));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        controle_technique: {
          date_dernier: form.date_dernier || null,
          date_prochain: form.date_prochain || null,
          centre: form.centre,
          resultat: form.resultat,
        },
      });
      toast.success("Contrôle technique enregistré");
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
          <span className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">Prochain contrôle · {dateFr(c.date_prochain)}</span>
          <StatusBadge level={cm.level} days={cm.days_remaining} showDays />
        </div>
        <AlertChips days={cm.days_remaining} thresholds={[90, 60, 30, 7]} testId="controle-alerts" />
      </div>

      {edit ? (
        <SectionCard title="Modifier le contrôle technique" testId="controle-edit">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormRow label="Date dernier contrôle"><Input data-testid="ctrl-date_dernier" type="date" value={form.date_dernier || ""} onChange={(e) => set("date_dernier", e.target.value)} /></FormRow>
            <FormRow label="Date prochain contrôle"><Input data-testid="ctrl-date_prochain" type="date" value={form.date_prochain || ""} onChange={(e) => set("date_prochain", e.target.value)} /></FormRow>
            <FormRow label="Centre de contrôle"><Input data-testid="ctrl-centre" value={form.centre} onChange={(e) => set("centre", e.target.value)} /></FormRow>
            <FormRow label="Résultat">
              <Select value={form.resultat || undefined} onValueChange={(v) => set("resultat", v)}>
                <SelectTrigger data-testid="ctrl-resultat"><SelectValue placeholder="Sélectionner" /></SelectTrigger>
                <SelectContent>{RESULTS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="ctrl-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard
          title="Contrôle technique"
          description={c.centre || "Aucun centre renseigné"}
          testId="controle-view"
          action={<Button variant="outline" size="sm" onClick={() => { setForm(pick(c)); setEdit(true); }} data-testid="ctrl-edit-btn" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Modifier</Button>}
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="Dernier contrôle" value={dateFr(c.date_dernier)} icon={Calendar} />
            <Stat label="Prochain contrôle" value={dateFr(c.date_prochain)} icon={Calendar} />
            <Stat label="Centre" value={c.centre} icon={Building2} />
            <Stat label="Résultat" value={c.resultat} icon={CheckCircle2} />
          </div>
        </SectionCard>
      )}

      <DocumentScanCard
        vehicle={vehicle}
        docType="controle_technique"
        testIdPrefix="ctrl-scan"
        title="Scan intelligent — Expertise / Contrôle technique"
        description="Photographiez ou importez le rapport : dates de contrôle, centre, résultat… sont extraits puis soumis à votre validation."
        onValidated={() => { onSaved?.(); refetchDocs?.(); }}
      />

      <SectionCard title="Rapports de contrôle" description="Rapport PDF d'expertise" testId="controle-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Contrôle technique" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>
    </div>
  );
}
