import { useQuery } from "@tanstack/react-query";
import { Fuel, Droplets, Tag, Gauge, Clock, Loader2 } from "lucide-react";
import { getVehicleEnergy } from "@/lib/api";
import { chfExact, fmtQty, dateFr } from "@/lib/format";
import { SectionCard, Stat } from "@/components/Field";
import QueryErrorState from "@/components/QueryErrorState";
import { energyLabel, qtyLabel, unitPriceLabel, txDateLabel, DeclarativeMark } from "@/pages/EnergyPage";

const SOURCE_FR = { can: "Mesure CAN embarquée", fuel_transactions: "Tickets carburant", manual: "Saisie manuelle" };

export default function EnergyTab({ vehicle }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["vehicle-energy", vehicle.id],
    queryFn: () => getVehicleEnergy(vehicle.id),
  });
  const t = data?.totals || {};
  const txs = (data?.transactions || []).slice(0, 10);

  if (isError) return <QueryErrorState error={error} testId="vehicle-energy-error" />;

  const prix = t.prix_moyen_l != null ? `${Number(t.prix_moyen_l).toFixed(3)} CHF/L`
    : t.prix_moyen_kwh != null ? `${Number(t.prix_moyen_kwh).toFixed(3)} CHF/kWh` : "—";
  const volume = t.litres ? fmtQty(t.litres, "L", 1) : t.energie_kwh ? fmtQty(t.energie_kwh, "kWh", 1) : "—";
  const consoFiche = data?.conso_reelle_l_100km
    ? `${data.conso_reelle_l_100km} L/100 km · ${SOURCE_FR[data.conso_reelle_source] || data.conso_reelle_source}`
    : null;
  const consoTickets = data?.conso_tickets ? `${data.conso_tickets.value} L/100 km (${data.conso_tickets.n} pleins · ${data.conso_tickets.km} km)`
    : data?.conso_kwh_tickets ? `${data.conso_kwh_tickets.value} kWh/100 km (${data.conso_kwh_tickets.n} recharges · ${data.conso_kwh_tickets.km} km)`
    : "Données insuffisantes (≥ 2 pleins avec km)";

  return (
    <div className="space-y-4" data-testid="energy-tab">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label="Dépenses énergie" value={chfExact(t.depenses || 0)} icon={Fuel} />
        <Stat label="Volume" value={volume} icon={Droplets} />
        <Stat label="Prix moyen" value={prix} icon={Tag} />
        <Stat label="Dernière transaction" value={t.derniere ? dateFr(t.derniere) : "—"} icon={Clock} />
        <div className="col-span-2 rounded-xl border border-slate-200 bg-white p-4" data-testid="vehicle-energy-conso">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
            <Gauge className="h-3.5 w-3.5" /> Consommation réelle
          </div>
          <p className="mt-1.5 font-medium text-slate-900">{consoFiche || "Non mesurée"}</p>
          <p className="mt-0.5 text-xs text-slate-500">Par tickets : {consoTickets}</p>
          {data?.conso_reelle_source === "can" && data?.conso_tickets && (
            <p className="mt-0.5 text-[11px] text-slate-400">La mesure CAN embarquée reste prioritaire sur l'estimation par tickets.</p>
          )}
        </div>
      </div>

      <SectionCard title="Historique récent" description="Transactions issues des tickets validés — le montant est déjà compté dans l'onglet Coûts." testId="vehicle-energy-list">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </div>
        )}
        {!isLoading && txs.length === 0 && (
          <p className="py-6 text-center text-sm text-slate-400" data-testid="vehicle-energy-empty">
            Aucune transaction — scannez un ticket carburant ou de recharge dans l'onglet Documents.
          </p>
        )}
        <div className="divide-y divide-slate-100">
          {txs.map((tx) => (
            <div key={tx.id} className="flex items-center justify-between gap-3 py-3" data-testid={`vehicle-energy-${tx.id}`}>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-800">{tx.station || "Station inconnue"}<DeclarativeMark tx={tx} /></p>
                <p className="text-xs text-slate-400">
                  {txDateLabel(tx)} · {energyLabel(tx)} · {qtyLabel(tx)} · {unitPriceLabel(tx)}
                  {tx.kilometrage ? ` · ${tx.kilometrage} km` : ""}
                  {tx.driver_nom ? <span data-testid={`vehicle-energy-driver-${tx.id}`}> · {tx.driver_nom}</span> : ""}
                </p>
              </div>
              <p className="text-sm font-semibold text-slate-900">{tx.montant != null ? chfExact(tx.montant, tx.devise) : "—"}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
