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
- Modules backend : `server.py` (routes), `auth.py`, `storage.py`, `extraction.py` (OCR), `astra_data.py`, `legacy_identity.py` (Lot A), `nofile.py` (Lot B), `drivers.py` (Lot C), `fines.py` (Lot D), `fuel_cards.py` (Lot E), `reports.py`.
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
| E | Cartes carburant : `fuel_cards` + `fuel_card_assignments`, `/energie/cartes`, `GET /api/fuel-cards/resolve` lecture seule | **PASS FINAL / CLOS** — tenant `lote-ui-test` **conservé** (inventaire dans CHANGELOG ; nettoyage sur GO) |
| F | Imports CSV/XLSX, `fuel_transactions.card_id`, matching transaction ↔ carte/véhicule, anomalies, scoring, warnings transactionnels | **NON AUTORISÉ** |
| G | Rapprochement achats/consommation, CAN, statements, close/lock mensuel, exports énergie | **NON AUTORISÉ** |
| H | Rôles `manager` / `driver`, vues chauffeur | **NON AUTORISÉ** |

MIGRATION = NONE · DRY-RUN = NONE · DEPLOYMENT (Phase 4C) = NONE · 0 donnée Journal réelle lue ou migrée.

## Dette acceptée (hors lots)
- Overlay dev CRA « ResizeObserver loop » (dev only, build PASS, 0 bug fonctionnel).
- Création directe en état terminal pour `legacy_import` d'amendes refusée (mécanisme d'import dédié à concevoir avec le futur dry-run).
