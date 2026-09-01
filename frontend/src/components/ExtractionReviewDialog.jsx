import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, AlertTriangle, Lock } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { getDocumentExtraction, validateScannedDocument } from "@/lib/api";
import { cn } from "@/lib/utils";

const inputType = (kind) => (kind === "date" ? "date" : kind === "int" || kind === "float" ? "number" : "text");

const fieldState = (f) => {
  if (f.conflict) return "CONFLIT";
  if (f.current_value !== null && f.current_value !== undefined) return "CORRESPONDANCE";
  if (f.status === "uncertain") return "INCERTAIN";
  return "COMPLETER";
};

const STATE_BADGE = {
  CONFLIT: { label: "Conflit", cls: "border-red-200 bg-red-50 text-red-700" },
  CORRESPONDANCE: { label: "Correspondance", cls: "border-emerald-200 bg-emerald-50 text-emerald-700" },
  COMPLETER: { label: "Compléter", cls: "border-sky-200 bg-sky-50 text-sky-700" },
  INCERTAIN: { label: "À vérifier", cls: "border-amber-200 bg-amber-50 text-amber-700" },
};

const isVinLocked = (f) => f.field === "vin" && f.reason === "VIN_BELONGS_TO_ANOTHER_VEHICLE";

function Confidence({ value }) {
  if (value === null || value === undefined) return null;
  const pct = Math.round(value * 100);
  const cls = value >= 0.9 ? "bg-emerald-50 text-emerald-700" : value >= 0.7 ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700";
  return <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold", cls)}>{pct} %</span>;
}

