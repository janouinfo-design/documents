import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Scale, ShieldAlert, Info, CheckCircle2, Settings2 } from "lucide-react";
import { getFuelReconciliations, getReconciliationSettings, getVehicles } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import EnergyTabs from "@/components/energy/EnergyTabs";
import Pill from "@/components/energy/Pill";
import ExportButtons from "@/components/energy/ExportButtons";
import ReconciliationDrawer from "@/components/energy/ReconciliationDrawer";
import { ThresholdsDialog } from "@/components/energy/ReconciliationDialogs";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { RECO_STATUS_META, CONSO_SOURCE_META, BLOCKER_META, na, signed, periodLabel, periodOptions, currentPeriod } from "@/lib/fuelStatements";

const ALL = "__all__";

// Énergie › Rapprochements : par véhicule / mois — achats (Documents) vs consommation réelle CAN, référence ASTRA, écart, statut (INDICATIF sans seuil), justification
export default function FuelReconciliationsPage() {
  const { user } = useAuth();
  const isAdmin = can(user, "settings");
  const [params, setParams] = useSearchParams();
  const period = params.get("period") || currentPeriod();
  const [vehicle, setVehicle] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [justified, setJustified] = useState(ALL);
  const [provider, setProvider] = useState(ALL);
  const [thresholds, setThresholds] = useState(false);
  const openVid = params.get("v");
  const setParam = (k, v) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });
  const query = useMemo(() => ({ period_month: period, ...(vehicle !== ALL ? { vehicle_id: vehicle } : {}), ...(status !== ALL ? { status } : {}), ...(justified !== ALL ? { justified } : {}) }), [period, vehicle, status, justified]);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fuel-reconciliations", query], queryFn: () => getFuelReconciliations(query), keepPreviousData: true });
  const { data: settings } = useQuery({ queryKey: ["fuel-reconciliation-settings"], queryFn: getReconciliationSettings, enabled: can(user, "settings.read") });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const all = useMemo(() => data?.items || [], [data]);
  const providers = useMemo(() => [...new Set(all.flatMap((r) => Object.keys(r.achats?.by_fournisseur || {})))].filter((p) => p !== "—").sort(), [all]);
  const items = useMemo(() => all.filter((r) => provider === ALL || Object.keys(r.achats?.by_fournisseur || {}).includes(provider)), [all, provider]);
  const stats = data?.stats || {};
  const conf = settings?.reconciliation || {};
  const configured = conf.threshold_pct != null || conf.threshold_l != null;
  const selected = all.find((r) => r.vehicle_id === openVid) || null;
  const reset = () => { setVehicle(ALL); setStatus(ALL); setJustified(ALL); setProvider(ALL); };
  return (
    <div className="space-y-6 animate-fade-in" data-testid="fuel-reconciliations-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Rapprochements achats / consommation</h2>
          <p className="mt-1 text-sm text-slate-500">Priorité : CAN mesuré = consommation réelle · tickets et relevés = achats (jamais une consommation) · ASTRA = référence comparative. Sans seuil configuré, tout rapprochement reste <b>INDICATIF</b>.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setThresholds(true)} className="gap-1.5" data-testid="fuel-reconciliation-thresholds-btn"><Settings2 className="h-4 w-4" /> Seuils</Button>}
          <ExportButtons path="/fuel/reconciliations/export" params={query} testIdPrefix="fuel-reconciliations" />
        </div>
      </div>
      <EnergyTabs />
      {isError && <QueryErrorState error={error} testId="fuel-reconciliations-error" />}
      <div className={`rounded-xl border px-4 py-2 text-sm ${configured ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-sky-200 bg-sky-50 text-sky-900"}`} data-testid="fuel-reconciliation-thresholds-banner">
        {configured ? <>Seuils configurés : {na(conf.threshold_pct, " %")} · {na(conf.threshold_l, " L")} — {settings?.rule?.label}</> : <>Aucun seuil configuré (threshold_pct / threshold_l = null) : les écarts bruts sont affichés et le statut reste <b>INDICATIF</b>, jamais « Cohérent » ni « À contrôler ».</>}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="fuel-reconciliations-kpis">
        <KpiCard testId="fuel-reconciliations-kpi-total" label="Véhicules rapprochés" value={isLoading ? "—" : items.length} icon={Scale} accent="slate" sub={periodLabel(period)} onClick={reset} />
        <KpiCard testId="fuel-reconciliations-kpi-controler" label="À contrôler" value={isLoading ? "—" : stats.by_status?.A_CONTROLER ?? 0} icon={ShieldAlert} accent="rose" sub="Au-delà des seuils" onClick={() => setStatus("A_CONTROLER")} active={status === "A_CONTROLER"} />
        <KpiCard testId="fuel-reconciliations-kpi-indicatif" label="Indicatifs" value={isLoading ? "—" : stats.by_status?.INDICATIF ?? 0} icon={Info} accent="sky" sub="Sans seuil ou sans CAN" onClick={() => setStatus("INDICATIF")} active={status === "INDICATIF"} />
        <KpiCard testId="fuel-reconciliations-kpi-justifies" label="Justifiés" value={isLoading ? "—" : stats.justified ?? 0} icon={CheckCircle2} accent="emerald" sub="Écart expliqué" onClick={() => setJustified("true")} active={justified === "true"} />
      </div>
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3 lg:grid-cols-5" data-testid="fuel-reconciliations-filters">
        <Select value={period} onValueChange={(v) => setParam("period", v)}><SelectTrigger data-testid="fuel-reconciliation-filter-period"><SelectValue /></SelectTrigger>
          <SelectContent>{periodOptions().map((p) => <SelectItem key={p} value={p}>{periodLabel(p)}</SelectItem>)}</SelectContent></Select>
        <Select value={vehicle} onValueChange={setVehicle}><SelectTrigger data-testid="fuel-reconciliation-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les véhicules</SelectItem>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}</SelectContent></Select>
        <Select value={provider} onValueChange={setProvider}><SelectTrigger data-testid="fuel-reconciliation-filter-provider"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les fournisseurs</SelectItem>{providers.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select>
        <Select value={status} onValueChange={setStatus}><SelectTrigger data-testid="fuel-reconciliation-filter-status"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les statuts</SelectItem>{Object.entries(RECO_STATUS_META).filter(([k]) => k !== "IMPOSSIBLE").map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
        <Select value={justified} onValueChange={setJustified}><SelectTrigger data-testid="fuel-reconciliation-filter-justified"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Justification : toutes</SelectItem><SelectItem value="true">Avec justification</SelectItem><SelectItem value="false">Sans justification</SelectItem></SelectContent></Select>
        <div className="col-span-2 flex items-center justify-between sm:col-span-3 lg:col-span-5">
          <p className="text-xs text-slate-500" data-testid="fuel-reconciliations-count">{isLoading ? "…" : `${items.length} rapprochement(s) · ${stats.with_blockers ?? 0} avec blockers`}</p>
          <Button variant="ghost" size="sm" onClick={reset} data-testid="fuel-reconciliations-filters-reset">Réinitialiser</Button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="fuel-reconciliations-table">
          <TableHeader><TableRow className="bg-slate-50">
            <TableHead>Véhicule</TableHead><TableHead>Période</TableHead><TableHead className="text-right">Litres achetés</TableHead><TableHead className="text-right">Conso CAN</TableHead><TableHead className="text-right">Réf. ASTRA</TableHead>
            <TableHead className="text-right">Δ L</TableHead><TableHead className="text-right">Δ %</TableHead><TableHead>Source conso</TableHead><TableHead>Statut</TableHead><TableHead>Justification</TableHead><TableHead>Blockers</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && <TableRow><TableCell colSpan={11}><p className="py-10 text-center text-sm text-slate-400" data-testid="fuel-reconciliations-empty">Aucun achat ni mesure CAN sur {periodLabel(period)}.</p></TableCell></TableRow>}
            {items.map((r) => (
              <TableRow key={r.vehicle_id} data-testid={`fuel-reconciliation-row-${r.vehicle_id}`} onClick={() => setParam("v", r.vehicle_id)} className="cursor-pointer hover:bg-slate-50">
                <TableCell className="text-sm font-semibold text-slate-800">{r.plaque || r.vehicle_id}<p className="text-[11px] font-normal text-slate-400">{r.vehicule_label}</p></TableCell>
                <TableCell className="whitespace-nowrap text-sm text-slate-600">{r.period_month}</TableCell>
                <TableCell className="text-right text-sm text-slate-800" data-testid={`fuel-reconciliation-purchased-${r.vehicle_id}`}>{na(r.achats.litres, " L")}<p className="text-[11px] text-slate-400">{r.achats.n_tx} tx · {na(r.achats.chf, " CHF")}</p></TableCell>
                <TableCell className="text-right text-sm text-slate-800" data-testid={`fuel-reconciliation-can-${r.vehicle_id}`}>{na(r.consommation.litres, " L")}<p className="text-[11px] text-slate-400">{r.consommation.l_100km != null ? `${r.consommation.l_100km} L/100` : "—"}{r.consommation.km ? ` · ${r.consommation.km} km` : ""}</p></TableCell>
                <TableCell className="text-right text-sm text-slate-600" data-testid={`fuel-reconciliation-astra-${r.vehicle_id}`}>{na(r.astra.conso_officielle_l_100km, " L/100", 1)}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900" data-testid={`fuel-reconciliation-delta-l-${r.vehicle_id}`}>{signed(r.ecart_l, " L")}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900" data-testid={`fuel-reconciliation-delta-pct-${r.vehicle_id}`}>{signed(r.ecart_pct, " %", 1)}</TableCell>
                <TableCell><Pill map={CONSO_SOURCE_META} code={r.source_consumption} testId={`fuel-reconciliation-source-${r.vehicle_id}`} /></TableCell>
                <TableCell><Pill map={RECO_STATUS_META} code={r.status} testId={`fuel-reconciliation-status-${r.vehicle_id}`} /></TableCell>
                <TableCell className="max-w-[180px] truncate text-xs text-slate-600" data-testid={`fuel-reconciliation-justification-${r.vehicle_id}`} title={r.justification?.reason}>{r.justification ? <span className="font-semibold text-emerald-700">Oui · {r.justification.reason}</span> : <span className="text-slate-400">Non</span>}</TableCell>
                <TableCell data-testid={`fuel-reconciliation-blockers-${r.vehicle_id}`}>{r.blockers?.count ? <div className="flex flex-wrap gap-1">{Object.entries(r.blockers.by_type).map(([k, v]) => <Pill key={k} map={BLOCKER_META} code={k} prefix={`${v} × `} />)}</div> : <span className="text-xs text-slate-300">—</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ReconciliationDrawer item={selected} onOpenChange={(o) => { if (!o) setParam("v", null); }} />
      <ThresholdsDialog settings={conf} rule={settings?.rule} open={thresholds} onOpenChange={setThresholds} />
    </div>
  );
}
