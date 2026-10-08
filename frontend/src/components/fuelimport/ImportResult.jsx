import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";

// Résultat d'un import confirmé : importées / déjà importées / mises de côté / anomalies / avertissements
export default function ImportResult({ result, job }) {
  const aside = result?.set_aside || {};
  const counts = result?.counts || job?.counts || {};
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4" data-testid="fuel-import-summary">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
        <div className="space-y-1 text-sm text-emerald-900">
          <p className="font-display text-base font-bold">Import confirmé</p>
          <p>
            <b data-testid="fuel-import-result-imported">{result?.imported ?? counts.imported ?? 0}</b> importée(s)
            {result?.already_imported ? <> · {result.already_imported} déjà importée(s) (rejeu idempotent)</> : null}
            {" · "}<b data-testid="fuel-import-result-set-aside">{Object.values(aside).reduce((a, b) => a + b, 0)}</b> mise(s) de côté
            {aside.duplicate ? ` (${aside.duplicate} doublon(s)` : ""}{aside.invalid ? `${aside.duplicate ? ", " : " ("}${aside.invalid} invalide(s)` : ""}{aside.unknown_vehicle ? `${aside.duplicate || aside.invalid ? ", " : " ("}${aside.unknown_vehicle} véhicule(s) non résolu(s)` : ""}{aside.duplicate || aside.invalid || aside.unknown_vehicle ? ")" : ""}
            {" · "}<b data-testid="fuel-import-result-anomalies">{result?.anomalies ?? 0}</b> anomalie(s) détectée(s)
          </p>
          {(result?.warnings || []).length > 0 && (
            <ul className="list-inside list-disc text-xs" data-testid="fuel-import-result-warnings">
              {result.warnings.slice(0, 8).map((w, i) => <li key={i}><b>{w.code}</b> — {w.detail}</li>)}
              {result.warnings.length > 8 && <li>… {result.warnings.length - 8} autre(s)</li>}
            </ul>
          )}
          {(result?.results || []).some((x) => x.anomalies?.length) && (
            <p className="text-xs">Types : {[...new Set(result.results.flatMap((x) => x.anomalies || []))].map((t) => ANOMALY_TYPE_LABELS[t] || t).join(", ")}</p>
          )}
          <p className="text-xs">
            Consulter : <Link to="/energie" className="font-semibold underline" data-testid="fuel-import-result-link-transactions">Transactions</Link> · <Link to="/energie/anomalies" className="font-semibold underline" data-testid="fuel-import-result-link-anomalies">Anomalies</Link>. Les lignes mises de côté restent résolubles ci-dessous puis ré-importables (idempotent).
          </p>
        </div>
      </div>
    </div>
  );
}
