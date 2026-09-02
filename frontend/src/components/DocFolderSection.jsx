import { useState } from "react";
import {
  FileText, Image as ImageIcon, FileSpreadsheet, FileArchive, File,
  Eye, Download, Trash2, Sparkles, Loader2, RefreshCw, ImagePlus,
} from "lucide-react";
import { toast } from "sonner";
import { uploadDocument, deleteDocument, fileUrl, scanVehicleDocument, setVehiclePhotoFromDocument } from "@/lib/api";
import { notifyNavixyPhoto } from "@/lib/navixyFeedback";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { fileSize } from "@/components/Field";
import { dateFr } from "@/lib/format";
import DropZone from "@/components/DropZone";
import FilePreview from "@/components/FilePreview";
import ExtractionReviewDialog from "@/components/ExtractionReviewDialog";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const iconFor = (ct = "") => {
  if (ct.startsWith("image/")) return { Icon: ImageIcon, color: "text-violet-500 bg-violet-50" };
  if (ct === "application/pdf") return { Icon: FileText, color: "text-red-500 bg-red-50" };
  if (ct.includes("sheet") || ct.includes("excel") || ct.includes("csv")) return { Icon: FileSpreadsheet, color: "text-emerald-500 bg-emerald-50" };
  if (ct.includes("zip")) return { Icon: FileArchive, color: "text-amber-500 bg-amber-50" };
  if (ct.includes("word")) return { Icon: FileText, color: "text-sky-500 bg-sky-50" };
  return { Icon: File, color: "text-slate-400 bg-slate-100" };
};

// Dossier → type de document attendu pour l'analyse (sinon détection automatique)
const FOLDER_DOC_TYPE = {
  "Carte grise": "permis_circulation",
  "Assurance": "assurance",
  "Leasing": "leasing",
  "Contrôle technique": "controle_technique",
  "Vignette": "vignette",
  "Factures": "facture",
};

const isScannable = (d) =>
  /^image\/(jpeg|png|webp)$/.test(d.content_type || "") || d.content_type === "application/pdf";

const isVehiclePhotoCandidate = (d) => /^image\/(jpeg|png|webp)$/.test(d.content_type || "");

