import { useState, Fragment } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Archive, ChevronDown, ChevronRight, Download, FileText, Loader2, Send, RotateCcw } from "lucide-react";
import { getVehiclesArchive, getArchiveDocuments, restoreArchivedVehicle, fileUrl } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import QueryErrorState from "@/components/QueryErrorState";
import TransferArchiveDialog from "@/components/TransferArchiveDialog";
import { useAuth } from "@/context/AuthContext";

function fmtSize(bytes) {
  if (!bytes) return "—";
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
  return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
}

function ArchiveDocs({ vehicleId }) {
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ["archive-docs", vehicleId],
    queryFn: () => getArchiveDocuments(vehicleId),
  });
  if (isLoading)
    return <div className="flex items-center gap-2 py-3 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" /> Chargement…</div>;
  if (docs.length === 0)
    return <p className="py-3 text-sm text-slate-400" data-testid={`archive-docs-empty-${vehicleId}`}>Aucun document conservé (déjà transférés ou aucun document au moment de la suppression).</p>;
  return (
    <div className="space-y-1.5" data-testid={`archive-docs-${vehicleId}`}>
      {docs.map((d) => (
        <div key={d.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2" data-testid={`archive-doc-${d.id}`}>
          <div className="flex min-w-0 items-center gap-2.5">
            <FileText className="h-4 w-4 shrink-0 text-slate-400" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-700">{d.original_filename}</p>
              <p className="text-xs text-slate-400">{d.folder} · {fmtSize(d.size)} · ajouté le {dateFr(d.created_at)}</p>
            </div>
          </div>
          <button
            onClick={() => window.open(fileUrl(d.storage_path, { download: true, filename: d.original_filename }), "_blank", "noopener")}
            data-testid={`archive-doc-download-${d.id}`}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Télécharger"
          >
            <Download className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export default function ArchivesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isSuperadmin = user?.role === "superadmin";
  const canWrite = user?.role !== "read_only";
  const [expanded, setExpanded] = useState(null);
  const [transferRow, setTransferRow] = useState(null);
  const [restoring, setRestoring] = useState(null);
  const { data: rows = [], isLoading, isError, error } = useQuery({
    queryKey: ["vehicles-archive"],
    queryFn: getVehiclesArchive,
  });

  const restore = async (r) => {
    setRestoring(r.id);
    try {
      const res = await restoreArchivedVehicle(r.id);
      toast.success(`Véhicule ${r.plaque} restauré · ${res.restored_documents} document(s) réactivé(s)`);
      ["vehicles-archive", "vehicles", "documents", "dashboard"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Restauration impossible");
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="archives-page">
      <div>
        <h2 className="flex items-center gap-3 font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          <Archive className="h-8 w-8 text-slate-400" /> Véhicules archivés
        </h2>
        <p className="mt-1 text-sm text-slate-500">
          Véhicules supprimés de la flotte — leurs documents sont conservés et restent récupérables.
        </p>
      </div>

      {isError && <QueryErrorState error={error} testId="archives-error" />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead className="w-8" />
              <TableHead>Véhicule</TableHead>
              <TableHead>Supprimé le</TableHead>
              <TableHead>Par</TableHead>
              <TableHead>Documents</TableHead>
              <TableHead>Transfert</TableHead>
              {canWrite && <TableHead className="text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow><TableCell colSpan={canWrite ? 7 : 6}>
                <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" /> Chargement…</div>
              </TableCell></TableRow>
            )}
            {!isLoading && rows.length === 0 && (
              <TableRow><TableCell colSpan={canWrite ? 7 : 6}>
                <div className="flex flex-col items-center gap-2 py-10 text-center" data-testid="archives-empty">
                  <Archive className="h-8 w-8 text-slate-300" />
                  <p className="text-sm font-medium text-slate-600">Aucun véhicule archivé</p>
                </div>
              </TableCell></TableRow>
            )}
            {rows.map((r) => (
              <Fragment key={r.id}>
                <TableRow data-testid={`archive-row-${r.id}`} className="cursor-pointer hover:bg-slate-50"
                          onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                  <TableCell>
                    {expanded === r.id ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                  </TableCell>
                  <TableCell>
                    <p className="font-display text-sm font-bold text-slate-900">{r.plaque || "—"}</p>
                    <p className="text-xs text-slate-400">{[r.marque, r.modele].filter(Boolean).join(" ")}</p>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{dateFr(r.deleted_at)}</TableCell>
                  <TableCell className="text-sm text-slate-600">{r.deleted_by || "—"}</TableCell>
                  <TableCell>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600" data-testid={`archive-docs-count-${r.id}`}>
                      {r.documents_count}
                    </span>
                  </TableCell>
                  <TableCell>
                    {r.transferred_to ? (
                      <span className="inline-flex rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700" data-testid={`archive-transferred-${r.id}`}>
                        {r.transferred_to.documents} doc(s) → {r.transferred_to.plaque || r.transferred_to.tenant_id}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </TableCell>
                  {canWrite && (
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" data-testid={`archive-restore-btn-${r.id}`}
                                disabled={restoring === r.id}
                                onClick={(e) => { e.stopPropagation(); restore(r); }} className="gap-1.5">
                          {restoring === r.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Restaurer
                        </Button>
                        {isSuperadmin && r.documents_count > 0 && (
                          <Button variant="outline" size="sm" data-testid={`archive-transfer-btn-${r.id}`}
                                  onClick={(e) => { e.stopPropagation(); setTransferRow(r); }} className="gap-1.5">
                            <Send className="h-3.5 w-3.5" /> Transférer les documents
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  )}
                </TableRow>
                {expanded === r.id && (
                  <TableRow className="bg-slate-50/60 hover:bg-slate-50/60">
                    <TableCell />
                    <TableCell colSpan={canWrite ? 6 : 5}><ArchiveDocs vehicleId={r.id} /></TableCell>
                  </TableRow>
                )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </div>

      <TransferArchiveDialog
        archive={transferRow}
        open={!!transferRow}
        onOpenChange={(o) => !o && setTransferRow(null)}
      />
    </div>
  );
}
