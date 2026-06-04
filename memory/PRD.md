# PRD — LogiTrak · Gestion Administrative de Flotte

## Original Problem Statement
Refonte du module "Documents & Licences" en "Gestion administrative de flotte" : un centre
administratif unique pour gérer tous les documents et coûts administratifs d'un véhicule.
Les éléments en bleu (plaque, carte grise, contrat, pièce jointe) deviennent des liens cliquables
ouvrant une fiche/drawer détaillée. Onglets: Leasing, Assurance, Carte grise, État des lieux,
Contrôles techniques, Documents (arborescence). Dashboard KPI + Timeline des échéances.
Intégration depuis Suivi Live / Historique / Véhicules via un onglet "Administration".
Inspirations: Fleetio, Motive, Samsara, Geotab.

## User Choices (V1)
- Authentification: AUCUNE (accès direct)
- OCR carte grise: DIFFÉRÉ (saisie manuelle en V1)
- Stockage fichiers: RÉEL (Emergent object storage)
- Données: flotte de démo pré-remplie (6 véhicules)
- Design: thème clair moderne (Swiss/high-contrast), devise CHF, langue française

## Architecture
- Frontend: React 19 + CRACO + Tailwind + Shadcn UI + react-query + recharts. Fonts: Cabinet Grotesk / Satoshi.
- Backend: FastAPI + Motor (MongoDB). Tous les endpoints préfixés /api.
- Stockage: Emergent object storage (EMERGENT_LLM_KEY), références en base (collections files/documents).
- Drawer véhicule partagé via VehicleDrawerContext (ouvrable depuis toutes les pages).

## User Personas
- Gestionnaire de flotte (admin): suit échéances, coûts, conformité, documents.
- Responsable de base/site: consulte les véhicules de sa base, ajoute états des lieux.

## Core Requirements (static)
1. Fiche véhicule administrative (drawer) avec infos générales + photo.
2. Onglet Leasing avec calculs auto (mois restants, coût restant, % utilisé) + alertes 180/90/30.
3. Onglet Assurance + alertes de renouvellement.
4. Onglet Carte grise (documents recto/verso/historique, OCR à venir).
5. Onglet État des lieux (historique, galerie par angle, comparaison avant/après).
6. Onglet Contrôles techniques + alertes 90/60/30/7.
7. Onglet Documents: arborescence 8 dossiers, drag&drop, prévisualisation, téléchargement.
8. Dashboard administratif: 8 KPI couleur (rouge/orange/vert).
9. Timeline des échéances: vues Mois/Trimestre/Année.
10. Intégration "Administration" depuis Suivi Live / Historique / Véhicules.

