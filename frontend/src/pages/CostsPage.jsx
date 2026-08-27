import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Wallet, Banknote, Layers, PieChart as PieIcon } from "lucide-react";
import { getCosts, getVehicles, getDocCategories } from "@/lib/api";
import { chf } from "@/lib/format";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const ALL = "__all__";
const FREQ_FR = { unique: "Unique", mensuel: "Mensuel", trimestriel: "Trimestriel", semestriel: "Semestriel", annuel: "Annuel" };

export default function CostsPage() {
  const { openVehicle } = useVehicleDrawer();
  const [vehicle, setVehicle] = useState(ALL);
  const [category, setCategory] = useState(ALL);

  const { data, isLoading, isError, error } = useQuery({ queryKey: ["costs"], queryFn: () => getCosts() });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const { data: categories = [] } = useQuery({ queryKey: ["doc-categories"], queryFn: getDocCategories });

  const totals = data?.totals || { annuel: 0, mensuel: 0, postes_actifs: 0 };
  const topCat = data?.by_category?.[0];
  const year = data?.year;

  const items = useMemo(() => (data?.items || []).filter((i) =>
    (vehicle === ALL || i.vehicle_id === vehicle) &&
    (category === ALL || i.category === category)
  ), [data, vehicle, category]);

  const categoryOptions = useMemo(() => {
    const names = new Set(categories.map((c) => c.name));
    (data?.by_category || []).forEach((c) => names.add(c.category));
    return [...names];
  }, [categories, data]);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="costs-page">
      <div>
        <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Coûts</h2>
        <p className="mt-1 text-sm text-slate-500">
          Coûts réels de la flotte, dérivés des montants des documents et des contrats — sans double comptage.
        </p>
      </div>

      {isError && <QueryErrorState error={error} testId="costs-error" />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard testId="costs-kpi-annuel" label={`Coût annuel ${year || ""}`} value={isLoading ? "—" : chf(totals.annuel)} accent="slate" icon={Wallet} sub="Tous postes actifs" />
        <KpiCard testId="costs-kpi-mensuel" label="Équivalent mensuel" value={isLoading ? "—" : chf(totals.mensuel)} accent="slate" icon={Banknote} sub="Coût annuel / 12" />
        <KpiCard testId="costs-kpi-postes" label="Postes actifs" value={isLoading ? "—" : totals.postes_actifs} accent="sky" icon={Layers} sub="Documents & contrats" />
        <KpiCard testId="costs-kpi-topcat" label="Poste principal" value={isLoading ? "—" : topCat ? topCat.category : "—"} accent="indigo" icon={PieIcon} sub={topCat ? chf(topCat.total_annuel) + " / an" : "Aucun montant saisi"} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Évolution annuelle */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-1" data-testid="costs-chart">
          <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">Évolution annuelle</h3>
          <p className="mb-3 text-xs text-slate-400">Basée sur les périodes des documents et contrats.</p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data?.series || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#64748b" }} />
                <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} width={54} tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
                <Tooltip formatter={(v) => chf(v)} labelFormatter={(l) => `Année ${l}`} />
                <Bar dataKey="total" fill="#0f172a" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Coûts par véhicule */}
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm lg:col-span-2" data-testid="costs-by-vehicle">
          <div className="border-b border-slate-100 px-6 py-4">
            <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">Coût annuel par véhicule ({year})</h3>
          </div>
          <div className="max-h-64 overflow-y-auto divide-y divide-slate-100">
            {(data?.by_vehicle || []).length === 0 && (
              <p className="px-6 py-8 text-center text-sm text-slate-400" data-testid="costs-by-vehicle-empty">
                Aucun montant saisi — renseignez les montants sur les fiches documents ou les contrats.
              </p>
            )}
            {(data?.by_vehicle || []).map((v) => (
              <button key={v.vehicle_id} onClick={() => setVehicle(vehicle === v.vehicle_id ? ALL : v.vehicle_id)}
                      data-testid={`costs-vehicle-${v.vehicle_id}`}
                      className={cn("flex w-full items-center justify-between px-6 py-3 text-left transition-colors hover:bg-slate-50",
                        vehicle === v.vehicle_id && "bg-slate-50 ring-1 ring-inset ring-slate-200")}>
                <div>
                  <span className="text-sm font-semibold text-slate-900">{v.plaque || "—"}</span>
                  <span className="ml-2 text-xs text-slate-400">{[v.marque, v.modele].filter(Boolean).join(" ")}</span>
                  <p className="text-[11px] text-slate-400">
                    {Object.entries(v.by_category).map(([c, m]) => `${c} ${chf(m)}`).join(" · ")}
                  </p>
                </div>
                <span className="font-display text-base font-bold text-slate-900">{chf(v.total_annuel)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filtres + détail des postes */}
      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2">
        <Select value={vehicle} onValueChange={setVehicle}>
          <SelectTrigger data-testid="costs-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les véhicules</SelectItem>
            {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger data-testid="costs-filter-category"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toutes catégories</SelectItem>
            {categoryOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="costs-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Véhicule</TableHead>
              <TableHead>Poste</TableHead>
              <TableHead>Catégorie</TableHead>
              <TableHead>Montant</TableHead>
              <TableHead>Fréquence</TableHead>
              <TableHead>Coût annuel</TableHead>
              <TableHead>Période</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <p className="py-10 text-center text-sm text-slate-400" data-testid="costs-empty">
                    Aucun poste de coût — saisissez un montant sur une fiche document ou un contrat.
                  </p>
                </TableCell>
              </TableRow>
            )}
            {items.map((i) => (
              <TableRow key={i.key} data-testid={`cost-row-${i.key}`} className={cn("hover:bg-slate-50", !i.actif && "opacity-60")}>
                <TableCell>
                  <button onClick={() => openVehicle(i.vehicle_id, i.source === "document" ? "documents" : "leasing")}
                          className="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline">
                    {i.plaque || "—"}
                  </button>
                </TableCell>
                <TableCell>
                  <p className="max-w-[220px] truncate text-sm text-slate-700">{i.label}</p>
                  {i.source === "legacy" && (
                    <span className="inline-flex rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">Fiche véhicule</span>
                  )}
                </TableCell>
                <TableCell><span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">{i.category}</span></TableCell>
                <TableCell className="text-sm text-slate-600">{chf(i.montant)}</TableCell>
                <TableCell className="text-sm text-slate-600">{FREQ_FR[i.frequence] || i.frequence}</TableCell>
                <TableCell className="text-sm font-semibold text-slate-900">
                  {chf(i.cout_annuel)}
                  {!i.recurrent && <span className="ml-1 text-[10px] font-normal text-slate-400">(unique)</span>}
                  {!i.actif && <span className="ml-1 text-[10px] font-normal text-amber-600">(hors {year})</span>}
                </TableCell>
                <TableCell className="text-xs text-slate-500">
                  {i.date_debut || i.date_expiration ? `${i.date_debut || "…"} → ${i.date_expiration || "…"}` : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
