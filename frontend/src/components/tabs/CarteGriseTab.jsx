import { useState } from "react";
import { toast } from "sonner";
import {
  Pencil, Loader2, ScrollText, Calendar, Weight, Users, Camera, FolderUp,
  Fuel, Gauge, Zap, Leaf, Hash,
} from "lucide-react";
import { updateVehicle } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import DocFolderSection from "@/components/DocFolderSection";
import ScanDocumentDialog from "@/components/ScanDocumentDialog";

const CG_FIELDS = ["date_mise_circulation", "poids_total", "nombre_places"];
const TECH_FIELDS = [
  "type_carburant", "cylindree_cm3", "puissance_kw", "poids_vide", "categorie",
  "co2_g_km", "conso_officielle_l_100km", "variante", "numero_homologation",
];

const pick = (vehicle) => ({
  ...Object.fromEntries(CG_FIELDS.map((k) => [k, (vehicle.carte_grise || {})[k] ?? ""])),
  ...Object.fromEntries(TECH_FIELDS.map((k) => [k, vehicle[k] ?? ""])),
});

export default function CarteGriseTab({ vehicle, onSaved, docs, refetchDocs }) {
  const c = vehicle.carte_grise || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(vehicle));
  const [saving, setSaving] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
  const [scanMode, setScanMode] = useState("import");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const openScan = (mode) => { setScanMode(mode); setScanOpen(true); };
  const litres = vehicle.cylindree_cm3 ? ` (${(vehicle.cylindree_cm3 / 1000).toFixed(1)} L)` : "";

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        type_carburant: form.type_carburant || "",
        cylindree_cm3: Number(form.cylindree_cm3) || 0,
        puissance_kw: Number(form.puissance_kw) || 0,
        poids_vide: Number(form.poids_vide) || 0,
        categorie: form.categorie || "",
        co2_g_km: Number(form.co2_g_km) || 0,
        conso_officielle_l_100km: Number(form.conso_officielle_l_100km) || 0,
        variante: form.variante || "",
        numero_homologation: form.numero_homologation || "",
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
        title="Scan intelligent — Permis de circulation"
        description="Photographiez ou importez le permis : plaque, VIN, carburant, cylindrée, puissance, poids… sont extraits puis soumis à votre validation."
        testId="carte-grise-ocr"
      >
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button data-testid="cg-scan-camera" onClick={() => openScan("camera")} className="gap-2 bg-slate-900 hover:bg-slate-800">
            <Camera className="h-4 w-4" /> Prendre une photo
          </Button>
          <Button data-testid="cg-scan-import" variant="outline" onClick={() => openScan("import")} className="gap-2">
            <FolderUp className="h-4 w-4" /> Importer PDF ou image
          </Button>
        </div>
      </SectionCard>

      {edit ? (
        <SectionCard title="Modifier la carte grise & données techniques" testId="carte-grise-edit">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ["date_mise_circulation", "Mise en circulation", "date"],
              ["type_carburant", "Carburant"],
              ["cylindree_cm3", "Cylindrée (cm³)", "number"],
              ["puissance_kw", "Puissance (kW)", "number"],
              ["poids_vide", "Poids à vide (kg)", "number"],
              ["poids_total", "Poids total (kg)", "number"],
              ["nombre_places", "Nombre de places", "number"],
              ["categorie", "Catégorie"],
              ["co2_g_km", "CO₂ (g/km)", "number"],
              ["conso_officielle_l_100km", "Conso officielle (L/100 km)", "number"],
              ["variante", "Variante / type"],
              ["numero_homologation", "N° homologation"],
            ].map(([k, label, type]) => (
              <FormRow key={k} label={label}>
                <Input data-testid={`cg-${k}`} type={type || "text"} value={form[k] || ""} onChange={(e) => set(k, e.target.value)} />
              </FormRow>
            ))}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="cg-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
            </Button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard
          title="Carte grise & données techniques"
          description="Informations véhicule officielles"
          testId="carte-grise-view"
          action={
            <Button variant="outline" size="sm" onClick={() => { setForm(pick(vehicle)); setEdit(true); }} data-testid="cg-edit-btn" className="gap-1.5">
              <Pencil className="h-3.5 w-3.5" /> Modifier
            </Button>
          }
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="Plaque" value={vehicle.plaque} icon={ScrollText} />
            <Stat label="VIN" value={vehicle.vin} />
            <Stat label="Mise en circulation" value={dateFr(c.date_mise_circulation)} icon={Calendar} />
            <Stat label="Carburant" value={vehicle.type_carburant || "—"} icon={Fuel} />
            <Stat label="Cylindrée" value={vehicle.cylindree_cm3 ? `${vehicle.cylindree_cm3} cm³${litres}` : "—"} icon={Gauge} />
            <Stat label="Puissance" value={vehicle.puissance_kw ? `${vehicle.puissance_kw} kW` : "—"} icon={Zap} />
            <Stat label="Poids à vide" value={vehicle.poids_vide ? `${vehicle.poids_vide} kg` : "—"} icon={Weight} />
            <Stat label="Poids total" value={c.poids_total ? `${c.poids_total} kg` : "—"} icon={Weight} />
            <Stat label="Nombre de places" value={c.nombre_places || "—"} icon={Users} />
            <Stat label="Catégorie" value={vehicle.categorie || "—"} />
            <Stat label="CO₂" value={vehicle.co2_g_km ? `${vehicle.co2_g_km} g/km` : "—"} icon={Leaf} />
            <Stat label="Conso officielle" value={vehicle.conso_officielle_l_100km ? `${vehicle.conso_officielle_l_100km} L/100 km` : "—"} icon={Fuel} />
            <Stat label="Variante / type" value={vehicle.variante || "—"} />
            <Stat label="N° homologation" value={vehicle.numero_homologation || "—"} icon={Hash} />
          </div>
        </SectionCard>
      )}

      <SectionCard title="Documents carte grise" description="Recto · Verso · Historique" testId="carte-grise-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Carte grise" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>

      <ScanDocumentDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        vehicle={vehicle}
        initialMode={scanMode}
        forcedType="permis_circulation"
        onValidated={() => { onSaved?.(); refetchDocs?.(); }}
      />
    </div>
  );
}
