import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { FileCheck2, Lock, AlertTriangle, GitBranchPlus, Plus } from "lucide-react";
import { getFuelStatements } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import EnergyTabs from "@/components/energy/EnergyTabs";
import Pill from "@/components/energy/Pill";
import ExportButtons from "@/components/energy/ExportButtons";
import StatementDrawer from "@/components/energy/StatementDrawer";
import TransactionDrawer from "@/components/energy/TransactionDrawer";
import { CreateStatementDialog } from "@/components/energy/StatementDialogs";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { STATEMENT_STATUS_META, STATEMENT_TYPE_META, BLOCKER_META, na, signed, periodLabel, periodOptions, currentPeriod, dateFrOrDash } from "@/lib/fuelStatements";

const ALL = "__all__";

// Énergie › Relevés / Décomptes : snapshots Documents par période / périmètre, relevé déclaré, écarts, blockers, clôture / exception, correctifs, exports
export default function FuelStatementsPage() {
  const { user } = useAuth();
  const isAdmin = can(user, "statements.write");
  const [params, setParams] = useSearchParams();
  const [period, setPeriod] = useState(ALL);
  const [provider, setProvider] = useState(ALL);
  const [type, setType] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [blockers, setBlockers] = useState(ALL);
  const [exception, setException] = useState(ALL);
  const [create, setCreate] = useState(false);
  const openId = params.get("id");
  const txId = params.get("tx");
  const setParam = (k, v) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });
  const query = useMemo(() => ({ ...(period !== ALL ? { period_month: period } : {}), ...(provider !== ALL ? { fournisseur: provider } : {}), ...(type !== ALL ? { type } : {}),
    ...(status !== ALL ? { status } : {}), ...(blockers !== ALL ? { with_blockers: blockers } : {}), ...(exception !== ALL ? { close_exception: exception } : {}) }), [period, provider, type, status, blockers, exception]);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fuel-statements", query], queryFn: () => getFuelStatements(query), keepPreviousData: true });
  const items = data?.items || [];
  const stats = data?.stats || {};
  const txPeriod = period !== ALL ? period : currentPeriod();
  const reset = () => { setPeriod(ALL); setProvider(ALL); setType(ALL); setStatus(ALL); setBlockers(ALL); setException(ALL); };
  return (
    <div className="space-y-6 animate-fade-in" data-testid="fuel-statements-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Relevés / Décomptes</h2>
          <p className="mt-1 text-sm text-slate-500">Un décompte = snapshot des transactions Documents d'un mois (tenant ou fournisseur), comparé au relevé fournisseur déclaré. La clôture verrouille les transactions ; aucune réouverture, corrections tardives par correctif.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ExportButtons path="/fuel/transactions/export" params={{ period_month: txPeriod, ...(provider !== ALL ? { fournisseur: provider } : {}) }} formats={["csv", "xlsx"]} testIdPrefix="fuel-transactions" />
          {isAdmin && <Button size="sm" onClick={() => setCreate(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-create-btn"><Plus className="h-4 w-4" /> Nouveau décompte</Button>}
        </div>
      </div>
      <EnergyTabs />
      {isError && <QueryErrorState error={error} testId="fuel-statements-error" />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5" data-testid="fuel-statements-kpis">
        <KpiCard testId="fuel-statements-kpi-total" label="Décomptes" value={isLoading ? "—" : stats.total ?? 0} icon={FileCheck2} accent="slate" sub="Tous périmètres" onClick={reset} />
        <KpiCard testId="fuel-statements-kpi-brouillons" label="Brouillons" value={isLoading ? "—" : stats.brouillons ?? 0} icon={FileCheck2} accent="amber" sub="Snapshots de travail" onClick={() => setStatus("brouillon")} active={status === "brouillon"} />
        <KpiCard testId="fuel-statements-kpi-clotures" label="Clôturés" value={isLoading ? "—" : stats.clotures ?? 0} icon={Lock} accent="emerald" sub="Immuables" onClick={() => setStatus("cloture")} active={status === "cloture"} />
        <KpiCard testId="fuel-statements-kpi-exceptions" label="Avec exception" value={isLoading ? "—" : stats.exceptions ?? 0} icon={AlertTriangle} accent="rose" sub="Blockers conservés" onClick={() => setException("true")} active={exception === "true"} />
        <KpiCard testId="fuel-statements-kpi-correctifs" label="Correctifs" value={isLoading ? "—" : stats.correctifs ?? 0} icon={GitBranchPlus} accent="indigo" sub="Transactions tardives" onClick={() => setType("correctif")} active={type === "correctif"} />
      </div>
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3 lg:grid-cols-6" data-testid="fuel-statements-filters">
        <Select value={period} onValueChange={setPeriod}><SelectTrigger data-testid="fuel-statement-filter-period"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Toutes les périodes</SelectItem>{periodOptions().map((p) => <SelectItem key={p} value={p}>{periodLabel(p)}</SelectItem>)}</SelectContent></Select>
        <Select value={provider} onValueChange={setProvider}><SelectTrigger data-testid="fuel-statement-filter-provider"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les fournisseurs</SelectItem>{(data?.fournisseurs || []).map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent></Select>
        <Select value={type} onValueChange={setType}><SelectTrigger data-testid="fuel-statement-filter-type"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les types</SelectItem>{Object.entries(STATEMENT_TYPE_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
        <Select value={status} onValueChange={setStatus}><SelectTrigger data-testid="fuel-statement-filter-status"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les statuts</SelectItem>{Object.entries(STATEMENT_STATUS_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
        <Select value={blockers} onValueChange={setBlockers}><SelectTrigger data-testid="fuel-statement-filter-blockers"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Blockers : tous</SelectItem><SelectItem value="true">Avec blockers</SelectItem><SelectItem value="false">Sans blocker</SelectItem></SelectContent></Select>
        <Select value={exception} onValueChange={setException}><SelectTrigger data-testid="fuel-statement-filter-exception"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Exception : toutes</SelectItem><SelectItem value="true">Clôturé avec exception</SelectItem><SelectItem value="false">Sans exception</SelectItem></SelectContent></Select>
        <div className="col-span-2 flex items-center justify-between sm:col-span-3 lg:col-span-6">
          <p className="text-xs text-slate-500" data-testid="fuel-statements-count">{isLoading ? "…" : `${items.length} décompte(s)`} · export des transactions : {periodLabel(txPeriod)}</p>
          <Button variant="ghost" size="sm" onClick={reset} data-testid="fuel-statements-filters-reset">Réinitialiser</Button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="fuel-statements-table">
          <TableHeader><TableRow className="bg-slate-50">
            <TableHead>N°</TableHead><TableHead>Périmètre</TableHead><TableHead>Période</TableHead><TableHead>Type</TableHead><TableHead>Statut</TableHead>
            <TableHead className="text-right">Documents CHF</TableHead><TableHead className="text-right">Volume</TableHead><TableHead className="text-right">Déclaré</TableHead><TableHead className="text-right">Écarts</TableHead>
            <TableHead className="text-right">Lignes</TableHead><TableHead>Blockers</TableHead><TableHead>Clôture</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && <TableRow><TableCell colSpan={12}><p className="py-10 text-center text-sm text-slate-400" data-testid="fuel-statements-empty">Aucun décompte — créez un snapshot pour une période.</p></TableCell></TableRow>}
            {items.map((s) => (
              <TableRow key={s.id} data-testid={`fuel-statement-row-${s.id}`} onClick={() => setParam("id", s.id)} className="cursor-pointer hover:bg-slate-50">
                <TableCell className="whitespace-nowrap font-mono text-xs font-semibold text-slate-800" data-testid={`fuel-statement-number-${s.id}`}>{s.number}{s.type === "correctif" && <p className="text-[10px] font-normal text-slate-400">↳ {s.parent_number}</p>}</TableCell>
                <TableCell className="text-sm text-slate-700">{s.scope_label}</TableCell>
                <TableCell className="whitespace-nowrap text-sm text-slate-600">{s.period_month}</TableCell>
                <TableCell><Pill map={STATEMENT_TYPE_META} code={s.type} testId={`fuel-statement-type-${s.id}`} /></TableCell>
                <TableCell><div className="flex flex-wrap gap-1"><Pill map={STATEMENT_STATUS_META} code={s.status} testId={`fuel-statement-status-${s.id}`} />{s.close_exception && <span className="rounded-full bg-rose-700 px-2 py-0.5 text-[10px] font-bold text-white" data-testid={`fuel-statement-exception-${s.id}`}>avec exception</span>}</div></TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900">{na(s.totals.montant_chf, " CHF")}{s.totals.pending_fx ? <p className="text-[10px] text-amber-700">{s.totals.pending_fx} FX en attente</p> : null}</TableCell>
                <TableCell className="text-right text-sm text-slate-700">{na(s.totals.litres, " L")}{s.totals.kwh ? <p className="text-[10px] text-slate-400">{na(s.totals.kwh, " kWh")}</p> : null}</TableCell>
                <TableCell className="text-right text-sm text-slate-700" data-testid={`fuel-statement-declared-${s.id}`}>{s.declared?.montant != null ? `${na(s.declared.montant)} ${s.declared.devise || "CHF"}` : "N/A"}{s.declared?.volume_l != null ? <p className="text-[10px] text-slate-400">{na(s.declared.volume_l, " L")}</p> : null}</TableCell>
                <TableCell className="text-right text-xs text-slate-700" data-testid={`fuel-statement-deltas-${s.id}`}>
                  <p>{s.deltas.montant_comparable === false ? "devise ≠ CHF" : signed(s.deltas.delta_montant, " CHF")}</p>
                  <p className="text-[10px] text-slate-400">{signed(s.deltas.delta_volume_l, " L")} · {signed(s.deltas.delta_nb_lignes, " ligne(s)", 0)}</p>
                </TableCell>
                <TableCell className="text-right text-sm text-slate-700">{s.totals.n_lignes}</TableCell>
                <TableCell data-testid={`fuel-statement-blockers-${s.id}`}>{s.totals.blocker_count ? <div className="flex flex-wrap gap-1">{Object.entries(s.totals.blockers_by_type).map(([k, v]) => <Pill key={k} map={BLOCKER_META} code={k} prefix={`${v} × `} />)}</div> : <span className="text-xs text-emerald-700">0</span>}</TableCell>
                <TableCell className="whitespace-nowrap text-xs text-slate-600" data-testid={`fuel-statement-closed-${s.id}`}>{s.closed_at ? <><Lock className="mr-1 inline h-3 w-3" />{dateFrOrDash(s.closed_at)}<p className="text-[10px] text-slate-400">{s.closed_by}</p></> : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <CreateStatementDialog open={create} onOpenChange={setCreate} fournisseurs={data?.fournisseurs || []} onCreated={(st) => setParam("id", st.id)} />
      <StatementDrawer statementId={openId} onOpenChange={(o) => { if (!o) setParam("id", null); }} onOpenTransaction={(id) => setParam("tx", id)} onOpenStatement={(id) => setParam("id", id)} />
      <TransactionDrawer txId={txId} onOpenChange={(o) => { if (!o) setParam("tx", null); }} />
    </div>
  );
}
