import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { CreditCard, Plus, Search, ShieldCheck, CalendarX2, CalendarClock, Link2Off, AlertTriangle } from "lucide-react";
import { getFuelCards, getVehicles } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import EnergyTabs from "@/components/energy/EnergyTabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import FuelCardStatusBadge, { ExpirationCell, CardWarnings } from "@/components/fuelcards/FuelCardStatusBadge";
import FuelCardDialog from "@/components/fuelcards/FuelCardDialog";
import FuelCardDrawer from "@/components/fuelcards/FuelCardDrawer";
import { CARD_STATUSES, CARD_STATUS_META, EXPIRATION_META, ARCHIVE_MODES } from "@/lib/fuelCards";

const ALL = "__all__";
const VIEWS = { utilisables: { utilisable: "true" }, expirees: { expiration_state: "expiree" }, bientot: { expiration_state: "bientot" },
  sans_affectation: { affectation: "sans" }, avertissements: {} };

export default function FuelCardsPage() {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [fournisseur, setFournisseur] = useState(ALL);
  const [statut, setStatut] = useState(ALL);
  const [expiration, setExpiration] = useState(ALL);
  const [archived, setArchived] = useState("false");
  const [vehicle, setVehicle] = useState(ALL);
  const [view, setView] = useState(params.get("view") || null);
  const [createOpen, setCreateOpen] = useState(false);
  const openId = params.get("id");
  const setOpenId = (id) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("id", id); else n.delete("id"); return n; }, { replace: true });

  const query = useMemo(() => ({
    ...(q.trim() ? { q: q.trim() } : {}), ...(fournisseur !== ALL ? { fournisseur } : {}), ...(statut !== ALL ? { statut } : {}),
    ...(expiration !== ALL ? { expiration_state: expiration } : {}), archived, ...(vehicle !== ALL ? { vehicle_id: vehicle } : {}), ...(view ? VIEWS[view] : {}),
  }), [q, fournisseur, statut, expiration, archived, vehicle, view]);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fuel-cards", "list", query], queryFn: () => getFuelCards(query), keepPreviousData: true });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const stats = data?.stats || {};
  const items = useMemo(() => (view === "avertissements" ? (data?.items || []).filter((c) => c.warnings?.length) : data?.items || []), [data, view]);
  const toggleView = (v) => setView((cur) => (cur === v ? null : v));
  const reset = () => { setQ(""); setFournisseur(ALL); setStatut(ALL); setExpiration(ALL); setArchived("false"); setVehicle(ALL); setView(null); };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="fuel-cards-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Cartes carburant</h2>
          <p className="mt-1 text-sm text-slate-500">Référentiel des cartes, affectations datées véhicule / conducteur, statut et expiration. Identité affichée « Fournisseur ••••1234 » (non unique).</p>
        </div>
        {isAdmin && (
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-cards-create-btn">
            <Plus className="h-4 w-4" /> Nouvelle carte
          </Button>
        )}
      </div>

      <EnergyTabs />
      {isError && <QueryErrorState error={error} testId="fuel-cards-error" />}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6" data-testid="fuel-cards-kpis">
        <KpiCard testId="fuel-cards-kpi-total" label="Cartes" value={isLoading ? "—" : stats.total ?? 0} icon={CreditCard} accent="slate" sub={`${stats.archivees ?? 0} archivée(s)`} onClick={reset} />
        <KpiCard testId="fuel-cards-kpi-utilisables" label="Utilisables" value={isLoading ? "—" : stats.utilisables ?? 0} icon={ShieldCheck} accent="emerald" sub="Active et non expirée" onClick={() => toggleView("utilisables")} active={view === "utilisables"} />
        <KpiCard testId="fuel-cards-kpi-expirees" label="Expirées" value={isLoading ? "—" : stats.by_expiration?.expiree ?? 0} icon={CalendarX2} accent="red" sub="Date dépassée" onClick={() => toggleView("expirees")} active={view === "expirees"} />
        <KpiCard testId="fuel-cards-kpi-bientot" label="Expirent bientôt" value={isLoading ? "—" : stats.by_expiration?.bientot ?? 0} icon={CalendarClock} accent="amber" sub={`≤ ${data?.thresholds?.warning_days ?? 90} jours`} onClick={() => toggleView("bientot")} active={view === "bientot"} />
        <KpiCard testId="fuel-cards-kpi-sans-affectation" label="Sans affectation" value={isLoading ? "—" : stats.sans_affectation ?? 0} icon={Link2Off} accent="sky" sub="Aucune affectation en cours" onClick={() => toggleView("sans_affectation")} active={view === "sans_affectation"} />
        <KpiCard testId="fuel-cards-kpi-avertissements" label="Avertissements" value={isLoading ? "—" : stats.avec_avertissement ?? 0} icon={AlertTriangle} accent="indigo" sub="Cartes à vérifier" onClick={() => toggleView("avertissements")} active={view === "avertissements"} />
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3 lg:grid-cols-6" data-testid="fuel-cards-filters">
        <div className="relative sm:col-span-3 lg:col-span-2">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
          <Input className="pl-8" placeholder="Fournisseur, 4 chiffres, plaque, conducteur…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="fuel-cards-search" />
        </div>
        <Select value={fournisseur} onValueChange={setFournisseur}>
          <SelectTrigger data-testid="fuel-cards-filter-fournisseur"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les fournisseurs</SelectItem>{(data?.fournisseurs || []).map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={statut} onValueChange={setStatut}>
          <SelectTrigger data-testid="fuel-cards-filter-statut"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les statuts</SelectItem>{CARD_STATUSES.map((s) => <SelectItem key={s} value={s}>{CARD_STATUS_META[s].label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={expiration} onValueChange={setExpiration}>
          <SelectTrigger data-testid="fuel-cards-filter-expiration"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Toute expiration</SelectItem>{Object.entries(EXPIRATION_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={archived} onValueChange={setArchived}>
          <SelectTrigger data-testid="fuel-cards-filter-archived"><SelectValue /></SelectTrigger>
          <SelectContent>{ARCHIVE_MODES.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={vehicle} onValueChange={setVehicle}>
          <SelectTrigger data-testid="fuel-cards-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={ALL}>Tous les véhicules</SelectItem>{vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}</SelectContent>
        </Select>
        <div className="flex items-center justify-between sm:col-span-3 lg:col-span-5">
          <p className="text-xs text-slate-500" data-testid="fuel-cards-count">{isLoading ? "…" : `${items.length} carte(s)`}{view ? " · vue filtrée" : ""}</p>
          <Button variant="ghost" size="sm" onClick={reset} data-testid="fuel-cards-filters-reset">Réinitialiser</Button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="fuel-cards-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Carte</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Expiration</TableHead>
              <TableHead>Véhicule</TableHead>
              <TableHead>Conducteur</TableHead>
              <TableHead>Avertissements</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && (
              <TableRow><TableCell colSpan={6}><p className="py-10 text-center text-sm text-slate-400" data-testid="fuel-cards-empty">Aucune carte ne correspond aux filtres.</p></TableCell></TableRow>
            )}
            {items.map((c) => (
              <TableRow key={c.id} data-testid={`fuel-card-row-${c.id}`} onClick={() => setOpenId(c.id)} className={`cursor-pointer hover:bg-slate-50 ${c.is_deleted ? "opacity-60" : ""}`}>
                <TableCell>
                  <p className="font-semibold text-slate-900" data-testid={`fuel-card-label-${c.id}`}>{c.label}</p>
                  <p className="text-xs text-slate-500">{c.type_affectation_label}{c.external_card_id ? ` · ${c.external_card_id}` : ""}{c.is_deleted ? " · archivée" : ""}</p>
                </TableCell>
                <TableCell>
                  <FuelCardStatusBadge statut={c.statut} />
                  {!c.utilisable && c.statut === "active" && <p className="mt-0.5 text-[10px] font-semibold text-red-600">non utilisable (date)</p>}
                </TableCell>
                <TableCell><ExpirationCell card={c} /></TableCell>
                <TableCell>
                  {c.vehicule_courant ? (
                    <button type="button" onClick={(e) => { e.stopPropagation(); openVehicle(c.vehicule_courant.vehicle_id); }} className="text-sm font-semibold text-slate-800 hover:underline" data-testid={`fuel-card-vehicle-${c.id}`}>
                      {c.vehicule_courant.plaque}
                    </button>
                  ) : <span className="text-xs text-slate-400">—</span>}
                </TableCell>
                <TableCell className="text-sm" data-testid={`fuel-card-driver-${c.id}`}>{c.conducteur_courant?.driver_nom || <span className="text-xs text-slate-400">—</span>}</TableCell>
                <TableCell><CardWarnings warnings={c.warnings} compact cardId={c.id} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <FuelCardDialog open={createOpen} onOpenChange={setCreateOpen} onSaved={(r) => setOpenId(r.id)} />
      <FuelCardDrawer cardId={openId} onOpenChange={(o) => { if (!o) setOpenId(null); }} />
    </div>
  );
}
