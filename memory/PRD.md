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

## Bugfix — build Docker VPS (2026-08-11)
- [x] **Bug utilisateur** : `docker compose up -d --build` échouait sur le VPS — « dockerfile parse error on line 28: unknown instruction: , » (ligne orpheline `, "8001"]` après le CMD dans backend/Dockerfile, reliquat d'une ancienne édition it.4).
- [x] Fix : ligne corrompue supprimée + ajout de **pymupdf** et **pillow** au pip install du Dockerfile backend (importés par extraction.py — sans eux le scan aurait planté en prod à l'exécution même après un build réussi).
- [x] Vérifié par testing agent it.7 (iteration_7.json) : parse statique des 2 Dockerfiles OK, croisement imports/dépendances complet, docker-compose.yml valide, régression preview 3/3 (12 véhicules, status SwissCarInfo, dashboard). Docker indisponible dans le pod → pas de build réel possible côté Emergent ; l'utilisateur doit refaire Save to GitHub + git pull + rebuild.

## Bugfix — scan caméra/analyse en production VPS (2026-08-11)
- [x] **Bug utilisateur** : (A) caméra indisponible dans l'iframe du hub (login.logitrak.fr) ; (B) en accès direct la caméra marche mais l'analyse échoue (« Analyse impossible… »).
- [x] **Cause A** : getUserMedia bloqué par le navigateur dans une iframe cross-origin sans `allow="camera"` (non configurable côté hub Navixy user-app). **Limitation navigateur, pas un bug de l'app.**
- [x] **Cause B (reproduite à distance sur la prod)** : EMERGENT_LLM_KEY absente de deploy/.env sur le VPS → RuntimeError du provider OCR masqué par un message générique. Redéploiement VPS confirmé fait (last-modified 11.08 16:07, /scanner/*.js servis 200, CSP OK).
- [x] Fixes : (1) fail-fast **503 explicite** au scan si EMERGENT_LLM_KEY vide (« Scan non configuré — renseignez EMERGENT_LLM_KEY (deploy/.env)… ») avant tout upload ; (2) catch extraction différencié (ImportError emergentintegrations → « Module OCR absent », RuntimeError clé → message config) ; (3) frontend : erreurs caméra différenciées par err.name + cas iframe → message dédié + bouton **« Ouvrir en plein écran »** (scan-open-fullscreen, window.open). Sur smartphone la caméra native (input capture) fonctionne même en iframe.
- [x] Testé : testing agent it.8 (iteration_8.json) — 503 fail-fast validé par monkeypatch (EMERGENT_KEY='', .env intact, aucun document créé), happy-path scan réel OK, NotAllowedError frontend OK, régressions pages OK. Catch différencié réappliqué post-rapport (avait été perdu) — pytest test_scan_failfast.py 4/4. Cas iframe validé par revue de code (simulation window.top fragile en headless).
- ⚠️ **Action utilisateur requise pour résoudre l'analyse en prod** : renseigner EMERGENT_LLM_KEY dans ~/documents/deploy/.env (clé = Universal Key du profil Emergent) puis `docker compose up -d backend`. Puis Save to GitHub + git pull + rebuild pour obtenir les nouveaux messages/bouton plein écran.

## Implemented — Itération 9 · Bannière config + Rapport de conformité PDF (2026-08-12)
- [x] `GET /api/config/status` → {scan_configured, technical_data_configured}. **Bannière ambre** (ConfigBanner) sur la page Véhicules quand une clé serveur manque (EMERGENT_LLM_KEY et/ou SWISSCARINFO_API_KEY), avec consigne deploy/.env. En preview : liste uniquement SwissCarInfo (scan configuré).
- [x] `GET /api/reports/conformite.pdf` (fpdf2 2.8.8, paysage A4, module reports.py) : titre + synthèse (conformes/avertissements/critiques/expirés), tableau « Échéances & conformité » (leasing/assurance/contrôle + jours restants/échu + statut), tableau « Coûts leasing & assurance » (mensualité, mois restants, coût restant, prime annuelle) avec **ligne TOTAL** et montants CHF format suisse (1'234). Audit action=download à chaque export. Bouton « Rapport PDF » (report-pdf-btn) sur la page Véhicules.
- [x] Dépendances : fpdf2 ajouté à requirements.txt + Dockerfile backend (+ COPY reports.py).
- [x] Tests : testing agent it.9 — backend 9/9 pytest (headers/contenu PDF via pymupdf, cross-check dates & coûts vs /api/vehicles, audit), frontend 100 % (bannière 1 item SwissCarInfo, bouton PDF, régressions Dashboard/Véhicules/Échéances/Alertes/Base technique). iteration_9.json.

## Implemented — Itération 10 · Export CSV + Fiche PDF véhicule (2026-08-12)
- [x] `GET /api/reports/couts.csv` : coûts flotte pour Excel — BOM UTF-8, séparateur ';', 15 colonnes (leasing/assurance/contrôle + statut), dates JJ.MM.AAAA, ligne TOTAL. Menu déroulant « Exporter » (export-menu-btn) sur la page Véhicules regroupe Rapport PDF (report-pdf-btn) + CSV (report-csv-btn).
- [x] `GET /api/reports/vehicule/{id}.pdf` : fiche individuelle portrait A4 (reports.py build_vehicle_pdf) — Identité & exploitation, Moteur & consommation, Leasing, Assurance, Contrôle technique, Documents (fichiers non supprimés), Historique (30 derniers audits). Filename fiche-{plaque}.pdf, 404 propre. Bouton « Fiche PDF » (vehicle-report-btn) dans l'en-tête du drawer (visible sur tous les onglets). Audit download pour chaque export.
- [x] Tests : testing agent it.10 — backend 10/10 pytest (BOM/colonnes/TOTAL/cross-check API, contenu fiche PDF via pymupdf, 404, audit +2), frontend 100 % (dropdown, bouton drawer persistant, régressions bannière/pages). iteration_10.json.

## Implemented — Itération 11 · Bouton Synchroniser + retrait du mot « Navixy » (2026-08-12)
- [x] La grande barre noire de synchronisation (NavixyBar) est remplacée par un simple bouton « Synchroniser » (SyncButton, data-testid sync-btn) dans la barre d'actions de la page Véhicules — pastille verte/rouge selon connexion, tooltip statut (x/x véhicules importés), désactivé si non connecté. NavixyBar.jsx supprimé.
- [x] Mot « Navixy » retiré de TOUS les textes visibles : toasts de sync (« Synchronisation réussie · N véhicules »), provenance (source → « Télématique »), messages d'erreur backend (« Clé API de synchronisation non configurée », « Réponse du service de synchronisation invalide », « Véhicule non lié à un tracker GPS », fallback compte → « Télématique »). Les identifiants techniques internes (navixy_tracker_id, endpoints /api/navixy/*, variables env) restent inchangés — invisibles pour l'utilisateur, aucune rupture d'API.
- [x] Self-testé (screenshot + clic réel) : bouton visible/actif, aucune occurrence visible de « Navixy » dans la page, sync E2E OK (12 véhicules mis à jour), ancienne barre absente.

## Implemented — Itération 12 · OCR via Claude Anthropic (2026-08-12)
- [x] **Provider OCR remplacé par Claude Sonnet 4.6** (choix utilisateur, clé Anthropic personnelle fournie et configurée dans backend/.env preview — variable ANTHROPIC_API_KEY, jamais exposée). extraction.py : classe générique LlmVisionProvider(api_key, llm_provider, model) via emergentintegrations ; get_provider(emergent_key, anthropic_key) → **Claude prioritaire si ANTHROPIC_API_KEY présente, GPT/Emergent en secours automatique**. Override possible via DOC_EXTRACTION_PROVIDER/DOC_EXTRACTION_MODEL.
- [x] server.py : fail-fast 503 seulement si LES DEUX clés absentes (message citant ANTHROPIC_API_KEY et EMERGENT_LLM_KEY) ; /api/config/status expose scan_provider ('claude'/'gpt'/null) ; ConfigBanner mise à jour. deploy/.env.example : ANTHROPIC_API_KEY= ajouté.
- [x] Tests : scan E2E réel avec Claude → type assurance 0.99, 7 champs corrects (self-test) ; suite pytest complète 67 passed / 1 skipped (tests mis à jour : failfast patch 2 clés, docscan reset déterministe, skip endpoint OCR obsolète) ; testing agent it.11 100 % backend+frontend (flux UI scan complet via Claude ~6 s, régressions OK). iteration_11.json.
- ⚠️ VPS : ajouter ANTHROPIC_API_KEY dans ~/documents/deploy/.env puis recreate backend. EMERGENT_LLM_KEY devient optionnelle (secours).
- Note mineure non bloquante (it.11) : TestAuditLog::test_download_audit_created flaky en exécution parallèle (état audit concurrent), passe en isolé — sans lien avec Claude.

## Implemented — Itération 13 · Mission « Lecture intelligente des documents » — audit + écarts (2026-08-12)
- [x] **Audit préalable présenté et validé par l'utilisateur** : ~80 % du cahier des charges déjà en place (acquisition unifiée, bibliothèque centrale, Claude, conflits, validation humaine, composants mutualisés). Choix confirmés : rester **sans auth/tenant** (chantier séparé plus tard) ; QC bloquant seulement si inexploitable ; Vignette avec schéma complet ; garder confidence + status.
- [x] **Incohérence de type** : Claude classifie toujours (liste des types dans le prompt même en mode forcé) → réponse `type_mismatch{expected,detected,labels,confidence}` + `detected_type` stocké → bandeau ⚠️ « Ce document semble être X et non Y » + bouton « Utiliser le type détecté » (réutilise reanalyze/document_id, pas de nouveau fichier). Testé E2E : assurance scannée en carte grise → détecté assurance 0.97.
- [x] **Status par champ** `found|uncertain|missing` EN PLUS de confidence (normalisation provider + fallback seuil 0.6) → badge « Incertain » UI + ligne « Non lisibles sur le document : … » (`missing_fields`).
- [x] **Contrôle qualité pré-analyse** (extraction.py check_image_quality, non-LLM) : bloquant 422 uniquement si inexploitable (<250 px ou variance de bords <5 — bords FIND_EDGES recadrés de 2 px pour éviter l'artefact de bordure) ; sinon `quality_warnings` non bloquants affichés en revue. Exécuté AVANT stockage et appel Claude (aucun coût gaspillé).
- [x] **Type « Vignette autoroutière »** (dossier Vignette, champs : annee, type_vignette e-vignette/autocollante, plaque, date_achat, date_expiration, prix_chf, statut — target document ; justificatif = le fichier) + champ **couleur** carte grise. Compteur `applied` du validate inclut désormais les champs target=document.
- [x] **Traçabilité complétée** : imported_by, analyzed_at, detected_type, quality_warnings, validated_by sur le document ; original jamais altéré.
- [x] **Onglet Documents** : recherche par nom (doc-search-input, ouvre tous les dossiers), dossier Vignette, badges statut d'analyse par document (Validé/Analysé/Échec/Analyse…). **Dialog scan** : glisser-déposer (scan-dropzone) + Tout sélectionner/désélectionner dans la revue.
- [x] Tests : testing agent it.12 — 10/10 backend (mismatch, re-scan, vignette+validate, QC bloquant/warning, traçabilité, aucune écriture avant validation, ~4 appels Claude), frontend 100 % 0 erreur console. Fix post-rapport : compteur applied (10/10 re-passés). iteration_12.json + tests/test_docscan_iter12.py.

## Implemented — Itération 14 · Vehicle Data API interne ASTRA/OFROU — Phases 1-2 (2026-08-12)
- [x] **Mission utilisateur validée** : base technique fondée sur les datasets officiels ASTRA/OFROU stockés localement, SANS SwissCarInfo (retiré du chemin actif, code/variables conservés pour compatibilité). Choix : libellé UI « Base officielle ASTRA/OFROU », sync mensuelle auto activée.
- [x] **Phase 1 — Import local** (`backend/astra_data.py`) : 4 datasets téléchargés en streaming (~790 Mo : TAS_Automobil 353 Mo, TAS_Emission 92 Mo, TG-Automobil 323 Mo, verbrauch 19 Mo) → parse ligne à ligne (jamais en mémoire), lots de 1000 ReplaceOne upserts → collections `astra_tas` (210 467), `astra_tas_emissions` (281 358), `astra_tg` (210 673), `astra_tg_verbrauch` (190 626) + suivi `astra_import_runs` (statut/lignes/durée, purge des docs des runs précédents). Import complet ≈ 64 s. Codes carburant traduits (doc officielle TARGA : B=Essence, D=Diesel, E=Électrique, C/F=hybrides…), CO₂ 0 accepté seulement pour E/W/X. Index uniques `_key` (+seq). Fichiers exclus de Git (.gitignore backend/astra_data/) et du contexte Docker (.dockerignore).
- [x] **Phase 2 — Resolver** (`resolve_vehicle_data`) : priorité ASTRA TAS local → ASTRA TG historique ; variantes par boîte (divergences → choix utilisateur, boîte unique connue → résolution auto) ; erreurs typées → HTTP : 503 non importé, **422 sans homologation** (message explicite : plaque seule indisponible sans fournisseur externe, VIN = phase 3), 404 introuvable. `lookup_ms` mesuré (<10 ms local, 234 ms E2E réseau — objectif <500 ms atteint). Endpoints : GET /api/astra/status · POST /api/astra/import (fond, 409 si en cours, download intelligent <25 j) · GET /api/astra/search?homologation|vin|plate (réponses de limitation explicites : plate_lookup_unavailable_without_external_provider). enrich-technical/apply : provider dynamique (astra_tas/astra_tg) dans field-meta + audit « (source: Base officielle ASTRA/OFROU) ». Garde CAN/OBD inchangée.
- [x] **Sync auto** : import au démarrage si collections vides (ASTRA_SYNC_ENABLED=true, défaut) + job APScheduler mensuel (30 j, force re-download). Env : ASTRA_DATA_DIR, ASTRA_SYNC_ENABLED (backend/.env preview + deploy/.env.example + volume Docker logitrak-fleet_astra_data + Dockerfile COPY astra_data.py).
- [x] **UI** : TechnicalEnrichDialog relabellisé (Base officielle ASTRA/OFROU, Registre TAS/TG, tech-match-info marque/modèle/homologation, hint 422 tech-hint-missing-homologation orientant vers le scan carte grise) ; ConfigBanner (données non importées au lieu de clé manquante) ; note provenance CarteGriseTab dynamique astra/swisscarinfo.
- [x] **Docs & tests** : `docs/vehicle-data-api.md` complet ; `tests/test_astra.py` (15 tests : normalisation, parsers fixtures, priorité WLTP, CO₂ BEV, divergence variantes, API limitations, E2E enrich 200/422/404, perf) ; tests existants adaptés (status astra, apply provider astra_tas). Testing agent it.13 : **backend 31/31, frontend 100 %**, 0 erreur console, données de test restaurées (iteration_13.json).
- Homologation de démonstration : 1AA101 (ALFA ROMEO 145 1.9 TD — Diesel, 1929 cm³, 66 kW, 6.4 L NEDC, 171 g CO₂). TAS couvre aussi les clés TG (superset) ; TG conservé en secours.
- ⚠️ VPS : Save to GitHub → git pull → `docker compose up -d --build`. Au 1er démarrage le backend télécharge (~790 Mo) puis importe (~5-10 min) automatiquement dans le volume dédié. Suivi : `curl http://127.0.0.1:8090/api/astra/status`.

## Implemented — Itération 15 · Recherche VIN + Statut ASTRA UI + Enrichissement flotte + Scan→Enrichir (2026-08-12)
- [x] **Recherche VIN (eDatenblatt)** : dataset officiel eDatenblatt.csv (807 Mo) téléchargé + importé → 581 743 lignes dédupliquées en **239 471 configurations** (upsert par préfixe VIN 10 car. + empreinte md5 de configuration, la date de fabrication propre à chaque véhicule est exclue). Les VIN ASTRA sont anonymisés aux 10 premiers caractères → correspondance par préfixe ; configs divergentes → variantes (label modèle·version·kW) ; >12 configs → erreur explicite `ambiguous_vin` (409). Champs sourcés de la fiche COC (codes carburant numériques officiels traduits, hybride via ClassOfHybridVehicleCode, électrique via PureElectricVehIndicator, WLTP combiné/pondéré puis NEDC). Resolver : homologation (TAS→TG) puis **repli VIN** ; 422 seulement si ni homologation ni VIN. `/api/astra/search?vin=` opérationnel.
- [x] **Verrou d'import en base** (`astra_locks`, atomique, TTL 30 min) : corrige un bug réel découvert en preview — le double démarrage (hot-reload) lançait 2 imports concurrents dont les purges croisées se supprimaient mutuellement. `import_active()` couvre multi-process ; POST /api/astra/import → 409 si en cours.
- [x] **UI Statut ASTRA** : menu « Base technique » (page Véhicules, `astra-menu-btn`) → `AstraStatusDialog` (5 datasets, compteurs, dernier import, badge import en cours avec polling 3 s, bouton « Mettre à jour les données »).
- [x] **Enrichissement flotte** : POST `/api/vehicles/enrich-technical/batch` (résout les 12 véhicules, AUCUNE écriture, statuts found/missing_homologation/not_found/ambiguous_vin) + `FleetEnrichDialog` : revue groupée, cases cochables seulement si champs applicables sans variante, conflits ignorés et renvoyés vers la fiche, application explicite par véhicule (provenance/audit conservés).
- [x] **Scan → Enrichir** : après validation d'un scan carte grise qui renseigne le n° d'homologation (auparavant vide), le dialogue Base technique s'ouvre automatiquement avec toast (CarteGriseTab, `scanValidatedRef` + useEffect).
- [x] **Tests** : test_astra.py étendu à 22 tests (parse eDatenblatt, normalize_vin, VIN search/fallback/ambigu, batch flotte) ; testing agent it.14 : **backend 38/38, frontend 100 %** (iteration_14.json), un test obsolète corrigé par l'agent (nettoyage VIN dans test 422). Docs `docs/vehicle-data-api.md` à jour.
- Références de test : VIN `W1N4N5DB3P1234567` → Mercedes-AMG GLA 45 (1 candidat) ; `WVGZZZA1ZR…` → ambigu (56 configs) ; flotte réelle : BE 579928 (1VD672, 3 champs applicables), VD 602 548 (1AE831, variantes de boîte).
- ⚠️ VPS : premier démarrage télécharge désormais **~1,6 Go** (5 datasets) puis importe (~10-15 min), automatique via ASTRA_SYNC_ENABLED=true.

## Implemented — Itération 16 · Historique des valeurs + Rapport environnemental + Préparation VPS (2026-08-12)
- [x] **Historique des valeurs / retour en arrière** : à l'apply ASTRA, `vehicle_field_meta` conserve `previous_value` + `applied_value` ; nouvel endpoint POST `/api/vehicles/{id}/enrich-technical/revert` {field} (restaure l'ancienne valeur, supprime la provenance, audit « retour à la valeur précédant l'enrichissement ASTRA » ; 404 sans historique, 422 champ inconnu). UI CarteGriseTab : liste `tech-history-list` sous la note de provenance (« Label : ancienne barrée → nouvelle » + bouton « Rétablir » `tech-revert-{field}`), rafraîchie via onSaved.
- [x] **Rapport conformité enrichi** : nouvelle section PDF « Environnement — consommation & CO2 officiels » (moyennes flotte : CO₂ officiel moyen g/km + conso officielle moyenne avec ratio de véhicules renseignés, puis tableau Plaque/Véhicule/Carburant/Conso officielle (norme)/Conso réelle/CO₂ (norme), note de source ASTRA/CAN). Vérifié sur données réelles : « CO2 officiel moyen : 156 g/km (2/12) ».
- [x] **Préparation déploiement VPS** : docker-compose validé (volume `logitrak-fleet_astra_data`, ASTRA_DATA_DIR=/data/astra), Dockerfile backend inclut astra_data.py, .dockerignore/.gitignore excluent les 1,6 Go de datasets, deploy/README.md mis à jour (section ASTRA auto-import + OCR Claude). Le déploiement lui-même reste à faire par l'utilisateur : Save to GitHub → git pull → docker compose up -d --build.
- [x] **Tests** : pytest test_astra.py étendu à 25 tests (apply→previous_value→revert e2e, 404/422) — 25/25 ; PDF vérifié par décompression des streams ; testing agent it.15 (frontend) : **100 % (3/3 flux + régressions)**, état restauré (iteration_15.json).

## Implemented — Itération 17 · Comparateur de consommation flotte (2026-08-12)
- [x] **Backend** : GET `/api/fleet/consumption-ranking` — classement du plus sobre au plus gourmand (référence = conso réelle si mesurée, sinon officielle), écart réel-officiel en L et % (`ecart_l`, `ecart_pct`), rangs, section `sans_donnees` pour les véhicules sans consommation. Aucune écriture. Tests `tests/test_fleet_ranking.py` 3/3 (tri, écart 0.9 L/15 %, sans-données).
- [x] **UI** : bouton « Consommation » (icône carburant, `conso-open-btn`) sur la page Véhicules → `FleetConsumptionDialog` : lignes classées avec pastille de rang (1 = vert, dernier = rouge), doubles barres proportionnelles Officielle (grise, norme affichée) / Réelle (verte si ≤ officielle, rouge sinon), badge d'écart (+0.9 L · +12 % rouge / vert si négatif / « officielle inconnue » sinon), pastilles des véhicules sans données + aide (Base technique ASTRA ou conso réelle).
- [x] **Testé** : pytest 3/3 + testing agent it.16 frontend **100 %** (mono et multi-véhicules avec rangs/couleurs/écarts corrects, restauration d'état vérifiée, 0 erreur console) — iteration_16.json. Données réelles : BE 579928 rang 1 (7.2 → 8.1, +12 %).

## Backlog (prioritized)
- Phase 2 nav (à valider): sous-onglets contextuels (ex. Véhicules: Liste/Échéances), en-tête module avec fil d'Ariane + recherche globale.
- Phase 3+ (gros chantiers, à cadrer 1 par 1): modules Contrats & renouvellements, Conducteurs, Clients, Modèles, Corbeille/Favoris/Partagés ; permissions/rôles + auth ; multi-tenant.
- P1: Envoi e-mail RÉEL des alertes (attente EMAIL_PROVIDER/API_KEY/FROM/RECIPIENTS).
- P2: Export PDF/CSV des coûts (leasing/assurance) et rapport de conformité. ✅ FAIT it.9 (PDF) — reste CSV si demandé.
- P2: Vue calendrier (grille mensuelle) en complément de la timeline.
- P3: Refactor server.py en routers ; upload async.

## Next Tasks
1. Déployer les itérations 4-14 sur le VPS : Save to GitHub → `cd ~/documents && git pull` → `cd deploy && docker compose up -d --build`. Renseigner ANTHROPIC_API_KEY dans deploy/.env. Au 1er boot, import ASTRA auto (~790 Mo, 5-10 min) — suivre via `curl http://127.0.0.1:8090/api/astra/status`.
2. Vérifier l'iframe hub après redéploiement : test visuel utilisateur dans https://login.logitrak.fr/#/user-app/14328 (CSP déjà confirmée côté serveur).
3. Phase 3 Vehicle Data API (à valider) : import eDatenblatt (~807 Mo) → recherche par VIN exact ; fallbacks optionnels AutoRef/NHTSA si accès fournis.
4. SwissCarInfo : clé plus nécessaire (resolver 100 % ASTRA local). Code conservé en historique uniquement.
