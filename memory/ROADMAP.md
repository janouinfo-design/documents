# ROADMAP — LogiTrak · Gestion Administrative de Flotte

Backlog priorisé. Rien ici n'est autorisé sans GO explicite de l'utilisateur (règle Phase 4C : un lot à la fois, tenant de test isolé, rapport + verdict avant clôture).

## P0 — Phase 4C, lots restants (ordre spec)
1. **Nettoyage `lote-ui-test`** (sur GO) : suppression par `tenant_id` exact + preuve 0 résidu + `default` inchangé (même procédure que `lotd_cleanup.py`).
2. **Lot F — Transactions carburant ↔ cartes** : imports CSV/XLSX, écriture `fuel_transactions.card_id` (décision humaine en cas d'`ambiguous` via `GET /api/fuel-cards/resolve`), matching transaction ↔ carte/véhicule, anomalies, scoring, warnings transactionnels `CARD_VEHICLE_MISMATCH` / `CARD_INACTIVE`.
3. **Lot G — Rapprochement énergie** : achats vs consommation, CAN, statements fournisseurs, close/lock mensuel, exports énergie complets.
4. **Lot H — Rôles `manager` / `driver`** : matrice RBAC étendue (`require_roles`), vues chauffeur.
5. **Dry-run migration Journal → Documents** (après F/G/H) : extraction lecture seule, mapping via `legacy_vehicle_map` confirmée, import `legacy_import` idempotent — nécessite un mécanisme d'import d'états terminaux d'amendes (faits de paiement/motif d'origine) séparé des actions interactives.
6. **Déploiement production Phase 4C** : uniquement sur GO explicite ; `openpyxl` déjà dans requirements/Dockerfile ; `deploy/.env.example` à versionner via Save to GitHub.

## P1
- Envoi e-mail RÉEL des alertes (attente `EMAIL_PROVIDER` / `EMAIL_API_KEY` / `EMAIL_FROM` / `ALERT_RECIPIENTS`).
- Harmonisation des testids du formulaire carte (`fuel-card-fournisseur/-last4/-expire-le/-type/-statut`) si une convention `fuel-card-field-*` est adoptée (documentaire, non bloquant).

## P2
- Vue calendrier (grille mensuelle) en complément de la timeline.
- Export CSV des coûts (leasing/assurance) si demandé (PDF conformité déjà livré).
- Sous-onglets contextuels / fil d'Ariane / recherche globale (Phase 2 nav, à valider).

## P3
- Refactor `server.py` (7 300 lignes) en routers par module ; upload async.
- Overlay dev CRA « ResizeObserver loop » (cosmétique, dev only).
