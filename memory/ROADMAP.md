# ROADMAP — LogiTrak · Gestion Administrative de Flotte

Backlog priorisé. Rien ici n'est autorisé sans GO explicite de l'utilisateur (règle Phase 4C : un lot à la fois, tenant de test isolé, rapport + verdict avant clôture).

## P0 — Phase 4C, lots restants (ordre spec)
1. ~~Nettoyage `lote-ui-test`~~ — FAIT (clôture technique Lot E, 0 résidu).
2. ~~**Lot F — Transactions carburant ↔ cartes**~~ — **LIVRÉ, PASS FINAL / CLOS** (voir CHANGELOG « LOT F LIVRÉ ») : imports CSV/XLSX (job → mapping → preview workspace → confirm idempotent), `fuel_transactions.card_id` uniquement si `found`, scoring explicable (100 direct / 90 card_assignment / plaque 0 jamais auto), `CARD_INACTIVE` (statut courant OU `expire_le` < date tx), `CARD_VEHICLE_MISMATCH` sans correction, anomalies D8 + décision motivée, corrections humaines individuelles/groupées (N audits), UI Énergie `Imports` / `Transactions` / `Anomalies`.
   - ~~Reste à faire~~ **TOUT FAIT** : nettoyage `lotf-ui-test` (`--apply` : 275 enregistrements, 0 résidu, `default` identique — PASS FINAL) ; **validation Docker réelle sur le VPS `ov-f04fc0`** (Docker 29.4.1, 2026-10-08T11:03:50Z, `bash deploy/validate-backend-docker.sh` : build PASS, modules A-F + server PASS, 0 ModuleNotFoundError/ImportError/Traceback, startup + scheduler PASS, smoke API PASS, `score_auto=90` / `score_review=70`, `card_assignment=90` / `direct_vehicle_id=100`, **18 PASS / 0 FAIL, exit 0**, 0 conteneur / 0 réseau résiduel) → `DOCKER BACKEND VALIDATION = PASS`, réserve levée. Déploiement production : toujours uniquement sur GO explicite.
   - **Limites documentées** : `CARD_INACTIVE` utilise le statut déclaré **courant** (pas d'historique effectif-daté du statut → modèle dédié si besoin) ; `depassement_reservoir` muet pour l'électrique (pas de capacité batterie dans le modèle) ; pas de rapprochement achats/consommation ni statements (Lot G).
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
- Refactor `server.py` (8 100 lignes) en routers par module ; upload async.
- Overlay dev CRA « ResizeObserver loop » (cosmétique, dev only).
