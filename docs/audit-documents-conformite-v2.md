# AUDIT — Documents & Conformité V2 (LOGITRAK)

- **Date de l'audit** : 2026-08-25 10:13 UTC
- **Environnement audité** : preview Emergent (staging) — base MongoDB `test_database` (via `MONGO_URL`/`DB_NAME` de `backend/.env`). **La production VPS n'a PAS été auditée ici : NON VÉRIFIÉ.**
- **Commit** : `2f8c434` — « Socle véhicule canonique multi-client livré » (arbre de travail propre, `git status` : aucun fichier suivi modifié)
- **Nature** : audit strictement en lecture seule. **AUCUN code applicatif modifié. AUCUNE écriture MongoDB d'audit** (le seul trafic d'écriture provient de l'exécution de la suite pytest existante, qui crée puis nettoie ses propres données de test ; l'instantané Mongo a été capturé AVANT ce run).
- **CODE APPLICATIF MODIFIÉ : NON** (aucune correction de collecte pytest n'a été nécessaire — voir §2.3).

---

## 1. SYNTHÈSE EXÉCUTIVE

1. Le module actuel n'est **pas** un système documentaire générique : `documents` est une bibliothèque de fichiers + pipeline OCR, avec **dossiers codés en dur** (8 côté backend, 9 côté frontend — divergence Vignette) et types de documents codés en dur (8 `DOC_TYPES`).
2. **Assurance et Leasing ne sont PAS des documents** : ce sont des sous-objets embarqués de `vehicles` (`vehicles.assurance`, `vehicles.leasing`). C'est la source de vérité unique pour l'affichage, le dashboard, la timeline, les alertes et les rapports.
3. Les documents scannés/validés conservent une **copie historique** (`validated_fields`) qui peut diverger de la fiche véhicule : **5 divergences réelles constatées** (4 sur documents soft-supprimés, 1 sur document actif).
4. Le décompte de tests est clarifié : **149 tests collectés / 147 PASS / 2 SKIP / 0 FAIL** (run réel du 2026-08-25, 121.94 s). L'ancien « 148 PASS » était **incorrect** (mélange collectés/passés) ; le « 10+118+30=158 » double-comptait les 10 tests multi-tenant inclus dans les 118 de régression.
5. Multi-tenant : backfill `tenant_id` **complet** (0 document sans tenant sur les 9 collections métier), mais index tenant manquants sur `files`, `inspections`, `alerts`, `audit_logs`, `vehicle_field_meta`.
6. **Découverte critique** : en preview, **11 des 12 véhicules portent des données Assurance/Leasing/Contrôle FICTIVES prouvées** (signatures exactes du code `_demo_admin_data` : contrats `LSG-2022-45xx`, polices `POL-78xxxx`, commentaires « Données de démonstration »). Migrer ces valeurs telles quelles poserait un problème « real data only ». État de la production VPS : NON VÉRIFIÉ.
7. **Module coûts documentaire : ABSENT** (seuls `leasing.mensualite_chf` / `assurance.prime_annuelle` agrégés dans dashboard/rapports).
8. Aucune notion de catégorie configurable, d'exigence documentaire par tenant, de statut documentaire central, d'échéance générique ni de préavis/date de résiliation : **NON RÉALISÉ**.
9. Verdict : **READY WITH CONDITIONS** (§17) — la migration est faisable de façon idempotente et non destructive, sous réserve de 5 décisions utilisateur (§16).

---

## 2. DÉCOMPTE DES TESTS — RE-COLLECTE PROPRE ET VÉRIFIABLE

### 2.1 DÉCOMPTE CORRIGÉ (run réel du 2026-08-25)

```text
TOTAL DE TESTS UNIQUES COLLECTÉS : 149
TOTAL DE TESTS UNIQUES EXÉCUTÉS  : 149 (147 exécutés jusqu'au verdict + 2 skips)
PASS   : 147
FAIL   : 0
SKIP   : 2
XFAIL  : 0
XPASS  : 0
ERROR  : 0
COLLECTION ERRORS : 0 (avec REACT_APP_BACKEND_URL exporté) / 2 (sans — voir §2.3)
Durée  : 121.94 s
```

Les 2 SKIP (volontaires, identifiés par node ID) :
1. `tests/test_alerts_ocr.py::test_ocr_carte_grise_extracts_plate_and_vin` — `@pytest.mark.skip(reason="Endpoint /carte-grise/ocr remplacé par /documents/scan — couvert par test_docscan.py")` (ligne 117). Skip permanent volontaire — endpoint obsolète.
2. `tests/test_sync_integrity.py::TestRealNavixyPushReversible::test_push_color_and_restore` — `@pytest.mark.skipif(os.environ.get("NAVIXY_WRITE_TEST") != "1")` (ligne 122). Test d'écriture RÉELLE Navixy, verrouillé volontairement hors opt-in explicite.

### 2.2 COLLECTE PAR FICHIER (source : `pytest --collect-only -q` par fichier)

| Fichier | Collectés | PASS (run 2026-08-25) | SKIP |
|---|---:|---:|---:|
| test_alerts_ocr.py | 4 | 3 | 1 |
| test_astra.py | 25 | 25 | 0 |
| test_config_and_report.py | 9 | 9 | 0 |
| test_docscan.py | 17 | 17 | 0 |
| test_docscan_iter12.py | 10 | 10 | 0 |
| test_fleet_ranking.py | 3 | 3 | 0 |
| test_logitrak_api.py | 9 | 9 | 0 |
| test_multitenant.py | 10 | 10 | 0 |
| test_navixy.py | 8 | 8 | 0 |
| test_p0_core.py | 24 | 24 | 0 |
| test_reports_csv_and_vehicle.py | 10 | 10 | 0 |
| test_scan_failfast.py | 4 | 4 | 0 |
| test_sync_integrity.py | 9 | 8 | 1 |
| test_tech_enrich_and_scan_pdf.py | 7 | 7 | 0 |
| **TOTAL** | **149** | **147** | **2** |

### 2.3 LES 2 ERREURS DE COLLECTE

```text
Erreur 1
Fichier concerné : tests/test_alerts_ocr.py (ligne 8)
Erreur exacte    : KeyError: 'REACT_APP_BACKEND_URL'
                   (BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/"))
Cause            : le module lit la variable d'environnement AU MOMENT DE L'IMPORT ;
                   si le shell qui lance pytest ne l'exporte pas, l'import échoue
                   avant toute collecte des 4 tests du fichier.
Préexistante ?   : OUI — code inchangé depuis l'itération 3 (git blame : aucun commit récent
                   sur cette ligne) ; le fichier passait dans tous les runs précédents
                   car l'environnement était exporté.
Impact décompte  : -4 tests collectés quand l'env manque (137 au lieu de 149) + arrêt pytest.
Bloque-t-elle ?  : NON quand REACT_APP_BACKEND_URL est exportée (méthode utilisée ici) —
                   les 4 tests collectent et 3 passent + 1 skip.

Erreur 2
Fichier concerné : tests/test_navixy.py (ligne 7)
Erreur exacte    : AttributeError: 'NoneType' object has no attribute 'rstrip'
                   (BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/"))
Cause            : même cause exacte (env lue à l'import, .get() retourne None sans l'env).
Préexistante ?   : OUI — même historique.
Impact décompte  : -8 tests collectés quand l'env manque.
Bloque-t-elle ?  : NON avec l'env exportée — 8/8 passent.
```

**Aucune correction de code n'a été nécessaire** : l'erreur est un problème d'invocation (env non exportée), pas un défaut des tests ni de l'application. Conformément à la consigne « si l'erreur peut être comprise sans modification, préfère ne rien modifier », **rien n'a été modifié**. `137 + 4 + 8 = 149` : la comptabilité est exacte.

### 2.4 EXPLICATION DU 148 VS 158 — HYPOTHÈSE A CONFIRMÉE (avec correctif)

Les « suites » des anciens rapports étaient des découpages du MÊME répertoire `tests/` :

- **Suite « OCR » (3 fichiers)** = test_docscan (17) + test_docscan_iter12 (10) + test_alerts_ocr (4) = **31 collectés → 30 PASS + 1 SKIP** (le skip = endpoint OCR obsolète). C'est l'origine exacte du « 30 OCR ».
- **Suite « régression » (les 11 autres fichiers)** = 25+9+3+9+10+8+24+10+9+4+7 = **118 collectés → 117 PASS + 1 SKIP** (le skip = écriture Navixy verrouillée).
- **Suite « multi-tenant »** = `test_multitenant.py` (10 tests) — **entièrement INCLUSE dans les 118 de régression**.

Donc :
```text
10 (multi-tenant) + 118 (régression) + 30 (OCR) = 158  → FAUX : double comptage
   des 10 tests multi-tenant, déjà contenus dans les 118 de régression.

118 (régression, DONT les 10 multi-tenant) + 31 (OCR) = 149 tests uniques.
PASS réels : 117 + 30 = 147.  SKIP réels : 1 + 1 = 2.
```

L'ancien « **148 PASS / 0 FAIL / 2 SKIP** » était **INCORRECT** : 148 provenait de l'addition `118 + 30`, qui mélange un nombre de tests **collectés** (118, incluant 1 skip) avec un nombre de tests **passés** (30). Le vrai total passé est **147**. Par ailleurs 148 PASS + 2 SKIP = 150 ≠ 149 collectés : l'incohérence interne de l'ancien rapport est ainsi démontrée.

### 2.5 DOUBLONS DE SUITES

Les 10 node IDs de `tests/test_multitenant.py::*` apparaissaient dans DEUX sous-totaux (« multi-tenant : 10 » ET « régression : 118 ») mais ne sont exécutés qu'une fois dans la suite globale. Aucun autre chevauchement : les 14 fichiers sont disjoints deux à deux (union = 149, somme des fichiers = 149).

### 2.6 COMMANDES UTILISÉES (exactes)

```bash
# Collecte SANS env (reproduit les « 2 erreurs ») :
cd /app/backend && python -m pytest tests/ --collect-only -q
# → 137 tests collected, 2 errors

# Collecte AVEC env (correcte) :
cd /app/backend && export REACT_APP_BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2) \
  && python -m pytest tests/ --collect-only -q
# → 149 tests collected in 0.70s

# Collecte par fichier :
for f in tests/test_*.py; do python -m pytest "$f" --collect-only -q | grep -c "::"; done

# Exécution complète réelle :
cd /app/backend && export REACT_APP_BACKEND_URL=... && python -m pytest tests/ -v --tb=short
# → 147 passed, 2 skipped, 5 warnings in 121.94s
```

### 2.7 MATRICE DE COMPTAGE

| Suite | Collectés | PASS | FAIL | SKIP | ERROR | Incluse dans une autre suite ? |
|---|---:|---:|---:|---:|---:|---|
| Globale (`tests/`) | 149 | 147 | 0 | 2 | 0 | — |
| Régression (11 fichiers hors OCR) | 118 | 117 | 0 | 1 | 0 | ⊂ Globale |
| Multi-tenant (`test_multitenant.py`) | 10 | 10 | 0 | 0 | 0 | ⊂ Régression ⊂ Globale |
| OCR (docscan + iter12 + alerts_ocr) | 31 | 30 | 0 | 1 | 0 | ⊂ Globale, disjointe de Régression |

### 2.8 CONCLUSION DU DÉCOMPTE

```text
ANCIEN RAPPORT INCORRECT — total corrigé à : 149 collectés / 147 PASS / 2 SKIP / 0 FAIL
```

---

## 3. RÉALISÉ (état actuel prouvé)

| # | Élément | Preuve |
|---|---|---|
| R1 | Bibliothèque documentaire par véhicule (upload manuel + scan) | `server.py` : `POST /api/vehicles/{id}/documents` (l.979), `GET .../documents` (l.969), `DELETE /api/documents/{id}` (l.1009, soft-delete) ; collection `documents` : 100 docs (30 actifs / 70 soft-supprimés) |
| R2 | Pipeline OCR complet à validation humaine obligatoire | `POST .../documents/scan` (l.1580) → `documents.extracted_fields` (69 docs) → `POST /api/documents/{id}/validate` (l.1752) seul point d'écriture fiche véhicule. Test it.12 : « aucune écriture avant validation » (10/10) |
| R3 | Provenance + audit trail des validations | `vehicle_field_meta` (36 docs : 35 `document_scan`, 1 `astra_tas`) ; `audit_logs` 368 entrées (scan 103, modify 80, download 73, validate 29…) |
| R4 | Isolation tenant des accès documents/fichiers | `find_tenant_vehicle` (l.667, 404 cross-tenant) sur list/add/scan/validate ; `GET /api/files/{path}` protégé par `_path_belongs_to_tenant` (l.692) ; `test_multitenant.py` 10/10 |
| R5 | Backfill tenant complet (preview) | Mesuré : 0 doc sans `tenant_id` sur vehicles(12), documents(100), files(11), inspections(3), alerts(61), audit_logs(368), vehicle_field_meta(36), users(1) — tenant unique `default` |
| R6 | tenant_id résolu du JWT, jamais du frontend | `require_auth` → `request.state.tenant_id` (l.50-54) ; `tid(request)` (l.663) ; aucun paramètre tenant dans `frontend/src/lib/api.js` |
| R7 | Échéances Leasing/Assurance/Contrôle calculées + alertes seuils | `compute_metrics` (l.578), `GET /api/timeline` (l.1105), `run_alerts` (l.1404) seuils 180/90/30 · 90/60/30 · 90/60/30/7, dédup par (vehicle, type, threshold, due_date) |
| R8 | Rapports PDF/CSV consommant leasing/assurance | `reports.py` : `build_conformity_pdf`, `build_costs_csv`, `build_vehicle_pdf` ; endpoints `/api/reports/*` (l.1913-1951) avec audit download |
| R9 | Stockage fichiers hors Mongo, servi authentifié | Emergent object storage (preview) / disque local (VPS, `STORAGE_BACKEND=local`, garde anti path-traversal `_local_path` l.134) ; chemins `logitrak-fleet/uploads/{vehicle_id}/{uuid}.{ext}` ; 100 % des 100 docs préfixés `logitrak-fleet` |
| R10 | Seed démo désactivé par défaut | `seed_data()` et `POST /api/demo/fill-admin` gardés par `SEED_DEMO_DATA` (absent de backend/.env → défaut false → 403) ; 0 véhicule `source=demo` en base |

## 4. PARTIEL (avec limites précises)

| # | Élément | Ce qui existe | Limite prouvée |
|---|---|---|---|
| P1 | Champs documentaires structurés | `documents.document_data` pour les types `target=document` (vignette/facture/amende/autre) | Seulement 8 docs (tous vignette, tous soft-supprimés) ; PAS de statut, PAS d'échéance générique, PAS de montant exploité par le moteur d'alertes |
| P2 | Catégorisation des documents | `folder` (8 dossiers backend `FOLDERS` l.964) + `document_type` (8 `DOC_TYPES`, extraction.py l.13) | Codés en dur, identiques pour tous les tenants ; **divergence backend/frontend : « Vignette » absent de FOLDERS backend → un upload manuel dans le dossier Vignette (visible dans l'UI, DocumentsTab.jsx l.18) est silencieusement reclassé « Divers » (l.997)** |
| P3 | « Conformité documentaire » | KPI `documents_missing` du dashboard : présence des 4 `REQUIRED_FOLDERS` (l.966) par véhicule | Règle fixe non configurable ; teste la présence d'un fichier dans un dossier, pas sa validité/expiration |
| P4 | RBAC | `users.role="superadmin"` existe (auth.py l.107) | **Aucune vérification de rôle nulle part** ; 1 seul compte ; pas de gestion utilisateurs/tenants dans l'UI |
| P5 | Audit trail documentaire | scan/validate/download audités | `add_document` (upload manuel) et `delete_document` **ne créent AUCUNE entrée d'audit** (vérifié l.979-1015) ; 318/368 entrées `user="anonymous"` (héritage pré-auth) |
| P6 | Alertes persistées | `alerts` 61 entrées (50 threshold + 11 digest), dédup fonctionnelle | Uniquement leasing/assurance/contrôle depuis `vehicles` ; e-mail 100 % `mocked` ; `ALERT_RECIPIENTS` est un env GLOBAL (l.345) — non tenantisé |
| P7 | Index multi-tenant | `vehicles(tenant_id+id, tenant_id+navixy_tracker_id)`, `documents(tenant_id+vehicle_id)`, `tenant_integrations(tenant+provider unique)` | Manquants : `files`, `inspections`, `alerts`, `audit_logs`, `vehicle_field_meta`, `fuel_snapshots` (aucun index tenant) ; aucun index unique sur les `id` métier (`vehicles.id`, `documents.id` non indexés) |

## 5. NON RÉALISÉ (sans embellissement)

1. **Catégories/sous-catégories configurables par tenant** — aucune collection, aucun endpoint, aucune UI.
2. **Moteur de statut documentaire central** (VALID / EXPIRING_SOON / EXPIRED / MISSING / TO_VERIFY / RENEWAL_IN_PROGRESS / ARCHIVED) — inexistant ; seuls existent `extraction_status` (processing/done/failed/validated) et `is_deleted`.
3. **Règles de documents requis configurables** (par tenant/profil de véhicule) — inexistant (seul REQUIRED_FOLDERS codé en dur).
4. **Score de conformité documentaire** — inexistant (le KPI actuel compte des dossiers, pas des documents valides).
5. **Échéances génériques sur documents** (expiry_date, préavis, date limite de résiliation) — inexistant ; seules les 3 dates des sous-objets `vehicles` alimentent timeline/alertes. Aucune collection `deadlines`.
6. **Vues Documents transverses** (Tous / Manquants / À vérifier / Expirés / Archivés) — inexistant ; la bibliothèque n'existe QUE par véhicule (drawer).
7. **Module coûts** — `MODULE COÛTS DOCUMENTAIRE : ABSENT`. Aucune collection coût ; seuls `leasing.mensualite_chf/cout_total` et `assurance.prime_annuelle` agrégés (dashboard l.1086-1087, rapports).
8. **Timeline d'événements documentaires par véhicule** — inexistant en tant que telle (seul `/vehicles/{id}/history` = 50 derniers audit_logs).
9. **Alertes e-mail/SMS réelles** — non configurées (100 % mocked, prouvé sur les 61 alertes).
10. **Gestion des tenants/utilisateurs (création de comptes clients)** — inexistant (1 user, 1 tenant, création manuelle en base uniquement).

---

## 6. CARTOGRAPHIE DE L'EXISTANT

### 6.1 Matrice de synthèse

| Domaine | État | Stockage actuel | Backend | Frontend | Source de vérité actuelle | Problème principal |
|---|---|---|---|---|---|---|
| Documents (fichiers) | RÉALISÉ | `documents` (métadonnées) + object storage (binaires) | list/add/delete/scan/validate/files | DocumentsTab + DocFolderSection + ScanDocumentDialog (drawer) | `documents` | Dossiers/types codés en dur ; divergence Vignette ; pas de statut/échéance |
| Assurance | RÉALISÉ (structure) | `vehicles.assurance` (sous-objet) | PUT /vehicles (fusion pointée) ; validate scan écrit dedans | AssuranceTab (lit `vehicle.assurance`, l.22) | `vehicles.assurance` | 11/12 valeurs preview = DÉMO PROUVÉE ; copie divergente dans documents validés |
| Leasing | RÉALISÉ (structure) | `vehicles.leasing` | idem | LeasingTab (lit `vehicle.leasing`, l.21) | `vehicles.leasing` | idem |
| Échéances | PARTIEL | AUCUNE collection — calcul à la volée | compute_metrics / GET /timeline / GET /alerts | TimelinePage, AlertsPage, KPI | dates des sous-objets `vehicles` | Limité à 5 dates fixes (leasing/assurance/contrôle/expertise/maintenance) ; rien pour documents génériques |
| Alertes | PARTIEL | `alerts` (61, journal de notifications) | run_alerts (startup + APScheduler 24 h + POST /alerts/run) | AlertsPage | calcul depuis `vehicles` ; `alerts` = journal | e-mail mocked ; destinataires globaux non tenantisés |
| Fichiers | RÉALISÉ | object storage Emergent (preview) / local (VPS) ; réfs dans documents.storage_path + pages[].storage_path, files, inspections.photos | GET /api/files/{path} (contrôle tenant), POST /upload | fileUrl()/photoSrc() avec ?token= | `documents`/`files` | soft-delete ne purge jamais les binaires ; fichiers de docs supprimés encore servis |
| OCR | RÉALISÉ | `documents.extracted_fields` (propositions) + `validated_fields` (trace) | scan → validate ; provider Claude Sonnet 4.6 (extraction.py get_provider l.327) | ScanDocumentDialog (conflits, badges confiance) | propositions : documents ; valeurs : `vehicles` après validation | copie `validated_fields` peut diverger ensuite de la fiche |
| Coûts | NON RÉALISÉ | champs épars dans `vehicles` | dashboard + reports (agrégation lecture) | KPI dashboard, exports | `vehicles.leasing/assurance` | pas de module, pas d'historique, pas de lien document→coût |
| Audit trail | PARTIEL | `audit_logs` (368) | audit() sur scan/validate/modify/download/enrich/integrity/navixy | ProvenanceSection (history) | `audit_logs` | upload/suppression documents non audités ; 318 entrées « anonymous » pré-auth |

### 6.2 Endpoints documentaires actuels (contrat de compatibilité à préserver)

```text
GET    /api/vehicles/{id}/documents        liste (actifs) du véhicule (tenant-vérifié)
POST   /api/vehicles/{id}/documents        upload manuel (folder parmi FOLDERS sinon Divers)
DELETE /api/documents/{doc_id}             soft-delete (tenant-scopé)
POST   /api/vehicles/{id}/documents/scan   scan multi-fichiers OU ré-analyse document_id
POST   /api/documents/{doc_id}/validate    applique les champs choisis vers la fiche véhicule
GET    /api/document-types                 8 types codés en dur
GET    /api/files/{path}                   sert un binaire (contrôle appartenance tenant)
POST   /api/upload                         upload générique (photos/inspections) → files
Consommateurs indirects : /api/dashboard, /api/timeline, /api/alerts[/log|/run],
/api/reports/conformite.pdf, /api/reports/couts.csv, /api/reports/vehicule/{id}.pdf,
/api/vehicles/{id}/history, /api/vehicles/{id}/field-meta
```

### 6.3 Frontend concerné

```text
pages/      Dashboard.jsx (KPI documents_missing), Vehicles.jsx, TimelinePage.jsx,
            AlertsPage.jsx, IntegrityPage.jsx, Login.jsx (⚠ bouton démo : identifiants
            superadmin codés en dur dans le bundle — demande utilisateur it.20)
drawer      VehicleDrawer.jsx + tabs/ : GeneralTab, LeasingTab, AssuranceTab, CarteGriseTab,
            ControleTab, InspectionTab, DocumentsTab (9 dossiers UI dont Vignette)
composants  DocFolderSection (upload/preview/download/delete), ScanDocumentDialog (810 l.),
            DocumentScanCard, DocumentCropper, DropZone, FilePreview
api.js      getDocuments/uploadDocument/deleteDocument/scanVehicleDocument/
            validateScannedDocument/fileUrl (token en query)
```

---

## 7. INSPECTION MONGODB (LECTURE SEULE — instantané avant le run pytest)

### A. Collections

| Collection | Nb docs | tenant_id | vehicle_id | Rôle réel |
|---|---:|---|---|---|
| vehicles | 12 | 12/12 `default` | — (id = uuid canonique) | Véhicule canonique + sous-objets leasing/assurance/carte_grise/controle_technique |
| documents | 100 (30 actifs / 70 soft-del) | 100/100 | 100/100 valides sauf 1 orphelin | Métadonnées documents + OCR |
| files | 11 | 11/11 | 9 « misc » + 2 orphelins | Uploads génériques (tests) |
| inspections | 3 | 3/3 | **3/3 orphelines** | États des lieux (résidus démo/tests) |
| alerts | 61 | 61/61 | 50/61 (11 digests sans vehicle_id — normal) | Journal notifications (100 % mocked) |
| audit_logs | 368 | 368/368 | 263 avec vehicle_id, 105 null (exports/flotte — normal) | Trace |
| vehicle_field_meta | 36 | 36/36 | 36/36 valides | Provenance par champ |
| fuel_snapshots | 0 | — | — | Snapshots CAN (vide) |
| users | 1 | 1/1 | — | Superadmin |
| tenants | 1 (`default` « Compte pilote ») | — | — | Référentiel tenants |
| tenant_integrations | 1 (navixy/default, enabled, write_enabled) | — | — | Credentials par tenant (api_hash non exposé ici) |
| login_attempts | 0 | — | — | Anti force brute |
| astra_* | 210 467 / 281 358 / 210 673 / 190 626 / 239 471 + runs 18 + locks 1 | non tenantisées (référentiel public partagé — normal) | — | Données officielles ASTRA |

**Aucun document sans tenant, tenant null ou tenant vide sur les 9 collections métier** (mesuré collection par collection). Tenant unique : `default`.

### B. Structure documentaire réelle observée (collection `documents`, 100 docs)

```text
Toujours présents (100/100) : id, vehicle_id, tenant_id, folder, original_filename,
                              storage_path, content_type, size, is_deleted, created_at
Sous-ensemble scan (70/100) : pages[], document_type, extraction_status, source,
                              type_confidence, extracted_fields (69)
Sous-ensemble it.13 (38/100): analyzed_at, detected_type, imported_by, quality_warnings
Après validation (29/100)   : validated_at, validated_fields, document_data ;
                              validated_by seulement 12/100 (champ ajouté it.13 —
                              17 validations antérieures ne l'ont pas : champ legacy hétérogène)
document_data non vide      : 8 docs (tous type vignette) — clés : annee, date_expiration,
                              prix_chf, statut, type_vignette
Répartition folder (100)    : Assurance 32, Carte grise 26, Divers 20, Leasing 12, Vignette 10
Répartition ACTIFS (30)     : Carte grise 15, Assurance 9, Leasing 3, Divers 3 — 0 vignette active
extraction_status           : done 41, validated 29, None 30 (uploads manuels sans scan)
Dates : 100 % chaînes ISO (created_at/analyzed_at/validated_at ISO datetime ;
        dates métier YYYY-MM-DD). Aucun ISODate BSON, aucun format hétérogène détecté.
IDs   : 100 % uuid string (aucun ObjectId métier).
```

### C. Assurance — stockage réel (tous les emplacements)

| Emplacement | Champs | Nb concernés | Utilisé par |
|---|---|---:|---|
| `vehicles.assurance` | compagnie, numero_police, type_couverture, prime_annuelle, franchise, assistance, contact_sinistre, date_debut, date_echeance | 12/12 renseignés (compagnie/echeance/prime) | AssuranceTab, dashboard, timeline, alerts, reports — **source de vérité affichage** |
| `documents` (folder Assurance) | fichier + extracted_fields + validated_fields (copie des valeurs validées) | 32 docs (9 actifs) | onglet Assurance/Documents (justificatifs) |
| `alerts` (type assurance) | due_date, plaque, threshold (instantanés) | 19 | AlertsPage (journal) |
| `vehicle_field_meta` | provenance des champs assurance.* validés par scan | inclus dans les 35 document_scan | ProvenanceSection |

→ **Une seule source d'affichage (`vehicles.assurance`) mais 3 copies historiques** (documents.validated_fields, alerts.due_date, audit_logs.detail). SOURCE DE VÉRITÉ AFFICHAGE UNIFIÉE / TRACES MULTIPLES NON SYNCHRONISÉES.

### D. Leasing — stockage réel

Identique à l'assurance : `vehicles.leasing` (11/12 renseignés : societe, numero_contrat, date_debut, date_fin, mensualite_chf, duree_mois, km_contractuel, km_annuel, option_achat, valeur_residuelle, cout_total, cout_mensuel, commentaires) + 12 documents folder Leasing (3 actifs) + 11 alertes type leasing. Champs préavis / date limite de résiliation : **INEXISTANTS**.

### E. Doublons fonctionnels

| Concept | Emplacement A (vérité) | Emplacement B (copie) | Emplacement C (journal) | Cohérent ? |
|---|---|---|---|---|
| Échéance assurance | vehicles.assurance.date_echeance | documents.validated_fields.date_echeance | alerts.due_date | **DIVERGENT** (5 cas, cf. F) |
| Fin leasing | vehicles.leasing.date_fin | documents.validated_fields.date_fin | alerts.due_date | non comparable (0 doc leasing validé avec date) |
| Prochain contrôle | vehicles.controle_technique.date_prochain | (aucun doc contrôle validé) | alerts.due_date | IDENTIQUE (journal = instantané) |
| Mensualité/prime | vehicles.leasing/assurance | documents.validated_fields | rapports (recalcul lecture) | idem échéances |
| navixy ids | vehicles.navixy_vehicle_id / navixy_tracker_id (racine, legacy) | vehicles.integrations.navixy.* (canonique) | — | IDENTIQUES (écrits ensemble, l.1246-1259) — doublon assumé documenté |

### F. Divergences mesurées

Comparaison `documents.validated_fields` (assurance/leasing validés) vs valeur actuelle `vehicles.*` :

```text
IDENTIQUES : 1    DIFFÉRENTES : 5    INCOMPARABLES : 0
```
Les 5 divergences portent sur `assurance.date_echeance` (doc validé 2026-08-26/27/09-03 vs fiche 2026-09-09). 4 des 5 documents sont soft-supprimés (artefacts de tests OCR) ; **1 document ACTIF diverge** (`5391814c…`, créé 2026-08-19) : la fiche a été modifiée APRÈS la validation (très probablement par le remplissage démo, cf. I). Aucune divergence n'a été corrigée (lecture seule).

### G. Données orphelines

```text
documents  : 1 orphelin (vehicle_id inexistant) — soft-supprimé, créé 2026-06-04 (pré-Navixy)
files      : 2 orphelins (vehicle_id « testveh », « pvtest ») + 9 rattachés à « misc » (tests)
inspections: 3/3 orphelines (véhicules démo supprimés lors de l'import Navixy) — dont 1 signature démo prouvée
alerts     : 0 orpheline
vehicle_field_meta / fuel_snapshots : 0 orpheline
Binaires   : les objets du storage des 70 documents soft-supprimés ne sont jamais purgés
             (aucun appel de suppression dans server.py) — orphelins de stockage
```

### H. Multi-tenant (données)

Backfill complet (cf. A). 0 document cross-tenant (tenant du doc = tenant du véhicule pour 99/100 ; le 100e est l'orphelin). Unicité globale potentiellement incompatible multi-client à terme : `users.email` (unique global — acceptable), `vehicle_field_meta(vehicle_id+field)` et `fuel_snapshots(vehicle_id+day)` uniques SANS tenant (sans risque réel car vehicle_id est un uuid, mais à tenantiser en V2), dédup `alerts` NON unique (index simple) → duplication possible en écriture concurrente.

### I. Restes de seed démo (croisés avec le code réel des seeds)

Sources code : `seed_data()` (server.py l.2554 — 6 véhicules `source="demo"`, VIN `WDB9066xx…`, tracker `LT-GPS-…`) et `_demo_admin_data()` (l.2453 — remplit les véhicules RÉELS avec `LSG-2022-45xx`, `POL-78xxxx`, « Données de démonstration », photos Unsplash), exposé par `POST /api/demo/fill-admin`.

| Donnée | Collection | Classification | Preuve |
|---|---|---|---|
| Véhicules seed (6 fictifs) | vehicles | ABSENTS (purgés) | 0 `source=demo`, 0 VIN `WDB9066…`, 0 tracker `LT-GPS-` |
| Leasing des 12 véhicules réels | vehicles.leasing | **DEMO_PROUVÉE (11/12)** | 11 numero_contrat `LSG-2022-45xx` + 11 commentaires « Données de démonstration » = valeurs littérales de `_demo_admin_data` |
| Assurance des 12 véhicules réels | vehicles.assurance | **DEMO_PROUVÉE (11/12)** | 11 numero_police `POL-78xxxx` (`780000 + i*11`) |
| Contrôle technique / carte grise (poids 3500, 3 places) | vehicles.controle_technique / carte_grise | DEMO_PROBABLE (11/12) | mêmes véhicules remplis par le même appel fill-admin ; centres = liste DEMO_CENTRES ; pas de signature unique par champ |
| Photos véhicules | vehicles.photo_url | DEMO_PROUVÉE (11/12) | 11 URLs Unsplash = constantes VAN_PHOTOS |
| 1 inspection « Rayure portière avant droite » | inspections | DEMO_PROUVÉE | texte littéral du seed ; orpheline |
| 2 autres inspections orphelines | inspections | INDÉTERMINÉE | pas de signature seed exacte (probables artefacts de tests) |
| 9 files « misc » test.txt | files | DEMO_PROBABLE (artefacts tests) | uploads text/plain nommés test.txt/sample.txt/pv.txt |
| Le 12e véhicule (données assurance sans POL-78) | vehicles | INDÉTERMINÉE | 1 véhicule a une assurance hors signature seed (probable scan réel validé — c'est lui qui porte la divergence active) |

**Rien n'a été supprimé ni modifié.** ⚠ Conséquence majeure pour la migration : en preview, la quasi-totalité des données Assurance/Leasing candidates à la migration V2 est FICTIVE PROUVÉE. **L'état de la production VPS est NON VÉRIFIÉ** (le bouton « Données démo » a existé en production à l'itération 19 avant d'être retiré à l'itération 22 — des données fictives peuvent y subsister).

### J. OCR — données persistées

`documents.extracted_fields` : 69 docs (propositions value/confidence/status par champ, jamais appliquées seules) ; `validated_fields` 29 ; `document_data` 8 (vignettes). `vehicle_field_meta` : 35 entrées source=document_scan (champs copiés UNIQUEMENT après validation humaine — chemin de code unique `validate_scanned_document`). **Aucune valeur OCR copiée automatiquement sans validation n'a été trouvée** (le seul écrivain automatique de la fiche est la sync télématique CAN — `conso_reelle_l_100km`, source `navixy_can`, qui n'est pas de l'OCR).

### K. Coûts

```text
MODULE COÛTS DOCUMENTAIRE : ABSENT
```
Aucune collection coût. Existants : `vehicles.leasing.mensualite_chf/cout_total/cout_mensuel/valeur_residuelle`, `vehicles.assurance.prime_annuelle/franchise`, agrégés en lecture par `/api/dashboard` (l.1086-1100) et `reports.py`. `documents.document_data.prix_chf/montant_chf` (facture/amende/vignette) existent dans le schéma mais ne sont reliés à aucun calcul.

### L. Échéances & alertes — sources de vérité actuelles

```text
Échéances : CALCULÉES à chaque lecture depuis vehicles (aucune collection deadlines).
            5 dates fixes : leasing.date_fin, assurance.date_echeance,
            controle_technique.date_prochain, prochaine_expertise, prochaine_maintenance.
Alertes   : /api/alerts = CALCUL à la volée (même logique compute_metrics) ;
            collection alerts = JOURNAL persistant des notifications franchissant un seuil
            (dédup vehicle+type+threshold+due_date) + digest quotidien par tenant.
            Déclencheurs : startup (tous tenants), APScheduler 24 h, POST /alerts/run (tenant).
            E-mail : 61/61 status=mocked (aucun envoi réel).
```

### M. Index Mongo (relevés réels)

| Collection | Nb docs | Index tenant | Index tenant+vehicle | Index unique | Anomalie (criticité) |
|---|---:|---|---|---|---|
| vehicles | 12 | tenant_id+id ✓ · tenant_id+navixy_tracker_id ✓ | n/a | aucun | `id` non unique (index non-unique seulement) — MOYEN |
| documents | 100 | via composé ✓ | tenant_id+vehicle_id ✓ | aucun | `documents.id` sans index (requêtes delete/validate par id = collscan) — FAIBLE au volume actuel |
| files | 11 | **ABSENT** | ABSENT | aucun | index tenant manquant — MOYEN |
| inspections | 3 | **ABSENT** | ABSENT | aucun | idem — FAIBLE (volume) |
| alerts | 61 | **ABSENT** | vehicle+type+threshold+due_date (NON unique) | aucun | dédup non atomique → doublons possibles en concurrence — MOYEN ; tenant manquant — MOYEN |
| audit_logs | 368 | **ABSENT** | vehicle_id+created_at ✓ | aucun | tenant manquant — FAIBLE |
| vehicle_field_meta | 36 | **ABSENT** | vehicle_id+field **UNIQUE GLOBAL** | oui | unicité non tenantisée (risque théorique nul avec uuid) — FAIBLE |
| fuel_snapshots | 0 | ABSENT | vehicle_id+day UNIQUE | oui | idem — FAIBLE |
| users | 1 | — | — | email UNIQUE GLOBAL | à arbitrer si multi-tenant (email unique par plateforme vs par tenant) — MOYEN |
| tenant_integrations | 1 | tenant+provider UNIQUE ✓ | — | oui | — |

**Aucun index n'a été créé, modifié ou supprimé.**

### N. Types de données

Dates : 100 % chaînes (`YYYY-MM-DD` métier, ISO 8601 timestamps techniques) — aucun ISODate, aucun format alternatif détecté. Montants : numériques (int/float), défauts Pydantic à `0` (ambiguïté 0 = « non renseigné » vs « zéro réel » — connue, gérée par `_is_empty`). Booléens : true/false natifs. IDs : uuid string partout (`_id` ObjectId jamais exposé). **Aucune incohérence de type bloquante détectée** ; le point d'attention est la sémantique du `0` par défaut.

### O. Recommandation données (résumé)

- Future source de vérité documentaire : collection `documents` étendue (V2) — cf. §10.
- À conserver temporairement : `vehicles.assurance/leasing` en miroir lecture (compatibilité dashboard/rapports/alertes) jusqu'à bascule complète.
- À migrer : 30 documents actifs (+ décision sur les 70 soft-supprimés → statut ARCHIVED ou exclusion), structures assurance/leasing → documents V2 « contrat » APRÈS arbitrage démo (§16-Q1).
- Doublons supprimables plus tard : `validated_fields` comme source (reste trace), alias racine navixy (déjà documenté).
- Données démo nettoyables APRÈS validation humaine : leasing/assurance DEMO_PROUVÉE (11 véhicules preview), 1 inspection démo orpheline, 9 files test, 1 document orphelin.

---

## 8. RISQUES DE MIGRATION (registre)

| ID | Risque | Gravité | Probabilité | Impact | Mesure prévue |
|---|---|---|---|---|---|
| RM1 | Migrer en V2 des données Assurance/Leasing FICTIVES (11/12 DEMO_PROUVÉE en preview ; prod NON VÉRIFIÉE) | **CRITIQUE** | Élevée | Données métier fausses présentées comme réelles | M0 : détection par signatures seed + marquage `data_origin=demo_suspect` + arbitrage utilisateur AVANT migration ; audit prod préalable |
| RM2 | Double création à la re-exécution de la migration | CRITIQUE | Moyenne | Doublons métier | Idempotence par `legacy_source+legacy_id+migration_version` avec index unique (§11.3) |
| RM3 | Écrasement silencieux d'une divergence (doc validé ≠ fiche : 1 cas actif prouvé) | ÉLEVÉ | Moyenne | Perte d'information | Statut `MIGRATION_CONFLICT` conservant les deux valeurs + résolution humaine (§11.4) |
| RM4 | Perte de références fichiers (pages[], storage_path, 70 docs soft-del, binaires jamais purgés) | ÉLEVÉ | Faible | Fichier inaccessibles | Migration copie les réfs SANS déplacer les binaires ; vérification d'existence en M0 ; aucun delete storage |
| RM5 | Casse des consommateurs legacy (dashboard KPI documents_missing, timeline, alertes, 3 rapports, AssuranceTab/LeasingTab) | ÉLEVÉ | Élevée sans compat | Régression massive | Période dual-read : anciens endpoints inchangés, V2 en parallèle, bascule par étape (M8-M9) |
| RM6 | Duplication d'alertes après migration (moteur legacy vehicles + moteur V2 documents) | ÉLEVÉ | Élevée | Alertes en double | Un seul moteur : clé de dédup unifiée (tenant, source_entity, date_kind, due_date, threshold) ; le moteur V2 remplace le legacy le jour de la bascule, jamais les deux actifs sur le même concept |
| RM7 | Fuite cross-tenant sur nouvelles routes V2 (catégories, exigences, vues transverses) | CRITIQUE | Moyenne | Confidentialité | tenant du JWT uniquement (pattern `tid()` existant), tests cross-tenant systématiques (§13.2) |
| RM8 | Orphelins injectés en V2 (1 doc orphelin, 3 inspections, 2 files) | MOYEN | Certaine si non filtrés | Incohérences | M0 : rapport d'orphelins ; migration saute les orphelins avec journalisation (pas de suppression) |
| RM9 | Sémantique du `0` par défaut (montants/années) migrée comme valeur réelle | MOYEN | Moyenne | Fausses données | Règle : `0`/`""` legacy → `null` V2 (sauf champs où 0 est prouvé légitime, ex. CO₂ BEV — logique `_is_empty` existante) |
| RM10 | Index uniques V2 posés sur des données sales (échec de création) | MOYEN | Faible | Migration bloquée | M0 pré-checks (unicité effective, comptages) avant création d'index |
| RM11 | Dossier « Vignette » incohérent backend/frontend (uploads reclassés Divers) | MOYEN | Certaine (existant) | Docs mal classés | Corriger dans la phase V2 (catégories) ; recenser les docs « Divers » potentiellement vignette AVANT migration |
| RM12 | Identifiants superadmin codés en dur dans Login.jsx (bundle public) | ÉLEVÉ (sécurité) | Certaine (existant) | Compromission compte | À retirer avant toute ouverture multi-client (décision utilisateur — c'était une demande explicite it.20) |
| RM13 | ALERT_RECIPIENTS global env → si e-mail réel activé, envois inter-tenants | ÉLEVÉ (futur) | Faible (mocked) | Fuite d'infos | Tenantiser les destinataires dans la phase alertes V2 |
| RM14 | Rollback impossible si legacy écrasé | CRITIQUE | Faible | Perte définitive | Legacy JAMAIS modifié/supprimé pendant M1-M9 ; V2 = ajouts uniquement ; drop interdit (§12) |
| RM15 | Tests OCR réels consommant la clé Anthropic à chaque run complet | FAIBLE | Certaine | Coût | Marqueur pytest pour isoler les tests LLM (déjà séparables par fichiers) |

---

## 9. SOURCE DE VÉRITÉ ACTUELLE (par concept)

```text
Assurance : affichage = vehicles.assurance · dashboard = vehicles.assurance ·
            alertes = vehicles.assurance · rapports = vehicles.assurance
            → UNIFIÉE côté lecture ; copies historiques non synchronisées
              (documents.validated_fields, alerts.due_date)
Leasing   : identique (vehicles.leasing)
Contrôle  : identique (vehicles.controle_technique)
Documents : documents (métadonnées) + object storage (binaires) → UNIFIÉE
Provenance: vehicle_field_meta → UNIFIÉE
Vignette/facture/amende : documents.document_data → UNIFIÉE mais SANS consommateur
            (aucun moteur ne lit ces champs)
```

---

## 10. ARCHITECTURE CIBLE — Documents & Conformité V2

Principe : **étendre l'existant, ne pas le dupliquer**. La collection `documents` devient le document V2 (mêmes ids, mêmes fichiers) ; on AJOUTE 3 collections de configuration et un moteur de statut/conformité en lecture. Indépendant de Navixy, fondé sur `tenant_id + vehicles.id` canonique.

```text
Vehicle canonique (vehicles, inchangé)
      │
      ├── documents (V2 = extension de la collection actuelle)
      │     statut central + échéances génériques + montants + catégorie
      ├── document_categories (NOUVELLE) — système + custom par tenant, sous-catégories
      ├── document_requirements (NOUVELLE) — règles « requis » par tenant/profil véhicule
      ├── compliance resolver (CODE, pas de collection) — REQUIS vs PRÉSENT vs VALIDE
      ├── attachments = documents.pages[] + storage_path (INCHANGÉ, aucun déplacement binaire)
      ├── OCR results = documents.extracted_fields (INCHANGÉ)
      ├── audit events = audit_logs (INCHANGÉ, + audit upload/delete manquants)
      └── migration_conflicts (NOUVELLE, temporaire) — divergences legacy tracées
```

Moteur de statut central (calculé, une seule fonction, jamais dupliqué frontend) :
`MISSING` (requis sans document) · `TO_VERIFY` (extraction non validée / import à vérifier) ·
`VALID` · `EXPIRING_SOON` (seuils configurables par catégorie) · `EXPIRED` ·
`RENEWAL_IN_PROGRESS` (marqué manuellement) · `ARCHIVED` (remplace/complète is_deleted).

### 10.1 Modèle document cible (adapté à l'audit réel)

```text
OBLIGATOIRES : id (uuid, conservé), tenant_id, category_id, title, status, created_at, updated_at
OPTIONNELS   : vehicle_id (un document peut être flotte/tenant-level), subcategory_id,
               provider (compagnie/organisme), contract_number,
               start_date, expiry_date, notice_period_days, termination_deadline,
               amount, currency (défaut CHF), billing_frequency,
               responsible_user_id, notes, tags[],
               pages[]/storage_path/content_type/size/original_filename (existants),
               document_type (legacy OCR), extracted_fields, validated_fields,
               document_data, quality_warnings, analyzed_at, detected_type
CALCULÉS (jamais stockés) : status_effectif temporel (EXPIRING_SOON/EXPIRED),
               days_remaining, conformité par véhicule
MIGRATION    : legacy_source ('documents_v1' | 'vehicles.assurance' | 'vehicles.leasing'),
               legacy_id, migration_version, data_origin ('scan_validated' | 'manual' |
               'migrated_legacy' | 'demo_suspect')
NE PAS COPIER: valeurs OCR non validées vers les champs métier (extracted_fields reste
               proposition) ; champs Navixy ; photo_url ; les 0 par défaut (→ null)
```

### 10.2 Catégories cibles

- **Catégories système** (seedées par tenant, non supprimables, modifiables en libellé) : mapping 1:1 des dossiers actuels — Carte grise, Assurance, Leasing, Contrôle technique, Vignette, Factures, États des lieux, Contrats, Divers (corrige la divergence Vignette).
- **Catégories custom tenant** : CRUD tenant-scopé ; suppression interdite si utilisée (→ archivage) ; sous-catégories 1 niveau ; unicité (tenant_id, slug).
- Rattachement véhicule : uniquement VIN exact, plaque exacte ou sélection explicite (règle resolver existante réutilisée) — jamais d'heuristique marque/modèle/couleur.

### 10.3 Exigences & score de conformité

`document_requirements` : {tenant_id, category_id, applies_to (all | filtre groupe/catégorie véhicule), obligatoire, seuils_alerte[]}. Resolver : pour chaque véhicule → requis vs présents vs valides → `Conformité documentaire : 6/8` (libellé explicite « selon les règles configurées », aucune prétention réglementaire). Seed initial = les 4 REQUIRED_FOLDERS actuels (compatibilité KPI dashboard).

### 10.4 Échéances cibles

Persisté sur le document : `expiry_date`, `notice_period_days`, `termination_deadline` (saisie/OCR validé). Calculés à la lecture : `days_remaining`, `next_action_date` = min(termination_deadline, expiry_date − préavis). Aucune collection deadlines (cohérent avec l'architecture actuelle qui a fait ses preuves) ; `/api/timeline` étendu aux échéances documentaires V2, les 3 dates legacy restant servies depuis vehicles pendant la transition (dédupliquées par le moteur, cf. RM6).

### 10.5 Alertes cibles

UN document/échéance = UNE ligne d'alerte. Clé de dédup unifiée `(tenant_id, entity_kind, entity_id, date_kind, due_date, threshold)` avec **index unique** (corrige la dédup non atomique actuelle). Le moteur lit : documents V2 (catégories avec échéance) + dates legacy vehicles NON migrées ; dès qu'un concept est migré (ex. assurance), sa date legacy est exclue du moteur (bascule par concept, pas de double alerte). Destinataires par tenant (préparé, e-mail réel toujours conditionné à une intégration validée — aucun envoi réel prétendu).

### 10.6 Documents ↔ Coûts

```text
NON RÉALISÉ DANS CETTE PHASE
```
Points d'intégration préparés uniquement : `amount/currency/billing_frequency` sur le document + `legacy_source/legacy_id` permettant à un futur module coûts de référencer un document sans dupliquer l'écriture. Aucune collection coût créée.

### 10.7 OCR cible

```text
UPLOAD → (check_image_quality) → OCR (Claude) → OCR_EXTRACTED (extracted_fields)
      → statut document TO_VERIFY → VALIDATION UTILISATEUR (choix champ par champ,
        conflits explicites — mécanisme actuel conservé) → VALIDATED
```
Écriture automatique autorisée : AUCUNE valeur métier. L'OCR ne peut remplir que `extracted_fields` + `detected_type` + `type_confidence`. Le passage TO_VERIFY→VALID exige l'action humaine (inchangé — c'est déjà le comportement prouvé §7.J).

---

## 11. PLAN DE MIGRATION IDEMPOTENT (NON EXÉCUTÉ)

```text
M0 — Préconditions & instantané (par environnement, preview PUIS prod)
     · comptages par collection, rapport orphelins, rapport divergences,
       DÉTECTION DÉMO par signatures seed (LSG-2022-45xx, POL-78xxxx, Unsplash, textes)
     · vérification existence des binaires référencés (échantillon)
     · backup Mongo (mongodump) — bloquant si échec
     · GATE UTILISATEUR : arbitrage données démo (§16-Q1) — bloquant
M1 — Structures V2 (ADDITIF uniquement)
     · collections document_categories / document_requirements / migration_conflicts
     · index : documents(tenant_id+status), documents(tenant_id+expiry_date),
       documents.id (unique), unicité (tenant_id, legacy_source, legacy_id),
       alerts dédup UNIQUE, + index tenant manquants (files/alerts/audit_logs/meta)
M2 — Seed catégories système par tenant (idempotent : upsert par (tenant, slug))
     · mapping folder actuel → category_id écrit sur chaque document (champ AJOUTÉ,
       folder conservé tel quel)
M3 — Extension des documents existants (30 actifs + 70 soft-del selon décision Q5)
     · status initial : validated→VALID (si date non expirée), done→TO_VERIFY,
       None (upload manuel)→TO_VERIFY, is_deleted→ARCHIVED
     · legacy_source='documents_v1', legacy_id=id, migration_version=1
     · AUCUN champ existant modifié ou supprimé
M4 — Matérialisation Assurance : vehicles.assurance → document V2 catégorie Assurance
     (« fiche contrat », sans binaire si aucun justificatif lié)
     · UNIQUEMENT pour les données arbitrées réelles (Q1) ; demo_suspect exclu ou marqué
     · legacy_source='vehicles.assurance', legacy_id=vehicle_id → ré-exécutable sans doublon
     · vehicles.assurance INTACT (miroir lecture pendant la transition)
M5 — Idem Leasing (legacy_source='vehicles.leasing')
M6 — Rattachement justificatifs : lier les documents fichiers Assurance/Leasing existants
     aux fiches contrat M4/M5 (référence, AUCUN déplacement de binaire)
M7 — Exigences documentaires : seed depuis REQUIRED_FOLDERS (4 règles par tenant)
M8 — Compatibilité API : endpoints legacy INCHANGÉS ; dashboard/timeline/alertes/rapports
     lisent V2 pour les concepts migrés, legacy sinon (dual-read piloté par concept)
M9 — Bascule lecture frontend (vues V2 : Tous/Manquants/À vérifier/Expirés/Archivés,
     onglets Assurance/Leasing lisant la fiche contrat V2)
M10 — Dépréciation legacy (PHASE SÉPARÉE, après validation utilisateur complète)
     · gel des écritures vehicles.assurance/leasing puis suppression des consommateurs
     · JAMAIS de drop de collection dans cette itération
```

### 11.3 Garantie d'idempotence

Chaque écriture de migration est un upsert dont la clé naturelle est **(tenant_id, legacy_source, legacy_id, migration_version)** protégée par index unique → 1, 2 ou 5 exécutions produisent le même état. Interdiction de clé fragile titre/date. Chaque run journalise {run_id, démarré, terminé, upserts, skips, conflits} dans `migration_runs`.

### 11.4 Divergences

Quand deux sources legacy portent des valeurs différentes (cas prouvé : doc validé 2026-09-03 vs fiche 2026-09-09) : AUCUN choix silencieux → document V2 créé avec la valeur de la SOURCE DE VÉRITÉ ACTUELLE (vehicles.*), statut `TO_VERIFY`, et entrée `migration_conflicts` {concept, valeur_A+source, valeur_B+source, vehicle_id, résolu:false}. Résolution uniquement humaine via l'UI (ou décision utilisateur groupée).

### 11.5 Données démo

`DEMO_PROUVÉE` → jamais migrée automatiquement en donnée métier V2 : soit exclue, soit créée avec `data_origin='demo_suspect'` + statut TO_VERIFY (arbitrage Q1). `DEMO_PROBABLE`/`INDÉTERMINÉE` → migrées avec `data_origin` correspondant, RIEN n'est supprimé ni exclu arbitrairement. Tout nettoyage physique = phase séparée post-validation humaine explicite.

### 11.6 Rollback

- V2 étant purement ADDITIVE (M1-M9), le rollback = désactiver la lecture V2 (flag par concept) → retour immédiat au comportement legacy, données intactes.
- Suppression des données V2 possible par filtre `legacy_source`/`migration_version` (jamais nécessaire pour restaurer le legacy).
- Le backup M0 couvre le cas catastrophe. Aucun `drop` de structure legacy avant validation complète + délai d'observation.

### 11.7 Compatibilité transitoire

Ancien frontend + nouveau backend : fonctionne (endpoints legacy inchangés). Nouveau frontend + concept non migré : le dual-read renvoie le legacy. Chaque concept bascule indépendamment (assurance, leasing, documents génériques), ce qui borne le rayon d'impact.

---

## 12. PLAN DE TESTS

### 12.1 Migration
- Assurance réelle simple → 1 fiche contrat V2, champs corrects, vehicles.assurance intact.
- Leasing idem. Document générique (upload manuel) → V2 TO_VERIFY.
- **Idempotence** : exécuter 2× puis 5× → comptages strictement identiques, 0 doublon (assertion sur l'index unique).
- Champs absents : date absente → expiry null (pas 1970) ; montant 0 legacy → null V2 ; document sans fichier accepté.
- Formats legacy : date string ISO, chaîne vide, null.
- Divergence : valeurs identiques → pas de conflit ; différentes → migration_conflicts + TO_VERIFY, aucune valeur perdue.
- Orphelins : doc avec vehicle_id inexistant → sauté + journalisé, jamais supprimé. Fichier storage inexistant → signalé, migration non bloquée.
- Démo : signature LSG/POL → data_origin=demo_suspect (ou exclusion selon arbitrage), JAMAIS VALID silencieux.

### 12.2 Multi-tenant (tout cross-tenant = bloqué, 404/403)
Tenant A/B : lecture, update, suppression, téléchargement fichier, association véhicule, catégorie custom (création/lecture croisée), exigence, scan/validate OCR, échéances/vues transverses, score conformité. + non-régression des 10 tests `test_multitenant.py` existants.

### 12.3 Documents
Création (manuelle/scan), modification, archivage (≠ suppression), pièce jointe, document sans date, sans montant, avec échéance + préavis + résiliation, catégorie custom, sous-catégorie, recherche, filtres (statut/catégorie/véhicule), vues Tous/Manquants/À vérifier/Expirés/Archivés.

### 12.4 Conformité
Requis présent valide → conforme ; requis absent → MISSING ; requis expiré → non conforme ; non requis → neutre ; aucun profil/règle → score « — » explicite (jamais 100 % silencieux) ; modification de règle → recalcul.

### 12.5 Échéances (frontières, TZ Europe/Zurich vs UTC)
aujourd'hui, J+1, J+7, J+30, J+31, J+90, J+91, déjà expiré, sans date, préavis > durée restante (termination_deadline passée), cohérence days_remaining à minuit.

### 12.6 OCR
Extraction complète / partielle / confiance faible (TO_VERIFY) ; plaque détectée → suggestion rattachement exact uniquement ; VIN détecté idem ; aucun véhicule correspondant → choix explicite ; plusieurs → jamais de choix automatique ; validation / rejet / modification utilisateur ; type mismatch (mécanisme existant conservé).

### 12.7 Régression (existant à protéger — liste des consommateurs prouvés)
Fiche véhicule (7 onglets), dashboard 8 KPI (dont documents_missing), timeline, alertes + journal + run, rapports conformite.pdf / couts.csv / vehicule/{id}.pdf, upload/download/suppression document (DocFolderSection), scan→conflits→validation→provenance, protection champs validés vs sync télématique, page Intégrité, resolver/core inter-projets, auth (login/401/change-password). Base : re-run de la suite complète (149) + nouveaux tests V2 en fichiers séparés (comptage disjoint, jamais de double comptage dans les rapports).

---

## 13. CRITÈRES GO / NO-GO (avant migration réelle)

### GO (tous requis)
```text
0 FAIL sur la suite complète (149 existants + nouveaux V2)
0 fuite cross-tenant (12.2 complet)
0 perte de fichier (comptage binaires référencés avant = après)
0 écriture sur les structures legacy pendant M1-M7 (diff Mongo prouvé)
Idempotence PASS (2× et 5×)
Comptages M0 = comptages post-migration + skips journalisés (équation exacte)
Arbitrage démo (Q1) rendu et appliqué
Backup M0 vérifié restaurable
```
### NO-GO (un seul suffit)
```text
Toute donnée legacy modifiée/perdue · tenant leak · migration non idempotente ·
fichier non récupérable · divergence écrasée silencieusement ·
données demo_suspect migrées en VALID sans décision utilisateur
```

---

## 14. ORDRE DE DÉVELOPPEMENT RECOMMANDÉ (8 phases max)

| Phase | Objectif | Dépendances | Risque | Tests | Critère de validation |
|---|---|---|---|---|---|
| 1 | Socle V2 : catégories (collections+API+seed système), extension modèle document, moteur de statut central | arbitrages §16 | Faible (additif) | unités statut + catégories + tenant | statuts corrects sur données synthétiques, 0 régression suite 149 |
| 2 | Migration M0-M3 (documents existants → V2) sur PREVIEW | Ph.1 | Moyen | 12.1 idempotence | comptages exacts, dual-read OK |
| 3 | Assurance/Leasing → fiches contrat V2 (M4-M6) + gestion conflits | Ph.2 + arbitrage démo | ÉLEVÉ (RM1/RM3) | 12.1 divergences/démo | 0 donnée démo en VALID, conflits visibles |
| 4 | Exigences + score conformité (M7) + vues transverses (Tous/Manquants/…) | Ph.1 | Moyen | 12.3/12.4 | score reproductible, KPI dashboard compatible |
| 5 | Échéances génériques + moteur d'alertes unifié (dédup unique, destinataires par tenant) | Ph.3-4 | ÉLEVÉ (RM6) | 12.5 + dédup | 0 alerte dupliquée sur concept migré |
| 6 | UI Documents V2 complète (bibliothèque tenant, fiche véhicule, timeline documentaire) | Ph.4-5 | Moyen | testing agent frontend | flux complets + régression pages |
| 7 | OCR V2 : statut TO_VERIFY intégré, rattachement VIN/plaque exact | Ph.6 | Faible (mécanisme existant) | 12.6 | aucune écriture auto prouvée |
| 8 | Bascule lecture (M8-M9), durcissement (audit upload/delete, index, RM11/RM12), préparation M10 | Ph.1-7 | Moyen | régression complète | GO/NO-GO §13 |

---

## 15. QUESTIONS BLOQUANTES (arbitrage utilisateur requis)

1. **Q1 — Données démo Assurance/Leasing** : en preview, 11/12 véhicules ont des données DEMO_PROUVÉE. (a) les exclure de la migration, (b) les migrer marquées `demo_suspect`+TO_VERIFY, ou (c) les nettoyer d'abord (après votre validation) ? Et **autorisez-vous un audit lecture seule de la base de PRODUCTION VPS avant toute migration** (état réel inconnu — le bouton démo a existé en prod) ?
2. **Q2 — Bouton démo du login** : `Login.jsx` contient les identifiants superadmin en clair dans le bundle (votre demande it.20). À conserver, ou à retirer avant la phase multi-client ?
3. **Q3 — Les 70 documents soft-supprimés** : migrer en statut ARCHIVED (visibles dans la vue Archivés) ou les laisser hors V2 (invisibles, comme aujourd'hui) ?
4. **Q4 — Fiches contrat sans fichier** : validez-vous que Assurance/Leasing deviennent des documents V2 « fiche contrat » (avec ou sans justificatif attaché), `vehicles.assurance/leasing` restant en miroir lecture pendant la transition ?
5. **Q5 — Liste des catégories système** : validez le mapping proposé des 9 dossiers actuels (dont correction Vignette) comme catégories système initiales ?

---

## 16. RECOMMANDATION FINALE

```text
READY WITH CONDITIONS
```
L'architecture existante est saine pour une extension V2 non destructive : source de vérité unifiée côté lecture, tenant backfillé à 100 %, OCR à validation humaine prouvée, fichiers isolés par tenant. Les conditions sont : (1) arbitrage des données démo prouvées AVANT toute matérialisation Assurance/Leasing (RM1, CRITIQUE) ; (2) audit lecture seule de la production VPS (état NON VÉRIFIÉ) ; (3) réponses aux 5 questions bloquantes ; (4) correction des anomalies MOYEN/ÉLEVÉ intégrée aux phases (Vignette, dédup alertes, index tenant, audit upload/delete, bouton démo login).

---

# ADDENDUM — Levée des conditions (2026-08-25, après validation de l'audit sous conditions)

## A. PRODUCTION : VÉRIFIÉE (partiellement, via API — lecture seule)

Constat majeur : **l'API de production https://documents.logitrak.ch est entièrement OUVERTE, sans authentification** (`/api/auth/login` → 404 ; `GET /api/vehicles` → 12 véhicules sans token). La production exécute une version ≈ itérations 14-17 (ASTRA importé, OCR Claude configuré) **SANS** l'auth (it.18), **SANS** le multi-tenant (it.22 : `tenant_id` absent 0/12) et **SANS** le P0 (champs batterie absents). L'audit prod a donc été réalisé par appels GET publics uniquement (endpoints écrivant un audit_log — integrity, reports — volontairement exclus ; AUCUN POST/PUT/DELETE).

| Élément | Preview | Production | Différence |
|---|---|---|---|
| Version déployée | it.22 (auth + tenant + P0) | ≈ it.14-17 (pré-auth, pré-tenant) | prod en retard de 5+ itérations |
| Authentification API | JWT obligatoire (401) | **AUCUNE — API publique lecture ET écriture** | **CRITIQUE** |
| Véhicules | 12 (Navixy) | 12 (Navixy, mêmes trackers) | ids uuid différents |
| tenant_id | 12/12 `default` | 0/12 (champ inexistant) | backfill non déployé |
| navixy_vehicle_id / VIN | 5/12 · 5/12 | 3/12 · 2/12 | liaisons/push it.21-22 non déployés |
| Données DEMO_PROUVÉE (LSG-2022-45xx + POL-78xxxx + commentaire démo) | 11/12 | **12/12** | fill-admin exécuté en prod aussi |
| Photos Unsplash (seed) | 11/12 | 12/12 | idem |
| Documents actifs | 30 (17 validés — majoritairement artefacts de tests OCR) | **1** (dossier Leasing, sans type, non validé) | prod quasi vide de documents |
| Documents soft-supprimés / orphelins | 70 / 1 | NON VÉRIFIABLE via API (pas d'accès Mongo prod) | — |
| Inspections rattachées | 0 (3 orphelines en base) | 0 | — |
| Alertes (journal) | 61, 100 % mocked | ≥100 lues (73 digest + 27 seuils), 100 % mocked | accumulation digests quotidiens |
| Index / collections internes prod | mesurés (preview) | NON VÉRIFIÉS (accès Mongo prod indisponible depuis le pod) | audit complet = commande à exécuter sur le VPS |

Limite explicite : sans accès Mongo direct au VPS, les index, documents soft-supprimés, orphelins et collections internes de production restent **NON VÉRIFIÉS**.

## B. DONNÉES DEMO — les deux environnements

- **Preview : 11/12 véhicules DEMO_PROUVÉE** (liste anonymisée des vehicle_id fournie dans le chat du 2026-08-25 : d1099b53, 6491d528, 8540d020, f4f234b5, 50c156cb, acb99cee, 32f08fa5, 9a19070f, ec488eb5, 1ad61c35, 5909a77b — tenant `default`, champs `leasing.*` + `assurance.*`, signatures LSG-2022-45xx / POL-78xxxx / commentaire « Données de démonstration » / photo Unsplash). Le 12e (6d00f932, « 1-Enyaq ») porte des données de TEST (« TEST Assur », prime 1234.0) — pas du seed, mais pas réelles non plus.
- **Production : 12/12 véhicules DEMO_PROUVÉE** (mêmes signatures, vérifiées champ par champ via l'API).
- Conclusion structurante pour la migration : **il n'existe pratiquement AUCUNE donnée Assurance/Leasing réelle** dans les deux environnements. Décision utilisateur confirmée : ces données ne seront JAMAIS migrées en V2 comme réelles ; rien n'a été supprimé/modifié/migré.

## C. DIVERGENCE ACTIVE — analyse exacte : ARTEFACT DE TEST PROUVÉ

```text
Tenant : default · Vehicle : 6d00f932-d74d-4e1b-84ad-6116ffb0af33 (« 1-Enyaq 01 Bern »,
tracker Navixy réel 3218549, importé 2026-06-04) · Champ : assurance.date_echeance

Fiche véhicule : 2027-06-01 (valeur actuelle ; 2026-09-09 au moment de l'instantané)
  Source : cycles pytest test_docscan — scan répété d'un PDF de test (1031 octets,
  compagnie « TEST Assur », prime 1234.0) puis reset déterministe à 2027-06-01.
  Provenance : vehicle_field_meta source=document_scan ; audit : « anonymous » (pré-auth)
  puis admin@logitrak.ch (runs récents via conftest).
Document 5391814c (actif) : validated_fields.date_echeance = 2026-09-03,
  validé le 2026-08-19 08:53 par un run de test.
Consommateurs (Dashboard, fiche, alertes, échéances, rapports) : TOUS lisent
  vehicles.assurance.date_echeance. Le document n'est lu par AUCUN consommateur (trace).
Preuve : audit trail complet = ≥6 cycles identiques scan→validate du même PDF de test
  entre le 11.08 et le 25.08 (2027-06-01 → 2026-08-26/27, 2026-09-03, 2026-09-09 → reset).
```
**Recommandation : VEHICLE DEVRAIT RESTER SOURCE** (architecture) — et pour ce cas précis, AUCUN arbitrage métier n'est nécessaire : les deux valeurs sont des artefacts de test prouvés, ni l'une ni l'autre n'est une donnée réelle. À traiter avec le futur nettoyage validé des données de test. Aucune valeur modifiée.

## D. FAILLE LOGIN DÉMO — cause exacte et correction

Cause : bloc JSX ajouté à l'itération 20 (commit `7e0a008`, demande utilisateur de l'époque) — `onClick` du bouton « Admin » appelait `setPassword("<secret en clair>")` → secret compilé dans le bundle JS livré à tout visiteur du preview. Audit AVANT correctif :
```text
SECRET DANS SOURCE : OUI (Login.jsx uniquement)
SECRET DANS BUNDLE CLIENT : OUI (bundle dev preview ; le bundle de PRODUCTION ne le
                            contenait PAS — la prod n'a jamais reçu la page login)
SECRET DANS VARIABLE FRONTEND : NON (aucune REACT_APP_* ne porte de secret)
SECRET DANS GIT TRACKÉ : OUI — présent dans 4 commits de l'historique (7e0a008 → 2f8c434)
```
**Correction : RÉALISÉE.** Fichier modifié : `frontend/src/pages/Login.jsx` (suppression complète du bloc « Comptes démo », aucune autre modification ; aucun mécanisme de remplacement — priorité à la suppression de l'exposition). Vérifications post-correctif : secret absent du source (grep=0), du build de production `yarn build` (0 fichier), du bundle dev servi (0 occurrence) ; `demo-admin-btn`/`demo-accounts` : 0 référence résiduelle (code + tests).

**ROTATION DU SECRET RECOMMANDÉE : OUI** — triple exposition : (1) bundle navigateur du preview, (2) historique Git (le retrait du code ne purge pas l'historique ; il partira sur GitHub au prochain « Save to GitHub »), (3) divulgation antérieure dans le chat. Procédure (EN ATTENTE D'AUTORISATION, non exécutée) : changer le mot de passe via le menu utilisateur de l'app OU `ADMIN_PASSWORD` dans backend/.env (+ `ADMIN_FORCE_RESET=true` une fois) puis restart ; mettre à jour /app/memory/test_credentials.md ; reporter la nouvelle valeur dans deploy/.env AVANT le déploiement de l'auth en prod.

## E-F. TESTS DE LA CORRECTION

- Testing agent it.20 (`/app/test_reports/iteration_20.json`) : **7/7 PASS (100 %)** — DOM login sans bloc démo, champs vides au chargement, secret absent du DOM et des 9 bundles JS servis, mauvais mot de passe → erreur sans redirection (1 seul essai, verrou force brute préservé), login manuel → dashboard, session sur /vehicules /timeline /alertes /integrite, logout → purge lt_token + redirection, route protégée → /login. Seule erreur console : le 401 volontaire du test d'échec. Aucune donnée métier créée/modifiée.
- `yarn build` : OK (24.3 s). Suite backend inchangée (147 PASS / 2 SKIP le matin même ; correctif 100 % frontend).
- Notes non bloquantes du testing agent : logout n'appelle pas POST /api/auth/logout (purge locale seulement) ; le champ mot de passe n'est pas vidé après un échec.

## G. CONDITIONS RESTANTES

1. **PROD — API publique (CRITIQUE, action utilisateur)** : redéployer les itérations 15-22 (auth incluse) : Save to GitHub → `git pull` → renseigner `JWT_SECRET`/`ADMIN_EMAIL`/`ADMIN_PASSWORD`/`ANTHROPIC_API_KEY` dans `~/documents/deploy/.env` → `docker compose up -d --build`. Tant que ce n'est pas fait, les données de flotte prod sont lisibles ET modifiables par n'importe qui.
2. **Rotation du mot de passe superadmin** : recommandée OUI — en attente d'autorisation.
3. **Audit Mongo prod complet** (index/orphelins/soft-deleted) : impossible depuis le pod ; possible via une commande lecture seule à exécuter sur le VPS si souhaité.
4. **GO utilisateur explicite** pour Documents V2 Phase 1 (catégories + moteur de statut, sans migration Assurance/Leasing).
5. Migration Assurance/Leasing (phases 3+) : reste conditionnée à la stratégie démo confirmée (exclusion des DEMO_PROUVÉE) et au redéploiement prod.

## H. VERDICT

```text
READY FOR DOCUMENTS V2 PHASE 1
```
(catégories documentaires + moteur de statut, additif, sans migration legacy — les conditions restantes G.1-G.3 concernent la production et la sécurité, pas la Phase 1 en preview. Ce verdict ne vaut PAS autorisation de commencer.)

**STATUT : EN ATTENTE DU GO UTILISATEUR POUR DOCUMENTS V2 PHASE 1**

---

# ADDENDUM 2 — Tentative d'audit MongoDB PRODUCTION (2026-08-25, lecture seule)

## Environnement confirmé
- Serveur : VPS OVH `83.228.207.198` · App : LOGITRAK Documents (`https://documents.logitrak.ch`, Nginx hôte → conteneur `logitrak-fleet_web`).
- Base configurée : `logitrak_fleet` sur `mongodb://mongo:27017` (réseau Docker interne `logitrak-fleet_net`) — source : `deploy/docker-compose.yml` l.30-31. Valeurs runtime du `deploy/.env` VPS : NON VÉRIFIÉES directement.

## Résultat : PRODUCTION (niveau MongoDB) : NON VÉRIFIÉE — ACCÈS INDISPONIBLE
Preuves : (1) le service `mongo` du docker-compose n'expose AUCUN port (pas de section `ports:`) — accessible uniquement depuis le réseau interne du VPS (bonne pratique) ; (2) test TCP 83.228.207.198:27017 depuis le pod : FERMÉ ; (3) aucune clé SSH VPS dans le projet. Aucune tentative d'intrusion effectuée, aucune écriture.

→ Script d'inspection STRICTEMENT LECTURE SEULE fourni : **`deploy/audit-mongo-prod-readonly.js`** (uniquement getCollectionNames/countDocuments/getIndexes/aggregate en lecture ; plaques masquées, aucun secret ni numéro de contrat affiché). Exécution par l'utilisateur sur le VPS :
```bash
cd ~/documents/deploy
docker exec -i logitrak-fleet_mongo mongosh logitrak_fleet --quiet < audit-mongo-prod-readonly.js
```
(Le fichier arrive sur le VPS via Save to GitHub + git pull, ou copier-coller.)

## Ce qui A PU être vérifié en production (API publique, GET uniquement — aucun endpoint écrivant)
- `vehicle_field_meta` équivalent : **0 validation OCR/ASTRA sur les 12 véhicules** (GET field-meta ×12).
- Audit trail : quasi vide (1 seule action `download` sur les 50 dernières entrées par véhicule).
- Timeline : 36 échéances calculées (12 leasing + 12 assurance + 12 contrôle) — **100 % issues des données DEMO_PROUVÉE**.
- Documents actifs : 1 (sans type, jamais validé) · Assurance/Leasing : sous-objets `vehicles` (même code, version antérieure), 12/12 remplis, 12/12 signatures seed.
- Index, orphelins, documents soft-supprimés, collections internes : NON VÉRIFIABLES via API → script VPS.

## Sécurité login (rappel de statut — aucune action dans cette étape)
```text
SECRET EXPOSÉ : OUI (prouvé — corrigé côté source/bundle preview le 2026-08-25 ;
                subsiste dans l'historique Git et a été divulgué dans le chat)
ROTATION RECOMMANDÉE : OUI (aucune rotation effectuée — en attente d'autorisation)
```

## API publique — PROUVÉE
```text
API PUBLIQUE NON AUTHENTIFIÉE : PROUVÉE (2026-08-25)
Preuves : POST /api/auth/login → 404 (auth non déployée) ;
GET /api/vehicles, /api/dashboard, /api/alerts/log, /api/timeline,
/api/vehicles/{id}/documents|history|field-meta, /api/astra/status,
/api/config/status → 200 SANS token.
Données exposées : flotte complète (plaques, VIN partiels, kilométrage, GPS tracker ids,
échéances, coûts leasing/assurance — actuellement fictifs), journal d'alertes, audit.
Risque : la version déployée (pré-it.18) n'a AUCUNE protection sur les routes
d'écriture (PUT/DELETE vehicles, POST sync, etc.) — non testées (aucune écriture),
mais le code déployé ne comporte aucun contrôle. Remédiation = redéployer it.15-22
(auth incluse) — action utilisateur, aucun changement effectué sur cette base.
```

## Verdict de l'étape
```text
READY FOR SECURITY FIXES
```
Priorité avant Documents V2 : (1) redéploiement prod avec auth (action utilisateur), (2) rotation du mot de passe superadmin (autorisation en attente), (3) exécution du script Mongo VPS et retour des résultats pour clore l'audit prod.

**STATUT : EN ATTENTE DE VALIDATION UTILISATEUR — AUCUNE MIGRATION DOCUMENTS V2 EXÉCUTÉE**

---

# ADDENDUM 3 — Rotation du secret & vérification de l'authentification API (2026-08-25)

## A. Rotation du secret superadmin
```text
PREVIEW ET PROD MÊME CREDENTIAL : NON (la production n'a AUCUN credential en service —
                                  auth non déployée, POST /api/auth/login → 404)
ROTATION PREVIEW REQUISE : OUI → EFFECTUÉE
ROTATION PROD REQUISE : NON (aucun secret actif) — INTERDICTION de réutiliser l'ancien
                        secret dans deploy/.env lors du déploiement
```
Détails (aucun secret affiché) : compte concerné = superadmin unique (`users`, rôle superadmin) ; credential configuré uniquement dans `backend/.env` preview (`ADMIN_PASSWORD`) ; frontend/bundle : 0 copie restante (vérifié avant rotation). Procédure : nouveau secret aléatoire 32 hex (sans caractères spéciaux, généré par `secrets.token_hex`), `ADMIN_PASSWORD` remplacé ligne à ligne dans `backend/.env` (19 lignes préservées), passage temporaire `ADMIN_FORCE_RESET=true` + restart (nécessaire car `password_changed_in_app=True`), puis retour à `false` + restart. `memory/test_credentials.md` mis à jour (fichier IGNORÉ par Git — le nouveau secret n'entre pas dans l'historique). Copie temporaire `/tmp/.rot_old` purgée.

Tests réels : login ANCIEN mot de passe → **401** · login ancienne variante (extrait fichier) → **401** · login NOUVEAU → **200** · `/auth/me` → 200 role=superadmin · après retour `ADMIN_FORCE_RESET=false` + restart → login **200** (hash non ré-écrasé).

## B. Historique Git
```text
SECRET ROTÉ : OUI
HISTORIQUE GIT CONTIENT ANCIEN SECRET : OUI — 4 commits (7e0a008 → 2f8c434),
                                        fichier frontend/src/pages/Login.jsx
RÉÉCRITURE HISTORIQUE RECOMMANDÉE : NON — la rotation neutralise l'ancien secret
  (il ne donne plus accès à rien) ; une réécriture d'historique casserait les clones,
  branches et le déploiement VPS (git pull) pour un bénéfice nul.
```

## C. Correctif authentification API (audité)
- Mécanisme : dépendance globale `require_auth` appliquée au router — `server.py` l.2791 : `app.include_router(api_router, dependencies=[Depends(require_auth)])` ; JWT Bearer vérifié dans `auth.py::require_auth` (401 « Non authentifié » sans/mauvais token, TTL 24 h) ; `tenant_id` injecté depuis le JWT (`request.state.tenant_id`).
- Routes protégées : **TOUTES** les routes `/api/*` métier (véhicules, documents, fichiers, alertes, timeline, dashboard, rapports, intégrité, ASTRA, Navixy, config, demo, upload).
- Routes volontairement publiques : **uniquement `POST /api/auth/login`** (router auth séparé ; `/auth/me`, `/auth/change-password`, `/auth/logout` exigent le Bearer). Aucun healthcheck HTTP applicatif n'existe (le healthcheck compose interroge Mongo directement) — rien à exempter.
- Comportement sans JWT : 401 immédiat, avant tout traitement métier.

## D. Tests preview (matrice réelle du 2026-08-25, après rotation)
- **Sans authentification — 16/16 GET → 401** : /vehicles, /vehicles/{id}, /vehicles/{id}/documents, /vehicles/{id}/history, /vehicles/{id}/field-meta, /alerts, /alerts/log, /timeline, /dashboard, /reports/conformite.pdf, /reports/couts.csv, /reports/vehicule/{id}.pdf, /fleet/integrity, /document-types, /config/status, /astra/status.
- **Sans authentification — 9/9 écritures → 401 (rejetées avant traitement, aucune écriture réelle)** : POST /vehicles, PUT /vehicles/{id}, DELETE /vehicles/{id}, POST /navixy/sync, POST /demo/fill-admin, POST /alerts/run, POST /documents/{id}/validate, DELETE /documents/{id}, POST /astra/import.
- **Avec JWT valide — 7/7 → 200** avec données du tenant (12 véhicules, 20 documents, alertes, timeline, dashboard, history, PDF conformité).
- **Isolation tenant re-prouvée après rotation** : `test_multitenant.py + test_logitrak_api.py` → **19 passed** (12.11 s).
- PASS : 51 vérifications · FAIL : 0 · SKIP : 0.

## E. Déploiement production : À FAIRE MANUELLEMENT (aucun accès VPS depuis le pod)
Contenu à déployer = HEAD au moment du « Save to GitHub » (inclut `4a0be47` = suppression du bloc démo Login.jsx, `18ecc44` = script d'audit Mongo, et toutes les itérations 15-22 dont l'auth). Fichiers du lot sécurité : `frontend/src/pages/Login.jsx` (modifié), `deploy/audit-mongo-prod-readonly.js` (nouveau) ; `backend/.env` preview non versionné (normal).
Procédure canonique (deploy/README.md §3-4bis) :
```bash
# 1. Depuis Emergent : « Save to GitHub »
# 2. Sur le VPS :
cd ~/documents && git pull
cd deploy
# Éditer .env : JWT_SECRET (openssl rand -hex 32), ADMIN_EMAIL,
# ADMIN_PASSWORD (NOUVEAU secret — JAMAIS l'ancien), ANTHROPIC_API_KEY,
# NAVIXY_API_HASH, ADMIN_FORCE_RESET=false, SEED_DEMO_DATA=false
docker compose up -d --build
docker compose ps
curl -s -X POST http://127.0.0.1:8090/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}'   # doit renvoyer {"token": ...}
```
Validation post-déploiement (je referai ces requêtes réelles dès que déployé) — matrice attendue :
| Endpoint | Avant (prouvé 25.08) | Après (attendu) |
|---|---|---|
| GET /api/vehicles | 200 sans token | 401 |
| GET /api/vehicles/{id}/documents | 200 sans token | 401 |
| GET /api/alerts, /api/alerts/log | 200 sans token | 401 |
| GET /api/timeline (échéances) | 200 sans token | 401 |
| GET /api/dashboard, /api/reports/* | 200 sans token | 401 |
| POST /api/auth/login (bons identifiants) | 404 | 200 + token |
| GET avec Bearer valide | n/a | 200, tenant correct |

## F. Audit Mongo production : NON VÉRIFIÉ — en attente de l'exécution du script par l'utilisateur
(`deploy/audit-mongo-prod-readonly.js`, strictement lecture seule — commande au §ADDENDUM 2.)

## G. Verdict de l'étape sécurité
```text
READY WITH CONDITIONS
```
Conditions restantes : (1) déploiement prod par l'utilisateur + validation post-déploiement, (2) sortie du script Mongo VPS, (3) GO explicite Phase 1. Côté preview : secret roté et testé, bundle propre, API 100 % protégée, isolation tenant PASS.

**STATUT : EN ATTENTE DU GO UTILISATEUR POUR DOCUMENTS V2 PHASE 1**

---

# ADDENDUM 4 — Lot Sécurité 2 : SEC-001 + SEC-002 implémentés et testés (2026-08-25)

## SEC-001 — RÉALISÉ
- File-token dédié : `create_file_token` (auth.py) — type=file, tenant_id, tv, **TTL 10 min** ; émis par `GET /api/auth/file-token` (session Bearer obligatoire).
- Query string : seuls les jetons type=file sont acceptés, et uniquement sur `/api/files/` et `/api/reports/` (`FILE_TOKEN_PATH_PREFIXES`, auth.py). Un JWT de session en query → 401 partout (ancien mécanisme désactivé). Un file-token sur l'API métier (header ou query) → 401.
- Révocation : champ `token_version` par utilisateur, embarqué (`tv`) dans tous les jetons, comparé en DB à chaque requête ; `POST /api/auth/logout` fait `$inc token_version` → tous les jetons (session + fichiers) de CET utilisateur meurent ; les autres utilisateurs ne sont pas affectés ; re-login immédiat OK.
- Frontend : `api.js` — le JWT de session n'est plus jamais mis en URL ; `refreshFileToken()` au login/bootstrap + toutes les 8 min + au focus fenêtre (AuthContext) ; logout appelle désormais réellement `POST /auth/logout` puis purge.

## SEC-002 — RÉALISÉ
- `validate_upload` (existant, était du code mort) branché sur `POST /api/upload` et `POST /api/vehicles/{id}/documents` : allowlist `ALLOWED_MEDIA_EXTS` (pdf,jpg,jpeg,png,webp,gif,docx,doc,xls,xlsx,zip,csv,mp4,mov,webm = exactement les besoins UI), taille max 25 Mo. Le scan avait déjà ses contrôles (SCAN_EXTS + taille).
- `/api/upload` vérifie désormais que `vehicle_id` appartient au tenant (404 sinon).
- `serve_file` : Content-Type **dérivé de l'extension côté serveur** (jamais la valeur client), `inline` uniquement pour SAFE_INLINE_MIME (images/PDF/vidéos), `attachment` forcé sinon, `X-Content-Type-Options: nosniff` systématique, `filename` de Content-Disposition assaini (CR/LF/guillemets).

## Fichiers modifiés
`backend/auth.py`, `backend/server.py` (login/logout/file-token/serve_file/upload/documents), `frontend/src/lib/api.js`, `frontend/src/context/AuthContext.jsx`, `frontend/src/components/FilePreview.jsx` (Escape ferme l'aperçu), `frontend/src/components/DocFolderSection.jsx` (accept aligné backend + erreur suppression), TEST_ONLY : `tests/test_logitrak_api.py`, `tests/test_navixy.py` (fixtures .txt→.csv), NOUVEAU : `tests/test_security_lot2.py` (19 tests).

## Tests (chiffres exacts, suites disjointes)
- `test_security_lot2.py` : **19 PASS / 0 FAIL / 0 SKIP** (14.82 s).
- Régression suite existante (149) : **147 PASS / 2 SKIP / 0 FAIL** (3 fixtures .txt corrigées TEST_ONLY puis re-run 17/17).
- Frontend E2E (testing agent, iteration_21.json) : **12/13** — révocation logout prouvée (ancien token → 401), rapports 200 avec file-token et 401 avec JWT session en query. Le point LOW (Escape aperçu PDF) corrigé ensuite.

## Risques restants (acceptés/documentés)
- file-token absent au bootstrap → images 401 silencieuses (mitigé par refresh login/8 min/focus).
- `change-password` ne bump pas token_version (session courante préservée volontairement).
- CORS origins prod + headers nginx (HSTS) à confirmer au déploiement.

## MODIFICATIONS DOCUMENTS V2 : AUCUNE
## VERDICT : SECURITY LOT 2 READY
⚠ Le HEAD au moment du « Save to GitHub » inclut désormais ce lot (testé). Déployer ce HEAD.

**STATUT : EN ATTENTE DES PREUVES VPS — PHASE 1 GELÉE**
