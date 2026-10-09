import { useEffect, useRef, useState } from "react";
import { Download, Maximize2, Minimize2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { fileUrl, mediaSrc } from "@/lib/api";
import { cn } from "@/lib/utils";

const EXT_CT = {
  pdf: "application/pdf", png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  webp: "image/webp", gif: "image/gif", mp4: "video/mp4", webm: "video/webm", mov: "video/quicktime",
};
const guessCt = (name = "") => EXT_CT[(name.split(".").pop() || "").toLowerCase()] || "";
const isImage = (ct) => (ct || "").startsWith("image/");
const isPdf = (ct) => ct === "application/pdf";
const isVideo = (ct) => (ct || "").startsWith("video/");

export default function FilePreview({ open, onOpenChange, file }) {
  const contentRef = useRef(null);
  const [full, setFull] = useState(false);

  useEffect(() => {
    if (!open) setFull(false);
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onOpenChange?.(false);
    };
    // Si le focus part dans l'iframe (clic dans le PDF), on le ramène au dialog
    // pour que la touche Escape continue d'atteindre la fenêtre parente.
    const onBlur = () => {
      setTimeout(() => {
        if (document.activeElement?.tagName === "IFRAME") contentRef.current?.focus();
      }, 0);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", onBlur);
    };
  }, [open, onOpenChange]);

  if (!file) return null;
  const src = mediaSrc(file);
  const ct = file.content_type || guessCt(file.original_filename);
  const downloadHref = file.path ? fileUrl(file.path, { download: true, filename: file.original_filename }) : src;
  const maxH = full ? "max-h-[82vh]" : "max-h-[70vh]";
  const viewerH = full ? "h-[82vh]" : "h-[70vh]";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        ref={contentRef}
        tabIndex={-1}
        onOpenAutoFocus={(e) => {
          // Empêche Radix de donner l'autofocus à l'iframe : Escape doit rester capté par le dialog
          e.preventDefault();
          requestAnimationFrame(() => contentRef.current?.focus());
        }}
        className={cn("transition-[max-width]", full ? "w-[96vw] max-w-[96vw]" : "max-w-3xl")}
        data-testid="file-preview-dialog"
      >
        <DialogHeader>
          <DialogTitle className="truncate pr-16 text-base">{file.original_filename || "Aperçu"}</DialogTitle>
          <DialogDescription className="sr-only">Aperçu du document</DialogDescription>
          <button
            type="button"
            onClick={() => setFull((v) => !v)}
            data-testid="file-preview-fullscreen"
            aria-label={full ? "Quitter le plein écran" : "Plein écran"}
            title={full ? "Quitter le plein écran" : "Plein écran"}
            className="absolute right-11 top-3.5 flex h-7 w-7 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
          >
            {full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </DialogHeader>
        <div className={cn("overflow-auto rounded-lg bg-slate-50", maxH)}>
          {isImage(ct) || (!ct && src) ? (
            <img src={src} alt={file.original_filename} className={cn("mx-auto object-contain", maxH)} />
          ) : isPdf(ct) ? (
            <iframe title="pdf-preview" src={src} className={cn("w-full rounded-lg", viewerH)} />
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
