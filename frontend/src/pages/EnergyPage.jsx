import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Fuel, Droplets, Tag, Gauge, PenLine, AlertTriangle, SearchCheck } from "lucide-react";
import { getEnergy, getVehicles, getDrivers, getFuelImports } from "@/lib/api";
import { chfExact, fmtQty, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import ManualFuelDialog from "@/components/documents/ManualFuelDialog";
import EnergyTabs from "@/components/energy/EnergyTabs";
import EnergyFilters, { ALL, EMPTY_FILTERS, applyFilters } from "@/components/energy/EnergyFilters";
import Pill from "@/components/energy/Pill";
import TransactionDrawer from "@/components/energy/TransactionDrawer";
import { MATCH_META, CARD_RES_META } from "@/lib/fuelImport";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import { useAuth } from "@/context/AuthContext";

export const isDeclarative = (tx) => ["manual", "legacy_import", "import"].includes(tx?.created_from);

// Pictogramme « déclaratif » : transaction saisie sans justificatif (manuelle, importée)
export function DeclarativeMark({ tx }) {
  if (!isDeclarative(tx)) return null;
  return (
    <span data-testid={`energy-declaratif-${tx.id}`} title={tx.motif_saisie ? `Déclaratif — ${tx.motif_saisie}` : `Déclaratif (sans justificatif · ${tx.created_from})`}
      className="ml-1 inline-flex items-center gap-0.5 rounded-full border border-dashed border-amber-400 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">
      <PenLine className="h-2.5 w-2.5" /> déclaratif
    </span>
  );
}

export const energyLabel = (tx) => tx.type_carburant || (tx.energie === "electrique" ? "Électricité" : "Carburant");
export const qtyLabel = (tx) => (tx.energie === "electrique" ? fmtQty(tx.energie_kwh, "kWh", 1) : fmtQty(tx.litres, "L", 2));
export const unitPriceLabel = (tx) => {
  if (tx.energie === "electrique") return tx.prix_kwh != null ? `${Number(tx.prix_kwh).toFixed(3)} ${tx.devise}/kWh` : "—";
  return tx.prix_litre != null ? `${Number(tx.prix_litre).toFixed(3)} ${tx.devise}/L` : "—";
};
export const txDateLabel = (tx) => `${dateFr(tx.date)}${tx.heure ? ` ${tx.heure}` : ""}`;
const cardCode = (tx) => (tx.card_manual ? "manual" : tx.carte_last4 ? tx.card_resolution?.status || "none" : "none");

export default function EnergyPage() {
  const { openVehicle } = useVehicleDrawer();
  const { user } = useAuth();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState(EMPTY_FILTERS);
  const [fuelOpen, setFuelOpen] = useState(false);
  const txId = params.get("tx");
  const setTx = (id) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("tx", id); else n.delete("tx"); return n; }, { replace: true });

  const { data, isLoading, isError, error } = useQuery({ queryKey: ["energy"], queryFn: () => getEnergy() });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const { data: drivers = [] } = useQuery({ queryKey: ["drivers", "picker"], queryFn: () => getDrivers({ include_archived: "1" }) });
  const { data: imports } = useQuery({ queryKey: ["fuel-imports"], queryFn: getFuelImports });

  const totals = data?.totals || {};
  const allTx = useMemo(() => data?.transactions || [], [data]);
  const txs = useMemo(() => applyFilters(allTx, f), [allTx, f]);
  const providers = useMemo(() => [...new Set(allTx.map((t) => t.fournisseur).filter(Boolean))].sort(), [allTx]);
  const cards = useMemo(() => [...new Map(allTx.filter((t) => t.card_id).map((t) => [t.card_id, `${t.fournisseur || "Carte"} ••••${t.carte_last4 || "????"}`])).entries()], [allTx]);
  const jobs = useMemo(() => (imports?.items || []).filter((j) => allTx.some((t) => t.import_job_id === j.id)), [imports, allTx]);
  const shown = f.vehicle === ALL ? totals : ((data?.by_vehicle || []).find((b) => b.vehicle_id === f.vehicle) || {});
  const prixMoyen = shown.prix_moyen_l != null ? `${Number(shown.prix_moyen_l).toFixed(3)} CHF/L` : shown.prix_moyen_kwh != null ? `${Number(shown.prix_moyen_kwh).toFixed(3)} CHF/kWh` : "—";
  const conso = f.vehicle === ALL
    ? (totals.conso_reelle_l_100km != null ? `${totals.conso_reelle_l_100km} L/100 km` : "—")
    : (shown.conso_tickets ? `${shown.conso_tickets.value} L/100 km` : shown.conso_kwh_tickets ? `${shown.conso_kwh_tickets.value} kWh/100 km` : "—");

  return (
    <div className="space-y-6 animate-fade-in" data-testid="energy-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Énergie & carburant</h2>
          <p className="mt-1 text-sm text-slate-500">Transactions dérivées des tickets validés, saisies ou importées dans Documents. Le montant est déjà compté dans Coûts (jamais deux fois).</p>
        </div>
        {isAdmin && (
          <Button data-testid="energy-manual-fuel-btn" size="sm" variant="outline" onClick={() => setFuelOpen(true)} className="gap-1.5 border-amber-300 text-amber-800 hover:bg-amber-50">
            <PenLine className="h-4 w-4" /> Plein sans justificatif
          </Button>
        )}
      </div>
      {isError && <QueryErrorState error={error} testId="energy-error" />}
      <EnergyTabs />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <KpiCard testId="energy-kpi-depenses" label="Dépenses" value={isLoading ? "—" : chfExact(shown.depenses || 0)} accent="slate" icon={Fuel} sub={`${shown.transactions || 0} transaction(s)`} />
        <KpiCard testId="energy-kpi-volume" label="Volume" value={isLoading ? "—" : (shown.litres ? fmtQty(shown.litres, "L", 1) : shown.energie_kwh ? fmtQty(shown.energie_kwh, "kWh", 1) : "—")} accent="sky" icon={Droplets} sub={shown.energie_kwh && shown.litres ? `+ ${fmtQty(shown.energie_kwh, "kWh", 1)}` : "Litres ou kWh"} />
        <KpiCard testId="energy-kpi-prix" label="Prix moyen" value={isLoading ? "—" : prixMoyen} accent="indigo" icon={Tag} sub="Dépenses / quantité" />
        <KpiCard testId="energy-kpi-conso" label="Conso réelle" value={isLoading ? "—" : conso} accent="emerald" icon={Gauge} sub={f.vehicle === ALL ? `${totals.vehicules_avec_conso || 0} véhicule(s) mesuré(s)` : (shown.conso_tickets ? `${shown.conso_tickets.n} pleins · ${shown.conso_tickets.km} km` : "Données insuffisantes")} />
        <KpiCard testId="energy-kpi-a-verifier" label="À vérifier" value={isLoading ? "—" : totals.a_verifier ?? 0} accent="amber" icon={SearchCheck} sub="Rattachement ou carte ambigus" onClick={() => setF((s) => ({ ...EMPTY_FILTERS, match: s.match === "matched_review" ? ALL : "matched_review" }))} active={f.match === "matched_review"} />
        <KpiCard testId="energy-kpi-anomalies" label="Anomalies ouvertes" value={isLoading ? "—" : totals.anomalies_ouvertes ?? 0} accent="red" icon={AlertTriangle} sub="Sur les transactions" onClick={() => setF((s) => ({ ...EMPTY_FILTERS, anomaly: s.anomaly === "open" ? ALL : "open" }))} active={f.anomaly === "open"} />
      </div>
      <EnergyFilters f={f} set={setF} vehicles={vehicles} drivers={drivers} providers={providers} cards={cards} jobs={jobs} count={txs.length} />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="energy-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Date</TableHead><TableHead>Véhicule</TableHead><TableHead>Fournisseur / station</TableHead><TableHead>Carte</TableHead><TableHead>Conducteur</TableHead>
              <TableHead>Énergie</TableHead><TableHead>Quantité</TableHead><TableHead>Prix unité</TableHead><TableHead className="text-right">Montant</TableHead><TableHead>Rattachement</TableHead><TableHead>Anomalies</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && txs.length === 0 && (
              <TableRow><TableCell colSpan={11}><p className="py-10 text-center text-sm text-slate-400" data-testid="energy-empty">Aucune transaction — validez un ticket, saisissez un plein ou importez un relevé fournisseur.</p></TableCell></TableRow>
            )}
            {txs.map((tx) => (
              <TableRow key={tx.id} data-testid={`energy-row-${tx.id}`} onClick={() => setTx(tx.id)} className="cursor-pointer hover:bg-slate-50">
                <TableCell className="whitespace-nowrap text-sm text-slate-700">{txDateLabel(tx)}</TableCell>
                <TableCell>
                  <button onClick={(e) => { e.stopPropagation(); openVehicle(tx.vehicle_id, "energie"); }} className="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline" data-testid={`energy-vehicle-${tx.id}`}>{tx.plaque || "—"}</button>
                </TableCell>
                <TableCell className="text-sm text-slate-700">
                  {tx.fournisseur && <span className="font-semibold">{tx.fournisseur} · </span>}{tx.station || "—"}
                  <DeclarativeMark tx={tx} />
                  {tx.kilometrage ? <span className="ml-1 text-[11px] text-slate-400">· {tx.kilometrage} km</span> : null}
                </TableCell>
                <TableCell data-testid={`fuel-transaction-card-${tx.id}`}>
                  {tx.carte_last4 ? <p className="font-mono text-xs text-slate-600">••••{tx.carte_last4}</p> : <p className="text-xs text-slate-300">—</p>}
                  {tx.carte_last4 && <Pill map={CARD_RES_META} code={cardCode(tx)} />}
                </TableCell>
                <TableCell className="text-sm text-slate-600" data-testid={`energy-driver-${tx.id}`}>{tx.driver_nom || <span className="text-slate-300">—</span>}</TableCell>
                <TableCell><span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", tx.energie === "electrique" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-700")}>{energyLabel(tx)}</span></TableCell>
                <TableCell className="text-sm text-slate-600">{qtyLabel(tx)}</TableCell>
                <TableCell className="text-sm text-slate-600">{unitPriceLabel(tx)}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900">
                  {tx.montant != null ? chfExact(tx.montant, tx.devise) : "—"}
                  {tx.devise && tx.devise !== "CHF" && <p className={`text-[10px] font-semibold ${tx.montant_chf != null ? "text-emerald-700" : "text-amber-700"}`}>{tx.montant_chf != null ? `= ${chfExact(tx.montant_chf)}` : "FX en attente"}</p>}
                </TableCell>
                <TableCell data-testid={`fuel-transaction-match-${tx.id}`}>
                  {tx.match_status ? <Pill map={MATCH_META} code={tx.match_status} /> : <span className="text-xs text-slate-400">document</span>}
                  {tx.match_score != null && <p className="text-[10px] text-slate-400">{tx.match_score} pt{tx.match_method ? ` · ${tx.match_method}` : ""}</p>}
                </TableCell>
                <TableCell data-testid={`fuel-transaction-anomalies-${tx.id}`}>
                  {tx.anomalies_open > 0 ? <span className="inline-flex items-center gap-1 rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-bold text-white"><AlertTriangle className="h-3 w-3" /> {tx.anomalies_open}</span> : <span className="text-xs text-slate-300">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ManualFuelDialog open={fuelOpen} onOpenChange={setFuelOpen} />
      <TransactionDrawer txId={txId} onOpenChange={(o) => { if (!o) setTx(null); }} />
    </div>
  );
}
