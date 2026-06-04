import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, ScrollText, Calendar, Weight, Users, ScanLine } from "lucide-react";
import { updateVehicle } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import DocFolderSection from "@/components/DocFolderSection";

const F = ["date_mise_circulation", "poids_total", "nombre_places"];
const pick = (c = {}) => Object.fromEntries(F.map((k) => [k, c[k] ?? ""]));

export default function CarteGriseTab({ vehicle, onSaved, docs, refetchDocs }) {
  const c = vehicle.carte_grise || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(c));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        carte_grise: {
          date_mise_circulation: form.date_mise_circulation || null,
          poids_total: Number(form.poids_total) || 0,
          nombre_places: Number(form.nombre_places) || 0,
        },
      });
      toast.success("Carte grise enregistrée");
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
      <div className="flex items-start gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-800">
        <ScanLine className="mt-0.5 h-5 w-5 shrink-0 text-sky-500" />
        <div>
          <p className="font-semibold">OCR automatique — bientôt disponible</p>
          <p className="text-sky-700">La lecture automatique (plaque, VIN, mise en circulation, poids, places) pré-remplira ces champs. Pour la V1, saisissez-les manuellement.</p>
        </div>
      </div>

      {edit ? (
        <SectionCard title="Modifier la carte grise" testId="carte-grise-edit">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <FormRow label="Mise en circulation"><Input data-testid="cg-date_mise_circulation" type="date" value={form.date_mise_circulation || ""} onChange={(e) => set("date_mise_circulation", e.target.value)} /></FormRow>
            <FormRow label="Poids total (kg)"><Input data-testid="cg-poids_total" type="number" value={form.poids_total} onChange={(e) => set("poids_total", e.target.value)} /></FormRow>
            <FormRow label="Nombre de places"><Input data-testid="cg-nombre_places" type="number" value={form.nombre_places} onChange={(e) => set("nombre_places", e.target.value)} /></FormRow>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="cg-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard
          title="Carte grise"
          description="Informations véhicule officielles"
          testId="carte-grise-view"
          action={<Button variant="outline" size="sm" onClick={() => { setForm(pick(c)); setEdit(true); }} data-testid="cg-edit-btn" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Modifier</Button>}
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="Plaque" value={vehicle.plaque} icon={ScrollText} />
            <Stat label="VIN" value={vehicle.vin} />
            <Stat label="Mise en circulation" value={dateFr(c.date_mise_circulation)} icon={Calendar} />
            <Stat label="Poids total" value={c.poids_total ? `${c.poids_total} kg` : "—"} icon={Weight} />
            <Stat label="Nombre de places" value={c.nombre_places || "—"} icon={Users} />
          </div>
        </SectionCard>
      )}

      <SectionCard title="Documents carte grise" description="Recto · Verso · Historique" testId="carte-grise-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Carte grise" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>
    </div>
  );
}
