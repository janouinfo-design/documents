// Lot H — capacités FRONTEND (miroir de la matrice serveur D6 / §10bis). Le backend reste l'unique source de vérité :
// un masquage UI n'est jamais une preuve RBAC ; chaque action est re-vérifiée côté serveur (403 / 404 fail-closed).
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
