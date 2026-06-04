import { cn } from "@/lib/utils";

export default function AlertChips({ days, thresholds = [180, 90, 30], testId }) {
  return (
    <div data-testid={testId} className="flex flex-wrap items-center gap-2">
      {thresholds.map((t) => {
        const triggered = days !== null && days !== undefined && days <= t;
        const tone = t <= 30 ? "red" : t <= 90 ? "amber" : "slate";
        const active = {
          red: "bg-red-50 text-red-700 border-red-200",
          amber: "bg-amber-50 text-amber-700 border-amber-200",
          slate: "bg-slate-100 text-slate-700 border-slate-200",
        }[tone];
        const dot = {
          red: "bg-red-500",
          amber: "bg-amber-500",
          slate: "bg-slate-400",
        }[tone];
        return (
          <span
            key={t}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors",
              triggered ? active : "border-slate-200 bg-white text-slate-400"
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", triggered ? dot : "bg-slate-300")} />
            {t} jours
          </span>
        );
      })}
    </div>
  );
}
