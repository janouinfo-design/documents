// Phase 4C — Lot G : libellés / styles des rapprochements, décomptes et blockers (miroir des enums backend fuel_statements.py)
export const RECO_STATUS_META = {
  OK: { label: "Cohérent", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  A_CONTROLER: { label: "À contrôler", cls: "bg-rose-50 text-rose-800 border-rose-200" },
  INDICATIF: { label: "INDICATIF", cls: "bg-sky-50 text-sky-800 border-sky-200" },
  IMPOSSIBLE: { label: "Impossible", cls: "bg-slate-100 text-slate-600 border-slate-200" },
};
export const CONSO_SOURCE_META = {
  can: { label: "CAN mesuré", cls: "bg-emerald-600 text-white border-emerald-600" },
  unavailable: { label: "Aucune mesure", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};
export const STATEMENT_STATUS_META = {
  brouillon: { label: "Brouillon", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  cloture: { label: "Clôturé", cls: "bg-slate-900 text-white border-slate-900" },
};
export const STATEMENT_TYPE_META = {
  regulier: { label: "Régulier", cls: "bg-slate-100 text-slate-700 border-slate-200" },
  correctif: { label: "Correctif", cls: "bg-violet-50 text-violet-800 border-violet-200" },
};
export const BLOCKER_META = {
  pending_fx: { label: "Conversion CHF en attente", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  matched_review: { label: "Véhicule à vérifier", cls: "bg-orange-50 text-orange-800 border-orange-200" },
  unmatched: { label: "Véhicule non rattaché", cls: "bg-rose-50 text-rose-800 border-rose-200" },
  open_anomaly: { label: "Anomalie ouverte", cls: "bg-red-50 text-red-700 border-red-200" },
  forced_duplicate: { label: "Doublon forcé", cls: "bg-fuchsia-50 text-fuchsia-800 border-fuchsia-200" },
};
export const na = (v, suffix = "", digits = 2) => (v === null || v === undefined ? "N/A" : `${typeof v === "number" ? Number(v).toLocaleString("fr-CH", { maximumFractionDigits: digits }) : v}${suffix}`);
export const signed = (v, suffix = "", digits = 2) => (v === null || v === undefined ? "N/A" : `${v > 0 ? "+" : ""}${Number(v).toLocaleString("fr-CH", { maximumFractionDigits: digits })}${suffix}`);
export const periodLabel = (p) => (p ? new Date(`${p}-01T00:00:00`).toLocaleDateString("fr-CH", { month: "long", year: "numeric" }) : "—");
export const currentPeriod = () => new Date().toISOString().slice(0, 7);
export const shiftPeriod = (p, d) => { const [y, m] = p.split("-").map(Number); const dt = new Date(y, m - 1 + d, 1); return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`; };
export const periodOptions = (n = 18) => Array.from({ length: n }, (_, i) => shiftPeriod(currentPeriod(), -i));
export const fmtDateTime = (s) => (s ? new Date(s).toLocaleString("fr-CH") : "—");
export const LOCK_CODE = "STATEMENT_LOCKED";
// Message métier exploitable pour toute erreur API Lot G (403 / 404 / 409 STATEMENT_LOCKED / 422 / réseau) — jamais un « Une erreur est survenue » nu
export const apiError = (e, fallback = "Action impossible") => {
  if (!e?.response) return "Serveur injoignable — vérifiez votre connexion puis réessayez.";
  const status = e.response.status;
  const d = e.response.data?.detail;
  if (status === 403) return "Vous n'avez pas les droits nécessaires pour effectuer cette action.";
  if (status === 404) return (typeof d === "string" && d) || "Élément introuvable ou inaccessible dans ce tenant.";
  if (status === 409 && d?.code === LOCK_CODE) {
    const parts = [d.message || "Décompte clôturé — données verrouillées."];
    if (d.statement_number || d.statement_id) parts.push(`décompte ${d.statement_number || d.statement_id}`);
    if (d.period_month) parts.push(`période ${d.period_month}`);
    if (d.blocked_fields?.length) parts.push(`champs protégés : ${d.blocked_fields.join(", ")}`);
    return parts.join(" · ");
  }
  if (status === 422 && Array.isArray(d)) return d.map((x) => `${(x.loc || []).slice(-1)[0] || "champ"} : ${x.msg}`).join(" ; ");
  if (typeof d === "string" && d) return d;
  if (d?.message) return d.message;
  if (status >= 500) return "Erreur serveur — réessayez dans un instant.";
  return fallback;
};
export const FormError = ({ error, testId }) => (error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800" role="alert" data-testid={testId}>{error}</p> : null);
export const dateFrOrDash = (s) => (s ? new Date(s).toLocaleDateString("fr-CH") : "—");
