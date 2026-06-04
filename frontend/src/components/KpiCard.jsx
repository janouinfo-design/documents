import { cn } from "@/lib/utils";

const ACCENTS = {
  red: { border: "border-l-red-500", icon: "bg-red-50 text-red-600" },
  amber: { border: "border-l-amber-500", icon: "bg-amber-50 text-amber-600" },
  emerald: { border: "border-l-emerald-500", icon: "bg-emerald-50 text-emerald-600" },
  slate: { border: "border-l-slate-800", icon: "bg-slate-100 text-slate-700" },
  indigo: { border: "border-l-indigo-500", icon: "bg-indigo-50 text-indigo-600" },
  sky: { border: "border-l-sky-500", icon: "bg-sky-50 text-sky-600" },
};

export default function KpiCard({ label, value, sub, icon: Icon, accent = "slate", onClick, testId }) {
  const a = ACCENTS[accent] || ACCENTS.slate;
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "group flex flex-col justify-between gap-4 rounded-xl border border-slate-200 border-l-4 bg-white p-5 text-left shadow-sm transition-all duration-200",
        a.border,
        onClick && "cursor-pointer hover:-translate-y-0.5 hover:shadow-md"
      )}
    >
      <div className="flex items-start justify-between">
        <p className="max-w-[80%] text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          {label}
        </p>
        {Icon && (
          <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", a.icon)}>
            <Icon className="h-[18px] w-[18px]" />
          </span>
        )}
      </div>
      <div>
        <p className="font-display text-3xl font-bold tracking-tight text-slate-900">{value}</p>
        {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
      </div>
    </Comp>
  );
}
