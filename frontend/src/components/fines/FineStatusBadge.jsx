import { cn } from "@/lib/utils";
import { FINE_STATUS_META, fineStatusLabel } from "@/lib/fines";

// Badge du statut métier (10 valeurs) — même code technique que le backend, libellé FR.
export default function FineStatusBadge({ status, late = false, className }) {
  const m = FINE_STATUS_META[status] || { label: fineStatusLabel(status), cls: "bg-slate-100 text-slate-600 border-slate-200" };
  const isLate = late && status === "a_payer";
  return (
    <span data-testid={`fine-status-badge-${status}`}
      className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold",
        isLate ? "bg-red-50 text-red-700 border-red-200" : m.cls, className)}>
      {isLate ? "En retard · à payer" : m.label}
    </span>
  );
}
