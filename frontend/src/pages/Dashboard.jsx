import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import {
  FileWarning,
  CalendarClock,
  ShieldCheck,
  ClipboardCheck,
  FileStack,
  Wallet,
  Banknote,
  CheckCircle2,
  ArrowRight,
  AlertTriangle,
  FileX,
  FileClock,
  FileSearch,
} from "lucide-react";
import { getDashboard, getDeadlines } from "@/lib/api";
import { chf, dateFr, daysLabel } from "@/lib/format";
import { lvl, EVENT_TYPES } from "@/lib/status";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import StatusBadge from "@/components/StatusBadge";
import QueryErrorState from "@/components/QueryErrorState";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const tabForType = (t) =>
  ["leasing", "assurance", "controle"].includes(t) ? t : t === "document" ? "documents" : "general";

export default function Dashboard() {
  const { openVehicle } = useVehicleDrawer();
  const { data: kpi, isLoading, isError, error } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const { data: dl } = useQuery({ queryKey: ["deadlines"], queryFn: () => getDeadlines() });

  const th = kpi?.deadline_thresholds || { urgent_days: 30, warning_days: 90 };
  // Moteur central : items déjà triés urgence d'abord puis chronologique
  const dated = (dl?.items || [])
    .filter((e) => e.days_remaining !== null && e.days_remaining !== undefined && e.days_remaining <= th.warning_days);
  const upcoming = dated.slice(0, 8);

  const total = kpi?.total_vehicles || 0;
  const conformes = kpi?.vehicles_conformes || 0;
  const pieData = [
    { name: "Conformes", value: conformes, color: "#10b981" },
    { name: "À traiter", value: Math.max(0, total - conformes), color: "#f59e0b" },
  ];

  return (
    <div className="space-y-8 animate-fade-in" data-testid="dashboard-page">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Tableau de bord administratif
        </h2>
        <p className="text-sm text-slate-500">
          Vue d'ensemble des contrats, assurances, contrôles et coûts de votre flotte.
        </p>
      </div>

      {isError && <QueryErrorState error={error} testId="dashboard-error" />}

      {/* KPI grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard testId="kpi-leasing-expired" label="Leasing expirés" value={!kpi ? "—" : kpi.leasing_expired} accent="red" icon={FileWarning} sub="Contrats échus" />
        <KpiCard testId="kpi-leasing-soon" label="Leasing bientôt expirés" value={!kpi ? "—" : kpi.leasing_soon} accent="amber" icon={CalendarClock} sub="≤ 90 jours" />
        <KpiCard testId="kpi-assurance-renew" label="Assurances à renouveler" value={!kpi ? "—" : kpi.assurance_renew} accent="sky" icon={ShieldCheck} sub="Renouvellement proche" />
        <KpiCard testId="kpi-controle-upcoming" label="Contrôles techniques à venir" value={!kpi ? "—" : kpi.controle_upcoming} accent="amber" icon={ClipboardCheck} sub="Expertise programmée" />
        <KpiCard testId="kpi-documents-missing" label="Véhicules · docs manquants" value={!kpi ? "—" : kpi.documents_missing} accent="red" icon={FileStack} sub="Documents requis absents" />
        <KpiCard testId="kpi-cout-leasing" label="Coût leasing mensuel" value={!kpi ? "—" : chf(kpi.cout_leasing_mensuel)} accent="slate" icon={Wallet} sub="Total flotte / mois" />
        <KpiCard testId="kpi-cout-assurance" label="Coût assurance annuel" value={!kpi ? "—" : chf(kpi.cout_assurance_annuel)} accent="slate" icon={Banknote} sub="Total flotte / an" />
        <KpiCard testId="kpi-conformes" label="Véhicules conformes" value={!kpi ? "—" : `${kpi.vehicles_conformes}/${kpi.total_vehicles}`} accent="emerald" icon={CheckCircle2} sub="Aucune alerte active" />
      </div>

      {/* KPI documents */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard testId="kpi-docs-expires" label="Échéances expirées" value={!kpi ? "—" : kpi.docs_expires ?? 0} accent="red" icon={FileX} sub="Documents & contrats" />
        <KpiCard testId="kpi-docs-expire-30" label={`Expirent ≤ ${th.urgent_days} jours`} value={!kpi ? "—" : kpi.docs_expire_30 ?? 0} accent="amber" icon={FileClock} sub="Documents & contrats" />
        <KpiCard testId="kpi-docs-expire-90" label={`Expirent ${th.urgent_days + 1}–${th.warning_days} jours`} value={!kpi ? "—" : kpi.docs_expire_31_90 ?? 0} accent="sky" icon={CalendarClock} sub="À planifier" />
        <KpiCard testId="kpi-docs-a-verifier" label="Documents à vérifier" value={!kpi ? "—" : kpi.docs_a_verifier ?? 0} accent="slate" icon={FileSearch} sub="Validation en attente" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Upcoming deadlines */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm lg:col-span-2" data-testid="upcoming-deadlines">
          <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
            <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">
              Prochaines échéances
            </h3>
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
              {dated.length} dans {th.warning_days} jours
            </span>
          </div>
          <div className="divide-y divide-slate-100">
            {upcoming.length === 0 && (
              <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
                <CheckCircle2 className="h-8 w-8 text-emerald-500" />
                <p className="text-sm font-medium text-slate-700">Aucune échéance imminente</p>
                <p className="text-xs text-slate-400">Toute la flotte est à jour sur {th.warning_days} jours.</p>
              </div>
            )}
            {upcoming.map((e, i) => {
              const t = EVENT_TYPES[e.type] || EVENT_TYPES.document || {};
              const s = lvl(e.level);
              return (
                <button
                  key={e.key || `${e.vehicle_id}-${e.type}-${i}`}
                  onClick={() => openVehicle(e.vehicle_id, tabForType(e.type))}
                  data-testid={`deadline-row-${i}`}
                  className="flex w-full items-center gap-4 px-6 py-3.5 text-left transition-colors hover:bg-slate-50"
                >
                  <span className="h-9 w-1 shrink-0 rounded-full" style={{ backgroundColor: t.color || "#94a3b8" }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{e.plaque}</span>
                      <span className="truncate text-xs text-slate-400">
                        {e.marque} {e.modele}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      <span className={cn("font-medium", t.text)}>{e.label}</span>
                      {e.category ? ` · ${e.category}` : ""} · {dateFr(e.date)}
                    </p>
                  </div>
                  <StatusBadge level={e.level} days={e.days_remaining} showDays />
                  <ArrowRight className="h-4 w-4 text-slate-300" />
                </button>
              );
            })}
          </div>
        </div>

        {/* Conformity donut */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="conformity-card">
          <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">
            Conformité de la flotte
          </h3>
          <div className="relative mx-auto mt-2 h-44 w-44">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" innerRadius={58} outerRadius={80} startAngle={90} endAngle={-270} stroke="none">
                  {pieData.map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-display text-3xl font-bold text-slate-900">
                {total ? Math.round((conformes / total) * 100) : 0}%
              </span>
              <span className="text-xs text-slate-400">conforme</span>
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-slate-600">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Conformes
              </span>
              <span className="font-semibold text-slate-900">{conformes}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 text-slate-600">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> À traiter
              </span>
              <span className="font-semibold text-slate-900">{Math.max(0, total - conformes)}</span>
            </div>
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              Les véhicules « à traiter » présentent au moins une alerte leasing, assurance ou contrôle technique.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