export default function DocFolderSection({ vehicleId, folder, docs = [], onChange, compact = false }) {
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [analyzingId, setAnalyzingId] = useState(null);
  const [reviewDocId, setReviewDocId] = useState(null);
  const [confirmPhotoDoc, setConfirmPhotoDoc] = useState(null);
  const items = docs.filter((d) => d.folder === folder);

  const setAsVehiclePhoto = async (d, replace = false) => {
    try {
      const r = await setVehiclePhotoFromDocument(vehicleId, d.id, replace);
      toast.success(`Photo du véhicule définie depuis « ${d.original_filename} »`);
      notifyNavixyPhoto(r.navixy_photo, vehicleId);
      setConfirmPhotoDoc(null);
      onChange?.();
    } catch (e) {
      if (e?.response?.status === 409) {
        setConfirmPhotoDoc(d); // Une photo existe déjà : jamais de remplacement silencieux
      } else {
        toast.error(e?.response?.data?.detail || "Impossible de définir la photo");
      }
    }
  };

  const handleFiles = async (files) => {
    setBusy(true);
    try {
      for (const f of files) {
        await uploadDocument(vehicleId, f, folder);
      }
      toast.success(`${files.length} fichier(s) ajouté(s) · ${folder}`);
      onChange?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec du téléversement");
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteDocument(id);
      toast.success("Document supprimé");
      onChange?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de la suppression");
    }
  };

  const analyzeDoc = async (d) => {
    if (analyzingId) return;
    setAnalyzingId(d.id);
    try {
      const res = await scanVehicleDocument(vehicleId, null, {
        documentId: d.id,
        documentType: d.document_type || FOLDER_DOC_TYPE[folder],
      });
      onChange?.();
      if (res.extraction_status === "failed") {
        toast.error(res.error || "Échec de l'analyse — réessayez ou vérifiez le fichier.");
        return;
      }
      toast.success(`Analyse terminée · ${res.fields?.length ?? 0} champ(s) détecté(s)`);
      setReviewDocId(res.document_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'analyse");
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="space-y-3">
      {!readOnly && (
        <DropZone
          onFiles={handleFiles}
          busy={busy}
          compact={compact}
          testId={`dropzone-${folder.replace(/\s/g, "-").toLowerCase()}`}
          accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.docx,.doc,.xlsx,.xls,.zip,.csv,.mp4,.mov,.webm"
        />
      )}
      {items.length === 0 ? (
        <p className="px-1 text-xs text-slate-400">Aucun document dans ce dossier.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((d) => {
            const { Icon, color } = iconFor(d.content_type);
            const fieldsCount = (d.extracted_fields || []).length;
            const analyzed = d.extraction_status === "done" || d.extraction_status === "validated";
            const failed = d.extraction_status === "failed";
            const processing = d.extraction_status === "processing" || analyzingId === d.id;
            const canAnalyze = !readOnly && isScannable(d) && !analyzed && !processing;
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
                    {analyzed && (
                      <button
                        type="button"
                        onClick={() => setReviewDocId(d.id)}
                        data-testid={`doc-extraction-open-${d.id}`}
                        className={cn(
                          "rounded-full px-1.5 py-0.5 text-[10px] font-bold underline-offset-2 transition-colors hover:underline",
                          d.extraction_status === "validated"
                            ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            : "bg-sky-50 text-sky-700 hover:bg-sky-100"
                        )}
                        title="Voir les informations détectées"
                      >
                        {d.extraction_status === "validated" ? "Validé" : "Analysé"} · {fieldsCount} champ{fieldsCount > 1 ? "s" : ""}
                      </button>
                    )}
                    {failed && (
                      <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] font-bold text-red-600" data-testid={`doc-status-${d.id}`}>
                        Échec analyse
                      </span>
                    )}
                    {processing && (
                      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500" data-testid={`doc-status-${d.id}`}>
                        <Loader2 className="h-2.5 w-2.5 animate-spin" /> Analyse en cours…
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {canAnalyze && (
                    <button
                      onClick={() => analyzeDoc(d)}
                      disabled={!!analyzingId}
                      data-testid={`doc-analyze-${d.id}`}
                      className="flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-xs font-semibold text-slate-600 hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
                      aria-label={failed ? "Réessayer l'analyse" : "Analyser"}
                    >
                      {failed ? <RefreshCw className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
                      {failed ? "Réessayer" : "Analyser"}
                    </button>
                  )}
                  <button onClick={() => setPreview(d)} data-testid={`doc-preview-${d.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Aperçu">
                    <Eye className="h-4 w-4" />
                  </button>
                  {!readOnly && isVehiclePhotoCandidate(d) && (
                    <button
                      onClick={() => setAsVehiclePhoto(d)}
                      data-testid={`doc-set-photo-${d.id}`}
                      title="Définir comme photo du véhicule"
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      aria-label="Définir comme photo du véhicule"
                    >
                      <ImagePlus className="h-4 w-4" />
                    </button>
                  )}
                  {/* URL résolue au clic : jeton fichier toujours frais (rafraîchi toutes les 8 min) */}
                  <button
                    onClick={() => window.open(fileUrl(d.storage_path, { download: true, filename: d.original_filename }), "_blank", "noopener")}
                    data-testid={`doc-download-${d.id}`}
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    aria-label="Télécharger"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  {!readOnly && (
                    <button onClick={() => handleDelete(d.id)} data-testid={`doc-delete-${d.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Supprimer">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  )}
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
      <Dialog open={!!confirmPhotoDoc} onOpenChange={(o) => !o && setConfirmPhotoDoc(null)}>
        <DialogContent data-testid="doc-photo-replace-dialog" className="w-[calc(100vw-1rem)] max-w-md rounded-xl sm:w-full">
          <DialogHeader>
            <DialogTitle className="font-display text-lg">Une photo principale existe déjà</DialogTitle>
            <DialogDescription>
              Voulez-vous la remplacer par « {confirmPhotoDoc?.original_filename} » ?
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="outline" data-testid="doc-photo-replace-cancel" onClick={() => setConfirmPhotoDoc(null)}>Annuler</Button>
            <Button data-testid="doc-photo-replace-confirm" onClick={() => setAsVehiclePhoto(confirmPhotoDoc, true)}
                    className="bg-slate-900 hover:bg-slate-800">
              Remplacer la photo
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <ExtractionReviewDialog
        docId={reviewDocId}
        open={!!reviewDocId}
        onOpenChange={(o) => !o && setReviewDocId(null)}
        readOnly={readOnly}
        onValidated={() => { setReviewDocId(null); onChange?.(); }}
      />
    </div>
  );
}
