import { AlertTriangle, CalendarClock, CalendarX2, Link2Off, Ban } from "lucide-react";
import { cn } from "@/lib/utils";
import { CARD_STATUS_META, EXPIRATION_META, cardStatusLabel } from "@/lib/fuelCards";
import { dateFr } from "@/lib/format";

export default function FuelCardStatusBadge({ statut, className }) {
  const m = CARD_STATUS_META[statut] || { label: statut || "—", cls: "bg-slate-100 text-slate-600 border-slate-200" };
  return (
    <span data-testid={`fuel-card-status-badge-${statut || "unknown"}`} className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-bold", m.cls, className)}>
      {cardStatusLabel(statut)}
    </span>
  );
}

// Expiration dérivée (lecture seule) : date + état calculé par les seuils Échéances du tenant — jamais un statut écrit
export function ExpirationCell({ card }) {
  const m = EXPIRATION_META[card.expiration_state] || EXPIRATION_META.sans_date;
  return (
    <div data-testid={`fuel-card-expiration-${card.id}`} className="text-sm">
      <p className={cn("font-semibold", m.cls)}>{card.expire_le ? dateFr(card.expire_le) : "—"}</p>
      <p className={cn("text-[11px]", m.cls)}>
        {m.label}{card.expiration_days != null && card.expiration_state !== "sans_date" ? ` · ${card.expiration_days < 0 ? `depuis ${-card.expiration_days} j` : `dans ${card.expiration_days} j`}` : ""}
      </p>
    </div>
  );
}

const WARN_ICON = { CARD_EXPIRED: CalendarX2, CARD_EXPIRING_SOON: CalendarClock, CARD_UNASSIGNED: Link2Off, ASSIGNMENT_INCONSISTENT: AlertTriangle, CARD_NOT_ACTIVE: Ban };
const WARN_CLS = { CARD_EXPIRED: "border-red-200 bg-red-50 text-red-700", CARD_EXPIRING_SOON: "border-amber-200 bg-amber-50 text-amber-800",
  CARD_UNASSIGNED: "border-sky-200 bg-sky-50 text-sky-800", ASSIGNMENT_INCONSISTENT: "border-orange-200 bg-orange-50 text-orange-800", CARD_NOT_ACTIVE: "border-slate-200 bg-slate-50 text-slate-600" };

export function CardWarnings({ warnings = [], compact = false, cardId }) {
  if (!warnings.length) return compact ? null : <p className="text-xs text-slate-400" data-testid={`fuel-card-warnings-none-${cardId}`}>Aucun avertissement</p>;
  return (
    <div className={cn("flex flex-wrap gap-1", compact && "gap-0.5")} data-testid={`fuel-card-warnings-${cardId}`}>
      {warnings.map((w) => {
        const Icon = WARN_ICON[w.code] || AlertTriangle;
        return (
          <span key={w.code} title={w.label} data-testid={`fuel-card-warning-${w.code}-${cardId}`}
            className={cn("inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold", WARN_CLS[w.code] || WARN_CLS.CARD_NOT_ACTIVE)}>
            <Icon className="h-3 w-3" />{!compact && w.label}
          </span>
        );
      })}
    </div>
  );
}
