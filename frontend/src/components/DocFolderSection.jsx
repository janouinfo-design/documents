import { useState } from "react";
import { FileText, Image as ImageIcon, FileSpreadsheet, FileArchive, File, Eye, Download, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { uploadDocument, deleteDocument, fileUrl } from "@/lib/api";
import { fileSize } from "@/components/Field";
import { dateFr } from "@/lib/format";
import DropZone from "@/components/DropZone";
import FilePreview from "@/components/FilePreview";
import { cn } from "@/lib/utils";

const iconFor = (ct = "") => {
  if (ct.startsWith("image/")) return { Icon: ImageIcon, color: "text-violet-500 bg-violet-50" };
  if (ct === "application/pdf") return { Icon: FileText, color: "text-red-500 bg-red-50" };
  if (ct.includes("sheet") || ct.includes("excel") || ct.includes("csv")) return { Icon: FileSpreadsheet, color: "text-emerald-500 bg-emerald-50" };
  if (ct.includes("zip")) return { Icon: FileArchive, color: "text-amber-500 bg-amber-50" };
  if (ct.includes("word")) return { Icon: FileText, color: "text-sky-500 bg-sky-50" };
  return { Icon: File, color: "text-slate-400 bg-slate-100" };
};

const ANALYSIS_BADGE = {
  validated: { label: "Validé", cls: "bg-emerald-50 text-emerald-700" },
  done: { label: "Analysé", cls: "bg-sky-50 text-sky-700" },
  failed: { label: "Échec analyse", cls: "bg-red-50 text-red-600" },
  processing: { label: "Analyse…", cls: "bg-slate-100 text-slate-500" },
};

export default function DocFolderSection({ vehicleId, folder, docs = [], onChange, compact = false }) {
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const items = docs.filter((d) => d.folder === folder);

  const handleFiles = async (files) => {
    setBusy(true);
    try {
      for (const f of files) {
        await uploadDocument(vehicleId, f, folder);
      }
      toast.success(`${files.length} fichier(s) ajouté(s) · ${folder}`);
      onChange?.();
    } catch (e) {
      toast.error("Échec du téléversement");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id) => {
    await deleteDocument(id);
    toast.success("Document supprimé");
    onChange?.();
  };

  return (
    <div className="space-y-3">
      <DropZone
        onFiles={handleFiles}
        busy={busy}
        compact={compact}
        testId={`dropzone-${folder.replace(/\s/g, "-").toLowerCase()}`}
        accept=".pdf,.jpg,.jpeg,.png,.webp,.docx,.doc,.xlsx,.xls,.zip,.csv,.mp4,.mov"
      />
      {items.length === 0 ? (
        <p className="px-1 text-xs text-slate-400">Aucun document dans ce dossier.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((d) => {
            const { Icon, color } = iconFor(d.content_type);
            return (
              <li
                key={d.id}
                data-testid={`doc-item-${d.id}`}
                className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-2.5 transition-colors hover:bg-slate-50"
              >
                <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", color)}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-800">{d.original_filename}</p>
                  <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                    <span>{fileSize(d.size)} · {dateFr(d.created_at)}</span>
                    {ANALYSIS_BADGE[d.extraction_status] && (
                      <span
                        className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-bold", ANALYSIS_BADGE[d.extraction_status].cls)}
                        data-testid={`doc-status-${d.id}`}
                      >
                        {ANALYSIS_BADGE[d.extraction_status].label}
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPreview(d)} data-testid={`doc-preview-${d.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Aperçu">
                    <Eye className="h-4 w-4" />
                  </button>
                  <a href={fileUrl(d.storage_path, { download: true, filename: d.original_filename })} target="_blank" rel="noreferrer" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Télécharger">
                    <Download className="h-4 w-4" />
                  </a>
                  <button onClick={() => handleDelete(d.id)} data-testid={`doc-delete-${d.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Supprimer">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <FilePreview
        open={!!preview}
        onOpenChange={(o) => !o && setPreview(null)}
        file={preview ? { ...preview, path: preview.storage_path } : null}
      />
    </div>
  );
}
