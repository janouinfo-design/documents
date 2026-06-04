import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Loader2, Trash2, Calendar, User, Gauge, GitCompareArrows, ImageOff } from "lucide-react";
import { getInspections, createInspection, deleteInspection, uploadFile, mediaSrc } from "@/lib/api";
import { dateFr, fmtKm } from "@/lib/format";
import { SectionCard, FormRow } from "@/components/Field";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import DropZone from "@/components/DropZone";
import FilePreview from "@/components/FilePreview";
import { cn } from "@/lib/utils";

const ANGLES = [
  { key: "avant_gauche", label: "Avant gauche" },
  { key: "avant_droite", label: "Avant droite" },
  { key: "arriere_gauche", label: "Arrière gauche" },
  { key: "arriere_droite", label: "Arrière droite" },
  { key: "interieur", label: "Intérieur" },
  { key: "toit", label: "Toit" },
  { key: "dommages", label: "Dommages" },
];
const angleLabel = (k) => ANGLES.find((a) => a.key === k)?.label || k;

function AddDialog({ open, onOpenChange, vehicleId, onCreated }) {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [responsable, setResponsable] = useState("");
  const [km, setKm] = useState("");
  const [commentaire, setCommentaire] = useState("");
  const [photos, setPhotos] = useState({});
  const [busyAngle, setBusyAngle] = useState(null);
  const [saving, setSaving] = useState(false);

  const addPhotos = async (angle, files) => {
    setBusyAngle(angle);
    try {
      const uploaded = [];
      for (const f of files) {
        const res = await uploadFile(f, vehicleId);
        uploaded.push({ angle, path: res.path, content_type: res.content_type, original_filename: res.original_filename, kind: (res.content_type || "").startsWith("video/") ? "video" : "image" });
      }
      setPhotos((p) => ({ ...p, [angle]: [...(p[angle] || []), ...uploaded] }));
    } catch {
      toast.error("Échec du téléversement");
    } finally {
      setBusyAngle(null);
    }
  };

  const submit = async () => {
    setSaving(true);
    try {
      const flat = Object.values(photos).flat();
      await createInspection(vehicleId, { date, responsable, kilometrage: Number(km) || 0, commentaire, photos: flat });
      toast.success("État des lieux enregistré");
      setPhotos({}); setResponsable(""); setKm(""); setCommentaire("");
      onCreated?.();
      onOpenChange(false);
    } catch {
      toast.error("Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto" data-testid="inspection-dialog">
        <DialogHeader>
          <DialogTitle>Nouvel état des lieux</DialogTitle>
          <DialogDescription className="sr-only">Formulaire d'ajout d'un état des lieux avec galerie photos</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FormRow label="Date"><Input data-testid="ins-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></FormRow>
          <FormRow label="Responsable"><Input data-testid="ins-responsable" value={responsable} onChange={(e) => setResponsable(e.target.value)} placeholder="Nom" /></FormRow>
          <FormRow label="Kilométrage"><Input data-testid="ins-km" type="number" value={km} onChange={(e) => setKm(e.target.value)} /></FormRow>
        </div>
        <FormRow label="Commentaire"><Textarea data-testid="ins-commentaire" rows={2} value={commentaire} onChange={(e) => setCommentaire(e.target.value)} placeholder="État général, dommages constatés…" /></FormRow>
        <div>
          <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.1em] text-slate-500">Galerie photos · vidéos · PDF HD</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {ANGLES.map((a) => (
              <div key={a.key} className="rounded-xl border border-slate-200 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">{a.label}</span>
                  {photos[a.key]?.length > 0 && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">{photos[a.key].length}</span>}
                </div>
                <DropZone onFiles={(files) => addPhotos(a.key, files)} busy={busyAngle === a.key} compact accept="image/*,video/*,.pdf" label="Ajouter" testId={`ins-drop-${a.key}`} />
                {photos[a.key]?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {photos[a.key].map((p, i) => (
                      <img key={i} src={mediaSrc(p)} alt={a.label} className="h-12 w-12 rounded-md border border-slate-200 object-cover" />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="ins-submit" onClick={submit} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Compare({ inspections }) {
  const [angle, setAngle] = useState("dommages");
  const sorted = [...inspections].sort((a, b) => new Date(a.date) - new Date(b.date));
  const oldest = sorted[0];
  const newest = sorted[sorted.length - 1];
  const photoFor = (ins) => ins?.photos?.find((p) => p.angle === angle);
  const before = photoFor(oldest);
  const after = photoFor(newest);

  return (
    <SectionCard title="Comparaison avant / après" description="Évolution de l'état du véhicule" testId="inspection-compare">
      <div className="mb-4 flex flex-wrap gap-1.5">
        {ANGLES.map((a) => (
          <button key={a.key} onClick={() => setAngle(a.key)} className={cn("rounded-full border px-3 py-1 text-xs font-medium transition-colors", angle === a.key ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50")}>{a.label}</button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {[{ label: `Avant · ${dateFr(oldest?.date)}`, p: before }, { label: `Après · ${dateFr(newest?.date)}`, p: after }].map((side, i) => (
          <div key={i}>
            <p className="mb-1.5 text-xs font-semibold text-slate-500">{side.label}</p>
            <div className="flex aspect-video items-center justify-center overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
              {side.p ? <img src={mediaSrc(side.p)} alt={side.label} className="h-full w-full object-cover" /> : <div className="flex flex-col items-center gap-1 text-slate-300"><ImageOff className="h-6 w-6" /><span className="text-xs">Aucune photo</span></div>}
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

export default function InspectionTab({ vehicle }) {
  const [addOpen, setAddOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const { data: inspections = [], refetch } = useQuery({ queryKey: ["inspections", vehicle.id], queryFn: () => getInspections(vehicle.id) });

  const handleDelete = async (id) => {
    await deleteInspection(id);
    toast.success("État des lieux supprimé");
    refetch();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="font-display text-base font-semibold tracking-tight text-slate-900">État des lieux</h4>
          <p className="text-xs text-slate-500">Historique annuel · {inspections.length} entrée(s)</p>
        </div>
        <Button data-testid="add-inspection-btn" onClick={() => setAddOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800"><Plus className="h-4 w-4" /> Nouvel état</Button>
      </div>

      {inspections.length >= 2 && <Compare inspections={inspections} />}

      {inspections.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <ImageOff className="h-7 w-7 text-slate-300" />
          <p className="text-sm font-medium text-slate-600">Aucun état des lieux</p>
          <p className="text-xs text-slate-400">Créez le premier pour démarrer l'historique.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {inspections.map((ins) => (
            <SectionCard key={ins.id} testId={`inspection-${ins.id}`}>
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                  <span className="flex items-center gap-1.5 font-semibold text-slate-900"><Calendar className="h-4 w-4 text-slate-400" /> {dateFr(ins.date)}</span>
                  <span className="flex items-center gap-1.5 text-slate-600"><User className="h-4 w-4 text-slate-400" /> {ins.responsable || "—"}</span>
                  <span className="flex items-center gap-1.5 text-slate-600"><Gauge className="h-4 w-4 text-slate-400" /> {fmtKm(ins.kilometrage)}</span>
                </div>
                <button onClick={() => handleDelete(ins.id)} data-testid={`inspection-delete-${ins.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Supprimer"><Trash2 className="h-4 w-4" /></button>
              </div>
              {ins.commentaire && <p className="mb-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{ins.commentaire}</p>}
              {ins.photos?.length > 0 && (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                  {ins.photos.map((p, i) => (
                    <button key={i} onClick={() => setPreview(p)} className="group relative aspect-square overflow-hidden rounded-lg border border-slate-200" data-testid={`inspection-photo-${ins.id}-${i}`}>
                      <img src={mediaSrc(p)} alt={angleLabel(p.angle)} className="h-full w-full object-cover transition-transform group-hover:scale-105" />
                      <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white">{angleLabel(p.angle)}</span>
                    </button>
                  ))}
                </div>
              )}
            </SectionCard>
          ))}
        </div>
      )}

      <AddDialog open={addOpen} onOpenChange={setAddOpen} vehicleId={vehicle.id} onCreated={refetch} />
      <FilePreview open={!!preview} onOpenChange={(o) => !o && setPreview(null)} file={preview} />
    </div>
  );
}
