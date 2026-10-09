# PRD — LogiTrak · Gestion Administrative de Flotte

> Historique détaillé (toutes les itérations, lots, déploiements, preuves) : **`memory/CHANGELOG.md`** (append-only).
> Backlog / lots restants : **`memory/ROADMAP.md`**. Identifiants de test : `memory/test_credentials.md` (emplacements seulement, aucun secret).

## Original Problem Statement
Refonte du module "Documents & Licences" en "Gestion administrative de flotte" : un centre
administratif unique pour gérer tous les documents et coûts administratifs d'un véhicule.
Les éléments en bleu (plaque, carte grise, contrat, pièce jointe) deviennent des liens cliquables
ouvrant une fiche/drawer détaillée. Onglets: Leasing, Assurance, Carte grise, État des lieux,
Contrôles techniques, Documents (arborescence). Dashboard KPI + Timeline des échéances.
Intégration depuis Suivi Live / Historique / Véhicules via un onglet "Administration".
Inspirations: Fleetio, Motive, Samsara, Geotab.

## User Choices (V1)
- Authentification: AUCUNE (accès direct) → remplacée depuis par JWT superadmin/admin/read_only + SSO Navixy (voir CHANGELOG).
- OCR carte grise: DIFFÉRÉ (saisie manuelle en V1) → livré ensuite (Claude Anthropic).
- Stockage fichiers: RÉEL (Emergent object storage / volume local VPS)
- Données: flotte de démo pré-remplie (6 véhicules)
- Design: thème clair moderne (Swiss/high-contrast), devise CHF, langue française

