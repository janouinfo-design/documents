import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CalendarDays, FileClock, FileX, Loader2, Settings2 } from "lucide-react";
import { getDeadlines, getDocCategories, getVehicles } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { EVENT_TYPES, DEADLINE_STATUT_META } from "@/lib/status";
import StatusBadge from "@/components/StatusBadge";
import KpiCard from "@/components/KpiCard";
import QueryErrorState from "@/components/QueryErrorState";
import DeadlineSettingsDialog from "@/components/deadlines/DeadlineSettingsDialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const ALL = "__all__";
const DATED = "EXPIRE,URGENT,A_PLANIFIER,OK";
const tabForType = (t) =>
  ["leasing", "assurance", "controle"].includes(t) ? t : t === "document" ? "documents" : "general";

const PERIODS = [
  [ALL, "Toutes périodes"],
  ["30", "≤ 30 jours"],
  ["90", "≤ 90 jours"],
  ["180", "≤ 180 jours"],
  ["365", "≤ 365 jours"],
];

export default function TimelinePage() {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [vehicle, setVehicle] = useState(ALL);
  const [category, setCategory] = useState(ALL);
  const [statut, setStatut] = useState(ALL);
  const [period, setPeriod] = useState(ALL);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const params = useMemo(() => ({
    ...(vehicle !== ALL && { vehicle_id: vehicle }),
    ...(category !== ALL && { category }),
    statut: statut === ALL ? DATED : statut,
    ...(period !== ALL && { days: Number(period) }),
  }), [vehicle, category, statut, period]);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["deadlines", params],
    queryFn: () => getDeadlines(params),
  });
  const { data: categories = [] } = useQuery({ queryKey: ["doc-categories"], queryFn: getDocCategories });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });

  const items = data?.items || [];
  const summary = data?.summary;
  const th = data?.thresholds || { urgent_days: 30, warning_days: 90 };

  const categoryOptions = useMemo(() => {
    const names = categories.map((c) => c.name);
    ["Expertise", "Maintenance"].forEach((n) => !names.includes(n) && names.push(n));
    return names;
  }, [categories]);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="timeline-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Échéances
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Toutes les échéances documentaires de la flotte — documents et contrats, source unique.
          </p>
        </div>
        {isAdmin && (
          <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}
                  data-testid="deadline-settings-btn" className="gap-1.5">
            <Settings2 className="h-4 w-4" /> Seuils ({th.urgent_days}/{th.warning_days} j)
          </Button>
        )}
      </div>

      {/* Résumé (moteur central, compte entier) */}
      <div className="space-y-1.5">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <KpiCard testId="deadlines-kpi-expired" label="Expirés" value={!summary ? "—" : summary.expired} accent="red" icon={FileX} />
          <KpiCard testId="deadlines-kpi-urgent" label={`Urgents (≤ ${th.urgent_days} j)`} value={!summary ? "—" : summary.urgent} accent="amber" icon={FileClock} />
          <KpiCard testId="deadlines-kpi-warning" label={`À planifier (${th.urgent_days + 1}–${th.warning_days} j)`} value={!summary ? "—" : summary.warning} accent="sky" icon={CalendarClock} />
          <KpiCard testId="deadlines-kpi-nodate" label="Sans échéance" value={!summary ? "—" : summary.no_date + (summary.invalid_date || 0)} accent="slate" icon={CalendarDays} />
        </div>
        <p className="text-[11px] text-slate-400" data-testid="deadlines-kpi-note">
          Résumé de la flotte entière — indépendant des filtres ci-dessous.
        </p>
      </div>

      {/* Filtres */}
      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
        <Select value={vehicle} onValueChange={setVehicle}>
          <SelectTrigger data-testid="deadlines-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les véhicules</SelectItem>
            {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={category} onValueChange={setCategory}>
          <SelectTrigger data-testid="deadlines-filter-category"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toutes catégories</SelectItem>
            {categoryOptions.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={statut} onValueChange={setStatut}>
          <SelectTrigger data-testid="deadlines-filter-statut"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toutes (avec date)</SelectItem>
            <SelectItem value="EXPIRE">Expirés</SelectItem>
            <SelectItem value="URGENT">{`Urgents (≤ ${th.urgent_days} j)`}</SelectItem>
            <SelectItem value="A_PLANIFIER">{`À planifier (${th.urgent_days + 1}–${th.warning_days} j)`}</SelectItem>
            <SelectItem value="OK">{`OK (> ${th.warning_days} j)`}</SelectItem>
            <SelectItem value="SANS_ECHEANCE">Sans échéance</SelectItem>
            <SelectItem value="DATE_INVALIDE">Date à vérifier</SelectItem>
          </SelectContent>
        </Select>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger data-testid="deadlines-filter-period"><SelectValue /></SelectTrigger>
          <SelectContent>
            {PERIODS.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {isError && <QueryErrorState error={error} testId="timeline-error" />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="deadlines-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Véhicule</TableHead>
              <TableHead>Échéance / document</TableHead>
              <TableHead>Catégorie</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Jours restants</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Responsable</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7}>
                  <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400" data-testid="deadlines-loading">
                    <Loader2 className="h-4 w-4 animate-spin" /> Chargement des échéances…
                  </div>
                </TableCell>
              </TableRow>
            )}
            {!isLoading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <div className="flex flex-col items-center gap-2 py-12 text-center" data-testid="deadlines-empty">
                    <CalendarDays className="h-8 w-8 text-slate-300" />
                    <p className="text-sm font-medium text-slate-600">Aucune échéance ne correspond aux filtres</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
            {items.map((e) => {
              const t = EVENT_TYPES[e.type] || EVENT_TYPES.document;
              return (
                <TableRow key={e.key} data-testid={`deadline-row-${e.key}`} className="hover:bg-slate-50">
                  <TableCell>
                    <button onClick={() => openVehicle(e.vehicle_id, tabForType(e.type))}
                            data-testid={`deadline-open-vehicle-${e.key}`}
                            className="text-sm font-semibold text-slate-800 underline-offset-2 hover:underline">
                      {e.plaque || "—"}
                    </button>
                    <p className="text-xs text-slate-400">{[e.marque, e.modele].filter(Boolean).join(" ")}</p>
                  </TableCell>
                  <TableCell>
                    <p className="max-w-[220px] truncate text-sm text-slate-700">{e.label}</p>
                    {e.source === "legacy" && (
                      <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Fiche véhicule</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", t.bg, t.text)}>
                      {e.category || t.label}
                    </span>
                  </TableCell>
                  <TableCell className={cn("text-sm", e.statut === "EXPIRE" ? "font-semibold text-red-600" : "text-slate-600")}>
                    {e.date ? dateFr(e.date) : "—"}
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">
                    {e.days_remaining === null || e.days_remaining === undefined
                      ? "—"
                      : e.days_remaining < 0
                        ? `Échu depuis ${-e.days_remaining} j`
                        : `${e.days_remaining} j`}
                  </TableCell>
                  <TableCell>
                    {["SANS_ECHEANCE", "DATE_INVALIDE"].includes(e.statut) ? (
                      <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                        {DEADLINE_STATUT_META[e.statut]?.label}
                      </span>
                    ) : (
                      <StatusBadge level={e.level} days={e.days_remaining} showDays />
                    )}
                  </TableCell>
                  <TableCell className={cn("text-sm", e.responsable ? "text-slate-700" : "text-slate-400")}>
                    {e.responsable || "Non attribué"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <DeadlineSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} thresholds={th} />
    </div>
  );
}
