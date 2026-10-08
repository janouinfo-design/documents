// Phase 4C — Lot F : libellés / styles des statuts d'import, de rattachement et des anomalies (miroir des enums backend)
export const ROW_STATUS_META = {
  pending: { label: "En attente", cls: "bg-slate-100 text-slate-600 border-slate-200" },
  ok: { label: "Valide", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  invalid: { label: "Invalide", cls: "bg-red-50 text-red-700 border-red-200" },
  duplicate: { label: "Doublon", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  unknown_card: { label: "Carte non résolue", cls: "bg-sky-50 text-sky-800 border-sky-200" },
  amount_mismatch: { label: "Montant incohérent", cls: "bg-orange-50 text-orange-800 border-orange-200" },
  unknown_vehicle: { label: "Véhicule non résolu", cls: "bg-rose-50 text-rose-800 border-rose-200" },
};
export const IMPORTABLE = ["ok", "amount_mismatch", "unknown_card"];

export const MATCH_META = {
  auto_matched: { label: "Rattaché auto", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  matched_review: { label: "À vérifier", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  unmatched: { label: "Non rattaché", cls: "bg-rose-50 text-rose-800 border-rose-200" },
  manual: { label: "Manuel", cls: "bg-slate-900 text-white border-slate-900" },
};

export const CARD_RES_META = {
  found: { label: "Carte trouvée", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  ambiguous: { label: "Carte ambiguë", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  not_found: { label: "Carte introuvable", cls: "bg-rose-50 text-rose-800 border-rose-200" },
  manual: { label: "Carte choisie", cls: "bg-slate-900 text-white border-slate-900" },
  none: { label: "Sans carte", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};

export const ANOMALY_TYPE_LABELS = {
  depassement_reservoir: "Dépassement réservoir", carte_inactive: "Carte inactive", double_plein: "Double plein", montant_inhabituel: "Montant inhabituel",
  incoherence_montant: "Quantité × prix ≠ montant", odometre_incoherent: "Kilométrage incohérent", plaque_differente: "Plaque différente",
  carte_vehicule_different: "Carte ↔ véhicule différent",
};
export const SEVERITY_META = {
  critical: { label: "Critique", cls: "bg-red-50 text-red-700 border-red-200" },
  warning: { label: "Avertissement", cls: "bg-amber-50 text-amber-800 border-amber-200" },
};
export const ANOMALY_STATUS_META = {
  ouverte: { label: "Ouverte", cls: "bg-rose-50 text-rose-800 border-rose-200" },
  justifiee: { label: "Justifiée", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  corrigee: { label: "Corrigée", cls: "bg-sky-50 text-sky-800 border-sky-200" },
  rejetee: { label: "Rejetée", cls: "bg-slate-100 text-slate-600 border-slate-200" },
};
export const DECISIONS = [
  { code: "justify", label: "Justifier", hint: "L'écart est expliqué et accepté (motif conservé)" },
  { code: "correct", label: "Corriger", hint: "La donnée a été corrigée manuellement" },
  { code: "reject", label: "Rejeter", hint: "Fausse alerte" },
];
export const REVIEW_REASON_LABELS = {
  CARD_INACTIVE: "Carte inactive / non utilisable", CARD_AMBIGUOUS: "Plusieurs cartes possibles", MULTIPLE_CARD_ASSIGNMENTS: "Plusieurs affectations à la date",
  PLATE_AMBIGUOUS: "Plaque correspondant à plusieurs véhicules", TIE: "Égalité entre candidats", FUEL_INCOMPATIBLE: "Carburant incompatible",
  BELOW_REVIEW_THRESHOLD: "Score insuffisant", DIFFERENT_FROM_TRANSACTION_VEHICLE: "Différent du véhicule de la transaction",
};
export const metaOf = (map, key) => map[key] || { label: key || "—", cls: "bg-slate-100 text-slate-600 border-slate-200" };
