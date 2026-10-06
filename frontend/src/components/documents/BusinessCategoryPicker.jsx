import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Copy, Loader2 } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { getBusinessCategories } from "@/lib/api";

const NONE = "__none__";
const FALLBACK_LABELS = {
  ENTRETIEN: "Entretien", REPARATION: "Réparation", PNEUS: "Pneus", CARBURANT: "Carburant",
  ENERGIE_ELECTRIQUE: "Énergie électrique", LAVAGE: "Lavage", PEAGE_VIGNETTE: "Péage / Vignette", AMENDE: "Amende",
  ASSURANCE: "Assurance", LEASING: "Leasing", TAXES: "Taxes", AUTRE: "Autre",
};

export const useBusinessCategories = () =>
  useQuery({ queryKey: ["business-categories"], queryFn: getBusinessCategories, staleTime: Infinity });

// Catégorie métier d'un justificatif : suggestion IA affichée, confirmation humaine obligatoire.
export function BusinessCategoryPicker({ value, onChange, suggestion, disabled = false }) {
  const { data: cats = [] } = useBusinessCategories();
  const label = (code) => cats.find((c) => c.code === code)?.label || FALLBACK_LABELS[code] || code;
  const pct = suggestion?.confidence != null ? ` · ${Math.round(suggestion.confidence * 100)} %` : "";
  return (
    <div data-testid="business-category-block" className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Catégorie métier (coût)</p>
        {suggestion?.code && (
          <span data-testid="business-category-suggestion" className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700">
            Suggestion IA : {label(suggestion.code)}{pct}
          </span>
        )}
      </div>
      <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? null : v)} disabled={disabled}>
        <SelectTrigger data-testid="business-category-select" className="mt-2 bg-white"><SelectValue placeholder="Non classé" /></SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>Non classé</SelectItem>
          {cats.map((c) => <SelectItem key={c.code} value={c.code} data-testid={`business-category-opt-${c.code}`}>{c.label}</SelectItem>)}
        </SelectContent>
      </Select>
      <p className="mt-1.5 text-[11px] text-slate-500">
        La catégorie confirmée alimente le module Coûts. Sans confirmation, le coût apparaît « Non classé » (jamais perdu).
      </p>
    </div>
  );
}

// 409 DUPLICATE_SUSPECTED : confirmation explicite, aucune suppression automatique.
export function DuplicateSuspectedBox({ info, onConfirmAnyway, busy }) {
  if (!info) return null;
  return (
    <div data-testid="duplicate-suspected" data-kind={info.kind || "document"} className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="flex items-start gap-2 font-semibold"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        {info.kind === "transaction" ? "Transaction énergie en doublon probable" : "Doublon probable"}</p>
      <p className="mt-1 text-xs">{info.message}{info.existing_filename ? ` Document existant : « ${info.existing_filename} ».` : ""}</p>
      <Button size="sm" variant="outline" data-testid="duplicate-confirm-anyway" onClick={onConfirmAnyway} disabled={busy}
              className="mt-2 gap-1.5 border-amber-300 bg-white text-amber-900 hover:bg-amber-100">
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />} Valider quand même (ce n'est pas un doublon)
      </Button>
    </div>
  );
}

// Fichier strictement identique déjà présent (SHA-256) : information, pas de blocage.
export function SameFileNotice({ dup }) {
  if (!dup) return null;
  return (
    <p data-testid="same-file-notice" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      Un fichier identique existe déjà pour ce véhicule : « {dup.original_filename} »{dup.folder ? ` (${dup.folder})` : ""}.
      Vérifiez qu'il ne s'agit pas d'un double envoi.
    </p>
  );
}

// Plaque d'un justificatif ≠ plaque du véhicule : avertissement, jamais de réaffectation.
export const isDocPlateMismatch = (f) => f.target === "document" && f.field === "plaque" && f.conflict;

// Types documentaires qui portent un coût (document = enregistrement de coût).
export const COST_DOC_TYPES = ["facture", "ticket_carburant"];

// Cohérence ticket (litres × prix ≈ montant, odomètre) : avertissements, jamais bloquants.
export function CoherenceWarnings({ warnings }) {
  if (!warnings?.length) return null;
  return (
    <div data-testid="coherence-warnings" className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      {warnings.map((w, i) => (
        <p key={`${w.code}-${i}`} className="flex items-start gap-1.5" data-testid={`coherence-${w.code}`}>
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {w.detail}
        </p>
      ))}
    </div>
  );
}

export function PlateMismatchNote() {
  return (
    <p data-testid="doc-plate-mismatch" className="mt-2 flex items-start gap-1.5 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs font-medium text-amber-700">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      La plaque mentionnée sur le document diffère de celle du véhicule — vérifiez que le justificatif est rattaché au bon véhicule.
      Aucune réaffectation automatique.
    </p>
  );
}
