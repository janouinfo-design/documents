import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Truck, Loader2 } from "lucide-react";
import { createVehicle, uploadFile } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FormRow } from "@/components/Field";
import DropZone from "@/components/DropZone";

const EMPTY = {
  plaque: "", marque: "", modele: "", annee: "", vin: "", kilometrage: "",
  groupe: "", base: "", responsable: "", tracker_gps: "", photo_url: "",
};

export default function NewVehicleDialog({ open, onOpenChange }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handlePhoto = async (files) => {
    setUploading(true);
    try {
      const res = await uploadFile(files[0]);
      set("photo_url", `${process.env.REACT_APP_BACKEND_URL}/api/files/${res.path}`);
      toast.success("Photo ajoutée");
    } catch {
      toast.error("Échec du téléversement de la photo");
    } finally {
      setUploading(false);
    }
  };

  const submit = async () => {
    if (!form.plaque.trim()) {
      toast.error("La plaque est obligatoire");
      return;
    }
    setSaving(true);
    try {
      await createVehicle({
        ...form,
        annee: Number(form.annee) || 0,
        kilometrage: Number(form.kilometrage) || 0,
      });
      qc.invalidateQueries({ queryKey: ["vehicles"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Véhicule créé");
      setForm(EMPTY);
      onOpenChange(false);
    } catch {
      toast.error("Erreur lors de la création");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl" data-testid="new-vehicle-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Truck className="h-5 w-5" /> Nouveau véhicule
          </DialogTitle>
          <DialogDescription className="sr-only">Formulaire de création d'un nouveau véhicule</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormRow label="Plaque *">
            <Input data-testid="nv-plaque" value={form.plaque} onChange={(e) => set("plaque", e.target.value)} placeholder="GE 123 456" />
          </FormRow>
          <FormRow label="VIN">
            <Input data-testid="nv-vin" value={form.vin} onChange={(e) => set("vin", e.target.value)} placeholder="WDB..." />
          </FormRow>
          <FormRow label="Marque">
            <Input data-testid="nv-marque" value={form.marque} onChange={(e) => set("marque", e.target.value)} placeholder="Mercedes-Benz" />
          </FormRow>
          <FormRow label="Modèle">
            <Input data-testid="nv-modele" value={form.modele} onChange={(e) => set("modele", e.target.value)} placeholder="Sprinter" />
          </FormRow>
          <FormRow label="Année">
            <Input data-testid="nv-annee" type="number" value={form.annee} onChange={(e) => set("annee", e.target.value)} placeholder="2024" />
          </FormRow>
          <FormRow label="Kilométrage">
            <Input data-testid="nv-km" type="number" value={form.kilometrage} onChange={(e) => set("kilometrage", e.target.value)} placeholder="0" />
          </FormRow>
          <FormRow label="Groupe">
            <Input data-testid="nv-groupe" value={form.groupe} onChange={(e) => set("groupe", e.target.value)} placeholder="Livraison" />
          </FormRow>
          <FormRow label="Base">
            <Input data-testid="nv-base" value={form.base} onChange={(e) => set("base", e.target.value)} placeholder="Genève" />
          </FormRow>
          <FormRow label="Responsable">
            <Input data-testid="nv-responsable" value={form.responsable} onChange={(e) => set("responsable", e.target.value)} placeholder="Nom Prénom" />
          </FormRow>
          <FormRow label="Tracker GPS">
            <Input data-testid="nv-tracker" value={form.tracker_gps} onChange={(e) => set("tracker_gps", e.target.value)} placeholder="LT-GPS-1010" />
          </FormRow>
          <div className="sm:col-span-2">
            <FormRow label="Photo du véhicule">
              {form.photo_url ? (
                <div className="flex items-center gap-3">
                  <img src={form.photo_url} alt="aperçu" className="h-16 w-24 rounded-lg border border-slate-200 object-cover" />
                  <Button variant="outline" size="sm" onClick={() => set("photo_url", "")}>Changer</Button>
                </div>
              ) : (
                <DropZone onFiles={handlePhoto} multiple={false} busy={uploading} compact accept="image/*" label="Photo du véhicule" testId="nv-photo-drop" />
              )}
            </FormRow>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="nv-submit" onClick={submit} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Créer le véhicule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
