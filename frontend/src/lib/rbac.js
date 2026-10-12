// Lot H — capacités FRONTEND (miroir de la matrice serveur D6 / §10bis). Le backend reste l'unique source de vérité :
// un masquage UI n'est jamais une preuve RBAC ; chaque action est re-vérifiée côté serveur (403 / 404 fail-closed).
import { getActingTenant } from "@/lib/api";

const ADMINS = ["admin", "superadmin"];
const WRITERS = [...ADMINS, "manager"];
const READERS = [...ADMINS, "read_only"];

const CAPS = {
  "vehicles.create": ADMINS,
  "vehicles.edit": WRITERS,
  "vehicles.delete": ADMINS,
  "documents.write": WRITERS,
  "documents.delete": ADMINS,
  "documents.settings": ADMINS,
  "inspections.write": WRITERS,
  "inspections.delete": ADMINS,
  "photo.write": WRITERS,
  "photo.delete": ADMINS,
  "fines.write": WRITERS,
  "fines.attachments.delete": ADMINS,
  "fuel.manual": WRITERS,
  "fuel.match": WRITERS,
  "anomalies.decide": WRITERS,
  "reconciliations.justify": WRITERS,
  "drivers.manage": ADMINS,
  "assignments.write": WRITERS,
  "cards.manage": ADMINS,
  "cards.history": READERS,
  "statements.write": ADMINS,
  "imports.write": ADMINS,
  "legacy.write": ADMINS,
  "archives.write": ADMINS,
  settings: ADMINS,
  "settings.read": READERS,
  integrations: ADMINS,
  "alerts.admin": ADMINS,
  "pages.imports": READERS,
  "pages.statements": READERS,
  "pages.archives": READERS,
  "pages.legacy": READERS,
  "pages.integrity": READERS,
  "ai.use": WRITERS,
  console: ["superadmin"],
};

export const can = (user, cap) => !!user && (CAPS[cap] || []).includes(user.role);
export const isDriver = (user) => user?.role === "driver";
export const isManager = (user) => user?.role === "manager";
export const DRIVER_HOME = "/mes-pleins";
export const ROLE_LABELS = { superadmin: "super admin", admin: "admin", manager: "manager", read_only: "lecture seule", driver: "chauffeur" };

// Modules fonctionnels activés par le Super Admin pour le client (miroir de backend/tenant_modules.py).
// Clé absente / payload absent = module ACTIVÉ. Le serveur reste la source de vérité (403 MODULE_DISABLED).
export const MODULES = [
  { key: "vehicles", label: "Véhicules", core: true, note: "Module socle : toutes les fiches véhicules deviennent inaccessibles pour ce client (documents, énergie, amendes et conducteurs restent en base mais ne sont plus consultables)." },
  { key: "documents", label: "Documents", note: "Échéances, Coûts, Alertes et Intégrité s'appuient sur les documents : leurs vues documentaires seront vides pour ce client." },
  { key: "deadlines", label: "Échéances", note: "Le tableau de bord n'affichera plus les prochaines actions ni les KPI d'échéances." },
  { key: "costs", label: "Coûts", note: "Le KPI « Coût annuel flotte » et l'onglet Coûts des véhicules seront masqués." },
  { key: "energy", label: "Énergie", note: "Cartes carburant, transactions, imports, rapprochements et alertes cartes seront masqués." },
  { key: "drivers", label: "Conducteurs", note: "Amendes et Énergie n'afficheront plus l'attribution conducteur ; les affectations sont conservées." },
  { key: "fines", label: "Amendes", note: "Échéances et alertes d'amendes masquées ; les amendes sont conservées." },
  { key: "ai", label: "Assistant IA", note: "Assistant, résumés de documents, courriers d'amende et synthèses de conformité IA indisponibles." },
  { key: "alerts", label: "Alertes", note: "Aucune alerte visible ni envoyée au client (alertes historiques conservées)." },
  { key: "integrity", label: "Intégrité", note: "La page Intégrité et le rapprochement télématique seront masqués." },
];
export const moduleOn = (user, key) => !key || !user?.tenant_modules || user.tenant_modules[key] !== false;
// Console Super Admin « pure » : superadmin sans client sélectionné (mode assistance = acting tenant présent).
export const isConsoleMode = (user) => user?.role === "superadmin" && !getActingTenant()?.id;
export const isAssistMode = (user) => user?.role === "superadmin" && !!getActingTenant()?.id;
