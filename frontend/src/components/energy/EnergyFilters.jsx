import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MATCH_META } from "@/lib/fuelImport";

export const ALL = "__all__";
export const EMPTY_FILTERS = { vehicle: ALL, driver: ALL, provider: ALL, card: ALL, match: ALL, anomaly: ALL, job: ALL, from: "", to: "", q: "" };

export const applyFilters = (txs, f) => txs.filter((t) =>
  (f.vehicle === ALL || t.vehicle_id === f.vehicle) && (f.driver === ALL || t.driver_id === f.driver)
  && (f.provider === ALL || (t.fournisseur || "") === f.provider) && (f.card === ALL || (f.card === "__none" ? !t.card_id : t.card_id === f.card))
  && (f.match === ALL || (t.match_status || "") === f.match) && (f.anomaly === ALL || (f.anomaly === "open" ? (t.anomalies_open || 0) > 0 : (t.anomalies_open || 0) === 0))
  && (f.job === ALL || t.import_job_id === f.job) && (!f.from || (t.date || "") >= f.from) && (!f.to || (t.date || "") <= f.to)
  && (!f.q || [t.plaque, t.station, t.fournisseur, t.carte_last4, t.external_transaction_id, t.driver_nom].some((x) => (x || "").toLowerCase().includes(f.q.toLowerCase()))));

// Filtres Transactions : période, fournisseur, véhicule, conducteur, carte, état de rattachement, anomalies, import, recherche
export default function EnergyFilters({ f, set, vehicles, drivers, providers, cards, jobs, count }) {
  const upd = (k) => (v) => set((s) => ({ ...s, [k]: v }));
  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3 lg:grid-cols-5" data-testid="energy-filters">
      <div className="relative col-span-2 sm:col-span-3 lg:col-span-2">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
        <Input className="pl-8" placeholder="Plaque, station, fournisseur, 4 chiffres, référence…" value={f.q} onChange={(e) => upd("q")(e.target.value)} data-testid="fuel-filter-search" />
      </div>
      <Input type="date" value={f.from} onChange={(e) => upd("from")(e.target.value)} data-testid="fuel-filter-date-from" aria-label="Du" />
      <Input type="date" value={f.to} onChange={(e) => upd("to")(e.target.value)} data-testid="fuel-filter-date-to" aria-label="Au" />
      <Select value={f.provider} onValueChange={upd("provider")}><SelectTrigger data-testid="fuel-filter-provider"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tous les fournisseurs</SelectItem>{providers.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select>
      <Select value={f.vehicle} onValueChange={upd("vehicle")}><SelectTrigger data-testid="energy-filter-vehicle"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tous les véhicules</SelectItem>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}</SelectContent></Select>
      <Select value={f.driver} onValueChange={upd("driver")}><SelectTrigger data-testid="energy-filter-driver"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tous les conducteurs</SelectItem>{drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.display}{d.is_deleted ? " (archivé)" : ""}</SelectItem>)}</SelectContent></Select>
      <Select value={f.card} onValueChange={upd("card")}><SelectTrigger data-testid="fuel-filter-card"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Toutes les cartes</SelectItem><SelectItem value="__none">Sans carte résolue</SelectItem>{cards.map(([id, label]) => <SelectItem key={id} value={id}>{label}</SelectItem>)}</SelectContent></Select>
      <Select value={f.match} onValueChange={upd("match")}><SelectTrigger data-testid="fuel-filter-match-status"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tout rattachement</SelectItem>{Object.entries(MATCH_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent></Select>
      <Select value={f.anomaly} onValueChange={upd("anomaly")}><SelectTrigger data-testid="fuel-filter-anomaly"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Anomalies : toutes</SelectItem><SelectItem value="open">Avec anomalie ouverte</SelectItem><SelectItem value="none">Sans anomalie ouverte</SelectItem></SelectContent></Select>
      <Select value={f.job} onValueChange={upd("job")}><SelectTrigger data-testid="fuel-filter-job"><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Toutes les sources</SelectItem>{jobs.map((j) => <SelectItem key={j.id} value={j.id}>Import {j.filename} ({new Date(j.created_at).toLocaleDateString("fr-CH")})</SelectItem>)}</SelectContent></Select>
      <div className="col-span-2 flex items-center justify-between sm:col-span-3 lg:col-span-5">
        <p className="text-xs text-slate-500" data-testid="energy-count">{count} transaction(s) · Priorité des sources de consommation : CAN embarquée &gt; tickets &gt; saisie manuelle.</p>
        <Button variant="ghost" size="sm" onClick={() => set(EMPTY_FILTERS)} data-testid="energy-filters-reset">Réinitialiser</Button>
      </div>
    </div>
  );
}
