import { useState } from "react";
import { toast } from "sonner";
import { Upload, FileSpreadsheet, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { uploadFuelImport } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";

// Étape 1 — upload CSV/XLSX : crée uniquement le job (aucun import au simple upload)
export default function UploadStep({ onJob }) {
  const [file, setFile] = useState(null);
  const [fournisseur, setFournisseur] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const job = await uploadFuelImport(file, fournisseur.trim() || undefined);
      if (job.same_file_warning) toast.warning(`Ce fichier a déjà été importé (${job.same_file_warning.length} fois) — les doublons seront détectés.`);
      onJob(job);
    } catch (e) { toast.error(errDetail(e, "Fichier refusé")); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6" data-testid="fuel-import-upload-step">
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-slate-900 p-2.5 text-white"><FileSpreadsheet className="h-5 w-5" /></div>
        <div>
          <p className="font-display text-base font-bold text-slate-900">Nouvel import carburant</p>
          <p className="text-xs text-slate-500">CSV (; , tab) ou XLSX — ≤ 30 MB, ≤ 20 000 lignes. Rien n'est importé avant la confirmation explicite.</p>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Fichier</Label>
          <Input type="file" accept=".csv,.txt,.xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="fuel-import-file-input" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Fournisseur (facultatif — réutilise le mapping sauvegardé)</Label>
          <Input value={fournisseur} onChange={(e) => setFournisseur(e.target.value)} placeholder="Migrol, Shell, Agrola…" data-testid="fuel-import-fournisseur-input" />
        </div>
      </div>
      <Button onClick={submit} disabled={!file || busy} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-import-upload-btn">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Lire le fichier
      </Button>
    </div>
  );
}
