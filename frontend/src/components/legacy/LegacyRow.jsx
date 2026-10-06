import { useState } from "react";
import { toast } from "sonner";
import { Check, Ban, AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { legacyVehicleConfirm, legacyVehicleReject } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLE = {
  pending: "bg-amber-50 text-amber-700 border-amber-200",
  confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected: "bg-slate-100 text-slate-600 border-slate-300",
};
const STATUS_LABEL = { pending: "En attente", confirmed: "Confirmée", rejected: "Rejetée" };
const SUGGESTION_LABEL = {
  strong_candidate: "Candidat fort", candidate_warning: "Tracker — à vérifier", manual_review: "Plaque — revue manuelle",
  ambiguous: "Ambigu", not_found: "Aucun candidat", direct: "Saisie directe",
};
const METHOD_LABEL = { vin: "VIN", navixy_vehicle_id: "ID télématique", tracker_history_confirmed: "tracker (confirmé)", manual: "manuel" };

export default function LegacyRow({ row, vehicles, canWrite, onChanged, onConflict }) {
  const lid = row.legacy_vehicle_id;
  const [choice, setChoice] = useState(row.candidates?.[0]?.vehicle_id || "");
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const legacy = row.legacy || {};
  const suggestion = row.suggestion || {};

  const act = async (fn) => {
    setBusy(true);
    try {
      await fn();
      onChanged?.();
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d?.conflicts) onConflict?.({ row, vehicleId: choice, note, conflicts: d.conflicts });
      else toast.error(String(d?.message || d || "Échec"));
    } finally {
      setBusy(false);
    }
  };

  const confirm = () => act(async () => {
    await legacyVehicleConfirm(lid, { vehicle_id: choice, note: note || undefined }, row.legacy_source);
    toast.success("Correspondance confirmée");
  });
  const reject = () => {
    if (!reason.trim()) return toast.warning("Motif de rejet obligatoire");
    act(async () => {
      await legacyVehicleReject(lid, reason.trim(), row.legacy_source);
      toast.success("Correspondance rejetée (quarantaine)");
    });
  };

  return (
    <tr className="border-t border-slate-100 align-top text-sm" data-testid={`legacy-row-${lid}`}>
      <td className="px-3 py-3">
        <p className="font-mono text-[11px] text-slate-500" title={lid}>{lid.slice(0, 8)}…</p>
        <p className="font-semibold text-slate-900">{legacy.plate || "—"}</p>
        <p className="text-xs text-slate-500">{legacy.model || ""}{legacy.vin ? ` · VIN ${legacy.vin}` : ""}{legacy.navixy_tracker_id ? ` · tracker ${legacy.navixy_tracker_id}` : ""}</p>
      </td>
      <td className="px-3 py-3">
        <span className={cn("inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold", STATUS_STYLE[row.status])} data-testid={`legacy-status-badge-${lid}`}>
          {STATUS_LABEL[row.status] || row.status}
        </span>
        <p className="mt-1 text-xs text-slate-500">{SUGGESTION_LABEL[suggestion.status] || suggestion.status}</p>
        {(suggestion.warnings || []).includes("tracker_join_no_assignment_history") && (
          <p className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-amber-700" data-testid={`legacy-warning-tracker-${lid}`}>
            <AlertTriangle className="h-3 w-3" /> tracker = affectation évolutive, pas une identité
          </p>
        )}
      </td>
      <td className="px-3 py-3">
        {row.status === "confirmed" ? (
          <p className="text-slate-800" data-testid={`legacy-confirmed-vehicle-${lid}`}>
            <span className="font-semibold">{row.vehicle?.plate || row.vehicle_id}</span>
            <span className="text-xs text-slate-500"> · via {METHOD_LABEL[row.method] || row.method} · {row.confirmed_by}</span>
          </p>
        ) : row.status === "rejected" ? (
          <p className="text-xs text-slate-500" data-testid={`legacy-reject-info-${lid}`}>Motif : {row.reject_reason} · {row.rejected_by}</p>
        ) : (
          <div className="space-y-2">
            {(row.candidates || []).map((c) => (
              <label key={c.vehicle_id} className="flex cursor-pointer items-center gap-2 text-sm">
                <input type="radio" name={`cand-${lid}`} value={c.vehicle_id} checked={choice === c.vehicle_id}
                  onChange={() => setChoice(c.vehicle_id)} disabled={!canWrite} data-testid={`legacy-candidate-${lid}-${c.vehicle_id}`} />
                <span className="font-semibold">{c.plate || c.vehicle_id}</span>
                <span className="text-xs text-slate-500">{[c.make, c.model].filter(Boolean).join(" ")} · par {c.matched_by === "plate" ? "plaque (à confirmer)" : c.matched_by}</span>
              </label>
            ))}
            <select data-testid={`legacy-manual-select-${lid}`} value={choice} disabled={!canWrite}
              onChange={(e) => setChoice(e.target.value)}
              className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs">
              <option value="">— choisir un véhicule Documents manuellement —</option>
              {vehicles.map((v) => <option key={v.id} value={v.id}>{v.plaque} · {[v.marque, v.modele].filter(Boolean).join(" ")}</option>)}
            </select>
          </div>
        )}
      </td>
      <td className="px-3 py-3">
        {row.status === "pending" && (
          <div className="flex flex-col gap-2">
            <Input data-testid={`legacy-note-${lid}`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (optionnel)" className="h-8 text-xs" disabled={!canWrite} />
            <Button size="sm" data-testid={`legacy-confirm-${lid}`} disabled={!canWrite || !choice || busy} onClick={confirm} className="gap-1 bg-slate-900 hover:bg-slate-800">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Confirmer
            </Button>
            <div className="flex gap-1">
              <Input data-testid={`legacy-reject-reason-${lid}`} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motif de rejet" className="h-8 text-xs" disabled={!canWrite} />
              <Button size="sm" variant="outline" data-testid={`legacy-reject-${lid}`} disabled={!canWrite || busy} onClick={reject} className="gap-1 text-slate-600">
                <Ban className="h-3.5 w-3.5" /> Rejeter
              </Button>
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}