## Implemented (2026-06-04)
- [x] Backend complet: vehicles CRUD, dashboard KPIs, timeline, documents, inspections, upload/serve.
- [x] compute_metrics (niveaux d'alerte expired/critical/warning/ok) + auto-seed 6 véhicules + 2 états des lieux.
- [x] Dashboard (8 KPI, donut conformité, échéances à venir cliquables).
- [x] Page Véhicules (tableau, plaques cliquables, recherche, création).
- [x] Drawer 7 onglets (Général, Leasing, Assurance, Carte grise, État des lieux, Contrôles, Documents) avec édition.
- [x] Upload/preview/suppression de documents par dossier (drag & drop) — object storage vérifié.
- [x] États des lieux: création avec galerie par angle + comparaison avant/après.
- [x] Timeline avec bascule Mois/Trimestre/Année.
- [x] Pages Suivi Live / Historique avec bouton Administration.
- [x] Tests: backend 9/9 pytest, frontend 11 flux — 100% pass.

## Implemented — Itération 2 · Compatibilité Navixy (2026-06-04)
- [x] Intégration RÉELLE Navixy User API v2 (EU, auth par hash) — clé dans backend/.env (NAVIXY_API_HASH).
- [x] Import flotte: `tracker/list` + `vehicle/list` + odomètre `tracker/counter/value/list` → Navixy = source de vérité (remplace la liste locale, démos supprimés). 12 trackers réels du compte LOGITRAK importés.
- [x] Synchronisation du cumul de km (odomètre) dans `kilometrage` ; association véhicule ↔ tracker (navixy_tracker_id, device_id IMEI).
- [x] Endpoints: GET /api/navixy/status, POST /api/navixy/sync, GET /api/vehicles/{id}/live (état GPS + mouvement + batterie + réseau + odomètre). Auto-sync au démarrage.
- [x] UI: barre Navixy (statut + bouton Synchroniser) sur la page Véhicules ; carte « Suivi Navixy en direct » dans l'onglet Général (position, mouvement, odomètre, batterie, lien carte).
- [x] Retrait des pages « Suivi Live » et « Historique » (gérées par Navixy).
- [x] Tests: backend 8/8 Navixy + régression admin OK, frontend 100% pass.

## Implemented — Itération 3 · OCR + Alertes + Planificateur (2026-06-04)
- [x] OCR carte grise via OpenAI GPT-4o vision (emergentintegrations / clé Emergent) : extraction plaque, VIN, date mise en circulation, poids total, places. Zone scan + bloc « Données extraites » + bouton Appliquer dans l'onglet Carte grise.
- [x] Moteur d'alertes d'échéances : seuils leasing 180/90/30, assurance 90/60/30, contrôle 90/60/30/7 + récapitulatif quotidien. Déduplication par (vehicle_id, type, seuil, due_date) + dédup récap par jour. Index DB ajoutés.
- [x] Page « Alertes » (KPI, liste actionnable cliquable, journal des envois, bannière statut e-mail).
- [x] Envoi e-mail : abstraction provider-agnostique (Resend/SendGrid prêts) — **MOCKÉ** (status 'mocked') tant qu'aucun EMAIL_PROVIDER/EMAIL_API_KEY/EMAIL_FROM n'est fourni.
- [x] Planificateur APScheduler : sync Navixy + run alertes **1×/jour** + run initial au démarrage.
- [x] Tests: backend 24/24 pytest, frontend 100% pass.

## Pending integration (en attente d'accès utilisateur)
- Envoi e-mail RÉEL : fournir EMAIL_PROVIDER (resend|sendgrid), EMAIL_API_KEY, EMAIL_FROM (vérifié), ALERT_RECIPIENTS dans backend/.env → bascule automatique de 'mocked' vers 'sent'.

## Déploiement VPS isolé (2026-06-04)
- [x] Stockage pluggable: STORAGE_BACKEND=emergent (aperçu) | local (VPS, volume disque dédié). Garde-fou anti path-traversal.
- [x] Package Docker isolé `deploy/`: docker-compose (préfixe logitrak-fleet_, réseau/volumes dédiés, MongoDB dédié), Dockerfiles backend/frontend, gateway Nginx (SPA + proxy /api), .env.example, vhost Nginx hôte exemple, README pas-à-pas.
- [x] Frontend same-origin (/api) → un seul port publié (APP_PORT, défaut 8090) derrière le Nginx hôte (sous-domaine dédié). Aucun mélange avec Navixy/autres apps.
- Note: build Docker non testé dans le pod (Docker indisponible) ; logique stockage local validée + aperçu Emergent non régressé.

## Backlog (prioritized)
- P1: OCR carte grise (lecture plaque/VIN/date/poids/places + pré-remplissage) via IA vision.
- P1: Alertes/notifications proactives (email/in-app) sur échéances 180/90/30/7.
- P2: Export PDF/CSV des coûts (leasing/assurance) et rapport de conformité.
- P2: Vue calendrier (grille mensuelle) en complément de la timeline verticale.
- P2: Authentification + rôles (admin/responsable) si multi-utilisateurs requis.
- P3: Refactor server.py en routers (vehicles/documents/inspections/dashboard) ; upload async (asyncio.to_thread).
- P3: DELETE /vehicles/{id} -> 404 si id inconnu (symétrie avec GET).

## Next Tasks
1. Recueillir le retour utilisateur sur la V1.
2. Prioriser OCR carte grise vs notifications d'échéances.
