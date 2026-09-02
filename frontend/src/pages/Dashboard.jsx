import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import {
  FileX,
  FileClock,
  FileStack,
  FileSearch,
  CheckCircle2,
  Banknote,
  ArrowRight,
  CalendarDays,
} from "lucide-react";
import { getDashboard, getDeadlines, getCosts } from "@/lib/api";
import { chf, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import StatusBadge from "@/components/StatusBadge";
import QueryErrorState from "@/components/QueryErrorState";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EVENT_TYPES, DEADLINE_STATUT_META } from "@/lib/status";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const tabForType = (t) =>
  ["leasing", "assurance", "controle"].includes(t) ? t : t === "document" ? "documents" : "general";

function SecondaryConformityCard({ conformes, total, onClick }) {
  const pct = total ? Math.round((conformes / total) * 100) : 0;
  const pieData = [
    { name: "Conformes", value: conformes, color: "#10b981" },
    { name: "À traiter", value: Math.max(0, total - conformes), color: "#f59e0b" },
  ];
  return (
    <button onClick={onClick} data-testid="kpi-conformes"
            className="flex min-h-[120px] items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <div>
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" /> Véhicules conformes
        </p>
        <p className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900">
          {conformes}/{total} <span className="text-base font-semibold text-slate-400">· {pct} %</span>
        </p>
        <p className="mt-1 text-xs text-slate-500">Sans alerte leasing, assurance ou contrôle</p>
      </div>
      <div className="relative h-20 w-20 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} dataKey="value" innerRadius={26} outerRadius={38} startAngle={90} endAngle={-270} stroke="none">
              {pieData.map((d, i) => <Cell key={i} fill={d.color} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs font-bold text-slate-700">
          {pct}%
        </span>
      </div>
    </button>
  );
}

function SecondaryCostCard({ costs, onClick }) {
  const available = costs && costs.totals && typeof costs.totals.annuel === "number";
  return (
    <button onClick={onClick} data-testid="kpi-cout-annuel"
            className="flex min-h-[120px] items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <div>
        <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          <Banknote className="h-4 w-4 text-slate-700" /> Coût annuel flotte
        </p>
        <p className="mt-2 font-display text-2xl font-bold tracking-tight text-slate-900">
          {available ? chf(costs.totals.annuel) : "—"}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          {available
            ? `${costs.totals.postes_actifs} poste(s) actif(s) · ${costs.year} — voir l'analyse détaillée`
            : "Donnée non disponible — voir la page Coûts"}
        </p>
      </div>
      <ArrowRight className="h-5 w-5 shrink-0 text-slate-300" />
    </button>
  );
}

export default function Dashboard() {
  const { openVehicle } = useVehicleDrawer();
  const navigate = useNavigate();
  const go = (path) => () => navigate(path);
  const { data: kpi, isLoading, isError, error } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const { data: dl, isError: dlIsError, error: dlError } = useQuery({ queryKey: ["deadlines"], queryFn: () => getDeadlines() });
  const { data: costs } = useQuery({ queryKey: ["costs"], queryFn: () => getCosts() });

  const th = kpi?.deadline_thresholds || { urgent_days: 30, warning_days: 90 };
  const summary = dl?.summary;

  // Prochaines actions : moteur central (déjà trié expirés → urgents → à planifier, puis chronologique)
  const actionable = (dl?.items || []).filter((e) => ["EXPIRE", "URGENT"].includes(e.statut));
  const planify = (dl?.items || []).filter((e) => e.statut === "A_PLANIFIER");
  const actions = [...actionable, ...planify].slice(0, 8);

  const total = kpi?.total_vehicles || 0;
  const conformes = kpi?.vehicles_conformes || 0;

  return (
    <div className="space-y-8 animate-fade-in" data-testid="dashboard-page">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Tableau de bord administratif
        </h2>
        <p className="text-sm text-slate-500">
          Pilotage rapide — le détail vit dans Échéances, Documents et Coûts.
        </p>
      </div>

      {isError && <QueryErrorState error={error} testId="dashboard-error" />}
      {dlIsError && <QueryErrorState error={dlError} testId="dashboard-deadlines-error" />}

      {/* KPI prioritaires — y a-t-il un problème, que traiter maintenant ? */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard testId="kpi-expired" label="Éléments expirés"
                 value={!summary ? "—" : summary.expired} accent="red" icon={FileX}
                 sub="Documents & contrats, toutes catégories"
                 onClick={go("/timeline?statut=EXPIRE")} />
        <KpiCard testId="kpi-urgent" label={`À traiter ≤ ${th.urgent_days} jours`}
                 value={!summary ? "—" : summary.urgent} accent="amber" icon={FileClock}
                 sub="Toutes catégories, seuil du compte"
                 onClick={go("/timeline?statut=URGENT")} />
        <KpiCard testId="kpi-docs-manquants" label="Documents manquants"
                 value={!kpi ? "—" : kpi.documents_missing ?? 0} accent="red" icon={FileStack}
                 sub="Véhicules avec documents requis absents"
                 onClick={go("/documents")} />
        <KpiCard testId="kpi-docs-a-verifier" label="Documents à vérifier"
                 value={!kpi ? "—" : kpi.docs_a_verifier ?? 0} accent="slate" icon={FileSearch}
                 sub="Validation en attente"
                 onClick={go("/documents?statut=A_VERIFIER")} />
      </div>

      {/* KPI secondaires — conformité & finance */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SecondaryConformityCard conformes={conformes} total={total} onClick={go("/integrite")} />
        <SecondaryCostCard costs={costs} onClick={go("/couts")} />
      </div>

      {/* Prochaines actions — les plus urgentes d'abord, puis chronologique */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="next-actions">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">
            Prochaines actions
          </h3>
          <button onClick={go("/timeline")} data-testid="see-all-deadlines-btn"
                  className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 underline-offset-2 hover:underline">
            Voir toutes les échéances <ArrowRight className="h-4 w-4" />
          </button>
        </div>
        {(!isLoading && actions.length === 0) ? (
          <div className="flex flex-col items-center gap-2 px-6 py-12 text-center" data-testid="next-actions-empty">
            <CheckCircle2 className="h-8 w-8 text-emerald-500" />
            <p className="text-sm font-medium text-slate-700">Rien à traiter maintenant</p>
            <p className="text-xs text-slate-400">Aucun élément expiré ni urgent sur la flotte.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table data-testid="next-actions-table">
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead>Véhicule</TableHead>
                  <TableHead>Élément / document</TableHead>
                  <TableHead>Catégorie</TableHead>
                  <TableHead>Échéance</TableHead>
                  <TableHead>Jours restants</TableHead>
                  <TableHead>Statut</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {actions.map((e, i) => {
                  const t = EVENT_TYPES[e.type] || EVENT_TYPES.document || {};
                  return (
                    <TableRow key={e.key || i} data-testid={`next-action-row-${i}`}
                              onClick={() => openVehicle(e.vehicle_id, tabForType(e.type))}
                              className="cursor-pointer hover:bg-slate-50">
                      <TableCell>
                        <span className="text-sm font-semibold text-slate-900">{e.plaque || "—"}</span>
                        <p className="text-xs text-slate-400">{[e.marque, e.modele].filter(Boolean).join(" ")}</p>
                      </TableCell>
                      <TableCell className="max-w-[240px] truncate text-sm text-slate-700">{e.label}</TableCell>
                      <TableCell>
                        <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", t.bg, t.text)}>
                          {e.category || t.label}
                        </span>
                      </TableCell>
                      <TableCell className={cn("text-sm", e.statut === "EXPIRE" ? "font-semibold text-red-600" : "text-slate-600")}>
                        {e.date ? dateFr(e.date) : "—"}
                      </TableCell>
                      <TableCell className="text-sm text-slate-600">
                        {e.days_remaining == null ? "—"
                          : e.days_remaining < 0 ? `Échu depuis ${-e.days_remaining} j`
                          : `${e.days_remaining} j`}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {["SANS_ECHEANCE", "DATE_INVALIDE"].includes(e.statut) ? (
                          <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                            {DEADLINE_STATUT_META[e.statut]?.label}
                          </span>
                        ) : (
                          <StatusBadge level={e.level} days={e.days_remaining} showDays />
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
        {actions.length > 0 && (
          <div className="border-t border-slate-100 px-6 py-3">
            <button onClick={go("/timeline")} data-testid="see-all-deadlines-footer-btn"
                    className="flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-slate-800">
              <CalendarDays className="h-4 w-4" /> Voir toutes les échéances
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
