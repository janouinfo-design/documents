import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, ScrollText, Calendar, Weight, Users, Sparkles, Check } from "lucide-react";
import { updateVehicle, ocrCarteGrise } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import DocFolderSection from "@/components/DocFolderSection";
import DropZone from "@/components/DropZone";

const F = ["date_mise_circulation", "poids_total", "nombre_places"];
const pick = (c = {}) => Object.fromEntries(F.map((k) => [k, c[k] ?? ""]));

export default function CarteGriseTab({ vehicle, onSaved, docs, refetchDocs }) {
  const c = vehicle.carte_grise || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(c));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const [ocrBusy, setOcrBusy] = useState(false);
  const [ocr, setOcr] = useState(null);

  const runOcr = async (files) => {
    setOcrBusy(true);
    try {
      const res = await ocrCarteGrise(vehicle.id, files[0]);
      setOcr(res);
      toast.success("Carte grise analysée");
    } catch {
      toast.error("Échec de l'analyse OCR");
    } finally {
      setOcrBusy(false);
    }
  };

  const applyOcr = async () => {
    try {
      await updateVehicle(vehicle.id, {
        plaque: ocr.plaque || vehicle.plaque,
        vin: ocr.vin || vehicle.vin,
        carte_grise: {
          date_mise_circulation: ocr.date_mise_circulation || c.date_mise_circulation || null,
          poids_total: ocr.poids_total || c.poids_total || 0,
          nombre_places: ocr.nombre_places || c.nombre_places || 0,
        },
      });
      toast.success("Champs pré-remplis appliqués");
      setOcr(null);
      onSaved?.();
    } catch {
      toast.error("Erreur lors de l'application");
    }
  };

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
      <SectionCard
        title="OCR automatique — Scanner la carte grise"
        description="Déposez une photo du recto : plaque, VIN, mise en circulation, poids et places sont lus automatiquement (GPT-4o)."
        testId="carte-grise-ocr"
      >
        <DropZone
          onFiles={runOcr}
          multiple={false}
          busy={ocrBusy}
          accept="image/*"
          label="Déposer une photo de la carte grise"
          hint="JPG · PNG · WEBP"
          testId="ocr-dropzone"
        />
        {ocr && (
          <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4" data-testid="ocr-result">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-emerald-800">
              <Sparkles className="h-4 w-4" /> Données extraites
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
              {[
                ["Plaque", ocr.plaque],
                ["VIN", ocr.vin],
                ["Mise en circ.", ocr.date_mise_circulation],
                ["Poids total", ocr.poids_total ? `${ocr.poids_total} kg` : null],
                ["Places", ocr.nombre_places || null],
              ].map(([k, v]) => (
                <div key={k}>
                  <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-emerald-600">{k}</p>
                  <p className="font-medium text-slate-800">{v || "—"}</p>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={applyOcr} data-testid="ocr-apply" className="gap-1.5 bg-emerald-600 hover:bg-emerald-700">
                <Check className="h-3.5 w-3.5" /> Appliquer aux champs
              </Button>
              <Button size="sm" variant="outline" onClick={() => setOcr(null)}>Ignorer</Button>
            </div>
          </div>
        )}
      </SectionCard>

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
