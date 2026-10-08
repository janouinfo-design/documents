import { REVIEW_REASON_LABELS } from "@/lib/fuelImport";

const EXTRA_KEYS = ["card_unique", "assignment_at_date", "card_usable", "assigned_vehicle_id", "plate", "provenance", "batch_id", "reason", "by"];

// Scoring explicable : règle → points, détails (card_unique, assignment_at_date, card_usable…), raisons de revue, candidats
export default function MatchBreakdown({ match, vehicleId }) {
  if (!match) return <p className="text-sm text-slate-400" data-testid="fuel-transaction-breakdown-empty">Aucun rattachement calculé.</p>;
  const rows = match.breakdown || [];
  return (
    <div className="space-y-3" data-testid="fuel-transaction-breakdown">
      <table className="w-full text-sm">
        <tbody>
          {rows.map((b, i) => (
            <tr key={i} className="border-b border-slate-100 last:border-0" data-testid={`fuel-transaction-breakdown-rule-${b.rule}`}>
              <td className="py-1 pr-2 text-slate-700">{b.label || b.rule}
                <span className="ml-1 text-[11px] text-slate-400">{EXTRA_KEYS.filter((k) => b[k] !== undefined).map((k) => `${k}=${String(b[k])}`).join(" · ")}</span>
              </td>
              <td className={`py-1 text-right font-bold ${b.points < 0 ? "text-red-600" : "text-slate-900"}`}>{b.points > 0 ? "+" : ""}{b.points}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td className="py-1 text-slate-400">Aucune règle applicable (aucun candidat).</td></tr>}
        </tbody>
      </table>
      {(match.review_reasons || []).length > 0 && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="fuel-transaction-review-reasons">
          Raisons de revue : {match.review_reasons.map((r) => REVIEW_REASON_LABELS[r] || r).join(" · ")}
        </p>
      )}
      {(match.candidates || []).length > 0 && (
        <div data-testid="fuel-transaction-candidates">
          <p className="text-xs font-semibold text-slate-700">Candidats évalués</p>
          <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
            {match.candidates.map((c) => (
              <li key={c.vehicle_id} data-testid={`fuel-transaction-candidate-${c.vehicle_id}`}>
                • {c.label || c.vehicle_id} — {c.partial_score} pt · {(c.sources || []).join(", ")}{c.vehicle_id === vehicleId ? " · véhicule actuel" : ""}{c.proposed ? " · proposé" : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
      {(match.history || []).length > 1 && (
        <details className="text-xs text-slate-500" data-testid="fuel-transaction-match-history">
          <summary className="cursor-pointer font-semibold">Historique du rattachement ({match.history.length})</summary>
          <ul className="mt-1 space-y-0.5">
            {[...match.history].reverse().map((h, i) => <li key={i}>{new Date(h.at).toLocaleString("fr-CH")} · {h.by} · {h.status}{h.method ? ` (${h.method})` : ""}{h.score != null ? ` · ${h.score} pt` : ""}{h.reason ? ` — ${h.reason}` : ""}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
