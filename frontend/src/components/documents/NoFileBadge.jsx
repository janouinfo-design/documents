import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileX2, Paperclip, Loader2 } from "lucide-react";
import { attachDocumentFile } from "@/lib/api";
import { cn } from "@/lib/utils";

export const hasNoFile = (d) => !!d && (d.justificatif_absent === true || !d.storage_path);

export const NOFILE_QUERY_KEYS = ["all-documents", "documents", "costs", "vehicle-costs", "energy", "vehicle-energy", "deadlines", "dashboard"];

export function NoFileBadge({ doc, className }) {
  if (!hasNoFile(doc)) return null;
  return (
    <span data-testid={`doc-nofile-${doc.id}`} title={doc.motif_saisie ? `Motif : ${doc.motif_saisie}` : "Saisie déclarative"}
      className={cn("inline-flex items-center gap-1 rounded-full border border-dashed border-amber-400 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-800", className)}>
      <FileX2 className="h-3 w-3" /> Aucun justificatif{doc.source === "legacy_import" ? " · import" : ""}
    </span>
  );
}

// « Joindre le justificatif » : même document, le coût n'est jamais recréé.
export function AttachFileButton({ doc, disabled, onDone, compact = false }) {
  const qc = useQueryClient();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  if (!hasNoFile(doc)) return null;

  const onPick = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    try {
      const r = await attachDocumentFile(doc.id, file);
      toast.success(`Justificatif « ${file.name} » joint — montant inchangé, aucun nouveau coût`);
      if (r?.duplicate_of) toast.warning(`Fichier identique à « ${r.duplicate_of.original_filename} » déjà présent.`, { duration: 9000 });
      NOFILE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onDone?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error((typeof detail === "string" && detail) || detail?.message || "Impossible de joindre le justificatif");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <input ref={inputRef} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={onPick} data-testid={`doc-attach-input-${doc.id}`} />
      <button type="button" onClick={() => inputRef.current?.click()} disabled={disabled || busy} data-testid={`doc-attach-${doc.id}`}
        title="Joindre le justificatif (le coût n'est pas recréé)"
        className={cn("inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-300 bg-white font-semibold text-amber-800 transition-colors hover:bg-amber-50 disabled:opacity-50",
          compact ? "w-8 justify-center" : "px-2.5 text-xs")}>
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />}
        {!compact && "Joindre le justificatif"}
      </button>
    </>
  );
}
