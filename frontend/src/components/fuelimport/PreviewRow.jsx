import { Button } from "@/components/ui/button";
import { TableCell, TableRow } from "@/components/ui/table";
import Pill from "@/components/energy/Pill";
import { ROW_STATUS_META, MATCH_META, CARD_RES_META, REVIEW_REASON_LABELS, ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";
import { chfExact, dateFr } from "@/lib/format";

export const fxLabel = (n) => {
  if (!n?.devise || n.devise === "CHF") return null;
  return n.montant_chf != null ? { text: `= ${chfExact(n.montant_chf)}`, cls: "text-emerald-700" } : { text: "FX en attente", cls: "text-amber-700" };
};

// Ligne du preview : statut, carte (found/ambiguous/not_found), véhicule (auto/review/manual/unknown), montant/devise/FX, avertissements, actions
export default function PreviewRow({ row: r, isAdmin, canMutate, onResolve, onForce }) {
  const n = r.normalized || {};
  const v = r.resolution?.vehicle || {};
  const c = r.resolution?.card || {};
  const fx = fxLabel(n);
  const cardCode = n.card_last4 ? (c.manual ? "manual" : c.status) : "none";
  const vehicleLabel = v.vehicle_id ? (v.candidates || []).find((x) => x.vehicle_id === v.vehicle_id)?.label || v.vehicle_id : null;
  const needsResolve = !r.imported && ["unknown_vehicle", "unknown_card"].includes(r.status);
  return (
    <TableRow data-testid={`fuel-preview-row-${r.id}`} className={r.imported ? "bg-emerald-50/40" : r.status === "invalid" ? "bg-red-50/40" : "hover:bg-slate-50"}>
      <TableCell className="text-xs text-slate-400">{r.row_index}</TableCell>
      <TableCell className="whitespace-nowrap text-sm text-slate-700">{n.date ? `${dateFr(n.date)}${n.heure ? ` ${n.heure}` : ""}` : <span className="text-red-600">{(r.raw && Object.values(r.raw)[0]) || "—"}</span>}</TableCell>
      <TableCell className="text-sm text-slate-700">
        {n.station || "—"}
        {n.fournisseur && <span className="ml-1 text-[11px] text-slate-400">· {n.fournisseur}</span>}
        {n.external_transaction_id && <p className="font-mono text-[10px] text-slate-400">réf. {n.external_transaction_id}</p>}
      </TableCell>
      <TableCell>
        {n.card_last4 ? <p className="font-mono text-xs text-slate-600">••••{n.card_last4}</p> : <p className="text-xs text-slate-300">—</p>}
        <Pill map={CARD_RES_META} code={cardCode} testId={`fuel-preview-card-${r.id}`} />
      </TableCell>
      <TableCell>
        {vehicleLabel ? <p className="text-sm font-semibold text-slate-800">{vehicleLabel}</p>
          : n.plaque_hint ? <p className="font-mono text-xs text-slate-500">plaque fichier « {n.plaque_hint} »</p> : <p className="text-xs text-slate-300">—</p>}
        <div className="flex flex-wrap items-center gap-1">
          <Pill map={MATCH_META} code={v.status} testId={`fuel-preview-match-${r.id}`} />
          {v.score != null && v.status !== "unmatched" && <span className="text-[11px] text-slate-500" data-testid={`fuel-preview-score-${r.id}`}>{v.score} pt{v.method ? ` · ${v.method}` : ""}</span>}
          {!v.vehicle_id && (v.candidates || []).length > 0 && <span className="text-[11px] text-amber-700">{v.candidates.length} candidat(s)</span>}
        </div>
      </TableCell>
      <TableCell className="text-right">
        <p className="text-sm font-semibold text-slate-900">{n.montant != null ? chfExact(n.montant, n.devise || "CHF") : "—"}</p>
        {fx && <p className={`text-[11px] font-semibold ${fx.cls}`} data-testid={`fuel-preview-fx-${r.id}`}>{fx.text}</p>}
        {(n.litres != null || n.energie_kwh != null) && <p className="text-[11px] text-slate-400">{n.litres != null ? `${n.litres} L` : `${n.energie_kwh} kWh`}</p>}
      </TableCell>
      <TableCell>
        <Pill map={ROW_STATUS_META} code={r.imported ? "ok" : r.status} testId={`fuel-preview-status-${r.id}`} prefix={r.imported ? "Importée · " : ""} />
        {r.duplicate_of && <p className="text-[10px] text-amber-700">doublon {r.duplicate_of.kind}{r.duplicate_of.row_index ? ` (ligne ${r.duplicate_of.row_index})` : ""}</p>}
      </TableCell>
      <TableCell className="max-w-xs">
        <div className="space-y-0.5 text-[11px]" data-testid={`fuel-preview-warnings-${r.id}`}>
          {(r.errors || []).map((e, i) => <p key={`e${i}`} className="text-red-600">{e}</p>)}
          {(v.review_reasons || []).map((x) => <p key={x} className="text-amber-800">⚠ {REVIEW_REASON_LABELS[x] || x}</p>)}
          {(r.anomalies || []).map((x) => <p key={x} className="text-rose-700">● {ANOMALY_TYPE_LABELS[x] || x}</p>)}
          {(r.notes || []).map((x, i) => <p key={`n${i}`} className="text-slate-500">{x}</p>)}
        </div>
      </TableCell>
      <TableCell className="text-right">
        {canMutate && isAdmin && !r.imported && (
          <div className="flex justify-end gap-1">
            {(needsResolve || r.status === "ok" || r.status === "amount_mismatch") && r.status !== "invalid" && (
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={() => onResolve(r)} data-testid={`fuel-row-resolve-btn-${r.id}`}>Résoudre</Button>
            )}
            {r.status === "duplicate" && v.vehicle_id && <Button size="sm" variant="outline" className="h-7 border-amber-300 px-2 text-xs text-amber-800" onClick={() => onForce(r)} data-testid={`fuel-row-force-btn-${r.id}`}>Forcer</Button>}
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
