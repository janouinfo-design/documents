import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";

// Résultat d'un import confirmé : importées / déjà importées / mises de côté / anomalies / avertissements.
// Sans `result` (job rechargé), le résumé est dérivé des lignes (statuts non importés, anomalies persistées par ligne).
export default function ImportResult({ result, job, rows = [] }) {
  const fromRows = !result;
  const pending = rows.filter((r) => !r.imported);
  const aside = fromRows
    ? pending.reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {})
    : result.set_aside || {};
  const imported = fromRows ? (job?.counts?.imported ?? rows.filter((r) => r.imported).length) : result.imported;
  const anomalies = fromRows ? rows.reduce((a, r) => a + (r.anomalies || []).length, 0) : result.anomalies ?? 0;
  const types = fromRows ? [...new Set(rows.flatMap((r) => r.anomalies || []))] : [...new Set((result.results || []).flatMap((x) => x.anomalies || []))];
  const asideTotal = Object.values(aside).reduce((a, b) => a + b, 0);
  const asideDetail = Object.entries(aside).filter(([, n]) => n > 0).map(([k, n]) => `${n} ${{ duplicate: "doublon(s)", invalid: "invalide(s)", unknown_vehicle: "véhicule(s) non résolu(s)", unknown_card: "carte(s) non résolue(s)", amount_mismatch: "montant(s) incohérent(s)", ok: "valide(s) non importée(s)" }[k] || k}`).join(", ");
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4" data-testid="fuel-import-summary">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 h-5 w-5 text-emerald-600" />
        <div className="space-y-1 text-sm text-emerald-900">
          <p className="font-display text-base font-bold">Import confirmé{fromRows ? " (état actuel)" : ""}</p>
          <p>
            <b data-testid="fuel-import-result-imported">{imported ?? 0}</b> importée(s)
            {!fromRows && result.already_imported ? <> · {result.already_imported} déjà importée(s) (rejeu idempotent)</> : null}
            {" · "}<b data-testid="fuel-import-result-set-aside">{asideTotal}</b> mise(s) de côté{asideDetail ? ` (${asideDetail})` : ""}
            {" · "}<b data-testid="fuel-import-result-anomalies">{anomalies}</b> anomalie(s) détectée(s)
          </p>
          {!fromRows && (result.warnings || []).length > 0 && (
            <ul className="list-inside list-disc text-xs" data-testid="fuel-import-result-warnings">
              {result.warnings.slice(0, 8).map((w, i) => <li key={i}><b>{w.code}</b> — {w.detail}</li>)}
              {result.warnings.length > 8 && <li>… {result.warnings.length - 8} autre(s)</li>}
            </ul>
          )}
          {types.length > 0 && <p className="text-xs" data-testid="fuel-import-result-anomaly-types">Types : {types.map((t) => ANOMALY_TYPE_LABELS[t] || t).join(", ")}</p>}
          <p className="text-xs">
            Consulter : <Link to="/energie" className="font-semibold underline" data-testid="fuel-import-result-link-transactions">Transactions</Link> · <Link to="/energie/anomalies" className="font-semibold underline" data-testid="fuel-import-result-link-anomalies">Anomalies</Link>. Les lignes mises de côté restent résolubles ci-dessous puis ré-importables (idempotent).
          </p>
        </div>
      </div>
    </div>
  );
}
