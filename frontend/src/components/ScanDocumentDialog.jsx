import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Camera, FolderUp, Loader2, RotateCw, Trash2, FileText, Sparkles,
  AlertTriangle, ScanLine, RefreshCw, ArrowLeft,
} from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { scanVehicleDocument, validateScannedDocument, deleteDocument } from "@/lib/api";
import { cn } from "@/lib/utils";

export const DOC_TYPE_OPTIONS = [
  { key: "permis_circulation", label: "Permis de circulation" },
  { key: "assurance", label: "Assurance" },
  { key: "leasing", label: "Contrat de leasing" },
  { key: "controle_technique", label: "Expertise / Contrôle technique" },
  { key: "facture", label: "Facture véhicule" },
  { key: "amende", label: "Amende" },
  { key: "autre", label: "Autre document" },
];

const typeLabel = (key) => DOC_TYPE_OPTIONS.find((t) => t.key === key)?.label || key;
const inputType = (kind) => (kind === "date" ? "date" : kind === "int" || kind === "float" ? "number" : "text");

const rotateImageFile = (file) =>
  new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.height;
      canvas.height = img.width;
      const ctx = canvas.getContext("2d");
      ctx.translate(canvas.width / 2, canvas.height / 2);
      ctx.rotate(Math.PI / 2);
      ctx.drawImage(img, -img.width / 2, -img.height / 2);
      URL.revokeObjectURL(url);
      canvas.toBlob(
        (blob) => resolve(new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" })),
        "image/jpeg",
        0.92
      );
    };
    img.src = url;
  });

function ConfidenceBadge({ value }) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  if (value >= 0.9)
    return <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">{pct} %</span>;
  if (value >= 0.7)
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
        <AlertTriangle className="h-3 w-3" /> {pct} %
      </span>
    );
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700">
      <AlertTriangle className="h-3 w-3" /> {pct} % · à vérifier
    </span>
  );
}

