import { cn } from "@/lib/utils";
import { lvl } from "@/lib/status";
import { daysLabel } from "@/lib/format";

export default function StatusBadge({ level = "unknown", days, showDays = false, className, testId }) {
  const s = lvl(level);
  return (
    <span
      data-testid={testId}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold",
        s.badge,
        className
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      {showDays && (days !== null && days !== undefined) ? daysLabel(days) : s.label}
    </span>
  );
}
