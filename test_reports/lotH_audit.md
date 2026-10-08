# LOT H — AUDIT READ-ONLY DE L'EXISTANT (rôles / RBAC / affectations / vues « mes… »)

Date : 2026-06 · Lecture seule (aucun code, aucune donnée modifiée) · Références : `docs/PHASE4C_SPECIFICATION.md` §7 (4C-7), D6, §10bis matrice ; `backend/auth.py`, `backend/server.py`, `backend/fines.py`, `backend/drivers.py`, `frontend/src/{App.js, context/AuthContext.jsx, components/Layout.jsx, components/admin/ClientUsers.jsx, pages/*, components/*}` ; DB preview (lecture).

## 1. Rôles actuels
| Source | Constat |
|---|---|
| `users.role` (DB, tous tenants) | `admin` 13 · `superadmin` 1 · `read_only` 8 — **0 `manager`, 0 `driver`** ; aucun `users.driver_id` |
| Enum acceptée API console (`server.py:8252`, `:8287`) | `("admin", "read_only")` → 422 sinon ; **superadmin seul** peut créer/modifier des utilisateurs (`admin_router`, `require_superadmin`) |
| Provisioning SSO Navixy (`server.py:229`) | nouvel utilisateur → `read_only` forcé |
| Seeds (`auth.py:134-188`) | superadmin `.env` (tenant `default`) + superadmin plateforme (`platform`) ; tout autre `superadmin` hérité → `admin` |
| Jeton | JWT HS256 24 h (`type=access`, `tv`=token_version), jeton `file` 10 min restreint à `/api/files/`, `/api/reports/` ; SSO 60 min |

## 2. RBAC backend
- **Couche 1 — `require_auth` (`server.py:71-96`)** : résout le tenant (`superadmin` + `X-Acting-Tenant` = override), bloque tenant `disabled`, module `documents=false` → 403, **`read_only` → 403 sur toute méthode ≠ GET/HEAD/OPTIONS** (hors `/api/auth`). Aucune autre règle de rôle.
- **Couche 2 — `require_roles(*roles)` (`server.py:833`)** : `superadmin` passe toujours ; sinon `role ∈ roles`. **43 usages, tous `require_roles("admin")`** (Lots A–G : drivers 4, driver-assignments 1, fuel 14, fuel-cards 6, fuel-card-assignments 1, fuel-transactions 2, legacy 5, tenants 4, tenant-settings 2, settings 1, users 1, documents 3 (amendes), vehicles 3, vehicles-archive 1, doc-requirements 1…). `_require_admin_role(request)` ×5 (doc-categories ×3, settings/deadlines, +1). `require_superadmin` : console `/api/admin/**`.
- **Couche 0 (absence de garde explicite)** : **32 routes mutantes protégées uniquement par le middleware read_only** (Phases 1–3 + intégrations) : `POST/PUT/DELETE /vehicles…` (create, update, **delete**, photo delete/from-document/navixy push/import, reservoir/conso/co2 suggest+apply, enrich-technical ×4, navixy push), `PATCH/DELETE /documents/{id}`, `POST /documents/{id}/validate`, `POST /vehicles/{id}/inspections`, `DELETE /inspections/{id}`, `POST /vehicles-archive/{id}/restore`, `POST /navixy/sync`, `POST /integrations/navixy/link|create-vehicle`, `POST /astra/import`, `POST /alerts/run`, `POST /demo/fill-admin`. → **tout rôle non `read_only` passe** : un futur `manager` pourrait supprimer (D6 : ✘), lancer sync/intégrations/import ASTRA (D6 paramètres : ✘) ; un futur `driver` passerait partout.
- **DELETE existants (6)** : `vehicles/{id}`, `vehicles/{id}/photo`, `documents/{id}`, `inspections/{id}` = middleware seul ; `doc-categories/{id}`, `documents/{id}/attachments/{att}` = garde explicite admin.
- **`notes_internes` (D6.3)** : `fines.strip_internal(doc, role)` (`fines.py:189`) ne masque que pour **`read_only`** ; appliqué sur 7 points de sérialisation ; exports : toujours retirées (`server.py:3743`) ; valeurs jamais journalisées. → à étendre à `driver`.
- **Audit** : `audit()` enregistre `user` = email (pas le rôle) ; tenant-scopé.
- **Tenant** : `tid(request)` serveur partout ; `find_tenant_vehicle` pivot ; cross-tenant → 404 (testé A–G).

