import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Users, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ROW_STATUS_META } from "@/lib/fuelImport";
import PreviewCounters, { rowWarnings } from "./PreviewCounters";
import PreviewRow from "./PreviewRow";
import ConfirmDialog from "./ConfirmDialog";
import ImportResult from "./ImportResult";
import { RowResolveDialog, AcceptUniqueDialog, ForceRowDialog } from "./RowDialogs";

const ALL = "__all__";
export const bulkEligible = (rows) => rows.filter((r) => r.status === "unknown_vehicle" && !r.imported && (r.resolution?.vehicle?.candidates || []).length === 1
  && r.resolution.vehicle.candidates[0].sources.includes("plate_candidate"));

// Étape 3 — preview (espace de travail : 0 écriture métier finale) + étape 4 — confirmation explicite ; résultat d'import.
export default function PreviewStep({ job, rows, isAdmin, onRows, onJob, onBack }) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState(ALL);
  const [resolve, setResolve] = useState(null);
  const [force, setForce] = useState(null);
  const [bulk, setBulk] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState(null);
  const visible = useMemo(() => rows.filter((r) => filter === ALL || (filter === "imported" ? r.imported : filter === "warnings" ? rowWarnings(r) > 0 : filter === "total" ? true : r.status === filter && !r.imported)), [rows, filter]);
  const eligible = bulkEligible(rows);
  const pendingImportable = rows.filter((r) => !r.imported && ["ok", "amount_mismatch", "unknown_card"].includes(r.status)).length;
  const refresh = async (res) => {
    if (res?.row) onRows(rows.map((r) => (r.id === res.row.id ? res.row : r)));
    else await onRows();
    if (res?.counts) onJob({ ...job, counts: res.counts });
    qc.invalidateQueries({ queryKey: ["fuel-imports"] });
  };
  const onConfirmed = async (res) => {
    setResult(res);
    await onRows();
    onJob({ ...job, status: "confirmed", counts: res.counts, imported_count: res.counts?.imported });
    qc.invalidateQueries({ queryKey: ["fuel-imports"] });
    qc.invalidateQueries({ queryKey: ["energy"] });
    qc.invalidateQueries({ queryKey: ["fuel-anomalies"] });
  };
  return (
    <div className="space-y-4" data-testid="fuel-import-preview-step">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-display text-base font-bold text-slate-900">{job.status === "confirmed" ? "Import confirmé" : "Prévisualisation"} — {job.filename}</p>
          <p className="text-xs text-slate-500" data-testid="fuel-import-preview-hint">
            {job.status === "confirmed" ? `Confirmé le ${new Date(job.confirmed_at).toLocaleString("fr-CH")} par ${job.confirmed_by || "—"}. Les lignes mises de côté peuvent encore être résolues puis importées.`
              : "Espace de travail : rien n'est écrit dans Documents / Transactions / Anomalies avant la confirmation explicite. Plaque = aide à la revue, jamais un rattachement automatique."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onBack && <Button variant="outline" size="sm" onClick={onBack} data-testid="fuel-preview-back-btn">Retour au mapping</Button>}
          {isAdmin && eligible.length > 0 && (
            <Button variant="outline" size="sm" className="gap-1.5 border-slate-900" onClick={() => setBulk(true)} data-testid="fuel-bulk-review-btn">
              <Users className="h-4 w-4" /> Accepter les {eligible.length} proposition(s) à candidat unique
            </Button>
          )}
          {isAdmin && (
            <Button size="sm" className="gap-1.5 bg-slate-900 hover:bg-slate-800" onClick={() => setConfirm(true)} disabled={pendingImportable === 0} data-testid="fuel-import-confirm-btn">
              <Upload className="h-4 w-4" /> {job.status === "confirmed" ? `Importer les ${pendingImportable} ligne(s) restante(s)` : `Confirmer l'import (${pendingImportable})`}
            </Button>
          )}
        </div>
      </div>
      {(result || job.status === "confirmed") && <ImportResult result={result} job={job} rows={rows} />}
      <PreviewCounters counts={job.counts} rows={rows} active={filter === ALL ? null : filter} onSelect={(k) => setFilter((f) => (f === k ? ALL : k))} />
      <div className="flex items-center justify-between gap-2">
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger className="h-8 w-60" data-testid="fuel-preview-filter-status"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toutes les lignes</SelectItem>
            {Object.entries(ROW_STATUS_META).filter(([k]) => k !== "pending").map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}
            <SelectItem value="warnings">Avec avertissements</SelectItem>
            <SelectItem value="imported">Importées</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-slate-500" data-testid="fuel-preview-visible-count">{visible.length} / {rows.length} ligne(s)</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <Table data-testid="fuel-preview-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>#</TableHead><TableHead>Date</TableHead><TableHead>Station / réf.</TableHead><TableHead>Carte</TableHead><TableHead>Véhicule / rattachement</TableHead>
              <TableHead className="text-right">Montant</TableHead><TableHead>Statut</TableHead><TableHead>Avertissements</TableHead><TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.length === 0 && <TableRow><TableCell colSpan={9}><p className="py-8 text-center text-sm text-slate-400" data-testid="fuel-preview-empty">Aucune ligne pour ce filtre.</p></TableCell></TableRow>}
            {visible.map((r) => <PreviewRow key={r.id} row={r} isAdmin={isAdmin} canMutate onResolve={setResolve} onForce={setForce} />)}
          </TableBody>
        </Table>
      </div>
      <RowResolveDialog job={job} row={resolve} open={!!resolve} onOpenChange={(o) => !o && setResolve(null)} onDone={refresh} />
      <ForceRowDialog job={job} row={force} open={!!force} onOpenChange={(o) => !o && setForce(null)} onDone={refresh} />
      <AcceptUniqueDialog job={job} rows={rows} open={bulk} onOpenChange={setBulk} onDone={refresh} />
      <ConfirmDialog job={job} rows={rows} open={confirm} onOpenChange={setConfirm} onDone={onConfirmed} />
    </div>
  );
}
