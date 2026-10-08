import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { setFuelImportMapping } from "@/lib/api";
import { errDetail } from "@/lib/fuelCards";

const NONE = "__none__";

// Étape 2 — mapping explicite colonne source → champ Documents (obligatoire / facultatif / exemple). Aucune valeur inventée.
export default function MappingStep({ job, onPreview, onBack }) {
  const [mapping, setMapping] = useState({});
  const [save, setSave] = useState(!!job.fournisseur);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setMapping({ ...(job.suggested_mapping || {}), ...(job.mapping || {}) }); }, [job.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const missing = ["tx_datetime", "amount_total"].filter((k) => !mapping[k]);
  const submit = async () => {
    setBusy(true);
    try {
      const res = await setFuelImportMapping(job.id, { mapping: Object.fromEntries(Object.entries(mapping).filter(([, v]) => v)), save_mapping: save });
      toast.success(`Preview : ${res.counts.ok} valide(s), ${res.counts.invalid} invalide(s), ${res.counts.duplicate} doublon(s)`);
      onPreview(res);
    } catch (e) { toast.error(errDetail(e, "Mapping refusé")); } finally { setBusy(false); }
  };
  const used = new Set(Object.values(mapping).filter(Boolean));
  return (
    <div className="space-y-4" data-testid="fuel-import-mapping-step">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-display text-base font-bold text-slate-900">Mapping des colonnes — {job.filename}</p>
          <p className="text-xs text-slate-500">{job.row_count} ligne(s) · {job.colonnes.length} colonne(s) · suggestions FR/DE/EN pré-remplies, à confirmer. Dates sans fuseau = heure locale Europe/Zurich.</p>
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={() => setMapping({ ...(job.suggested_mapping || {}) })} data-testid="fuel-mapping-suggest-btn"><Wand2 className="h-4 w-4" /> Réappliquer les suggestions</Button>
      </div>
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <Table data-testid="fuel-mapping-table">
          <TableHeader><TableRow className="bg-slate-50"><TableHead>Champ Documents</TableHead><TableHead>Obligatoire</TableHead><TableHead>Colonne source</TableHead><TableHead>Exemple</TableHead></TableRow></TableHeader>
          <TableBody>
            {job.fields.map((f) => {
              const col = mapping[f.key] || "";
              return (
                <TableRow key={f.key} data-testid={`fuel-mapping-row-${f.key}`}>
                  <TableCell className="text-sm"><p className="font-semibold text-slate-800">{f.label}</p>{f.hint && <p className="text-[11px] text-slate-400">{f.hint}</p>}</TableCell>
                  <TableCell>{f.required ? <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-700">obligatoire</span> : <span className="text-[11px] text-slate-400">facultatif</span>}</TableCell>
                  <TableCell>
                    <Select value={col || NONE} onValueChange={(v) => setMapping((m) => ({ ...m, [f.key]: v === NONE ? "" : v }))}>
                      <SelectTrigger className="h-8 w-56" data-testid={`fuel-mapping-source-${f.key}`}><SelectValue placeholder="— non mappé —" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE}>— non mappé —</SelectItem>
                        {job.colonnes.map((c) => <SelectItem key={c} value={c} disabled={used.has(c) && c !== col}>{c}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="text-xs text-slate-500" data-testid={`fuel-mapping-example-${f.key}`}>{col ? (job.examples?.[col] || []).slice(0, 2).join(" · ") || "—" : "—"}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <Checkbox checked={save} onCheckedChange={(v) => setSave(!!v)} disabled={!job.fournisseur} data-testid="fuel-mapping-save-checkbox" />
          Sauvegarder ce mapping pour le fournisseur {job.fournisseur ? `« ${job.fournisseur} »` : "(fournisseur non renseigné)"}
        </label>
        <div className="flex items-center gap-3">
          {missing.length > 0 && <p className="text-xs font-semibold text-red-600" data-testid="fuel-mapping-missing">Champs obligatoires manquants : {missing.join(", ")}</p>}
          {onBack && <Button variant="outline" onClick={onBack} data-testid="fuel-mapping-back-btn">Retour</Button>}
          <Button onClick={submit} disabled={busy || missing.length > 0} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-mapping-next-btn">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Prévisualiser (lecture seule)
          </Button>
        </div>
      </div>
    </div>
  );
}