export default function ScanDocumentDialog({ open, onOpenChange, vehicle, initialMode = "import", forcedType, onValidated }) {
  const [step, setStep] = useState("capture");
  const [pages, setPages] = useState([]);
  const [result, setResult] = useState(null);
  const [docType, setDocType] = useState(forcedType || "autre");
  const [rows, setRows] = useState({});
  const [error, setError] = useState(null);
  const [failedDocId, setFailedDocId] = useState(null);
  const [validating, setValidating] = useState(false);
  const cameraRef = useRef(null);
  const fileRef = useRef(null);
  const validatedRef = useRef(false);

  const reset = () => {
    pages.forEach((p) => p.preview && URL.revokeObjectURL(p.preview));
    setStep("capture");
    setPages([]);
    setResult(null);
    setRows({});
    setError(null);
    setFailedDocId(null);
    setDocType(forcedType || "autre");
    validatedRef.current = false;
  };

  useEffect(() => {
    if (open && initialMode === "camera") {
      const t = setTimeout(() => cameraRef.current?.click(), 200);
      return () => clearTimeout(t);
    }
  }, [open, initialMode]);

  const close = (o) => {
    if (!o) {
      if (step === "review" && result && !validatedRef.current) {
        deleteDocument(result.document_id).catch(() => {});
      }
      reset();
    }
    onOpenChange(o);
  };

  const addFiles = (list) => {
    const arr = Array.from(list || []);
    if (!arr.length) return;
    const hasPdf = arr.some((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (hasPdf) {
      if (arr.length > 1 || pages.length > 0) {
        toast.error("Un PDF doit être analysé seul (il contient déjà ses pages)");
        return;
      }
      setPages([{ id: crypto.randomUUID(), file: arr[0], preview: null, isPdf: true }]);
      return;
    }
    if (pages.some((p) => p.isPdf)) {
      toast.error("Un PDF doit être analysé seul");
      return;
    }
    if (pages.length + arr.length > 8) {
      toast.error("Maximum 8 pages par scan");
      return;
    }
    setPages((ps) => [
      ...ps,
      ...arr.map((f) => ({ id: crypto.randomUUID(), file: f, preview: URL.createObjectURL(f), isPdf: false })),
    ]);
  };

  const rotatePage = async (id) => {
    const page = pages.find((p) => p.id === id);
    if (!page || page.isPdf) return;
    const rotated = await rotateImageFile(page.file);
    URL.revokeObjectURL(page.preview);
    setPages((ps) => ps.map((p) => (p.id === id ? { ...p, file: rotated, preview: URL.createObjectURL(rotated) } : p)));
  };

  const removePage = (id) => {
    setPages((ps) => {
      const page = ps.find((p) => p.id === id);
      if (page?.preview) URL.revokeObjectURL(page.preview);
      return ps.filter((p) => p.id !== id);
    });
  };

  const initReview = (res) => {
    setResult(res);
    setDocType(res.document_type);
    setRows(Object.fromEntries((res.fields || []).map((f) => [f.field, { value: f.value ?? "", apply: !f.conflict, useNew: false }])));
    setStep("review");
  };

  const analyze = async () => {
    setError(null);
    setStep("analyzing");
    try {
      const res = await scanVehicleDocument(vehicle.id, pages.map((p) => p.file), { documentType: forcedType || undefined });
      if (res.extraction_status === "failed") {
        setFailedDocId(res.document_id);
        setError(res.error);
        setStep("failed");
        return;
      }
      initReview(res);
    } catch (e) {
      setError(e?.response?.data?.detail || "Échec de l'analyse — vérifiez le fichier puis réessayez.");
      setStep("capture");
    }
  };

  const reanalyze = async (type) => {
    const documentId = result?.document_id || failedDocId;
    setError(null);
    setStep("analyzing");
    try {
      const res = await scanVehicleDocument(vehicle.id, null, { documentType: type, documentId });
      if (res.extraction_status === "failed") {
        setFailedDocId(res.document_id);
        setError(res.error);
        setStep("failed");
        return;
      }
      initReview(res);
    } catch (e) {
      setError(e?.response?.data?.detail || "Échec de la ré-analyse.");
      setStep(result ? "review" : "failed");
    }
  };

  const setRow = (field, patch) => setRows((r) => ({ ...r, [field]: { ...r[field], ...patch } }));

  const conflicts = (result?.fields || []).filter((f) => f.conflict);
  const normals = (result?.fields || []).filter((f) => !f.conflict);

  const buildPayload = () => {
    const fields = {};
    (result?.fields || []).forEach((f) => {
      const row = rows[f.field];
      if (!row || row.value === "" || row.value === null) return;
      if (f.conflict ? row.useNew : row.apply) fields[f.field] = row.value;
    });
    return fields;
  };

  const validate = async () => {
    setValidating(true);
    try {
      const fields = buildPayload();
      const res = await validateScannedDocument(result.document_id, { document_type: docType, fields });
      validatedRef.current = true;
      toast.success(
        res.applied > 0
          ? `Document validé · ${res.applied} champ(s) mis à jour sur la fiche véhicule`
          : "Document validé et classé"
      );
      onValidated?.();
      close(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur lors de la validation");
    } finally {
      setValidating(false);
    }
  };

  const appliedCount = result ? Object.keys(buildPayload()).length : 0;

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent data-testid="scan-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-2xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <ScanLine className="h-5 w-5 text-slate-500" /> Scanner un document — {vehicle?.plaque}
          </DialogTitle>
          <DialogDescription>
            {step === "capture" && "Prenez une photo ou importez un PDF/image. Plusieurs pages possibles (recto, verso…)."}
            {step === "analyzing" && "Analyse en cours…"}
            {step === "review" && "Vérifiez les données détectées — rien n'est enregistré sans votre validation."}
            {step === "failed" && "L'analyse a échoué."}
          </DialogDescription>
        </DialogHeader>

        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        />
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp,application/pdf"
          multiple
          className="hidden"
          onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
        />

        {step === "capture" && (
          <div className="space-y-4">
            {error && (
              <div data-testid="scan-error" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button data-testid="scan-take-photo" onClick={() => cameraRef.current?.click()} className="flex-1 gap-2 bg-slate-900 hover:bg-slate-800">
                <Camera className="h-4 w-4" /> Prendre une photo
              </Button>
              <Button data-testid="scan-import-file" variant="outline" onClick={() => fileRef.current?.click()} className="flex-1 gap-2">
                <FolderUp className="h-4 w-4" /> Importer PDF ou image
              </Button>
            </div>
            {pages.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="scan-pages">
                {pages.map((p, i) => (
                  <div key={p.id} className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
                    {p.isPdf ? (
                      <div className="flex h-32 flex-col items-center justify-center gap-1 p-2 text-center">
                        <FileText className="h-8 w-8 text-red-400" />
                        <p className="w-full truncate text-xs font-medium text-slate-600">{p.file.name}</p>
                      </div>
                    ) : (
                      <img src={p.preview} alt={`Page ${i + 1}`} className="h-32 w-full object-cover" />
                    )}
                    <span className="absolute left-1.5 top-1.5 rounded bg-slate-900/80 px-1.5 py-0.5 text-[10px] font-bold text-white">
                      Page {i + 1}
                    </span>
                    <div className="absolute right-1.5 top-1.5 flex gap-1">
                      {!p.isPdf && (
                        <button onClick={() => rotatePage(p.id)} data-testid={`scan-rotate-${i}`} className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/90 text-slate-600 shadow hover:bg-white" aria-label="Pivoter">
                          <RotateCw className="h-3.5 w-3.5" />
                        </button>
                      )}
                      <button onClick={() => removePage(p.id)} data-testid={`scan-remove-${i}`} className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/90 text-red-500 shadow hover:bg-white" aria-label="Supprimer">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-xl border-2 border-dashed border-slate-200 p-6 text-center text-sm text-slate-400">
                Aucune page ajoutée pour l'instant
              </p>
            )}
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button variant="outline" data-testid="scan-cancel-btn" onClick={() => close(false)}>Annuler</Button>
              <Button data-testid="scan-analyze-btn" onClick={analyze} disabled={pages.length === 0} className="gap-2 bg-slate-900 hover:bg-slate-800">
                <Sparkles className="h-4 w-4" /> Analyser le document
              </Button>
            </div>
          </div>
        )}

        {step === "analyzing" && (
          <div className="flex flex-col items-center justify-center gap-3 py-14" data-testid="scan-analyzing">
            <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            <p className="text-sm font-medium text-slate-700">Analyse du document en cours…</p>
            <p className="text-xs text-slate-400">Reconnaissance du type et extraction des données (10–30 s)</p>
          </div>
        )}

        {step === "failed" && (
          <div className="space-y-4 py-4 text-center" data-testid="scan-failed">
            <AlertTriangle className="mx-auto h-8 w-8 text-red-400" />
            <p className="text-sm text-slate-600">{error || "Document illisible ou analyse impossible."}</p>
            <div className="flex justify-center gap-2">
              <Button variant="outline" onClick={() => close(false)}>Fermer</Button>
              <Button data-testid="scan-retry-btn" onClick={() => reanalyze(forcedType || undefined)} className="gap-2 bg-slate-900 hover:bg-slate-800">
                <RefreshCw className="h-4 w-4" /> Réessayer l'analyse
              </Button>
            </div>
          </div>
        )}

        {step === "review" && result && (
          <div className="space-y-5" data-testid="scan-review">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Type de document détecté</p>
                {result.type_confidence != null && <ConfidenceBadge value={result.type_confidence} />}
              </div>
              <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                <Select value={docType} onValueChange={setDocType}>
                  <SelectTrigger data-testid="scan-type-select" className="bg-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DOC_TYPE_OPTIONS.map((t) => (
                      <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {docType !== result.document_type && (
                  <Button data-testid="scan-reanalyze-btn" variant="outline" onClick={() => reanalyze(docType)} className="gap-2 whitespace-nowrap">
                    <RefreshCw className="h-4 w-4" /> Ré-analyser
                  </Button>
                )}
              </div>
            </div>

            {conflicts.length > 0 && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-4" data-testid="scan-conflicts">
                <p className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <AlertTriangle className="h-4 w-4" /> Différence(s) détectée(s) — choisissez la valeur à conserver
                </p>
                <div className="mt-3 space-y-3">
                  {conflicts.map((f) => {
                    const row = rows[f.field] || {};
                    return (
                      <div key={f.field} className="rounded-lg border border-amber-200 bg-white p-3">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{f.label}</p>
                          <ConfidenceBadge value={f.confidence} />
                        </div>
                        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            data-testid={`conflict-keep-${f.field}`}
                            onClick={() => setRow(f.field, { useNew: false })}
                            className={cn(
                              "rounded-lg border p-2.5 text-left transition-colors",
                              !row.useNew ? "border-slate-900 bg-slate-50 ring-1 ring-slate-900" : "border-slate-200 hover:border-slate-400"
                            )}
                          >
                            <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400">Conserver la valeur actuelle</p>
                            <p className="mt-0.5 text-sm font-medium text-slate-800">{String(f.current_value)}</p>
                          </button>
                          <button
                            type="button"
                            data-testid={`conflict-new-${f.field}`}
                            onClick={() => setRow(f.field, { useNew: true })}
                            className={cn(
                              "rounded-lg border p-2.5 text-left transition-colors",
                              row.useNew ? "border-emerald-600 bg-emerald-50 ring-1 ring-emerald-600" : "border-slate-200 hover:border-slate-400"
                            )}
                          >
                            <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-emerald-600">Utiliser la nouvelle valeur</p>
                            <p className="mt-0.5 text-sm font-medium text-slate-800">{String(f.value)}</p>
                          </button>
                        </div>
                        {row.useNew && (
                          <Input
                            data-testid={`conflict-input-${f.field}`}
                            className="mt-2"
                            type={inputType(f.kind)}
                            value={row.value ?? ""}
                            onChange={(e) => setRow(f.field, { value: e.target.value })}
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {normals.length > 0 ? (
              <div className="space-y-3">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
                  Données détectées — décochez pour ignorer, modifiez si besoin
                </p>
                {normals.map((f) => {
                  const row = rows[f.field] || {};
                  return (
                    <div key={f.field} className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3" data-testid={`scan-field-${f.field}`}>
                      <Checkbox className="mt-1" checked={!!row.apply} onCheckedChange={(ch) => setRow(f.field, { apply: !!ch })} data-testid={`scan-apply-${f.field}`} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <label className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{f.label}</label>
                          <ConfidenceBadge value={f.confidence} />
                        </div>
                        <Input
                          className="mt-1.5"
                          type={inputType(f.kind)}
                          value={row.value ?? ""}
                          disabled={!row.apply}
                          onChange={(e) => setRow(f.field, { value: e.target.value })}
                          data-testid={`scan-input-${f.field}`}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              conflicts.length === 0 && (
                <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="scan-no-fields">
                  Aucune donnée exploitable détectée. Le document sera simplement classé dans « {typeLabel(docType)} ».
                </p>
              )
            )}

            <div className="flex flex-col-reverse justify-between gap-2 border-t border-slate-100 pt-4 sm:flex-row">
              <Button variant="ghost" onClick={() => setStep("capture")} className="gap-1.5 text-slate-500">
                <ArrowLeft className="h-4 w-4" /> Pages
              </Button>
              <div className="flex justify-end gap-2">
                <Button variant="outline" data-testid="scan-review-cancel" onClick={() => close(false)}>Annuler</Button>
                <Button data-testid="scan-validate-btn" onClick={validate} disabled={validating} className="gap-2 bg-emerald-600 hover:bg-emerald-700">
                  {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                  Valider et enregistrer{appliedCount > 0 ? ` (${appliedCount})` : ""}
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
