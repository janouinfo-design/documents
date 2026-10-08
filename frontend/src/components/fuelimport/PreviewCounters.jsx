import { cn } from "@/lib/utils";

const ITEMS = [
  { key: "total", label: "Lignes", testId: "fuel-preview-total-count", cls: "border-slate-300 text-slate-900" },
  { key: "ok", label: "Valides", testId: "fuel-preview-valid-count", cls: "border-emerald-300 text-emerald-700" },
  { key: "invalid", label: "Invalides", testId: "fuel-preview-invalid-count", cls: "border-red-300 text-red-700" },
  { key: "duplicate", label: "Doublons", testId: "fuel-preview-duplicate-count", cls: "border-amber-300 text-amber-800" },
  { key: "unknown_card", label: "Carte non résolue", testId: "fuel-preview-unknown-card-count", cls: "border-sky-300 text-sky-800" },
  { key: "unknown_vehicle", label: "Véhicule non résolu", testId: "fuel-preview-unknown-vehicle-count", cls: "border-rose-300 text-rose-800" },
  { key: "amount_mismatch", label: "Montant incohérent", testId: "fuel-preview-amount-mismatch-count", cls: "border-orange-300 text-orange-800" },
  { key: "warnings", label: "Avertissements", testId: "fuel-preview-anomaly-count", cls: "border-indigo-300 text-indigo-800" },
  { key: "imported", label: "Importées", testId: "fuel-preview-imported-count", cls: "border-slate-900 text-slate-900" },
];

export const rowWarnings = (r) => (r.resolution?.vehicle?.review_reasons || []).length + (r.anomalies || []).length;

// Compteurs du preview / résultat (valides, invalides, doublons, carte/véhicule non résolus, avertissements, importées)
export default function PreviewCounters({ counts = {}, rows = [], active, onSelect }) {
  const values = { ...counts, warnings: rows.filter((r) => rowWarnings(r) > 0).length };
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9" data-testid="fuel-preview-counters">
      {ITEMS.map((it) => (
        <button key={it.key} type="button" onClick={() => onSelect?.(it.key)} data-testid={it.testId}
          className={cn("rounded-lg border-2 bg-white px-2 py-2 text-left transition-colors hover:bg-slate-50", it.cls, active === it.key && "ring-2 ring-slate-900/30")}>
          <p className="text-[10px] font-semibold uppercase tracking-wide opacity-70">{it.label}</p>
          <p className="font-display text-xl font-bold">{values[it.key] ?? 0}</p>
        </button>
      ))}
    </div>
  );
}
