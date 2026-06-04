import { Download } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { fileUrl, mediaSrc } from "@/lib/api";

const isImage = (ct) => (ct || "").startsWith("image/");
const isPdf = (ct) => ct === "application/pdf";
const isVideo = (ct) => (ct || "").startsWith("video/");

export default function FilePreview({ open, onOpenChange, file }) {
  if (!file) return null;
  const src = mediaSrc(file);
  const ct = file.content_type || "";
  const downloadHref = file.path ? fileUrl(file.path, { download: true, filename: file.original_filename }) : src;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl" data-testid="file-preview-dialog">
        <DialogHeader>
          <DialogTitle className="truncate pr-8 text-base">{file.original_filename || "Aperçu"}</DialogTitle>
          <DialogDescription className="sr-only">Aperçu du document</DialogDescription>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-auto rounded-lg bg-slate-50">
          {isImage(ct) || (!ct && src) ? (
            <img src={src} alt={file.original_filename} className="mx-auto max-h-[70vh] object-contain" />
          ) : isPdf(ct) ? (
            <iframe title="pdf-preview" src={src} className="h-[70vh] w-full rounded-lg" />
          ) : isVideo(ct) ? (
            <video src={src} controls className="w-full rounded-lg" />
          ) : (
            <div className="p-12 text-center text-sm text-slate-500">
              Aperçu non disponible pour ce format. Utilisez le téléchargement.
            </div>
          )}
        </div>
        <a
          href={downloadHref}
          target="_blank"
          rel="noreferrer"
          data-testid="file-download-link"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
        >
          <Download className="h-4 w-4" /> Télécharger
        </a>
      </DialogContent>
    </Dialog>
  );
}
