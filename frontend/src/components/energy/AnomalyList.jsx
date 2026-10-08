import { Button } from "@/components/ui/button";
import Pill from "@/components/energy/Pill";
import { ANOMALY_STATUS_META, SEVERITY_META, ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";

// Liste des anomalies d'une transaction (drawer) : type, sévérité, statut, explication, décision (acteur / motif / date)
export default function AnomalyList({ anomalies = [], isAdmin, onDecide, testId = "fuel-transaction-anomalies" }) {
  if (anomalies.length === 0) return <p className="text-sm text-slate-400" data-testid={`${testId}-empty`}>Aucune anomalie détectée.</p>;
  return (
    <ul className="space-y-2" data-testid={testId}>
      {anomalies.map((a) => (
        <li key={a.id} className="rounded-lg border border-slate-200 p-3" data-testid={`fuel-anomaly-item-${a.id}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm font-semibold text-slate-900">{ANOMALY_TYPE_LABELS[a.type] || a.label}</span>
              <Pill map={SEVERITY_META} code={a.severity} testId={`fuel-anomaly-item-severity-${a.id}`} />
              <Pill map={ANOMALY_STATUS_META} code={a.status} testId={`fuel-anomaly-item-status-${a.id}`} />
            </div>
            {isAdmin && a.status === "ouverte" && onDecide && (
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => onDecide(a)} data-testid={`fuel-anomaly-item-decide-${a.id}`}>Décider</Button>
            )}
          </div>
          <p className="mt-1 text-xs text-slate-600">{a.explanation}</p>
          {a.status !== "ouverte" && (
            <p className="mt-1 text-[11px] text-slate-500" data-testid={`fuel-anomaly-item-decision-${a.id}`}>
              {a.status_label} par <b>{a.decided_by}</b> le {a.decided_at ? new Date(a.decided_at).toLocaleString("fr-CH") : "—"} — motif : {a.decision_reason}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
