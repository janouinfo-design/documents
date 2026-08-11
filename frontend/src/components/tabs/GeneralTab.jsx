import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, Car, Calendar, Hash, Gauge, Users, MapPin, User, Radio, Wrench, ClipboardList } from "lucide-react";
import { updateVehicle, uploadFile } from "@/lib/api";
import { fmtKm, dateFr } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import DropZone from "@/components/DropZone";
import ProvenanceSection from "@/components/ProvenanceSection";

const GEN_FIELDS = ["photo_url", "plaque", "marque", "modele", "annee", "vin", "kilometrage", "groupe", "base", "responsable", "tracker_gps", "prochaine_maintenance", "prochaine_expertise"];
const pick = (v) => Object.fromEntries(GEN_FIELDS.map((k) => [k, v[k] ?? ""]));

export default function GeneralTab({ vehicle, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(vehicle));
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const set = (k, val) => setForm((f) => ({ ...f, [k]: val }));

  const startEdit = () => {
    setForm(pick(vehicle));
    setEdit(true);
  };

  const handlePhoto = async (files) => {
    setUploading(true);
    try {
      const res = await uploadFile(files[0], vehicle.id);
      set("photo_url", `${process.env.REACT_APP_BACKEND_URL}/api/files/${res.path}`);
      toast.success("Photo mise à jour");
    } catch {
      toast.error("Échec du téléversement");
    } finally {
      setUploading(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        ...form,
        annee: Number(form.annee) || 0,
        kilometrage: Number(form.kilometrage) || 0,
        prochaine_maintenance: form.prochaine_maintenance || null,
        prochaine_expertise: form.prochaine_expertise || null,
      });
      toast.success("Informations enregistrées");
      onSaved?.();
      setEdit(false);
    } catch {
      toast.error("Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  if (edit) {
    return (
      <SectionCard title="Modifier les informations générales" testId="general-edit">
        <div className="mb-5">
          <FormRow label="Photo du véhicule">
            <div className="flex items-center gap-3">
              {form.photo_url && <img src={form.photo_url} alt="aperçu" className="h-16 w-24 rounded-lg border border-slate-200 object-cover" />}
              <div className="flex-1"><DropZone onFiles={handlePhoto} multiple={false} busy={uploading} compact accept="image/*" label="Changer la photo" testId="general-photo-drop" /></div>
            </div>
          </FormRow>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {[
            ["plaque", "Plaque"], ["vin", "VIN"], ["marque", "Marque"], ["modele", "Modèle"],
            ["annee", "Année", "number"], ["kilometrage", "Kilométrage", "number"],
            ["groupe", "Groupe"], ["base", "Base"], ["responsable", "Responsable"], ["tracker_gps", "Tracker GPS"],
            ["prochaine_maintenance", "Prochaine maintenance", "date"], ["prochaine_expertise", "Prochaine expertise", "date"],
          ].map(([k, label, type]) => (
            <FormRow key={k} label={label}>
              <Input data-testid={`gen-${k}`} type={type || "text"} value={form[k] || ""} onChange={(e) => set(k, e.target.value)} />
            </FormRow>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
          <Button data-testid="general-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
          </Button>
        </div>
      </SectionCard>
    );
  }

  return (
    <div className="space-y-5">
      <SectionCard
        title="Informations générales"
      description="Identité administrative du véhicule"
      testId="general-view"
      action={<Button variant="outline" size="sm" onClick={startEdit} data-testid="general-edit-btn" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Modifier</Button>}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Stat label="Marque" value={vehicle.marque} icon={Car} />
        <Stat label="Modèle" value={vehicle.modele} icon={Car} />
        <Stat label="Année" value={vehicle.annee || "—"} icon={Calendar} />
        <Stat label="VIN" value={vehicle.vin} icon={Hash} />
        <Stat label="Kilométrage" value={fmtKm(vehicle.kilometrage)} icon={Gauge} />
        <Stat label="Groupe" value={vehicle.groupe} icon={Users} />
        <Stat label="Base" value={vehicle.base} icon={MapPin} />
        <Stat label="Responsable" value={vehicle.responsable} icon={User} />
        <Stat label="Tracker GPS" value={vehicle.tracker_gps} icon={Radio} />
        <Stat label="Prochaine maintenance" value={dateFr(vehicle.prochaine_maintenance)} icon={Wrench} />
        <Stat label="Prochaine expertise" value={dateFr(vehicle.prochaine_expertise)} icon={ClipboardList} />
      </div>
      </SectionCard>
      <ProvenanceSection vehicleId={vehicle.id} />
    </div>
  );
}