## 3. RBAC frontend
- `AuthContext` expose `user` (dont `role`) ; `Protected` (`App.js:32`) = authentifié ou non, **aucun routage par rôle** ; `Layout.NAV` statique (11 entrées) + « Administration » si `superadmin` ; badge « lecture seule » si `read_only`.
- Deux conventions de gating : **Phases 1–3** `readOnly = user.role === "read_only"` (12 composants : tabs véhicule, DocFolderSection, SyncButton, VehicleDrawer…) → un `manager` verrait l'édition (conforme D6) ; **Lots C–G** `isAdmin = ["admin","superadmin"].includes(role)` (11 pages/drawers : FineDrawer, FuelCardDrawer, Anomaly/Transaction/Reconciliation/StatementDrawer, DocumentsPage, TimelinePage, FuelAnomalies/FuelStatements…) → un `manager` serait **traité comme lecture seule** même sur les capacités que D6 lui accorde (amendes, affectations, match/anomalies, rapprochements). Pas de helper central.
- Console superadmin `ClientUsers.jsx` : select rôle `admin | read_only` uniquement.
- Aucune page « mes… » ; `TransactionDrawer`/Documents : attach-file (Lot B) réservé admin via `isAdmin`.

## 4. `manager` / `driver`
Inexistants côté Documents (enum, données, UI). Journal (4B §13, cité dans la spec) : `manager` = exploitation sans cartes/imports/settings/suppressions ; `driver` = ses transactions/justificatifs, `/fines/mine` sans `internal_notes`. La spec D6 figée : **D6.1 driver = OUI · D6.2 manager = OUI · D6.3 notes_internes admin(+manager P) uniquement** ; matrice §10bis avec lignes `(P)` **à confirmer au GO**.

## 5. Affectations véhicule ↔ chauffeur (Lot C, livré)
`drivers` (UUID tenant, `nom/prenom/email/telephone/matricule_interne/navixy_employee_id/actif/dates/groupe/notes`, `source manual|legacy_import`) · `driver_assignments` (`vehicle_id`, `driver_id`, `valid_from`, `valid_to`, `principal`, clôture motivée, remplacement J-1, index `(tenant,vehicle,valid_from)`, `(tenant,driver,valid_from)`, `(tenant,valid_to)`) · `GET /vehicles/{id}/driver-at?date=` (principal / ambigu / candidats) · `driver_id` porté par `fuel_transactions` et amendes (`documents`) — **0 lien `users` ↔ `drivers`** (ni `users.driver_id`, ni `drivers.user_id`) ; `drivers.email` existe mais **ne doit pas servir de résolution automatique** (règle « aucun mapping par nom/email », D2). DB preview : drivers 0, assignments 0 (tenants de test nettoyés), `fuel_transactions.driver_id` renseigné 0/5.

## 6. Vues « mes véhicules / mes données »
Aucune. Les filtres `driver_id` existent côté API (`GET /energy`, `GET /fines`, exports) mais sont **libres** (tout conducteur du tenant). Fichiers : `/api/files/**` tenant-scopé seulement (pas de scoping conducteur).

