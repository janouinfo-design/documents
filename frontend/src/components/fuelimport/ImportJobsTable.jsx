import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

const JOB_META = {
  mapping: { label: "Mapping à définir", cls: "bg-slate-100 text-slate-600 border-slate-200" },
  preview: { label: "Preview (non importé)", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  confirmed: { label: "Confirmé", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

// Historique des imports (jobs) : date, fichier, auteur, statut, lignes, importées, invalides, doublons, à vérifier
export default function ImportJobsTable({ jobs = [], isLoading, selectedId, onSelect }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
      <Table data-testid="fuel-imports-table">
        <TableHeader>
          <TableRow className="bg-slate-50">
            <TableHead>Date</TableHead><TableHead>Fichier</TableHead><TableHead>Auteur</TableHead><TableHead>Statut</TableHead>
            <TableHead className="text-right">Lignes</TableHead><TableHead className="text-right">Importées</TableHead><TableHead className="text-right">Invalides</TableHead>
            <TableHead className="text-right">Doublons</TableHead><TableHead className="text-right">À vérifier</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {!isLoading && jobs.length === 0 && <TableRow><TableCell colSpan={9}><p className="py-8 text-center text-sm text-slate-400" data-testid="fuel-imports-empty">Aucun import pour l'instant.</p></TableCell></TableRow>}
          {jobs.map((j) => {
            const c = j.counts || {};
            const m = JOB_META[j.status] || JOB_META.mapping;
            return (
              <TableRow key={j.id} data-testid={`fuel-import-row-${j.id}`} onClick={() => onSelect(j.id)} className={cn("cursor-pointer hover:bg-slate-50", selectedId === j.id && "bg-slate-100")}>
                <TableCell className="whitespace-nowrap text-sm text-slate-700">{new Date(j.created_at).toLocaleString("fr-CH", { dateStyle: "short", timeStyle: "short" })}</TableCell>
                <TableCell className="text-sm">
                  <p className="font-semibold text-slate-900" data-testid={`fuel-import-filename-${j.id}`}>{j.filename}</p>
                  <p className="text-[11px] text-slate-400">{j.meta?.format?.toUpperCase()}{j.fournisseur ? ` · ${j.fournisseur}` : ""}{j.same_file_jobs?.length ? ` · même fichier ×${j.same_file_jobs.length}` : ""}</p>
                </TableCell>
                <TableCell className="text-xs text-slate-600">{j.created_by || "—"}</TableCell>
                <TableCell><span className={cn("inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold", m.cls)} data-testid={`fuel-import-status-${j.id}`}>{m.label}</span></TableCell>
                <TableCell className="text-right text-sm">{c.total ?? j.row_count ?? 0}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-emerald-700">{c.imported ?? 0}</TableCell>
                <TableCell className="text-right text-sm text-red-700">{c.invalid ?? 0}</TableCell>
                <TableCell className="text-right text-sm text-amber-800">{c.duplicate ?? 0}</TableCell>
                <TableCell className="text-right text-sm text-rose-800">{(c.unknown_vehicle ?? 0) + (c.unknown_card ?? 0) + (c.amount_mismatch ?? 0)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
