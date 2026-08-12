import { useEffect, useState } from "react";
import { Loader2, Fuel, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { getConsumptionRanking } from "@/lib/api";

const DeltaBadge = ({ item }) => {
  if (item.ecart_l == null)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
        <Minus className="h-3 w-3" /> {item.basis === "reelle" ? "officielle inconnue" : "réelle inconnue"}
      </span>
    );
  if (item.ecart_l > 0)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-700">
        <TrendingUp className="h-3 w-3" /> +{item.ecart_l} L{item.ecart_pct != null ? ` · +${item.ecart_pct} %` : ""}
      </span>
    );
  if (item.ecart_l < 0)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
        <TrendingDown className="h-3 w-3" /> {item.ecart_l} L{item.ecart_pct != null ? ` · ${item.ecart_pct} %` : ""}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
      <Minus className="h-3 w-3" /> conforme
    </span>
  );
};

const Bar = ({ label, value, norme, max, color }) => (
  <div className="flex items-center gap-2">
    <span className="w-16 shrink-0 text-[11px] text-slate-400">{label}</span>
    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
      {value != null && (
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.max((value / max) * 100, 3)}%` }} />
      )}
    </div>
    <span className="w-32 shrink-0 text-right text-[11px] tabular-nums text-slate-600">
      {value != null ? `${value} L/100 km${norme ? ` · ${norme}` : ""}` : "—"}
    </span>
  </div>
);

export default function FleetConsumptionDialog({ open, onOpenChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getConsumptionRanking()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [open]);

  const items = data?.classement || [];
  const max = Math.max(1, ...items.flatMap((x) => [x.conso_officielle || 0, x.conso_reelle || 0]));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="fleet-conso-dialog" className="max-h-[92vh] w-[calc(100vw-1rem)] max-w-2xl overflow-y-auto rounded-xl sm:w-full">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <Fuel className="h-5 w-5 text-slate-500" /> Comparateur de consommation
          </DialogTitle>
          <DialogDescription>
            Du plus sobre au plus gourmand — consommation réelle mesurée face à la valeur officielle d'homologation.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex justify-center py-10"><Loader2 className="h-7 w-7 animate-spin text-slate-400" /></div>
        )}

        {data && !loading && (
          <div className="space-y-4">
            {items.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-500" data-testid="conso-empty">
                Aucun véhicule avec une consommation renseignée pour l'instant.
              </p>
            ) : (
              <div className="space-y-2">
                {items.map((it) => (
                  <div
                    key={it.vehicle_id}
                    data-testid={`conso-row-${(it.plaque || it.vehicle_id).replace(/\s/g, "")}`}
                    className="rounded-xl border border-slate-200 bg-white p-3"
                  >
                    <div className="mb-2 flex items-center gap-3">
                      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${it.rang === 1 ? "bg-emerald-100 text-emerald-700" : it.rang === items.length && items.length > 1 ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"}`}>
                        {it.rang}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        <span className="text-sm font-semibold text-slate-900">{it.plaque}</span>
                        <span className="ml-2 text-xs text-slate-500">{[it.marque, it.modele].filter(Boolean).join(" ")}</span>
                        {it.type_carburant && <span className="ml-2 text-[11px] text-slate-400">{it.type_carburant}</span>}
                      </span>
                      <DeltaBadge item={it} />
                    </div>
                    <div className="space-y-1">
                      <Bar label="Officielle" value={it.conso_officielle} norme={it.conso_officielle_norme} max={max} color="bg-slate-400" />
                      <Bar label="Réelle" value={it.conso_reelle} max={max} color={it.ecart_l != null && it.ecart_l > 0 ? "bg-red-400" : "bg-emerald-500"} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {(data.sans_donnees || []).length > 0 && (
              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-3" data-testid="conso-missing-list">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Sans données de consommation ({data.sans_donnees.length})
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {data.sans_donnees.map((v) => (
                    <span key={v.vehicle_id} className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200">
                      {v.plaque}
                    </span>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-slate-400">
                  Renseignez la conso officielle via « Base technique » (ASTRA) ou la conso réelle dans la fiche véhicule.
                </p>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
