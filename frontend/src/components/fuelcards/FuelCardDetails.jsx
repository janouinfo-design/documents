import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Link2, Lock, Truck, User, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getFuelCardHistory, closeFuelCardAssignment } from "@/lib/api";
import { dateFr, dateFrLong } from "@/lib/format";
import { cn } from "@/lib/utils";
import { assignmentTypeLabel, errDetail } from "@/lib/fuelCards";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import CardAssignmentDialog from "@/components/fuelcards/CardAssignmentDialog";
import { CARD_QUERY_KEYS } from "@/components/fuelcards/FuelCardLifecycleDialogs";

// Affectations datées (courantes + historique) ; clôture explicite (aujourd'hui) auditée — l'historique n'est jamais supprimé
export function FuelCardAssignments({ card, canEdit }) {
  const qc = useQueryClient();
  const { openVehicle } = useVehicleDrawer();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const rows = card.assignments || [];
  const close = async (a) => {
    setBusy(a.id);
    try {
      await closeFuelCardAssignment(a.id, {});
      toast.success("Affectation clôturée (historique conservé)");
      CARD_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      qc.invalidateQueries({ queryKey: ["fuel-card-history", card.id] });
    } catch (e) { toast.error(errDetail(e)); } finally { setBusy(null); }
  };
  return (
    <section className="space-y-3" data-testid="fuel-card-assignments">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500"><Link2 className="h-4 w-4" /> Affectations datées ({rows.length})</h3>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setOpen(true)} data-testid="fuel-card-assign-btn">Affecter</Button>}
      </div>
      {rows.length === 0 && <p className="text-sm text-slate-400" data-testid="fuel-card-assignments-empty">Aucune affectation — carte non rattachée à un véhicule ou un conducteur.</p>}
      <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {rows.map((a) => (
          <li key={a.id} className={cn("flex flex-wrap items-center gap-3 px-3 py-2 text-sm", !a.active && "text-slate-500")} data-testid={`fuel-card-assignment-${a.id}`}>
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-bold", a.active ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500")}>
              {a.active ? "En cours" : a.replaced ? "Remplacée" : "Clôturée"}
            </span>
            <span className="inline-flex items-center gap-1 font-semibold">
              {a.type === "vehicule" ? <Truck className="h-3.5 w-3.5" /> : a.type === "conducteur" ? <User className="h-3.5 w-3.5" /> : null}
              {assignmentTypeLabel(a.type)} →{" "}
              {a.type === "vehicule" && a.vehicle_id
                ? <button type="button" className="underline-offset-2 hover:underline" onClick={() => openVehicle(a.vehicle_id)} data-testid={`fuel-card-assignment-vehicle-${a.id}`}>{a.plaque || a.vehicle_id}{a.vehicule_label ? ` · ${a.vehicule_label}` : ""}</button>
                : (a.driver_nom || a.cible)}
            </span>
            <span className="text-xs text-slate-500">
              {a.valid_from ? `du ${dateFr(a.valid_from)}` : "depuis toujours"}{a.valid_to ? ` au ${dateFr(a.valid_to)}` : " · sans fin"}
              {a.motif ? ` · ${a.motif}` : ""}{a.close_motif ? ` · clôture : ${a.close_motif}` : ""}
            </span>
            {canEdit && a.valid_to == null && (
              <Button size="sm" variant="ghost" className="ml-auto h-7 gap-1 text-xs" onClick={() => close(a)} disabled={busy === a.id} data-testid={`fuel-card-assignment-close-${a.id}`}>
                <Lock className="h-3 w-3" /> Clôturer aujourd'hui
              </Button>
            )}
          </li>
        ))}
      </ul>
      <CardAssignmentDialog card={card} open={open} onOpenChange={setOpen} />
    </section>
  );
}

const ACTION_LABELS = { create: "Création", legacy_replay: "Rejeu legacy", modify: "Modification", status: "Statut", archive: "Archivage", restore: "Restauration",
  replace: "Remplacement d'affectation", close: "Clôture d'affectation" };
const ACTION_CLS = { status: "bg-amber-100 text-amber-800", archive: "bg-slate-200 text-slate-700", restore: "bg-emerald-100 text-emerald-800",
  replace: "bg-orange-100 text-orange-800", close: "bg-slate-100 text-slate-700", create: "bg-emerald-100 text-emerald-800" };

export function FuelCardHistory({ cardId }) {
  const { data = [], isLoading } = useQuery({ queryKey: ["fuel-card-history", cardId], queryFn: () => getFuelCardHistory(cardId), enabled: !!cardId });
  return (
    <section className="space-y-3" data-testid="fuel-card-history">
      <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500"><History className="h-4 w-4" /> Historique ({data.length})</h3>
      {isLoading && <p className="text-sm text-slate-400">Chargement…</p>}
      {!isLoading && data.length === 0 && <p className="text-sm text-slate-400">Aucun événement.</p>}
      <ol className="relative space-y-3 border-l border-slate-200 pl-4">
        {data.map((h) => (
          <li key={h.id} className="relative text-sm" data-testid={`fuel-card-history-${h.action}`}>
            <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-slate-400" />
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide", ACTION_CLS[h.action] || "bg-slate-100 text-slate-600")}>
                {ACTION_LABELS[h.action] || h.action}{h.entity === "fuel_card_assignment" && h.action === "create" ? " (affectation)" : ""}
              </span>
              <span className="text-xs text-slate-500">{dateFrLong(h.created_at)} · {h.user}</span>
            </div>
            <p className="mt-0.5 text-slate-700">{h.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
