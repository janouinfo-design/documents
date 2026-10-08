import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, ShieldAlert, CheckCircle2, RefreshCw, Flame } from "lucide-react";
import { getFuelAnomalies, getVehicles, scanFuelAnomalies } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { chfExact, dateFr } from "@/lib/format";
import { errDetail } from "@/lib/fuelCards";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import EnergyTabs from "@/components/energy/EnergyTabs";
import Pill from "@/components/energy/Pill";
import AnomalyDrawer from "@/components/energy/AnomalyDrawer";
import TransactionDrawer from "@/components/energy/TransactionDrawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ANOMALY_STATUS_META, SEVERITY_META, ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";

const ALL = "__all__";

// Énergie › Anomalies : table filtrable (type, statut, sévérité, période, véhicule, carte, fournisseur, justifiée), fiche, décision motivée
export default function FuelAnomaliesPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [params, setParams] = useSearchParams();
  const [type, setType] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [severity, setSeverity] = useState(ALL);
  const [vehicle, setVehicle] = useState(ALL);
  const [card, setCard] = useState(ALL);
  const [provider, setProvider] = useState(ALL);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [scanning, setScanning] = useState(false);
  const openId = params.get("id");
  const txId = params.get("tx");
  const setParam = (k, v) => setParams((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n; }, { replace: true });
  const query = useMemo(() => ({ ...(type !== ALL ? { type } : {}), ...(status !== ALL ? { status } : {}), ...(severity !== ALL ? { severity } : {}), ...(vehicle !== ALL ? { vehicle_id: vehicle } : {}) }), [type, status, severity, vehicle]);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fuel-anomalies", query], queryFn: () => getFuelAnomalies(query), keepPreviousData: true });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const all = useMemo(() => data?.items || [], [data]);
  const cards = useMemo(() => [...new Map(all.filter((a) => a.card_id).map((a) => [a.card_id, a.card_label || a.card_id])).entries()], [all]);
  const providers = useMemo(() => [...new Set(all.map((a) => a.transaction?.fournisseur).filter(Boolean))].sort(), [all]);
  const items = useMemo(() => all.filter((a) => (card === ALL || a.card_id === card) && (provider === ALL || a.transaction?.fournisseur === provider)
    && (!from || (a.transaction?.date || "") >= from) && (!to || (a.transaction?.date || "") <= to)), [all, card, provider, from, to]);
  const stats = data?.stats || {};
  const selected = all.find((a) => a.id === openId) || null;
  const reset = () => { setType(ALL); setStatus(ALL); setSeverity(ALL); setVehicle(ALL); setCard(ALL); setProvider(ALL); setFrom(""); setTo(""); };
  const scan = async () => {
    setScanning(true);
    try { const r = await scanFuelAnomalies(); toast.success(`${r.scanned} transaction(s) analysée(s), ${r.created} nouvelle(s) anomalie(s)`); qc.invalidateQueries({ queryKey: ["fuel-anomalies"] }); }
    catch (e) { toast.error(errDetail(e)); } finally { setScanning(false); }
  };
  return (
    <div className="space-y-6 animate-fade-in" data-testid="fuel-anomalies-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Anomalies carburant</h2>
          <p className="mt-1 text-sm text-slate-500">Détectées et recalculées par Documents (carte inactive, carte ↔ véhicule différent, double plein, montant, réservoir, kilométrage, plaque). Une anomalie décidée reste visible — aucune correction automatique.</p>
        </div>
        {isAdmin && <Button size="sm" variant="outline" onClick={scan} disabled={scanning} className="gap-1.5" data-testid="fuel-anomalies-scan-btn"><RefreshCw className={`h-4 w-4 ${scanning ? "animate-spin" : ""}`} /> Relancer la détection</Button>}
      </div>
      <EnergyTabs />
      {isError && <QueryErrorState error={error} testId="fuel-anomalies-error" />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="fuel-anomalies-kpis">
        <KpiCard testId="fuel-anomalies-kpi-total" label="Anomalies" value={isLoading ? "—" : stats.total ?? 0} icon={AlertTriangle} accent="slate" sub="Historique complet" onClick={reset} />
        <KpiCard testId="fuel-anomalies-kpi-ouvertes" label="Ouvertes" value={isLoading ? "—" : stats.ouvertes ?? 0} icon={Flame} accent="rose" sub="À décider" onClick={() => setStatus("ouverte")} active={status === "ouverte"} />
        <KpiCard testId="fuel-anomalies-kpi-critical" label="Critiques ouvertes" value={isLoading ? "—" : stats.critical_ouvertes ?? 0} icon={ShieldAlert} accent="red" sub="Carte inactive, carte ↔ véhicule, réservoir" onClick={() => { setStatus("ouverte"); setSeverity("critical"); }} active={severity === "critical"} />
        <KpiCard testId="fuel-anomalies-kpi-justifiees" label="Justifiées" value={isLoading ? "—" : stats.by_status?.justifiee ?? 0} icon={CheckCircle2} accent="emerald" sub="Décision humaine motivée" onClick={() => setStatus("justifiee")} active={status === "justifiee"} />
      </div>
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-4 lg:grid-cols-8" data-testid="fuel-anomalies-filters">
        <Select value={type} onValueChange={setType}><SelectTrigger data-testid="fuel-filter-anomaly-type"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les types</SelectItem>{(data?.types || []).map((t) => <SelectItem key={t.code} value={t.code}>{ANOMALY_TYPE_LABELS[t.code] || t.label}</SelectItem>)}</SelectContent></Select>
        <Select value={status} onValueChange={setStatus}><SelectTrigger data-testid="fuel-filter-anomaly-status"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les statuts</SelectItem>{Object.entries(ANOMALY_STATUS_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
        <Select value={severity} onValueChange={setSeverity}><SelectTrigger data-testid="fuel-filter-anomaly-severity"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Toute sévérité</SelectItem>{Object.entries(SEVERITY_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
        <Select value={vehicle} onValueChange={setVehicle}><SelectTrigger data-testid="fuel-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les véhicules</SelectItem>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}</SelectContent></Select>
        <Select value={card} onValueChange={setCard}><SelectTrigger data-testid="fuel-filter-card"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Toutes les cartes</SelectItem>{cards.map(([id, label]) => <SelectItem key={id} value={id}>{label}</SelectItem>)}</SelectContent></Select>
        <Select value={provider} onValueChange={setProvider}><SelectTrigger data-testid="fuel-filter-provider"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les fournisseurs</SelectItem>{providers.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="fuel-filter-date-from" aria-label="Du" />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="fuel-filter-date-to" aria-label="Au" />
        <div className="col-span-2 flex items-center justify-between sm:col-span-4 lg:col-span-8">
          <p className="text-xs text-slate-500" data-testid="fuel-anomalies-count">{isLoading ? "…" : `${items.length} anomalie(s)`}</p>
          <Button variant="ghost" size="sm" onClick={reset} data-testid="fuel-anomalies-filters-reset">Réinitialiser</Button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="fuel-anomalies-table">
          <TableHeader><TableRow className="bg-slate-50">
            <TableHead>Date</TableHead><TableHead>Transaction</TableHead><TableHead>Type</TableHead><TableHead>Fournisseur</TableHead><TableHead>Carte</TableHead><TableHead>Véhicule</TableHead>
            <TableHead className="text-right">Montant</TableHead><TableHead>Statut</TableHead><TableHead>Justifiée</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && <TableRow><TableCell colSpan={9}><p className="py-10 text-center text-sm text-slate-400" data-testid="fuel-anomalies-empty">Aucune anomalie ne correspond aux filtres.</p></TableCell></TableRow>}
            {items.map((a) => {
              const tx = a.transaction || {};
              return (
                <TableRow key={a.id} data-testid={`fuel-anomaly-row-${a.id}`} onClick={() => setParam("id", a.id)} className="cursor-pointer hover:bg-slate-50">
                  <TableCell className="whitespace-nowrap text-sm text-slate-700">{tx.date ? `${dateFr(tx.date)}${tx.heure ? ` ${tx.heure}` : ""}` : "—"}</TableCell>
                  <TableCell className="text-sm text-slate-700">{tx.station || "—"}<p className="max-w-xs truncate text-[11px] text-slate-400" title={a.explanation}>{a.explanation}</p></TableCell>
                  <TableCell><div className="flex flex-wrap gap-1"><span className="text-sm font-semibold text-slate-900" data-testid={`fuel-anomaly-type-${a.id}`}>{ANOMALY_TYPE_LABELS[a.type] || a.label}</span><Pill map={SEVERITY_META} code={a.severity} testId={`fuel-anomaly-severity-${a.id}`} /></div></TableCell>
                  <TableCell className="text-sm text-slate-600">{tx.fournisseur || "—"}</TableCell>
                  <TableCell className="text-sm text-slate-600" data-testid={`fuel-anomaly-card-${a.id}`}>{a.card_label || (tx.carte_last4 ? `••••${tx.carte_last4}` : "—")}</TableCell>
                  <TableCell className="text-sm font-semibold text-slate-800" data-testid={`fuel-anomaly-vehicle-${a.id}`}>{a.plaque || "—"}</TableCell>
                  <TableCell className="text-right text-sm font-semibold text-slate-900">{tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : "—"}</TableCell>
                  <TableCell><Pill map={ANOMALY_STATUS_META} code={a.status} testId={`fuel-anomaly-status-${a.id}`} /></TableCell>
                  <TableCell className="text-sm" data-testid={`fuel-anomaly-justified-${a.id}`}>{a.status === "justifiee" ? <span className="font-semibold text-emerald-700">Oui · {a.decided_by}</span> : a.status === "ouverte" ? <span className="text-slate-400">Non</span> : <span className="text-slate-500">{a.status_label}</span>}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <AnomalyDrawer anomaly={selected} onOpenChange={(o) => { if (!o) setParam("id", null); }} onOpenTransaction={(id) => setParam("tx", id)} />
      <TransactionDrawer txId={txId} onOpenChange={(o) => { if (!o) setParam("tx", null); }} />
    </div>
  );
}
