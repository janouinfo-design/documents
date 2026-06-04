// Status / alert level mapping shared across the app
export const LEVELS = {
  expired: {
    label: "Expiré",
    short: "Expiré",
    dot: "bg-red-500",
    text: "text-red-700",
    badge: "bg-red-50 text-red-700 border-red-200",
    bar: "bg-red-500",
    ring: "ring-red-200",
    accent: "#ef4444",
  },
  critical: {
    label: "Urgent",
    short: "< 30 j",
    dot: "bg-red-500",
    text: "text-red-700",
    badge: "bg-red-50 text-red-700 border-red-200",
    bar: "bg-red-500",
    ring: "ring-red-200",
    accent: "#ef4444",
  },
  warning: {
    label: "Bientôt",
    short: "< 90 j",
    dot: "bg-amber-500",
    text: "text-amber-700",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    bar: "bg-amber-500",
    ring: "ring-amber-200",
    accent: "#f59e0b",
  },
  ok: {
    label: "Conforme",
    short: "Conforme",
    dot: "bg-emerald-500",
    text: "text-emerald-700",
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
    bar: "bg-emerald-500",
    ring: "ring-emerald-200",
    accent: "#10b981",
  },
  unknown: {
    label: "Non renseigné",
    short: "—",
    dot: "bg-slate-300",
    text: "text-slate-500",
    badge: "bg-slate-50 text-slate-500 border-slate-200",
    bar: "bg-slate-300",
    ring: "ring-slate-200",
    accent: "#cbd5e1",
  },
};

export const lvl = (level) => LEVELS[level] || LEVELS.unknown;

export const EVENT_TYPES = {
  leasing: { label: "Leasing", color: "#6366f1", bg: "bg-indigo-50", text: "text-indigo-700", border: "border-indigo-200" },
  assurance: { label: "Assurance", color: "#0ea5e9", bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200" },
  controle: { label: "Contrôle technique", color: "#f59e0b", bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  expertise: { label: "Expertise", color: "#8b5cf6", bg: "bg-violet-50", text: "text-violet-700", border: "border-violet-200" },
  maintenance: { label: "Maintenance", color: "#10b981", bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-200" },
};
