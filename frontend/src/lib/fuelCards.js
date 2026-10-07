// Lot E — libellés de présentation (les codes techniques restent ceux de l'API ; parité Journal 1:1)
export const CARD_STATUSES = ["active", "suspendue", "expiree", "bloquee", "remplacee"];
export const CARD_STATUS_META = {
  active: { label: "Active", cls: "bg-emerald-100 text-emerald-800 border-emerald-200" },
  suspendue: { label: "Suspendue", cls: "bg-amber-100 text-amber-800 border-amber-200" },
  expiree: { label: "Expirée", cls: "bg-slate-200 text-slate-700 border-slate-300" },
  bloquee: { label: "Bloquée", cls: "bg-red-100 text-red-700 border-red-200" },
  remplacee: { label: "Remplacée", cls: "bg-indigo-100 text-indigo-800 border-indigo-200" },
};
export const ASSIGNMENT_TYPES = [["vehicule", "Véhicule"], ["conducteur", "Conducteur"], ["pool", "Pool"], ["autre", "Autre"]];
export const EXPIRATION_META = {
  valide: { label: "Valide", cls: "text-emerald-700" },
  bientot: { label: "Expire bientôt", cls: "text-amber-700" },
  expiree: { label: "Expirée", cls: "text-red-600" },
  sans_date: { label: "Sans date", cls: "text-slate-400" },
};
export const ARCHIVE_MODES = [["false", "Actives (non archivées)"], ["true", "Archivées"], ["all", "Toutes"]];
export const cardStatusLabel = (code) => CARD_STATUS_META[code]?.label || code || "—";
export const assignmentTypeLabel = (code) => ASSIGNMENT_TYPES.find(([c]) => c === code)?.[1] || code || "—";
export const cardLabel = (c) => c?.label || `${c?.fournisseur || "Carte"} ••••${c?.last4 || "????"}`;
export const todayIso = () => new Date().toISOString().slice(0, 10);
export const errDetail = (e, fallback = "Action impossible") => {
  const d = e?.response?.data?.detail;
  return (typeof d === "string" && d) || d?.message || fallback;
};
export const errCode = (e) => e?.response?.data?.detail?.code || null;
