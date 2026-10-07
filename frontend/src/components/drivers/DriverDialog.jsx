import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { createDriver, updateDriver } from "@/lib/api";
import { F } from "@/components/documents/nofileShared";

const EMPTY = { nom: "", prenom: "", email: "", telephone: "", matricule_interne: "", navixy_employee_id: "", groupe: "", date_debut: "", date_fin: "", notes: "", actif: true };
const n = (v) => (v === "" || v === null || v === undefined ? null : v);

// Création / édition d'un conducteur. Le nom/prénom est une donnée d'affichage : aucune unicité, aucun matching.
export default function DriverDialog({ open, onOpenChange, driver, onSaved }) {
  const qc = useQueryClient();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));

  useEffect(() => {
    if (!open) return;
    setF(driver ? Object.fromEntries(Object.keys(EMPTY).map((k) => [k, driver[k] ?? (k === "actif" ? true : "")])) : EMPTY);
  }, [open, driver]);

  const submit = async () => {
    setBusy(true);
    try {
      const body = { nom: f.nom.trim(), prenom: n(f.prenom.trim()), email: n(f.email.trim()), telephone: n(f.telephone.trim()),
        matricule_interne: n(f.matricule_interne.trim()), navixy_employee_id: f.navixy_employee_id === "" ? null : Number(f.navixy_employee_id),
        groupe: n(f.groupe.trim()), date_debut: n(f.date_debut), date_fin: n(f.date_fin), notes: n(f.notes.trim()), actif: !!f.actif };
      const r = driver ? await updateDriver(driver.id, body) : await createDriver(body);
      toast.success(driver ? `Conducteur ${r.display} mis à jour` : `Conducteur ${r.display} créé`);
      qc.invalidateQueries({ queryKey: ["drivers"] });
      onSaved?.(r);
      onOpenChange(false);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((typeof d === "string" && d) || d?.message || "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto" data-testid="driver-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">{driver ? "Modifier le conducteur" : "Nouveau conducteur"}</DialogTitle>
          <DialogDescription>Identité technique = identifiant stable du tenant. Le nom n'est jamais utilisé pour rapprocher des données.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <F label="Nom *"><Input data-testid="driver-nom" value={f.nom} onChange={set("nom")} /></F>
          <F label="Prénom"><Input data-testid="driver-prenom" value={f.prenom} onChange={set("prenom")} /></F>
          <F label="Matricule interne"><Input data-testid="driver-matricule" value={f.matricule_interne} onChange={set("matricule_interne")} placeholder="ex. CH-042" /></F>
          <F label="Groupe / équipe"><Input data-testid="driver-groupe" value={f.groupe} onChange={set("groupe")} /></F>
          <F label="Email (unique dans le tenant)"><Input data-testid="driver-email" type="email" value={f.email} onChange={set("email")} /></F>
          <F label="Téléphone"><Input data-testid="driver-telephone" value={f.telephone} onChange={set("telephone")} /></F>
          <F label="Début d'activité"><Input data-testid="driver-date-debut" type="date" value={f.date_debut} onChange={set("date_debut")} /></F>
          <F label="Fin d'activité"><Input data-testid="driver-date-fin" type="date" value={f.date_fin} onChange={set("date_fin")} /></F>
          <F label="ID employé Navixy (attribut, pas une clé)"><Input data-testid="driver-navixy-id" type="number" min="0" value={f.navixy_employee_id} onChange={set("navixy_employee_id")} /></F>
          <F label="Actif">
            <div className="flex h-9 items-center gap-2">
              <Switch checked={!!f.actif} onCheckedChange={set("actif")} data-testid="driver-actif" />
              <span className="text-sm text-slate-600">{f.actif ? "Affectable" : "Désactivé (non affectable)"}</span>
            </div>
          </F>
          <F label="Notes" className="sm:col-span-2"><Textarea data-testid="driver-notes" rows={2} value={f.notes} onChange={set("notes")} /></F>
        </div>
        <DialogFooter>
          <Button variant="outline" data-testid="driver-cancel" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="driver-save" onClick={submit} disabled={busy || !f.nom.trim()} className="bg-slate-900 hover:bg-slate-800">
            {busy ? "Enregistrement…" : driver ? "Enregistrer" : "Créer le conducteur"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
