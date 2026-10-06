import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Fuel, Droplets, Tag, Gauge } from "lucide-react";
import { getEnergy, getVehicles } from "@/lib/api";
import { chfExact, fmtQty, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const ALL = "__all__";

export const energyLabel = (tx) =>
  tx.type_carburant || (tx.energie === "electrique" ? "Électricité" : "Carburant");

export const qtyLabel = (tx) =>
  tx.energie === "electrique" ? fmtQty(tx.energie_kwh, "kWh", 1) : fmtQty(tx.litres, "L", 2);

export const unitPriceLabel = (tx) => {
  if (tx.energie === "electrique") return tx.prix_kwh != null ? `${Number(tx.prix_kwh).toFixed(3)} ${tx.devise}/kWh` : "—";
  return tx.prix_litre != null ? `${Number(tx.prix_litre).toFixed(3)} ${tx.devise}/L` : "—";
};

export const txDateLabel = (tx) => `${dateFr(tx.date)}${tx.heure ? ` ${tx.heure}` : ""}`;

export default function EnergyPage() {
  const { openVehicle } = useVehicleDrawer();
  const [vehicle, setVehicle] = useState(ALL);

  const { data, isLoading, isError, error } = useQuery({ queryKey: ["energy"], queryFn: () => getEnergy() });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });

  const totals = data?.totals || {};
  const txs = useMemo(() => (data?.transactions || []).filter((t) => vehicle === ALL || t.vehicle_id === vehicle), [data, vehicle]);
  const shown = vehicle === ALL ? totals : ((data?.by_vehicle || []).find((b) => b.vehicle_id === vehicle) || {});

  const prixMoyen = shown.prix_moyen_l != null
    ? `${Number(shown.prix_moyen_l).toFixed(3)} CHF/L`
    : shown.prix_moyen_kwh != null ? `${Number(shown.prix_moyen_kwh).toFixed(3)} CHF/kWh` : "—";
  const conso = vehicle === ALL
    ? (totals.conso_reelle_l_100km != null ? `${totals.conso_reelle_l_100km} L/100 km` : "—")
    : (shown.conso_tickets ? `${shown.conso_tickets.value} L/100 km` : shown.conso_kwh_tickets ? `${shown.conso_kwh_tickets.value} kWh/100 km` : "—");
  const consoSub = vehicle === ALL
    ? (totals.vehicules_avec_conso ? `${totals.vehicules_avec_conso} véhicule(s) mesuré(s) par tickets` : "Données insuffisantes (≥ 2 pleins avec km)")
    : (shown.conso_tickets ? `${shown.conso_tickets.n} pleins · ${shown.conso_tickets.km} km` : "Données insuffisantes (≥ 2 pleins avec km)");

  return (
    <div className="space-y-6 animate-fade-in" data-testid="energy-page">
      <div>
        <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Énergie & carburant</h2>
        <p className="mt-1 text-sm text-slate-500">
          Transactions dérivées des tickets validés dans Documents. Le montant est déjà compté dans Coûts (jamais deux fois).
        </p>
      </div>

      {isError && <QueryErrorState error={error} testId="energy-error" />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard testId="energy-kpi-depenses" label="Dépenses" value={isLoading ? "—" : chfExact(shown.depenses || 0)} accent="slate" icon={Fuel} sub={`${shown.transactions || 0} transaction(s)`} />
        <KpiCard testId="energy-kpi-volume" label="Volume" value={isLoading ? "—" : (shown.litres ? fmtQty(shown.litres, "L", 1) : shown.energie_kwh ? fmtQty(shown.energie_kwh, "kWh", 1) : "—")} accent="sky" icon={Droplets} sub={shown.energie_kwh && shown.litres ? `+ ${fmtQty(shown.energie_kwh, "kWh", 1)}` : "Litres ou kWh"} />
        <KpiCard testId="energy-kpi-prix" label="Prix moyen" value={isLoading ? "—" : prixMoyen} accent="indigo" icon={Tag} sub="Dépenses / quantité" />
        <KpiCard testId="energy-kpi-conso" label="Conso réelle" value={isLoading ? "—" : conso} accent="emerald" icon={Gauge} sub={consoSub} />
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2">
        <Select value={vehicle} onValueChange={setVehicle}>
          <SelectTrigger data-testid="energy-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les véhicules</SelectItem>
            {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}
          </SelectContent>
        </Select>
        <p className="self-center text-xs text-slate-400">
          Priorité des sources de consommation : mesure CAN embarquée &gt; tickets &gt; saisie manuelle.
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="energy-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Date</TableHead>
              <TableHead>Véhicule</TableHead>
              <TableHead>Station</TableHead>
              <TableHead>Énergie</TableHead>
              <TableHead>Quantité</TableHead>
              <TableHead>Prix unité</TableHead>
              <TableHead className="text-right">Montant</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && txs.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <p className="py-10 text-center text-sm text-slate-400" data-testid="energy-empty">
                    Aucune transaction — validez un ticket carburant ou de recharge depuis Documents.
                  </p>
                </TableCell>
              </TableRow>
            )}
            {txs.map((tx) => (
              <TableRow key={tx.id} data-testid={`energy-row-${tx.id}`} className="hover:bg-slate-50">
                <TableCell className="whitespace-nowrap text-sm text-slate-700">{txDateLabel(tx)}</TableCell>
                <TableCell>
                  <button onClick={() => openVehicle(tx.vehicle_id, "energie")}
                          className="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline"
                          data-testid={`energy-vehicle-${tx.id}`}>
                    {tx.plaque || "—"}
                  </button>
                </TableCell>
                <TableCell className="text-sm text-slate-700">
                  {tx.station || "—"}
                  {tx.carte_last4 && <span className="ml-1 text-[11px] text-slate-400">· carte ****{tx.carte_last4}</span>}
                  {tx.kilometrage && <span className="ml-1 text-[11px] text-slate-400">· {tx.kilometrage} km</span>}
                </TableCell>
                <TableCell>
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold",
                    tx.energie === "electrique" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-700")}>
                    {energyLabel(tx)}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-slate-600">{qtyLabel(tx)}</TableCell>
                <TableCell className="text-sm text-slate-600">{unitPriceLabel(tx)}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900">
                  {tx.montant != null ? chfExact(tx.montant, tx.devise) : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
