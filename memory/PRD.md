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

## Déploiement VPS — mise en production (2026-06 → 07, session fork)
- [x] VPS OVH `83.228.207.198` (IPv4) / IPv6, Ubuntu, Docker 29.4 + Compose v5.1. Repo GitHub `janouinfo-design/documents` cloné dans `~/documents`.
- [x] Correctif build: `frontend/Dockerfile` → `COPY package.json yarn.lock* ./` + `yarn install` (sans `--frozen-lockfile`) car `yarn.lock` non committé au repo. Build frontend OK (16s, bundle same-origin `/api` validé, pas de `undefined/api`).
- [x] `.gitignore`: ajout `!deploy/.env.example` (était exclu par `.env.*`).
- [x] `docker-compose.yml`: healthcheck MongoDB + backend `depends_on: condition: service_healthy` (évite flotte vide au 1er boot à froid).
- [x] Stack lancé sur VPS (port 8090), Navixy sync OK (12 véhicules réels), MongoDB `logitrak_fleet` dédiée. DNS A `documents.logitrak.ch` → 83.228.207.198 + Nginx hôte + certbot (HTTPS).
- [x] Feature « Données démo »: endpoint `POST /api/demo/fill-admin` (non destructif) + bouton page Véhicules. Remplit leasing/assurance/carte grise/contrôles fictifs (échéances variées) + états des lieux. Peuple Dashboard/Timeline/Alertes.

