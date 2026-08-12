import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Database, AlertTriangle, KeyRound, Check, RefreshCw } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { enrichTechnical, applyTechnicalEnrichment } from "@/lib/api";
import { cn } from "@/lib/utils";

const MATCHED_LABELS = { plate: "plaque d'immatriculation", homologation: "n° d'homologation (case 24)", vin: "VIN" };
const PROVIDER_LABELS = { astra_tas: "Registre TAS", astra_tg: "Registre TG (historique dès 1995)", swisscarinfo: "SwissCarInfo" };
const fmtDateTime = (iso) => {
  try {
    return new Date(iso).toLocaleString("fr-CH", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso || "—";
  }
};

export default function TechnicalEnrichDialog({ open, onOpenChange, vehicle, onApplied }) {
  const [step, setStep] = useState("loading");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [notConfigured, setNotConfigured] = useState(false);
  const [missingHomologation, setMissingHomologation] = useState(false);
  const [variantIdx, setVariantIdx] = useState(null);
  const [rows, setRows] = useState({});
  const [applying, setApplying] = useState(false);

  const variantFields = variantIdx != null ? data?.variantes?.[variantIdx]?.fields || [] : [];
  const allFields = data ? [...(data.fields || []), ...variantFields] : [];
  const conflicts = allFields.filter((f) => f.conflict);
  const normals = allFields.filter((f) => !f.conflict);

  const initRows = (fields) =>
    setRows(Object.fromEntries(fields.map((f) => [f.field, { value: f.value ?? "", apply: !f.conflict, useNew: false }])));

  const search = async () => {
    setStep("loading");
    setError(null);
    setNotConfigured(false);
    setMissingHomologation(false);
    setData(null);
    setVariantIdx(null);
    setRows({});
    try {
      const res = await enrichTechnical(vehicle.id);
      setData(res);
      if (res.requires_variant_choice) setStep("variant");
      else {
        initRows(res.fields || []);
        setStep("review");
      }
    } catch (e) {
      setNotConfigured(e?.response?.status === 503);
      setMissingHomologation(e?.response?.status === 422);
      setError(e?.response?.data?.detail || "Recherche impossible — réessayez plus tard.");
      setStep("error");
    }
  };

  useEffect(() => {
    if (open) search();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const chooseVariant = () => {
    initRows([...(data.fields || []), ...(data.variantes[variantIdx]?.fields || [])]);
    setStep("review");
  };

  const setRow = (field, patch) => setRows((r) => ({ ...r, [field]: { ...r[field], ...patch } }));

  const buildPayload = () => {
    const fields = {};
    allFields.forEach((f) => {
      const row = rows[f.field];
      if (!row || row.value === "" || row.value === null) return;
      if (f.conflict ? row.useNew : row.apply) fields[f.field] = row.value;
    });
    return fields;
  };

  const apply = async () => {
    setApplying(true);
    try {
      const res = await applyTechnicalEnrichment(vehicle.id, {
        fields: buildPayload(),
        matched_by: data.matched_by,
        retrieved_at: data.retrieved_at,
        provider: data.provider,
      });
      toast.success(res.applied > 0 ? `${res.applied} champ(s) mis à jour depuis la base technique` : "Aucune modification appliquée");
      onApplied?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur lors de l'application");
    } finally {
      setApplying(false);
    }
  };

  const appliedCount = data ? Object.keys(buildPayload()).length : 0;

  const sourceInfo = data && (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4" data-testid="tech-source-info">
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Source des données</p>
      <p className="mt-1 text-sm font-semibold text-slate-800">Base officielle ASTRA/OFROU — homologations suisses (copie locale)</p>
      {data.match && (
        <p className="mt-0.5 text-xs font-medium text-slate-600" data-testid="tech-match-info">
          {[data.match.make, data.match.model].filter(Boolean).join(" ")} · homologation {data.match.approval_no}
        </p>
      )}
      <p className="mt-0.5 text-xs text-slate-500">
        {PROVIDER_LABELS[data.provider] || data.provider} · Trouvé par {MATCHED_LABELS[data.matched_by] || data.matched_by} · Récupéré le {fmtDateTime(data.retrieved_at)}
      </p>
      {step === "review" && variantIdx != null && (
        <p className="mt-0.5 text-xs text-slate-500">
          Variante : <span className="font-semibold">{data.variantes[variantIdx]?.label}</span>{" "}
          <button type="button" data-testid="tech-change-variant" onClick={() => setStep("variant")} className="underline hover:text-slate-800">
            Changer
          </button>
        </p>
      )}
    </div>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="tech-enrich-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-2xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Database className="h-5 w-5 text-slate-500" /> Base technique — {vehicle?.plaque}
          </DialogTitle>
          <DialogDescription>
            {step === "loading" && "Recherche dans la base d'homologation officielle…"}
            {step === "variant" && "Plusieurs variantes correspondent — choisissez celle de votre véhicule."}
            {step === "review" && "Vérifiez les données proposées — rien n'est enregistré sans votre validation."}
            {step === "error" && "La recherche n'a pas abouti."}
          </DialogDescription>
        </DialogHeader>

        {step === "loading" && (
          <div className="flex flex-col items-center gap-3 py-12" data-testid="tech-loading">
            <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
            <p className="text-sm font-medium text-slate-700">Interrogation de la base officielle ASTRA/OFROU…</p>
            <p className="text-xs text-slate-400">Recherche locale par n° d'homologation (case 24) — aucune clé externe requise</p>
          </div>
        )}

        {step === "error" && (
          <div className="space-y-4 py-4 text-center" data-testid="tech-error">
            {notConfigured ? <KeyRound className="mx-auto h-8 w-8 text-slate-400" /> : <AlertTriangle className={cn("mx-auto h-8 w-8", missingHomologation ? "text-amber-400" : "text-red-400")} />}
            <p className="text-sm text-slate-600" data-testid="tech-error-message">{error}</p>
            {notConfigured && (
              <p className="mx-auto max-w-md text-xs text-slate-400">
                Les données officielles ASTRA (registres TAS + TG) ne sont pas encore importées sur ce serveur. L'import se lance automatiquement au démarrage, ou manuellement via POST /api/astra/import.
              </p>
            )}
            {missingHomologation && (
              <p className="mx-auto max-w-md text-xs text-slate-500" data-testid="tech-hint-missing-homologation">
                Le plus simple : scannez la carte grise (onglet Carte grise) — le n° d'homologation est extrait automatiquement — ou saisissez-le via « Modifier ».
              </p>
            )}
            <div className="flex justify-center gap-2">
              <Button variant="outline" data-testid="tech-close-btn" onClick={() => onOpenChange(false)}>Fermer</Button>
              {!notConfigured && !missingHomologation && (
                <Button data-testid="tech-retry-btn" onClick={search} className="gap-2 bg-slate-900 hover:bg-slate-800">
                  <RefreshCw className="h-4 w-4" /> Réessayer
                </Button>
              )}
            </div>
          </div>
        )}

        {step === "variant" && data && (
          <div className="space-y-4" data-testid="tech-variant-step">
            {sourceInfo}
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              <AlertTriangle className="mr-1.5 inline h-4 w-4" />
              Plusieurs variantes d'homologation correspondent — sélectionnez celle qui équipe ce véhicule.
            </div>
            <div className="space-y-2">
              {data.variantes.map((v, i) => (
                <button
                  key={i}
                  type="button"
                  data-testid={`tech-variant-${i}`}
                  onClick={() => setVariantIdx(i)}
                  className={cn(
                    "w-full rounded-xl border p-3 text-left transition-colors",
                    variantIdx === i ? "border-slate-900 bg-slate-50 ring-1 ring-slate-900" : "border-slate-200 hover:border-slate-400"
                  )}
                >
                  <p className="text-sm font-semibold text-slate-800">{v.label}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {(v.fields || []).map((f) => `${f.label} : ${f.value}`).join(" · ") || "Aucune donnée spécifique"}
                  </p>
                </button>
              ))}
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
              <Button data-testid="tech-variant-continue" onClick={chooseVariant} disabled={variantIdx == null} className="gap-2 bg-slate-900 hover:bg-slate-800">
                Continuer <Check className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {step === "review" && data && (
          <div className="space-y-5" data-testid="tech-review">
            {sourceInfo}
            {allFields.length === 0 && (
              <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="tech-no-fields">
                Aucune donnée exploitable trouvée pour ce véhicule.
              </p>
            )}
            {conflicts.length > 0 && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-4" data-testid="tech-conflicts">
                <p className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <AlertTriangle className="h-4 w-4" /> Différence(s) avec la fiche véhicule — choisissez la valeur à conserver
                </p>
                <div className="mt-3 space-y-3">
                  {conflicts.map((f) => {
                    const row = rows[f.field] || {};
                    return (
                      <div key={f.field} className="rounded-lg border border-amber-200 bg-white p-3">
                        <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{f.label}</p>
                        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            data-testid={`tech-conflict-keep-${f.field}`}
                            onClick={() => setRow(f.field, { useNew: false })}
                            className={cn(
                              "rounded-lg border p-2.5 text-left transition-colors",
                              !row.useNew ? "border-slate-900 bg-slate-50 ring-1 ring-slate-900" : "border-slate-200 hover:border-slate-400"
                            )}
                          >
                            <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-slate-400">Valeur actuelle (fiche véhicule)</p>
                            <p className="mt-0.5 text-sm font-medium text-slate-800">{String(f.current_value)}</p>
                          </button>
                          <button
                            type="button"
                            data-testid={`tech-conflict-new-${f.field}`}
                            onClick={() => setRow(f.field, { useNew: true })}
                            className={cn(
                              "rounded-lg border p-2.5 text-left transition-colors",
                              row.useNew ? "border-emerald-600 bg-emerald-50 ring-1 ring-emerald-600" : "border-slate-200 hover:border-slate-400"
                            )}
                          >
                            <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-emerald-600">Donnée technique proposée</p>
                            <p className="mt-0.5 text-sm font-medium text-slate-800">{String(f.value)}</p>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            {normals.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Données proposées — décochez pour ignorer</p>
                {normals.map((f) => {
                  const row = rows[f.field] || {};
                  return (
                    <label key={f.field} className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-3" data-testid={`tech-field-${f.field}`}>
                      <Checkbox checked={!!row.apply} onCheckedChange={(ch) => setRow(f.field, { apply: !!ch })} data-testid={`tech-apply-${f.field}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-bold uppercase tracking-[0.08em] text-slate-500">{f.label}</span>
                        <span className="mt-0.5 block text-sm font-medium text-slate-800">{String(f.value)}</span>
                      </span>
                      {f.current_value == null && (
                        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500">Nouveau</span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}
            <p className="text-xs text-slate-400">
              Aucune donnée n'est enregistrée sans votre validation. Les valeurs mesurées via CAN/OBD ne sont jamais remplacées par des données constructeur.
            </p>
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button variant="outline" data-testid="tech-review-cancel" onClick={() => onOpenChange(false)}>Annuler</Button>
              <Button
                data-testid="tech-apply-btn"
                onClick={apply}
                disabled={applying || appliedCount === 0}
                className="gap-2 bg-emerald-600 hover:bg-emerald-700"
              >
                {applying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Appliquer à la fiche{appliedCount > 0 ? ` (${appliedCount})` : ""}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
