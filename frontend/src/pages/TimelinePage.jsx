import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, CalendarDays } from "lucide-react";
import { getTimeline } from "@/lib/api";
import { dateFr, daysLabel } from "@/lib/format";
import { EVENT_TYPES, lvl } from "@/lib/status";
import StatusBadge from "@/components/StatusBadge";
import QueryErrorState from "@/components/QueryErrorState";
import { cn } from "@/lib/utils";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const VIEWS = [
  { key: "month", label: "Mois", months: 1 },
  { key: "quarter", label: "Trimestre", months: 3 },
  { key: "year", label: "Année", months: 12 },
];

const tabForType = (t) => (t === "leasing" ? "leasing" : t === "assurance" ? "assurance" : t === "controle" ? "controle" : "general");

export default function TimelinePage() {
  const { openVehicle } = useVehicleDrawer();
  const [view, setView] = useState("quarter");
  const { data: events = [], isLoading, isError, error } = useQuery({ queryKey: ["timeline"], queryFn: getTimeline });

  const months = VIEWS.find((v) => v.key === view).months;
  const horizon = new Date();
  horizon.setMonth(horizon.getMonth() + months);

  const visible = events.filter((e) => new Date(e.date) <= horizon);

  // group by year-month
  const groups = {};
  visible.forEach((e) => {
    const d = new Date(e.date);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleDateString("fr-CH", { month: "long", year: "numeric" });
    if (!groups[key]) groups[key] = { label, items: [], overdue: new Date(e.date) < new Date() };
    groups[key].items.push(e);
  });
  const sortedKeys = Object.keys(groups).sort();

  return (
    <div className="space-y-6 animate-fade-in" data-testid="timeline-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Timeline des échéances
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Fin de leasing, assurance, expertise, contrôle technique et maintenance.
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1" data-testid="timeline-view-toggle">
          {VIEWS.map((v) => (
            <button
              key={v.key}
              onClick={() => setView(v.key)}
              data-testid={`view-${v.key}`}
              className={cn(
                "rounded-md px-4 py-1.5 text-sm font-medium transition-all",
                view === v.key ? "bg-slate-900 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(EVENT_TYPES).map(([k, t]) => (
          <span key={k} className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: t.color }} />
            {t.label}
          </span>
        ))}
      </div>

      {isError && <QueryErrorState error={error} testId="timeline-error" />}

      {isLoading && <p className="text-sm text-slate-400">Chargement…</p>}

      {!isLoading && sortedKeys.length === 0 && (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <CalendarDays className="h-8 w-8 text-slate-300" />
          <p className="text-sm font-medium text-slate-600">Aucune échéance sur cette période</p>
        </div>
      )}

      <div className="space-y-8">
        {sortedKeys.map((key) => {
          const g = groups[key];
          return (
            <div key={key} data-testid={`timeline-month-${key}`}>
              <div className="mb-3 flex items-center gap-3">
                <CalendarClock className="h-4 w-4 text-slate-400" />
                <h3 className="font-display text-lg font-semibold capitalize tracking-tight text-slate-900">
                  {g.label}
                </h3>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">
                  {g.items.length}
                </span>
              </div>
              <div className="relative space-y-3 border-l-2 border-slate-100 pl-5">
                {g.items.sort((a, b) => new Date(a.date) - new Date(b.date)).map((e, i) => {
                  const t = EVENT_TYPES[e.type] || {};
                  return (
                    <button
                      key={`${e.vehicle_id}-${e.type}-${i}`}
                      onClick={() => openVehicle(e.vehicle_id, tabForType(e.type))}
                      data-testid={`timeline-event-${key}-${i}`}
                      className="group relative flex w-full items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-md"
                    >
                      <span
                        className="absolute -left-[27px] top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-white ring-2"
                        style={{ backgroundColor: t.color, boxShadow: `0 0 0 2px ${t.color}33` }}
                      />
                      <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xs font-bold", t.bg, t.text)}>
                        {new Date(e.date).getDate()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-900">{e.plaque}</span>
                          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", t.bg, t.text)}>{t.label}</span>
                        </div>
                        <p className="text-xs text-slate-500">{e.label} · {dateFr(e.date)} · {e.marque} {e.modele}</p>
                      </div>
                      <StatusBadge level={e.level} days={e.days_remaining} showDays />
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