## Intégration dans le hub « New Navixy » (projet SÉPARÉ) (2026-07)
- Contexte: LogiTrak (= module « Documents ») sera embarqué en **iframe** dans un autre projet Emergent `logistics-hub-maker.preview.emergentagent.com`. New Navixy = projet distinct, NE PAS TOUCHER.
- [x] `frontend/nginx.conf`: en-tête `Content-Security-Policy: frame-ancestors 'self' https://*.emergentagent.com https://*.logitrak.ch` (autorise l'iframe depuis le hub, bloque le clickjacking ailleurs).
- Reste à faire côté hub (autre projet): ajouter une page/menu avec `<iframe src="https://documents.logitrak.ch">`.

## Refonte navigation — Phase 1 (2026-07)
- [x] Périmètre STRICT: uniquement le projet Documents (LogiTrak). Aucune modif de New Navixy / autres apps VPS / connexion Navixy (API backend inchangée).
- [x] Remplacé le menu vertical gauche (`Layout.jsx`) par une **barre d'onglets horizontale** sticky (SaaS, style clair/Swiss existant): Tableau de bord, Véhicules, Échéances, Alertes. Onglet actif = soulignement slate-900. Testids conservés (nav-dashboard/vehicles/timeline/alerts).
- [x] Responsive: onglets `overflow-x-auto no-scrollbar` (swipe mobile), libellé module `hidden sm:flex`. Utilitaire `.no-scrollbar` ajouté à index.css.
- [x] Retiré la carte « Suivi Navixy en direct » de l'onglet Général (le GPS live est géré par le hub) + suppression composant `NavixyLiveCard.jsx` et API `getVehicleLive` devenus morts.
- [x] Testé aperçu Emergent: 4 onglets présents, navigation + états actifs OK, Dashboard/Véhicules rendus.
- Note: routes inchangées (`/`, `/vehicules`, `/timeline`, `/alertes`) → aucune 404, migration sûre sans conserver l'ancien menu.

## Implemented — Itération 4 · Scan intelligent des documents (2026-08-11)
- [x] Backend `extraction.py`: abstraction `DocumentExtractionProvider` (extensible Azure/Google/AWS) + `GptVisionProvider` (gpt-5.4 via emergentintegrations, override env DOC_EXTRACTION_PROVIDER/DOC_EXTRACTION_MODEL). Interface future `VehicleEnrichmentProvider` (OFROU/TARGA — volontairement non implémentée).
- [x] 7 types de documents: permis_circulation, assurance, leasing, controle_technique, facture, amende, autre (FIELD_DEFS extensibles). Support JPG/PNG/WEBP + PDF multi-pages (PyMuPDF, max 8 pages), redressement EXIF + resize (Pillow).
- [x] `POST /api/vehicles/{id}/documents/scan` (multi-fichiers ou ré-analyse via document_id sans doublon) → type détecté + champs avec confidence/current_value/conflict. `POST /api/documents/{id}/validate` → applique UNIQUEMENT les champs choisis, met à jour la fiche véhicule (source unique de vérité), classe le document.
- [x] Nouveaux champs véhicule (racine, sans doublon): type_carburant, cylindree_cm3, puissance_kw, variante, numero_homologation, categorie, poids_vide, co2_g_km, conso_officielle_l_100km (+ leasing.km_annuel). Litres = calculés à l'affichage.
- [x] Provenance: collection `vehicle_field_meta` + GET /api/vehicles/{id}/field-meta. Audit trail activé (db.audit_logs) + GET /api/vehicles/{id}/history ("ancien → nouveau (source: ...)").
- [x] Protection Navixy: plaque/marque/modele/vin/annee validés par document ne sont plus écrasés par la sync (kilometrage reste Navixy).
- [x] Frontend `ScanDocumentDialog.jsx` mobile-first: photo caméra (capture=environment), import PDF/image, multi-pages (vignettes/rotation/suppression), étapes Analyse → Type (modifiable + ré-analyse) → Revue (badges confiance vert ≥90% / ambre 70-90% / rouge <70%) → Conflits (Conserver/Utiliser, défaut = conserver) → Valider. Annulation en revue = soft-delete.
- [x] Onglet Documents: « + Ajouter un document » (Scanner / Importer / Manuellement). Carte grise: scan permis (type forcé) + données techniques affichées/éditables. Général: section « Provenance & historique ». Ancien endpoint OCR remplacé (pas de 2e système parallèle).
- [x] Échéances validées par scan alimentent le moteur d'alertes existant.
- [x] Deploy VPS: backend/Dockerfile (pymupdf + pillow, COPY extraction.py). ⚠️ Le scan exige EMERGENT_LLM_KEY dans deploy/.env sur le VPS.
- [x] Tests: E2E curl (scan→conflits→validation→provenance→protection Navixy) + testing agent it.4: backend 17/17 pytest, frontend 100% (/app/test_reports/iteration_4.json). Correctifs post-test: valeur 0 légitime (CO₂ BEV), SheetTitle a11y, affordance provenance.


## Implemented — Itération 5 · Scan mutualisé + webcam + bibliothèque centrale (2026-08-11)
- [x] Composant générique `DocumentScanCard` (📷 Prendre une photo / 📁 Importer un fichier) réutilisé dans les 4 onglets : Carte grise (permis_circulation), Assurance, Leasing, Contrôles — une seule logique, zéro duplication.
- [x] « Prendre une photo » : caméra native sur mobile (input capture=environment) ; **vraie webcam sur desktop** (getUserMedia, aperçu vidéo, bouton « Prendre la photo », reprise possible) ; message propre + fallback import si caméra indisponible/refusée.
- [x] Onglet Documents = bibliothèque centrale : bouton unique « + Ajouter un document » → étape choix du type (Détection automatique + 7 types, lien « Changer ») → capture/import → même moteur. Les documents scannés depuis n'importe quel onglet apparaissent dans Documents (enregistrement unique, pas de copie physique — document_type + folder assurent le lien module).
- [x] Conflits : raccourcis « Tout conserver / Tout remplacer » (défaut sécurisé = conserver). Fermeture depuis l'étape échec = soft-delete du document orphelin.
- [x] Chaque onglet garde sa section documents (Voir / Télécharger / Supprimer via DocFolderSection) + re-scan via la carte.
- [x] Tests : testing agent itération 5 frontend 100 % (iteration_5.json) — flux assurance forcé, auto-détection permis avec 6 conflits conservés (aucun écrasement), webcam headless, annulation, régressions Dashboard/Échéances/Alertes/éditions classiques. Console vérifiée : aucun warning Radix a11y.

## Implemented — Itération 6 · Consommation officielle vs réelle + télémétrie carburant (2026-08-11)
- [x] 5 nouveaux champs véhicule (réutilisation des existants, zéro doublon) : conso_officielle_norme (WLTP/NEDC), co2_norme, capacite_reservoir_l, conso_reelle_l_100km, conso_reelle_source (can|fms|obd|fuel_transactions|manual|unavailable) + télémétrie carburant_niveau_pct / carburant_niveau_date (sync-only, non éditables).
- [x] Sync Navixy enrichie : /tracker/readings/list par tracker → niveau carburant frais (≤7 j, ex. VD 311225 = 99 % vérifié) + compteur litres cumulés CAN (can_consumption/obd_total_fuel) → snapshots quotidiens `fuel_snapshots` (litres+km) → conso réelle MESURÉE = ΔL/Δkm×100 uniquement si Δkm ≥ 100 et 2–60 L/100km plausible → source="can" + provenance (provider navixy_can). JAMAIS d'estimation ; l'IA n'extrait aucune consommation du permis.
- [x] Priorité des sources respectée : CAN écrase manuel ; saisie manuelle possible uniquement si source ≠ can, marquée « Source : Manuelle », sinon champ verrouillé (« Mesurée via CAN »).
- [x] UI Carte grise restructurée : carte « Carte grise » (données du document) + carte « Données moteur & consommation » : Carburant · Cylindrée « 1968 cm³ — 2.0 L » (litres calculés, jamais stockés) · Puissance · CO₂+norme · Officielle+norme · Réelle+source ou « Données insuffisantes » · Écart % (+12.5 % vérifié) · Capacité réservoir · Niveau carburant (% ≈ L estimés, niveau ≠ consommation).
- [x] Abstraction `VehicleTechnicalDataProvider.lookup(vin, homologation, marque, modele, variante)` prête à brancher (SwissCarInfo / reception-par-type.ch / auto-i-dat / Eurotax) — aucun fournisseur codé (pas d'API OFROU publique ; TARGA → IVITA). Comparatif fourni à l'utilisateur, décision en attente.
- [x] Tests (self-test) : sync Navixy réelle OK (12 véhicules, niveau 99 % capté), PUT manuel officielle 7.2 WLTP + réelle 8.1 manual → écart +12.5 % affiché, screenshot validé. Aucune conso réelle CAN calculée à ce jour (compteurs litres anciens sur la flotte — pipeline s'alimentera dès que les trackers remontent des litres frais).



## Implemented — Itération 7 · SwissCarInfo + Scanner à détection de contours (2026-08-11)
- [x] **SwissCarInfo API v3** (backend/technical_data.py): recherche **plaque IVI en priorité** (regex canton+numéro, /v3/plate), repli **n° d'homologation** (/v3/search type=variant). Clé exclusivement backend (SWISSCARINFO_API_KEY + SWISSCARINFO_BASE_URL, aussi dans deploy/.env.example). Sans clé → provider None, mode « non configuré » propre (503 message français, UI avec icône clé). Gestion erreurs 300/401/404/429.
- [x] Endpoints: GET /api/technical-data/status · POST /api/vehicles/{id}/enrich-technical (lookup + review fields avec conflits, AUCUNE écriture) · POST .../enrich-technical/apply (validation explicite uniquement). Architecture prête pour un enrichissement en masse futur (endpoints par véhicule réutilisables) — bouton global volontairement NON développé (quota 500 plaques/mois).
- [x] **Variantes obligatoires**: si plusieurs lignes d'émissions divergent sans correspondance boîte → conso/CO₂ exclus des fields, `requires_variant_choice=true` + liste variantes ; l'UI force le choix avant la revue. Boîte connue/valeurs identiques → résolution auto. CO₂ 0 accepté (BEV, _num0).
- [x] **Garde CAN/OBD**: _can_locked_keys — tout champ avec vehicle_field_meta provider=navixy_can est exclu du lookup ET bloqué à l'apply (jamais écrasé par des données constructeur).
- [x] UI (TechnicalEnrichDialog + bouton « Base technique » dans la carte Données moteur & consommation, onglet Carte grise): source « SwissCarInfo — base officielle OFROU/ASTRA », trouvé par plaque/homologation, date de récupération, conflits « Valeur actuelle (fiche) / Donnée technique proposée », validation explicite. Note de provenance persistante sous la carte (tech-provenance-note) via field-meta. Provenance source=external_vehicle_database + audit « … (source: Base technique SwissCarInfo) ».
- [x] **Scanner documents à détection de contours** (commun à TOUS les onglets via ScanDocumentDialog): jscanify 1.4 + OpenCV.js auto-hébergés (/scanner/, lazy-load ~9 Mo au 1er usage). Webcam desktop: **cadre de détection vert en direct** (overlay canvas, 350 ms). Après capture (mobile ou webcam): étape recadrage (DocumentCropper) — détection auto des 4 coins (validation aire >8%), **poignées SVG draggables** pour ajustement manuel, correction de perspective (extractPaper). Échec détection → coins par défaut + message « ajustez manuellement ». OpenCV indisponible → photo utilisée telle quelle (fallback propre).
- [x] **Conversion PDF**: photos capturées → backend as_pdf=1 → enhance_and_pdf (EXIF + autocontraste Pillow + resize 2200px) → **PDF multi-pages unique** stocké (scan-YYYYMMDD-HHMMSS.pdf) ; OCR sur les pages améliorées. Imports classiques inchangés (régression testée).
- [x] Tests: testing agent itération 6 — backend 7/7 pytest, frontend 100 % (iteration_6.json). Post-test: guard images vides dans enhance_and_pdf, TechnicalApply Optional=None. E2E self-test: apply + provenance + audit + garde CAN vérifiés puis nettoyés ; provider testé contre mock local (ambiguïté/résolution boîte).
- ⚠️ SwissCarInfo NON ACTIVÉ: en attente de la clé compte Max de l'utilisateur (à mettre dans backend/.env en preview et deploy/.env sur VPS, puis restart backend).

## Vérifications session (2026-08-11, suite)
- [x] **CSP iframe CONFIRMÉE en production** : `curl -sI https://documents.logitrak.ch` retourne `content-security-policy: frame-ancestors 'self' https://*.logitrak.fr https://*.logitrak.ch https://*.navixy.com https://*.emergentagent.com` → le correctif *.logitrak.fr est déjà déployé sur le VPS. Reste : test visuel utilisateur dans https://login.logitrak.fr/#/user-app/14328.
- [x] **date_prochain SwissCarInfo → échéances/alertes : DÉJÀ CÂBLÉ et prouvé E2E** : apply date_prochain=2026-08-31 → metrics controle recalculées (critical/20j) → /api/timeline contient l'échéance → /api/alerts/run created=1, alerte contrôle visible. Aucun code ajouté (TECH_FIELD_DEFS target=controle_technique.date_prochain alimente le moteur existant seuils 90/60/30/7). Données de test restaurées/nettoyées (date 2026-06-24, alerte, meta, audit).
- [x] **Deploy-readiness vérifiée** : backend/Dockerfile copie technical_data.py ; requests==2.34.2 dans requirements ; deploy/.env.example contient SWISSCARINFO_API_KEY/SWISSCARINFO_BASE_URL (untracked mais exception .gitignore OK) ; frontend/.dockerignore n'exclut pas public/ (opencv.js 9 Mo + jscanify seront dans l'image et le repo) ; frontend/yarn.lock sera commité (Dockerfile gère yarn.lock*).
- Le déploiement lui-même doit être fait par l'utilisateur : Save to GitHub → `cd ~/documents && git pull` → `cd deploy && docker compose up -d --build`.

## Backlog (prioritized)
- Phase 2 nav (à valider): sous-onglets contextuels (ex. Véhicules: Liste/Échéances), en-tête module avec fil d'Ariane + recherche globale.
- Phase 3+ (gros chantiers, à cadrer 1 par 1): modules Contrats & renouvellements, Conducteurs, Clients, Modèles, Corbeille/Favoris/Partagés ; permissions/rôles + auth ; multi-tenant.
- P1: Envoi e-mail RÉEL des alertes (attente EMAIL_PROVIDER/API_KEY/FROM/RECIPIENTS).
- P2: Export PDF/CSV des coûts (leasing/assurance) et rapport de conformité.
- P2: Vue calendrier (grille mensuelle) en complément de la timeline.
- P3: Refactor server.py en routers ; upload async.

## Next Tasks
1. Recevoir la clé SwissCarInfo (compte Max) → SWISSCARINFO_API_KEY dans backend/.env (preview) et deploy/.env (VPS) → restart backend → tester une vraie recherche plaque sur la flotte.
2. Déployer les itérations 4-7 sur le VPS: Save to GitHub → `cd ~/documents && git pull` → `cd deploy && docker compose up -d --build`. Renseigner EMERGENT_LLM_KEY + SWISSCARINFO_API_KEY dans deploy/.env.
3. Vérifier l'iframe Navixy après redéploiement: `curl -sI https://documents.logitrak.ch | grep -i content-security-policy` doit inclure `https://*.logitrak.fr`, puis tester https://login.logitrak.fr/#/user-app/14328.
4. Valider Phase 2 nav (sous-onglets) ou prioriser un nouveau module.
