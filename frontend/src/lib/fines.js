// Phase 4C — Lot D : référentiel UI des amendes (codes techniques = backend/fines.py, libellés FR uniquement ici)
export const FINE_STATUSES = ["recue", "a_analyser", "conducteur_a_identifier", "en_attente_conducteur", "contestee",
  "a_payer", "payee", "refacturee", "cloturee", "annulee"];

export const FINE_STATUS_META = {
  recue: { label: "Reçue", cls: "bg-sky-50 text-sky-700 border-sky-200" },
  a_analyser: { label: "À analyser", cls: "bg-violet-50 text-violet-700 border-violet-200" },
  conducteur_a_identifier: { label: "Conducteur à identifier", cls: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200" },
  en_attente_conducteur: { label: "En attente conducteur", cls: "bg-indigo-50 text-indigo-700 border-indigo-200" },
  contestee: { label: "Contestée", cls: "bg-orange-50 text-orange-700 border-orange-200" },
  a_payer: { label: "À payer", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  payee: { label: "Payée", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  refacturee: { label: "Refacturée", cls: "bg-teal-50 text-teal-700 border-teal-200" },
  cloturee: { label: "Clôturée", cls: "bg-slate-100 text-slate-600 border-slate-200" },
  annulee: { label: "Annulée", cls: "bg-slate-200 text-slate-700 border-slate-300 line-through decoration-slate-400" },
};

export const PAID_STATUSES = ["payee", "refacturee"];
export const DEADLINE_INACTIVE = ["payee", "refacturee", "cloturee", "annulee"];

export const PIECE_TYPES = [["pdf", "PDF"], ["photo", "Photo"], ["courrier", "Courrier"], ["contestation", "Contestation"],
  ["preuve_paiement", "Preuve de paiement"], ["libre", "Libre"]];
export const PRIORITIES = [["low", "Basse"], ["normal", "Normale"], ["high", "Haute"], ["urgent", "Urgente"]];
// Codes Journal PROUVÉS (4B) — enum complet figé après lecture seule du code Journal, aucun code inventé ici
// Enum Journal prouvée (backend/app/routes/fines.py · INFRACTION_TYPES, 8 codes, ordre source) — codes techniques en API, libellés FR = présentation.
export const INFRACTION_TYPES = [["speeding", "Excès de vitesse"], ["parking", "Stationnement"], ["red_light", "Feu rouge"], ["toll", "Péage"],
  ["forbidden_zone", "Zone interdite"], ["phone", "Téléphone au volant"], ["seatbelt", "Ceinture de sécurité"], ["other", "Autre"]];

export const fineStatusLabel = (code) => FINE_STATUS_META[code]?.label || code || "—";
export const infractionLabel = (code) => INFRACTION_TYPES.find(([c]) => c === code)?.[1] || code || "—";
export const priorityLabel = (code) => PRIORITIES.find(([c]) => c === code)?.[1] || "Normale";
export const todayIso = () => new Date().toISOString().slice(0, 10);
export const errDetail = (e, fallback = "Action impossible") => {
  const d = e?.response?.data?.detail;
  return (typeof d === "string" && d) || d?.message || fallback;
};
