import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { updateDocument } from "@/lib/api";

const FREQUENCES = [["unique", "Unique"], ["mensuel", "Mensuel"], ["trimestriel", "Trimestriel"], ["semestriel", "Semestriel"], ["annuel", "Annuel"]];

const F = ({ label, children }) => (
  <div className="space-y-1">
    <Label className="text-xs text-slate-500">{label}</Label>
    {children}
  </div>
);

export default function DocumentEditDialog({ doc, categories = [], open, onOpenChange, onSaved }) {
  const qc = useQueryClient();
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (doc) {
      setF({
        label: doc.label || "", folder: doc.folder || "Divers", sub_category: doc.sub_category || "",
        fournisseur: doc.fournisseur || "", numero: doc.numero || "",
        date_debut: (doc.date_debut || "").slice(0, 10), date_expiration: (doc.date_expiration || "").slice(0, 10),
        preavis_jours: doc.preavis_jours ?? "", montant: doc.montant ?? "", devise: doc.devise || "CHF",
        frequence: doc.frequence || "", responsable: doc.responsable || "",
        tags: (doc.tags || []).join(", "), notes: doc.notes || "",
        renouvellement_auto: !!doc.renouvellement_auto, en_renouvellement: !!doc.en_renouvellement,
        a_verifier: !!doc.a_verifier, archived: !!doc.archived,
      });
    }
  }, [doc]);

  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v }));
  const setI = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  const subCats = (categories.find((c) => c.name === f.folder) || {}).sub_categories || [];

  const save = async () => {
    setBusy(true);
    try {
      await updateDocument(doc.id, {
        label: f.label || null, folder: f.folder, sub_category: f.sub_category || null,
        fournisseur: f.fournisseur || null, numero: f.numero || null,
        date_debut: f.date_debut || null, date_expiration: f.date_expiration || null,
        preavis_jours: f.preavis_jours === "" ? null : Number(f.preavis_jours),
        montant: f.montant === "" ? null : Number(f.montant),
        devise: f.devise, frequence: f.frequence || null, responsable: f.responsable || null,
        tags: f.tags.split(",").map((s) => s.trim()).filter(Boolean), notes: f.notes || null,
        renouvellement_auto: f.renouvellement_auto, en_renouvellement: f.en_renouvellement,
        a_verifier: f.a_verifier, archived: f.archived,
      });
      toast.success("Fiche document enregistrée");
      qc.invalidateQueries({ queryKey: ["all-documents"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'enregistrement");
    } finally {
      setBusy(false);
    }
  };

  if (!doc) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" data-testid="doc-edit-dialog">
        <DialogHeader>
          <DialogTitle>Fiche document — {doc.label || doc.original_filename}</DialogTitle>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <F label="Nom du document"><Input data-testid="doc-edit-label" value={f.label} onChange={setI("label")} placeholder={doc.original_filename} /></F>
          <F label="Catégorie">
            <Select value={f.folder} onValueChange={set("folder")}>
              <SelectTrigger data-testid="doc-edit-folder"><SelectValue /></SelectTrigger>
              <SelectContent>{categories.map((c) => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </F>
          <F label={subCats.length ? "Sous-catégorie" : "Sous-catégorie (libre)"}>
            {subCats.length ? (
              <Select value={f.sub_category || "__none__"} onValueChange={(v) => set("sub_category")(v === "__none__" ? "" : v)}>
                <SelectTrigger data-testid="doc-edit-subcategory"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {subCats.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            ) : <Input data-testid="doc-edit-subcategory" value={f.sub_category} onChange={setI("sub_category")} />}
          </F>
          <F label="Organisme / fournisseur"><Input data-testid="doc-edit-fournisseur" value={f.fournisseur} onChange={setI("fournisseur")} /></F>
          <F label="N° contrat / document"><Input data-testid="doc-edit-numero" value={f.numero} onChange={setI("numero")} /></F>
          <F label="Responsable"><Input data-testid="doc-edit-responsable" value={f.responsable} onChange={setI("responsable")} /></F>
          <F label="Date de début"><Input data-testid="doc-edit-date-debut" type="date" value={f.date_debut} onChange={setI("date_debut")} /></F>
          <F label="Date d'expiration"><Input data-testid="doc-edit-date-expiration" type="date" value={f.date_expiration} onChange={setI("date_expiration")} /></F>
          <F label="Préavis (jours)"><Input data-testid="doc-edit-preavis" type="number" min="0" max="730" value={f.preavis_jours} onChange={setI("preavis_jours")} placeholder="30" /></F>
          <F label="Montant"><Input data-testid="doc-edit-montant" type="number" min="0" step="0.05" value={f.montant} onChange={setI("montant")} /></F>
          <F label="Devise">
            <Select value={f.devise} onValueChange={set("devise")}>
              <SelectTrigger data-testid="doc-edit-devise"><SelectValue /></SelectTrigger>
              <SelectContent>{["CHF", "EUR", "USD"].map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
            </Select>
          </F>
          <F label="Fréquence">
            <Select value={f.frequence || "__none__"} onValueChange={(v) => set("frequence")(v === "__none__" ? "" : v)}>
              <SelectTrigger data-testid="doc-edit-frequence"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {FREQUENCES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
              </SelectContent>
            </Select>
          </F>
          <div className="sm:col-span-2">
            <F label="Tags (séparés par des virgules)"><Input data-testid="doc-edit-tags" value={f.tags} onChange={setI("tags")} placeholder="contrat, flotte, urgent" /></F>
          </div>
          <div className="sm:col-span-2">
            <F label="Notes"><Textarea data-testid="doc-edit-notes" rows={3} value={f.notes} onChange={setI("notes")} /></F>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:col-span-2">
            {[["renouvellement_auto", "Renouvellement automatique"], ["en_renouvellement", "En renouvellement"],
              ["a_verifier", "À vérifier"], ["archived", "Archivé"]].map(([k, l]) => (
              <label key={k} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700">
                {l}
                <Switch data-testid={`doc-edit-${k}`} checked={!!f[k]} onCheckedChange={set(k)} />
              </label>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="doc-edit-save" onClick={save} disabled={busy} className="bg-slate-900 hover:bg-slate-800">
            {busy ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
