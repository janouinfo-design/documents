import { cn } from "@/lib/utils";

export const DOC_STATUT_META = {
  VALIDE: { label: "Valide", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  EXPIRE_BIENTOT: { label: "Expire bientôt", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  EXPIRE: { label: "Expiré", cls: "bg-red-50 text-red-700 border-red-200" },
  A_VERIFIER: { label: "À vérifier", cls: "bg-violet-50 text-violet-700 border-violet-200" },
  EN_RENOUVELLEMENT: { label: "En renouvellement", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  ARCHIVE: { label: "Archivé", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};

export const DocStatutBadge = ({ statut }) => {
  const m = DOC_STATUT_META[statut] || DOC_STATUT_META.VALIDE;
  return (
    <span data-testid={`doc-statut-${statut?.toLowerCase()}`}
      className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold", m.cls)}>
      {m.label}
    </span>
  );
};