export default function ExtractionReviewDialog({ docId, open, onOpenChange, readOnly = false, onValidated }) {
  const [data, setData] = useState(null);
  const [rows, setRows] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    if (!open || !docId) return;
    setLoading(true);
    setError(null);
    setData(null);
    getDocumentExtraction(docId)
      .then((d) => {
        setData(d);
        setRows(Object.fromEntries((d.fields || []).map((f) => {
          const st = fieldState(f);
          return [f.field, { value: f.value ?? "", apply: st === "COMPLETER" && !isVinLocked(f) }];
        })));
      })
      .catch((e) => setError(e?.response?.data?.detail || "Impossible de charger le résultat d'analyse"))
      .finally(() => setLoading(false));
  }, [open, docId]);

  const setRow = (field, patch) => setRows((r) => ({ ...r, [field]: { ...r[field], ...patch } }));

  const buildPayload = () => {
    const fields = {};
    (data?.fields || []).forEach((f) => {
      const row = rows[f.field];
      if (!row?.apply || row.value === "" || row.value === null || isVinLocked(f)) return;
      fields[f.field] = row.value;
    });
    return fields;
  };

  const selectedCount = data ? Object.keys(buildPayload()).length : 0;

  const confirm = async () => {
    setValidating(true);
    try {
      const res = await validateScannedDocument(docId, { document_type: data.document_type, fields: buildPayload() });
      if (res.skipped_fields?.length) {
        res.skipped_fields.forEach((s) => toast.warning(s.detail || `Champ ${s.field} non appliqué (${s.reason})`));
      }
      toast.success(res.applied > 0
        ? `${res.applied} champ(s) appliqué(s) sur la fiche véhicule`
        : "Aucun nouveau champ à appliquer — fiche déjà à jour");
      onValidated?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur lors de la confirmation");
    } finally {
      setValidating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="extraction-review-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-2xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Sparkles className="h-5 w-5 text-slate-500" /> Informations détectées
          </DialogTitle>
          <DialogDescription>
            {data ? `${data.document_type_label} · ${data.vehicle_plaque || ""} — comparaison avec les données actuelles du véhicule.` : "Résultat de l'analyse du document."}
            {readOnly && " Compte en lecture seule : consultation uniquement."}
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500" data-testid="extraction-loading">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement du résultat…
          </div>
        )}
        {error && <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="extraction-error">{error}</p>}

        {data && data.extraction_status === "failed" && (
          <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700" data-testid="extraction-failed-note">
            L'analyse de ce document a échoué — relancez-la depuis la ligne du document.
          </p>
        )}

        {data && data.fields?.length === 0 && data.extraction_status !== "failed" && (
          <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="extraction-no-fields">
            Aucune donnée exploitable n'a été détectée sur ce document.
          </p>
        )}

        {data?.quality_warnings?.length > 0 && (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Qualité de l'image limitée ({data.quality_warnings.join(", ")}) — vérifiez attentivement les valeurs.
          </p>
        )}

        {data && data.fields?.length > 0 && (
          <div className="space-y-2.5">
            {data.fields.map((f) => {
              const st = fieldState(f);
              const badge = STATE_BADGE[st];
              const row = rows[f.field] || {};
              const locked = isVinLocked(f);
              const showCheckbox = !readOnly && st !== "CORRESPONDANCE";
              return (
                <div
                  key={f.field}
                  data-testid={`extraction-field-${f.field}`}
                  className={cn("rounded-lg border bg-white p-3",
                    st === "CONFLIT" ? "border-red-200" : "border-slate-200")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{f.label}</p>
                    <span className="flex items-center gap-1.5">
                      <span data-testid={`extraction-status-${f.field}`} className={cn("rounded-full border px-2 py-0.5 text-[10px] font-bold", badge.cls)}>
                        {badge.label}
                      </span>
                      <Confidence value={f.confidence} />
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400">Valeur actuelle</p>
                      <p className="mt-0.5 font-medium text-slate-800">
                        {f.current_value === null || f.current_value === undefined ? "—" : String(f.current_value)}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400">Valeur détectée</p>
                      <p className="mt-0.5 font-medium text-slate-800">{String(f.value)}</p>
                    </div>
                  </div>
                  {locked && (
                    <p className="mt-2 flex items-start gap-1.5 rounded-md bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700" data-testid="extraction-vin-locked">
                      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Le VIN détecté correspond à un autre véhicule de votre flotte — il ne peut pas être appliqué ici.
                    </p>
                  )}
                  {f.field === "vin" && f.valid_format === false && (
                    <p className="mt-2 flex items-start gap-1.5 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-700" data-testid="extraction-vin-invalid">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      VIN détecté invalide ou incomplet ({String(f.value).length}/17) — vérifiez et corrigez manuellement si besoin.
                    </p>
                  )}
                  {st === "CONFLIT" && !locked && (
                    <p className="mt-2 flex items-start gap-1.5 text-xs text-red-600">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      Valeur différente de la fiche — cochez uniquement si vous voulez remplacer la valeur actuelle.
                    </p>
                  )}
                  {showCheckbox && (
                    <div className="mt-2 flex items-center gap-2.5">
                      <Checkbox
                        checked={!!row.apply}
                        disabled={locked}
                        onCheckedChange={(ch) => setRow(f.field, { apply: !!ch })}
                        data-testid={`extraction-apply-${f.field}`}
                      />
                      <span className="text-xs text-slate-500">
                        {st === "CONFLIT" ? "Remplacer par la valeur détectée" : "Utiliser cette valeur"}
                      </span>
                      {row.apply && !locked && (
                        <Input
                          className="h-8 flex-1"
                          type={inputType(f.kind)}
                          value={row.value ?? ""}
                          onChange={(e) => setRow(f.field, { value: e.target.value })}
                          data-testid={`extraction-input-${f.field}`}
                        />
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="flex flex-col-reverse items-center justify-end gap-2 border-t border-slate-100 pt-4 sm:flex-row">
          <Button variant="outline" data-testid="extraction-close-btn" onClick={() => onOpenChange(false)}>Fermer</Button>
          {!readOnly && data && data.fields?.length > 0 && (
            <Button
              data-testid="extraction-confirm-btn"
              onClick={confirm}
              disabled={validating}
              className="gap-2 bg-emerald-600 hover:bg-emerald-700"
            >
              {validating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Confirmer et compléter le véhicule{selectedCount > 0 ? ` (${selectedCount})` : ""}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