## 7. Permissions par module (état réel vs cible D6/§10bis)
| Module | Lecture | Écriture aujourd'hui | Cible manager (D6) | Cible driver (D6) | Écart Lot H |
|---|---|---|---|---|---|
| Véhicules / fiche / photo / enrichissement (Ph.1–3) | tous | middleware (≠ read_only) | ✔ sauf DELETE | ✘ | garde admin sur `DELETE /vehicles/{id}`, `DELETE …/photo`, `/vehicles-archive/{id}/restore` ; driver bloqué |
| Documents / scan / validate / PATCH (Ph.1–3) | tous | middleware | ✔ sauf DELETE | ✘ | garde admin `DELETE /documents/{id}` ; driver bloqué |
| Inspections | tous | middleware | ✔ sauf DELETE | ✘ | garde admin `DELETE /inspections/{id}` |
| Catégories / requirements / settings échéances | tous | `_require_admin_role` | ✘ (paramètres) | ✘ | inchangé (admin) |
| Intégrations Navixy / ASTRA import / sync / alerts run / demo | tous | middleware | ✘ | ✘ | **gardes admin à ajouter** (8 routes) |
| Conducteurs référentiel (C) | tous | admin | ✘ (P) | ✘ | inchangé si (P) confirmé |
| Affectations véhicule↔conducteur (C) | tous | admin | ✔ (P) | ✘ | `require_roles("admin","manager")` ×2 |
| Amendes statut/paiement/conducteur/pièces (D) | tous (`notes_internes` sauf read_only) | admin | ✔ ; notes ✔ (P) | ses amendes via `/api/me`, sans notes | extension ×~8 + `strip_internal(driver)` |
| Plein / amende sans justificatif (B) | tous | admin | amende ✔ · plein ✔ (P) | ✘ | extension ×2 |
| Cartes (E) | tous | admin | ✘ | ✘ | inchangé |
| Imports / mappings (F) | tous | admin | ✘ | ✘ | inchangé |
| Match manuel / run / décisions anomalies (F) | tous | admin | ✔ | ✘ | extension ×4 |
| Rapprochements justify / décomptes create-declared-recalc (G) | tous | admin | ✔ (P) | ✘ | extension ×4 |
| Décomptes close / close_exception (G) | — | admin | ✘ (P) | ✘ | inchangé |
| `tenant-settings/fuel`, `…/reconciliation` | tous | admin | ✘ | ✘ | inchangé |
| Exports CSV/XLSX/PDF | tous | — | ✔ | ses données (P) | `/api/me/**/export` optionnel |
| Legacy (A) | tous | admin / superadmin | ✘ (P) | ✘ | inchangé |
| Console `/api/admin/**` | superadmin | superadmin | ✘ | ✘ | enum rôles + `driver_id` |
| `/api/me/**` (nouveau) | — | — | — | ✔ (ses tx, ses amendes, justificatif) | **à créer** |

## 8. Tests existants à préserver
`test_security_lot2` 19 · `test_readonly_extraction_rbac` 4 · `test_multitenant` 10 · `test_admin_console` 25 · `test_sso_navixy` 18 (10 cas 403) · chaque suite A–G contient ses cas read_only 403 / cross-tenant 404 (259 PASS). Tous écrits avec `admin` → l'extension de matrice ne doit modifier aucun comportement `admin`/`read_only`/`superadmin`.

## 9. Synthèse des écarts (gaps)
| # | Gap | Sévérité |
|---|---|---|
| G1 | Enum rôles API/UI limitée à `admin/read_only` ; pas de `users.driver_id` | bloquant Lot H |
| G2 | 43 gardes `require_roles("admin")` : aucune ligne `manager` | bloquant |
| G3 | 32 mutations sans garde explicite (middleware read_only seul) dont 4 DELETE + 8 intégrations/sync/import/demo : un `manager` ou `driver` passerait | **sécurité** — à fermer avant d'activer les rôles |
| G4 | `strip_internal` ne couvre que `read_only` | D6.3 |
| G5 | Aucune route `/api/me/**`, aucun scoping conducteur (API ni fichiers) | bloquant driver |
| G6 | `require_auth` : pas de règle fail-closed `driver` (tout sauf `/api/me`, `/api/auth` → 403) | **sécurité** |
| F1 | Frontend : 2 conventions de gating, pas de helper central → `manager` vu comme lecture seule sur les pages 4C | UX/cohérence |
| F2 | `Protected`/NAV sans rôle → `driver` verrait toute la navigation (403 partout) | bloquant driver |
| F3 | Console superadmin : pas de `manager`/`driver`, pas de choix du conducteur lié | bloquant |
| F4 | Pas de pages `/mes-pleins`, `/mes-amendes` ; attach-file réservé admin | bloquant driver |
| I1 | Index `fuel_transactions (tenant_id, driver_id, date_heure)` absent | perf (spec §7.7) |

Aucune donnée Journal lue ; aucune migration ; aucun déploiement.