## Architecture
- Frontend: React 19 + CRACO + Tailwind + Shadcn UI + react-query + recharts. Fonts: Cabinet Grotesk / Satoshi.
- Backend: FastAPI + Motor (MongoDB). Tous les endpoints préfixés /api. Multi-tenant strict (`tenant_id` résolu depuis l'utilisateur authentifié, jamais du client).
- Stockage: Emergent object storage (EMERGENT_LLM_KEY) ou local (`STORAGE_BACKEND`), références en base (collections files/documents).
- Drawer véhicule partagé via VehicleDrawerContext (ouvrable depuis toutes les pages).
- Modules backend : `server.py` (routes), `auth.py`, `storage.py`, `extraction.py` (OCR), `astra_data.py`, `legacy_identity.py` (Lot A), `nofile.py` (Lot B), `drivers.py` (Lot C), `fines.py` (Lot D), `fuel_cards.py` (Lot E), `fuel_import.py` / `fuel_matching.py` / `fuel_anomalies.py` (Lot F), `fuel_statements.py` (Lot G : rapprochements, blockers, décomptes, declared/deltas, exports), `reports.py`.
- Production : VPS Docker Compose + Nginx (`deploy/`) — déploiement UNIQUEMENT sur GO explicite utilisateur.

## User Personas
- Gestionnaire de flotte (admin): suit échéances, coûts, conformité, documents.
- Responsable de base/site: consulte les véhicules de sa base, ajoute états des lieux.
- Lecteur (read_only) : consultation seule, aucune mutation (UI masquée + 403 serveur).
- Super Admin plateforme : console clients/tenants, vue client.

## Core Requirements (static)
1. Fiche véhicule administrative (drawer) avec infos générales + photo.
2. Onglet Leasing avec calculs auto (mois restants, coût restant, % utilisé) + alertes 180/90/30.
3. Onglet Assurance + alertes de renouvellement.
4. Onglet Carte grise (documents recto/verso/historique, OCR).
5. Onglet État des lieux (historique, galerie par angle, comparaison avant/après).
6. Onglet Contrôles techniques + alertes 90/60/30/7.
7. Onglet Documents: arborescence 8 dossiers, drag&drop, prévisualisation, téléchargement.
8. Dashboard administratif: 8 KPI couleur (rouge/orange/vert).
9. Timeline des échéances: vues Mois/Trimestre/Année.
10. Intégration "Administration" depuis Suivi Live / Historique / Véhicules.

## Invariants permanents (Phases 1–3, à préserver)
- DOCUMENT VALIDÉ = enregistrement de coût canonique ; `collect_costs` lit les documents et **n'agrège jamais `fuel_transactions`**.
- FUEL_TRANSACTION = donnée énergie métier, pas une seconde source de coût. Priorité consommation : CAN > fuel_transactions.
- Baselines démo `default` : facture 510.77 CHF · transaction Migrol 74.17 CHF · amende 120 CHF (ancien état « À payer », 0 champ `fine_status` écrit).
- Moteur central d'échéances `collect_deadlines` + seuils tenant (`urgent_days=30`, `warning_days=90`) : source unique pour Dashboard / Timeline / alertes / cartes carburant.
- Toute mutation = audit (`audit_logs`, tenant-scopé). read_only : 403 serveur sur toute méthode ≠ GET.
- Jamais d'ObjectId exposé ; `datetime.now(timezone.utc)` ; pas de secret dans les rapports/PRD.

## Phase 4C — statut courant (2026-06)
Spécification : `docs/PHASE4C_SPECIFICATION.md` (décisions figées). Livraison par lots sur GO explicite, tenant de test isolé par lot, rapport + inventaire + verdict avant clôture.

| Lot | Périmètre | Statut |
|---|---|---|
| A | Correspondances legacy véhicules Journal → Documents (lecture seule + confirmation humaine) | **PASS FINAL / CLOS** (tenant test supprimé) |
| B | Document sans fichier (D1) + D7 générique + D5 | **PASS FINAL / CLOS** (tenant test supprimé) |
| C | Conducteurs / affectations datées / DriverPicker | **PASS FINAL / CLOS** (tenant test supprimé) |
| D | Amendes : 10 statuts, paiement métier, pièces liées, `/amendes`, exports, enum `type_infraction` 8 valeurs | **PASS FINAL / CLOS** (tenant test supprimé) |
| E | Cartes carburant : `fuel_cards` + `fuel_card_assignments`, `/energie/cartes`, `GET /api/fuel-cards/resolve` lecture seule | **PASS FINAL / CLOS** — checkpoint `8147c66`, tenant `lote-ui-test` **supprimé** (58 enregistrements, 0 résidu, `default` identique) |
| F | Imports CSV/XLSX (job → mapping → preview workspace → confirm idempotent), `fuel_transactions.card_id` (si `found` uniquement), matching transaction ↔ carte/véhicule scoré/explicable, anomalies D8 + décision motivée, warnings `CARD_INACTIVE` / `CARD_VEHICLE_MISMATCH`, corrections humaines (individuelle + groupée = N audits), UI Énergie `Imports` / `Transactions` / `Anomalies` | **PASS FINAL / CLOS** — 235 tests PASS, build PASS, testing agent it.45 ; tenant `lotf-ui-test` **supprimé** (275 enregistrements, 0 résidu, `default` identique) ; **Docker validé sur VPS** (`ov-f04fc0`, Docker 29.4.1, 2026-10-08T11:03:50Z : build, imports A-F + server, startup, smoke 18 PASS / 0 FAIL, exit 0, 0 résidu) — réserve Docker **levée** |
| G | Rapprochements achats ↔ consommation (CAN prioritaire, tickets = achats, ASTRA comparative, seuils null → `INDICATIF`, justification), décomptes mensuels = snapshot Documents (`fuel_statements` / `fuel_statement_lines`, scope tenant/fournisseur, `declared` manuel null = N/A, 5 blockers, close normal 409 `CLOSE_BLOCKED` / `close_exception` motivé, correctif), verrou transactions à la clôture seulement (409 `STATEMENT_LOCKED`, aucune réouverture), exports CSV/XLSX/PDF audités SHA-256, UI `/energie/rapprochements` + `/energie/releves` | **PASS FINAL / CLOS** — `LOT G FULL-FLOW = PASS` (rapport `test_reports/lotg_final_report.md` : 259 tests A–G, build, it.46/47, A–AB 28/28) · `LOT G CLEANUP = PASS` (tenant `lotg-ui-test` **supprimé** : 260 enregistrements, 0 résidu, `default` / autres tenants identiques avant/après) · `LOT G DOCKER VALIDATION VPS = PASS` (VPS HEAD `4b6728a`, Dockerfile corrigé `fuel_statements.py`, 16 fichiers, imports A–G, startup, scheduler, smoke + endpoints Lot G, seuils null : **23 PASS / 0 FAIL, exit 0, 0 résidu `logitrak-validate_*`**) · DIVERGENCES BLOQUANTES = 0 |
| H | Rôles `manager` / `driver` (RBAC backend source de vérité, re-lecture DB par requête), vues chauffeur limitées (`/mes-pleins` · `/mes-amendes` · `/mes-vehicules`), manager scopé `vehicle_scope` (fail-closed 404 hors scope, `[]`=0 donnée), justificatif driver 1 fichier (409 `FILE_ALREADY_PRESENT`) | **FULL-FLOW = PASS** — rapport `test_reports/loth_final_report.md` : 7/7 familles d'isolation PASS (43/43 preuves API), suite Lot H 21/21, régression A–H mono-process 704 PASS / 2 FAIL (hors Lot H, non bloquants) / 2 SKIP (documentés, préexistants) — 708 tests collectés, durée 739,98 s (~12 min 19 s), build PASS, it.49 PASS ; empreintes `verify` DEFAULT/OTHER_TENANTS = FAIL (hors Lot H, non bloquant) ; **CLEANUP FINAL = PASS (GO séparé 2026-10-09)** : 167 enreg. DB + tenant supprimés, `LOTH_RESIDUAL_RECORDS=0`, `DEFAULT_UNCHANGED_DURING_CLEANUP=PASS` + `OTHER_TENANTS_UNCHANGED_DURING_CLEANUP=PASS` (26 autres tenants intacts), 5 objets storage orphelins non supprimables (objstore HTTP 405, 0 réf DB, non bloquant) ; Docker runtime non vérifié en preview (statique PASS) → **LOT H = PASS FINAL / CLOS** |

MIGRATION = NONE · DRY-RUN = NONE · DEPLOYMENT (Phase 4C) = NONE · LOT H FULL-FLOW = PASS · LOT H CLEANUP = PASS (LOTH_RESIDUAL_RECORDS=0 ; default + 26 autres tenants inchangés) · LOT H = PASS FINAL / CLOS · MIGRATION HARNESS = READY (dry-run Journal→Documents préparé, auto-testé ; `test_reports/MIGRATION_HARNESS_READY.md`) · JOURNAL DATA EXTRACTION = NOT RUN · MIGRATION DRY-RUN = NOT RUN · MIGRATION APPLY = NOT AUTHORIZED · 0 donnée Journal réelle lue ou migrée.

## Tenant démo commercial `demo-logitrak` (2026-10) — DEMO TENANT = READY
Jeu de démonstration réaliste et cohérent, créé via l'API du compte admin du tenant (règles métier + isolation garanties), marqué `demo_seed=true` / `demo_seed_version="2026-10"` / `demo_seed_group="commercial-demo"` (aucun préfixe artificiel visible). `default` + 26 autres tenants **inchangés** (fingerprint avant/après = PASS). Aucun déploiement, aucune migration.
- Script unique idempotent : `test_reports/demo_logitrak_seed.py` (`baseline|seed|mark|verify|inventory|report|reset|snapshot|all`). Preuves : `demo_logitrak_{baseline,result,inventory,verify,snapshot}.json` + `demo_logitrak_report.md`. Verify = **17/17 PASS**.
- `reset` : purge tenant-scopée (sauf tenant + 3 comptes) + re-seed + verify → `DEMO RESET=PASS` · `DEFAULT UNCHANGED=PASS` · `OTHER TENANTS UNCHANGED=PASS` (idempotent ; blobs storage orphelins non supprimables, objstore 405, 0 réf DB, non bloquant). `snapshot` : santé lecture seule → `DEMO TENANT HEALTH=PASS` + isolation. Parcours commercial 5 min : `test_reports/demo_logitrak_walkthrough.md`.
- Dates ajustables (env, défauts = état actuel) : `DEMO_DOC_EXPIRED_DAYS` · `DEMO_DOC_SOON_DAYS` · `DEMO_CARD_EXPIRED_DAYS` · `DEMO_FINE_OPEN_DAYS` · `DEMO_FINE_LATE_DAYS` pour caler les cas « expiré / <30j / amendes » le jour de la présentation.
- Bandeau « Données de démonstration » (ambre, discret, toutes pages/tous rôles) affiché **uniquement** pour les tenants `demo_seed=true` : `/auth/login` + `/auth/me` renvoient `tenant_demo` (dérivé du marquage, aucune incidence auth) ; frontend `components/Layout.jsx` (`DemoBanner`, `data-testid=demo-mode-banner`). `default` = jamais de bandeau (vérifié).
- Contenu : 10 véhicules (4 thermiques · 3 électriques · 2 hybrides rechargeables · 1 utilitaire) · 6 conducteurs · 4 cartes (Migrol/Shell valides, Tamoil **expirée**, Avia **suspendue**) · 16 transactions (8 carburant + 8 recharges EV multi-mois) · 33 documents · amendes ouverte/payée/en retard/contestée · factures entretien/pneus/réparation/assurance/leasing/énergie.
- Cas visibles : EV avec recharges · véhicule sans conducteur · ancienne affectation terminée · conducteur sans véhicule · carte expirée/suspendue · transaction sans carte · document expiré · échéance <30j · document à vérifier · document requis manquant.
- Comptes (mots de passe : `memory/test_credentials.md` §6, gitignored, jamais affichés) : `admin@demo-logitrak.ch` (admin) · `driver@demo-logitrak.ch` (driver, lié conducteur actif « Marc Rochat »/Tesla Model 3) · `readonly@demo-logitrak.ch` (read_only, mutations 403).

## Décisions Lot F figées (réconciliation spec §6a.5 / §6a.15)
- Scoring véhicule : `vehicle_id` explicite valide → **100 / `direct_vehicle_id` / auto** · carte unique `found` + exactement 1 affectation `vehicule` à la date + carte utilisable → **90 normatif / `card_assignment` / auto** (règle déterministe, pas une addition du barème ; breakdown `card_unique/assignment_at_date/assigned_vehicle_id/card_usable`) · carte inactive → jamais auto (−50, `matched_review`, `CARD_INACTIVE`) · ambiguïté → jamais auto · **plaque = 0 point, jamais auto-match** (revue humaine) · conducteur +20 (jamais suffisant seul) · carburant +10 / −40 · seuils tenant `score_auto=90` / `score_review=70`.
- PREVIEW = 0 écriture métier finale (seuls `fuel_import_jobs` / `fuel_import_rows` [/ `fuel_import_mappings`] varient) ; CONFIRM = seule écriture métier, idempotente ; jobs/rows conservés (audit).
- `CARD_INACTIVE` = (statut courant ≠ `active`) OU (`expire_le` renseignée ET `expire_le` < date transaction) — modèle `current_status_tx_date_expiration`, jamais via `audit_logs`. `CARD_VEHICLE_MISMATCH` = warning/anomalie, aucune substitution de `vehicle_id` / `card_id`.
- Action groupée « Accepter les N propositions à candidat unique » = N décisions humaines, motif global obligatoire, N audits unitaires (`row_id`, `batch_id`, plaque source, avant/après), fail-closed si la ligne a changé.
- D7 inchangé (document = coût, `pending_fx` exclu) · D8 inchangé (anomalies recalculées par Documents ; legacy `justified` repris uniquement si redétecté même transaction/type ; `issues[]` jamais anomalies) · aucun HMAC Journal (dédup `dedup_key` propre à Documents).

## Décisions Lot G figées
- Ordre canonique : CAN mesuré = consommation réelle · `fuel_transactions` / tickets = achats (estimation tickets = indicative, jamais une consommation) · ASTRA = référence comparative (jamais substituée) · aucune autre estimation.
- Seuils `threshold_pct` / `threshold_l` **null par défaut** (aucune valeur arbitraire) ; règle `single_or_both` ; sans seuil → `INDICATIF` ; négatif → 422 ; PATCH admin/superadmin audité avant/après.
- Décompte = snapshot Documents (pas une source canonique nouvelle), **aucun import fournisseur ligne-à-ligne** ; `declared` manuel facultatif, null = N/A jamais 0, deltas uniquement si devises comparables.
- Blockers : `pending_fx · matched_review · unmatched · open_anomaly · forced_duplicate` ; close normal ⇔ intégrité PASS et 0 blocker (sinon 409 `CLOSE_BLOCKED` détaillé) ; `close_exception` = motif + confirmation explicite, snapshot des blockers conservé et visible.
- Verrou (`locked`, `statement_id`, `locked_at` = `closed_at`) **uniquement** à la clôture (normale ou exception) ; brouillon = 0 lock, recalcul admin ; mutation source verrouillée → 409 `STATEMENT_LOCKED` (patch mixte notes+montant rejeté intégralement ; notes/tags seuls autorisés) ; matching ignore les transactions verrouillées ; décisions d'anomalie non destructives autorisées après lock ; **aucun endpoint/UI de réouverture** — corrections tardives = décompte `correctif` (parent requis, même période/scope, transactions non verrouillées uniquement, parent immuable).
- Exports CSV/XLSX/PDF (décompte, rapprochements, transactions période) = audit `fuel_export/download` tenant-scopé avec acteur, type, format, filtres, `statement_id`, taille, SHA-256 des octets finaux (`X-Content-SHA256`). read_only : lectures + exports 200, toute mutation 403.

## Dette acceptée (hors lots)
- Overlay dev CRA « ResizeObserver loop » (dev only, build PASS, 0 bug fonctionnel).
- Création directe en état terminal pour `legacy_import` d'amendes refusée (mécanisme d'import dédié à concevoir avec le futur dry-run).
