import { useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, Upload, FolderOpen, Trash2, Loader2, DownloadCloud, RefreshCw } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  setVehiclePhoto, setVehiclePhotoFromDocument, deleteVehiclePhoto,
  importVehiclePhotoFromNavixy, retryVehiclePhotoNavixy, fileUrl,
} from "@/lib/api";
import { notifyNavixyPhoto } from "@/lib/navixyFeedback";
import { fileSize } from "@/components/Field";

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function VehiclePhotoMenu({ vehicle, docs = [], onChanged }) {
  const inputRef = useRef(null);
  const [preview, setPreview] = useState(null); // { file, url }
  const [pickerOpen, setPickerOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [busy, setBusy] = useState(false);
  const hasPhoto = !!vehicle.photo_url;
  const sync = vehicle.integrations?.navixy?.photo_sync;
  const imageDocs = docs.filter((d) => IMAGE_TYPES.includes(d.content_type));

  const finish = (navixyPhoto) => {
    notifyNavixyPhoto(navixyPhoto, vehicle.id);
    onChanged?.();
  };

  const onFilePicked = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!IMAGE_TYPES.includes(f.type)) {
      toast.error("Format non supporté — JPEG, PNG ou WEBP uniquement");
      return;
    }
    setPreview({ file: f, url: URL.createObjectURL(f) });
  };

  const savePreview = async () => {
    setBusy(true);
    try {
      const r = await setVehiclePhoto(vehicle.id, preview.file, hasPhoto);
      toast.success(hasPhoto ? "Photo principale remplacée" : "Photo du véhicule enregistrée");
      setPreview(null);
      finish(r.navixy_photo);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'enregistrement de la photo");
    } finally {
      setBusy(false);
    }
  };

  const chooseFromDoc = async (doc) => {
    setBusy(true);
    try {
      const r = await setVehiclePhotoFromDocument(vehicle.id, doc.id, hasPhoto);
      toast.success(`Photo définie depuis « ${doc.original_filename} »`);
      setPickerOpen(false);
      finish(r.navixy_photo);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec");
    } finally {
      setBusy(false);
    }
  };

  const importNavixy = async () => {
    setBusy(true);
    try {
      await importVehiclePhotoFromNavixy(vehicle.id, hasPhoto);
      toast.success("Photo Navixy importée dans LogiTrak");
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible");
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async () => {
    setBusy(true);
    try {
      await deleteVehiclePhoto(vehicle.id);
      toast.success("Photo supprimée dans LogiTrak — la photo Navixy reste inchangée (suppression non supportée par leur API)");
      setConfirmDelete(false);
      onChanged?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de la suppression");
    } finally {
      setBusy(false);
    }
  };

  const retrySync = async () => {
    try {
      const r = await retryVehiclePhotoNavixy(vehicle.id);
      notifyNavixyPhoto(r.navixy_photo, vehicle.id);
      onChanged?.();
    } catch {
      toast.error("Relance impossible");
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" capture="environment"
             className="hidden" onChange={onFilePicked} data-testid="vehicle-photo-input" />
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5" data-testid="vehicle-photo-menu-btn">
            <Camera className="h-3.5 w-3.5" /> {hasPhoto ? "Modifier la photo" : "Ajouter une photo"}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem data-testid="photo-import-file" onClick={() => inputRef.current?.click()}>
            <Upload className="mr-2 h-4 w-4" /> Importer une photo
          </DropdownMenuItem>
          <DropdownMenuItem data-testid="photo-from-documents" onClick={() => setPickerOpen(true)}>
            <FolderOpen className="mr-2 h-4 w-4" /> Choisir depuis Documents
          </DropdownMenuItem>
          {vehicle.navixy_vehicle_id && (
            <DropdownMenuItem data-testid="photo-import-navixy" onClick={importNavixy}>
              <DownloadCloud className="mr-2 h-4 w-4" /> Importer la photo Navixy
            </DropdownMenuItem>
          )}
          {hasPhoto && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem data-testid="photo-delete" className="text-red-600 focus:text-red-700"
                                onClick={() => setConfirmDelete(true)}>
                <Trash2 className="mr-2 h-4 w-4" /> Supprimer la photo
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      {hasPhoto && sync?.status === "synced" && (
        <span data-testid="photo-sync-badge" className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">
          Photo synchronisée Navixy
        </span>
      )}
      {hasPhoto && sync?.status === "failed" && (
        <button onClick={retrySync} data-testid="photo-sync-retry"
                className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-600 hover:bg-red-100">
          <RefreshCw className="h-2.5 w-2.5" /> Sync Navixy échouée — réessayer
        </button>
      )}
      {hasPhoto && sync?.status === "not_linked" && (
        <span data-testid="photo-sync-badge" className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
          Photo locale — véhicule non lié Navixy
        </span>
      )}

      {/* Aperçu avant enregistrement */}
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent data-testid="photo-preview-dialog" className="w-[calc(100vw-1rem)] max-w-md rounded-xl sm:w-full">
          <DialogHeader>
            <DialogTitle className="font-display text-lg">Photo du véhicule — aperçu</DialogTitle>
            <DialogDescription>
              {hasPhoto
                ? "Une photo principale existe déjà. Voulez-vous la remplacer ?"
                : `Cette image deviendra la photo principale de ${vehicle.plaque}.`}
            </DialogDescription>
          </DialogHeader>
          {preview && (
            <img src={preview.url} alt="aperçu" className="max-h-64 w-full rounded-lg border border-slate-200 object-contain bg-slate-50" />
          )}
          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="outline" data-testid="photo-preview-cancel" onClick={() => setPreview(null)}>Annuler</Button>
            <Button data-testid="photo-preview-save" onClick={savePreview} disabled={busy}
                    className="gap-2 bg-slate-900 hover:bg-slate-800">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {hasPhoto ? "Remplacer la photo" : "Enregistrer comme photo du véhicule"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Choisir depuis Documents */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent data-testid="photo-doc-picker" className="w-[calc(100vw-1rem)] max-w-lg rounded-xl sm:w-full">
          <DialogHeader>
            <DialogTitle className="font-display text-lg">Choisir une image depuis Documents</DialogTitle>
            <DialogDescription>
              Le fichier existant est réutilisé — aucune copie. {hasPhoto ? "La photo actuelle sera remplacée." : ""}
            </DialogDescription>
          </DialogHeader>
          {imageDocs.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400" data-testid="photo-doc-picker-empty">
              Aucune image dans les documents de ce véhicule.
            </p>
          ) : (
            <ul className="max-h-80 space-y-2 overflow-y-auto">
              {imageDocs.map((d) => (
                <li key={d.id}>
                  <button onClick={() => chooseFromDoc(d)} disabled={busy} data-testid={`photo-doc-pick-${d.id}`}
                          className="flex w-full items-center gap-3 rounded-lg border border-slate-200 p-2 text-left hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50">
                    <img src={fileUrl(d.storage_path)} alt="" loading="lazy"
                         className="h-12 w-16 shrink-0 rounded-md border border-slate-100 object-cover bg-slate-50" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-800">{d.original_filename}</span>
                      <span className="text-xs text-slate-400">{d.folder} · {fileSize(d.size)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirmation de suppression */}
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent data-testid="photo-delete-dialog" className="w-[calc(100vw-1rem)] max-w-md rounded-xl sm:w-full">
          <DialogHeader>
            <DialogTitle className="font-display text-lg">Supprimer la photo du véhicule ?</DialogTitle>
            <DialogDescription>
              La photo sera retirée de LogiTrak (liste, fiche, documents). La photo côté Navixy restera
              inchangée — leur API ne permet pas la suppression d'avatar.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
            <Button variant="outline" data-testid="photo-delete-cancel" onClick={() => setConfirmDelete(false)}>Annuler</Button>
            <Button data-testid="photo-delete-confirm" onClick={doDelete} disabled={busy}
                    className="gap-2 bg-red-600 hover:bg-red-700">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />} Supprimer
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
