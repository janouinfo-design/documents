# RAPPORT FINAL — LOT H · Rôles `manager` / `driver` + vues chauffeur

> Environnement : **preview uniquement**. Aucun déploiement, aucune migration, aucun dry-run de migration, aucune lecture de données Journal réelles, aucun nettoyage de `loth-ui-test` (celui-ci est **conservé**). Rapport factuel en lecture seule produit après le correctif KPI autorisé et la revalidation complète.

- Date : 2026-10-09
- HEAD : `e660d2729fc9e196a2789e76762b10695f1b8cb0` (`checkpoint before testing_agent_full_stack`)
- Tenant de test isolé : `loth-ui-test` (conservé — `TARGET_TENANT_PRESENT = PASS`)

---

## 0. Correctif autorisé — KPI `/api/me/fines` (cause racine + implémentation)

**Cause racine (it.48).** La projection Mongo `_ME_FINE_PROJ` omettait les deux champs que `fines.is_fine` / `with_statut` lisent pour poser `deadline_active` : `document_type` et `business_category`. Sans eux, `deadline_active` n'était jamais positionné → la KPI « En retard » tombait à **0** alors que l'amende seedée `LOTH-F3` est échue (−3 j dans le test, −4 j en UI).

**Correctif (`backend/server.py`, +7 lignes, diff `28a05b3..HEAD`).**
- `_ME_FINE_PROJ` ajoute `"document_type": 1, "business_category": 1` (usage **interne serveur** uniquement).
- `_ME_FINE_CALC_ONLY = ("document_type", "business_category")`.
- Dans `me_fines`, après calcul de `deadline_active` / `days_remaining` et **avant** de renvoyer, chaque item subit `x.pop(k)` pour ces 2 clés.
- **Forme publique inchangée** : le chauffeur ne reçoit jamais `document_type` ni `business_category`, ni `notes_internes` / `dossier_interne` / `priorite`.

**Test de régression dédié** : `backend/tests/test_rbac_lotH.py::test_driver_fines_kpi_calc_fields_used_server_side_never_exposed` prouve :
- A. les 2 champs de calcul existent dans la source `documents` (`document_type == "amende"`, `business_category == "AMENDE"`) ;
- B. KPI corrects (`LOTH-F3` : `deadline_active=True`, `days_remaining=-3`, `payee=False`) ; `totals.en_retard == 1` ;
- C+D. `document_type` / `business_category` / `notes_internes` / `dossier_interne` / `priorite` **jamais** dans les items renvoyés ;
- E. self-scope strict : F1 (D1) + F3 (D1) uniquement ; F2 (D2) et F4 (V1 sans `driver_id`) **jamais** dans liste / total / KPI.

---

## 1. Tableau de revalidation (post-correctif)

| Contrôle | Résultat | Preuve |
|---|---|---|
| Test ciblé KPI driver | **PASS** | `test_rbac_lotH.py::test_driver_fines_kpi_calc_fields_used_server_side_never_exposed` |
| Suite Lot H dédiée | **21 / 21 PASS** | `test_reports/pytest/loth_full_regression_v2.xml` (`test_rbac_lotH`) ; isolée aussi dans `loth_isolation_rerun.log` |
| Régression complète A–H (1 seul process) | **704 PASS / 2 FAIL (hors Lot H) / 2 SKIP (documentés)** — 708 tests collectés, durée réelle **739,98 s ≈ 12 min 19 s** | `test_reports/loth_regression_full_v2.log` + `loth_full_regression_v2.xml` |
| `loth_seed.py verify` — isolation fonctionnelle Lot H | **7/7 familles · 43/43 preuves API PASS** | `test_reports/loth_verify.json` |
| `loth_seed.py verify` — empreintes globales | **DEFAULT_UNCHANGED = FAIL · OTHER_TENANTS_UNCHANGED = FAIL** (hors Lot H, non bloquant) | `test_reports/loth_verify.json` + `loth_drift_attribution.log` |
| Curl driver réel `GET /api/me/fines` | **200**, `total=2`, `en_retard=1`, `montant_ouvert_chf=160`, 0 fuite | it.49 + curl ciblé (handoff) |
| Build frontend production `yarn build` | **Compiled successfully · exit 0** (23,38 s) | `test_reports/loth_yarn_build.log` |
| Testing agent frontend `/mes-amendes` | **PASS · 0 issue** | `test_reports/iteration_49.json` |
| Dockerfile — contrôle statique packaging | **non copiés = []** (aucun nouveau module `.py` introduit par le correctif) | diff `backend/` = `server.py` + 2 fichiers de test seulement |

### Détail régression complète A–H (run propre, 1 process)
**Régression A–H : 704 PASS / 2 FAIL hors Lot H non bloquants / 2 SKIP documentés** (708 tests collectés).

> ⚠️ Précision durée : `708` est le **nombre de tests collectés**, *pas* une durée. La **durée réelle d'exécution (horloge)** est **739,98 s ≈ 12 min 19 s** — ligne pytest `2 failed, 704 passed, 2 skipped, 5 warnings in 739.98s (0:12:19)` ; attribut JUnit `testsuite time=739.979`. **Aucune valeur `708,74` (ni en secondes, ni en heures) n'apparaît dans les logs.** (`loth_full_regression_v2.xml` : `tests=708 failures=2 errors=0 skipped=2`.)

Suites liées au Lot H toutes **vertes** dans ce run :
- `test_rbac_lotH` **21/21**
- `test_drivers_phase4c` **19/19** (dont `test_33` corrigé : les rôles manager/driver existent en tenant de test, **jamais** dans `default`)
- `test_fuel_cards_phase4c` **22/22**
- `test_nofile_phase4c` **22/22**
- `test_business_data` **17/17**

> Note méthodologique : un premier run complet avait affiché 56 FAIL / 16 ERR dans le XML. Cause identifiée et écartée : **deux process pytest concurrents** écrivaient simultanément dans le même tenant `default` et le même fichier (contention d'état partagé). Après `pkill` et relance **mono-process**, le résultat propre est 704/2/2. Les échecs transitoires de ce run contaminé (`test_22` snapshot global, `test_07` ReadTimeout, 2 `test_business_data`) sont tous **repassés PASS** en run propre et en isolation.

---

## 2. Sections d'isolation obligatoires (7/7) — `loth_seed.py verify` (lecture seule)

Toutes les familles **PASS** (`loth_verify.json`). Total preuves API = **43/43**.

### 2.1 TENANT_ISOLATION — PASS (3/3)
- Véhicule d'un autre tenant (`default`) → admin 404 · manager 404 · manager documents 404 · admin énergie 404 · **driver 403**.
- Toutes les transactions / documents du tenant référencent des véhicules du tenant (tx=4, docs=4, véhicules=4).
- Admin : liste véhicules = tenant complet (4) sans fuite.

### 2.2 MANAGER_SCOPE_ISOLATION — PASS (11/11)
- `auth/me` manager : rôle + `vehicle_scope=[V1,V2]`.
- Liste véhicules manager = exactement [V1, V2].
- Accès DIRECT par ID **hors scope** (V3) → **404 fail-closed sur 19 familles** (vehicle, documents, inspections, energy, fine, transaction, anomaly, reconciliation, document_patch/history, assignment_close, assignments_list, fine_status, file, export_vehicle_pdf, vehicle_update, inspection_create, fuel_manual, card_out).
- Accès DIRECT par ID **dans le scope** (V1) → 200 (vehicle, fine, transaction, anomaly, file, inspections).
- Fonctions interdites au manager → **403** (vehicle_create, vehicle_delete, photo_delete, document_delete, inspection_delete, archive_list, statements, imports, settings_fuel, card_create, card_history, driver_create, navixy_sync, alerts_log, alerts_run, legacy, console, deadline_settings).
- Mutations autorisées dans le scope → 200 (vehicle_update, document_patch, fine_status, inspection_create_v2).
- Audit des mutations manager : `role=manager` + `vehicle_id ∈ scope`, aucun véhicule hors scope (13 audits).
- Notes internes : visibles au manager dans le scope, jamais hors scope (404), absentes pour read_only.
- Cartes : scope visible · hors scope invisible · mixte sans affectation hors scope · stats = 2.
- Conducteurs : liste minimale (sans email/téléphone/notes), affectations hors scope jamais exposées.
- **`scope = []` ⇒ 0 véhicule, 0 donnée** (jamais de fallback tenant ; v1_direct → 404).

### 2.3 DRIVER_SELF_SCOPE_ISOLATION — PASS (13/13)
- Justificatif image : 1er dépôt → 200 (`present=true`) ; PDF : 1er dépôt → 200.
- Driver hors `/api/me` → **403 DRIVER_FORBIDDEN sur 15 routes** (listes ET accès directs).
- Driver : toute mutation hors `/api/me` → 403 (fuel_manual, vehicle_update, fine_status, attach_admin_route).
- `me/profile` : D1 sans email / téléphone / notes.
- `me/vehicles` : affectation **ACTIVE uniquement** (V1) ; V3 terminée et V2 future exclues ; aucune donnée leasing/assurance.
- `me/fuel-transactions` : pleins avec `driver_id = D1` (V1 ×2 + V3 historique), jamais ceux de D2 / sans conducteur ; `total = len(items)`.
- `me/fines` : amendes D1 (F1 V1 + F3 V2), **sans** `notes_internes` / `dossier_interne` / `priorite` (et sans `document_type` / `business_category` — correctif §0).
- Justificatif d'un plein d'un autre conducteur / sans conducteur → 404 (aucune fuite).
- 2e fichier → **409 FILE_ALREADY_PRESENT**, fichier existant jamais écrasé.
- Audit `attach_file role=driver` présent.
- Fichiers : son justificatif 200 · document véhicule 404 · autre chauffeur 404 · manager hors scope 404 · admin 200.
- États de liaison : non lié → **403 DRIVER_ACCOUNT_NOT_LINKED** · inactif → **403 DRIVER_INACTIVE** · lié sans affectation → **200 listes vides** · admin/read_only sur `/me` → 403.

### 2.4 MANAGER_SCOPE_REVOCATION — PASS (2/2)
- Même jeton : V1 200 → retrait du scope par le superadmin → V1 404, liste [V2], dashboard 1, amende V1 404 → restauration → 200.
- Audit console avant/après du scope (superadmin) : 6 audits.

### 2.5 DRIVER_LINK_REVOCATION — PASS (4/4)
- Même jeton : lié 200 → déliaison superadmin → **403 DRIVER_ACCOUNT_NOT_LINKED** → re-liaison → 200.
- Même jeton : conducteur désactivé par l'admin → **403 DRIVER_INACTIVE** sur `/me/*` → réactivé → 200.
- Affectation active → V2 visible ; clôturée à J-1 → disparaît immédiatement (règle de date serveur).
- Audit console avant/après de la liaison conducteur : 6 audits.

### 2.6 EXPORT_SCOPE_ISOLATION — PASS (4/4)
- Export amendes CSV manager : F1/F3 présentes, F2 (V3) absente, aucune note interne ; admin : F2 présente.
- Export transactions CSV manager : stations V1/V2 présentes, V3/V4 absentes ; filtre `vehicle_id=V3` → 0 ligne.
- Export coûts CSV manager : plaques V1/V2 présentes, V3/V4 absentes.
- Exports PDF / rapprochements : scope 200, hors scope 404 (conformité 200, vehicule_v1 200, vehicule_v3 404, reco_v3 404, reco_all 200).

### 2.7 KPI_SCOPE_ISOLATION — PASS (6/6)
- Dashboard : `total_vehicles` manager = 2 < admin = 4.
- Amendes : total / pagination / KPI sur le scope (manager 2 : F1 V1 + F3 V2 ; admin 3).
- Énergie : transactions / by_vehicle / totaux manager V1-V2 (3 tx) vs admin (6 tx).
- Anomalies : total / stats manager = 1 (V1) vs admin = 2.
- Échéances / alertes / coûts / timeline : V1-V2 uniquement, count < admin, recipients tenant-global = [].
- Rapprochements : items / total manager ⊆ scope.

---

## 3. Empreintes globales `verify` — classées HORS LOT H, NON BLOQUANTES

Formulation exacte :

```
LOT H isolation invariants = PASS
DEFAULT_UNCHANGED fingerprint = FAIL (hors Lot H, non bloquant)
OTHER_TENANTS_UNCHANGED fingerprint = FAIL (hors Lot H, non bloquant)
```

**Détail DEFAULT_UNCHANGED (FAIL).** `alerts|default` 94→95 · `audit_logs|default` 2546→2567 · `documents|default` 450→456 · `vehicles_archive|default` 93→94 (`users|default` et `vehicles|default` inchangés).

**Détail OTHER_TENANTS_UNCHANGED (FAIL).** Dérives sur `pytest-cost-*`, `pytest-dl4a-*`, `pytest-lh-a-*` (alerts +1 ou nouvelles) + nouveau tenant de régression `pytest-client-f75b2606` (audit_logs 10).

**Attribution factuelle (preuves `loth_drift_attribution.log`) :**
- **0** enregistrement attribuable à un compte `loth-*`.
- **0** enregistrement attribuable à un rôle `manager` / `driver`.
- **0** rôle Lot H créé dans `default` (`db.users.count_documents({tenant_id:"default", role∈{manager,driver}}) == 0`).
- Dérive `default` attribuée à : (a) l'activité du compte `admin@logitrak.ch` (22 audits après baseline, documents/archive créés via l'UI) ; (b) le **job planifié digest** (`alerts|default` type `digest`, 2026-10-09T06:09:47) ; (c) les **suites de régression legacy** exécutées pendant la campagne, qui écrivent **par construction dans `default`** (`test_security_lot2.py` et voisines : uploads de documents dans le tenant admin `default`).
- Dérive autres tenants attribuée aux **digests planifiés** (alerts type `digest` sur `pytest-cost-a` / `pytest-lh-a` à 06:09:47) et à un tenant créé/supprimé par une suite de régression (`pytest-client-f75b2606` : 10 audits `superadmin` `admin_tenant_*` / `admin_user_*`, tenant inexistant après la suite).
- Aucune correction possible côté Lot H sans **modifier artificiellement `default`**, ce qui est **interdit**. Les empreintes ne sont donc **pas** réécrites et `default` n'est **pas** nettoyé.

> Les empreintes ne sont **pas** déclarées PASS. Elles restent FAIL, explicitement classées **hors Lot H / non bloquantes** sur la base de l'attribution ci-dessus.

---

## 4. Régression complète A–H — détail des 2 FAIL (HORS LOT H) et des 2 SKIP (documentés)

**Formulation retenue :** `Régression A–H : 704 PASS / 2 FAIL hors Lot H non bloquants / 2 SKIP documentés.`

### 4.1 Les 2 FAIL (déterministes, rejouent à l'identique en isolation en 7,33 s)

**FAIL 1 — `tests/test_alerts_ocr.py::test_alerts_list_structure`**
- **Suite** : `test_alerts_ocr` (alertes / OCR, legacy lots A–B).
- **Cause exacte** : `AssertionError: assert 'amende' in ('leasing', 'assurance', 'controle')` — le test attend un tuple de types d'alerte figé et incomplet ; le produit émet aussi `amende` / `digest` / `document`.
- **Preuve hors Lot H** : `git diff --stat 3dc2514..HEAD -- backend/tests/test_alerts_ocr.py` = **vide** (ni le test ni le moteur d'alertes ne sont modifiés par le Lot H) ; le type `amende` est une fonctionnalité produit **antérieure** au Lot H ; `db.users` manager/driver dans `default` = **0**.
- **Bloquant** : **NON**.

**FAIL 2 — `tests/test_navixy.py::test_navixy_sync_imports_fleet`**
- **Suite** : `test_navixy` (télématique Navixy, legacy).
- **Cause exacte** : `AssertionError: Found non-navixy vehicles after sync: ['VD 594 862']` (`assert 1 == 0`) — après sync, le test exige que tous les véhicules soient `source=navixy` ; or `VD 594 862` est `source=manual`.
- **Preuve hors Lot H** : `git diff --stat 3dc2514..HEAD -- backend/tests/test_navixy.py` = **vide** ; `db.vehicles` `VD 594 862` → `source=manual, created_at=2026-09-01T12:41:55Z`, donc **antérieur** au Lot H (octobre), issu d'un script e2e historique (`e2e_vd594862.py`).
- **Bloquant** : **NON**.

> Ces 2 suites n'ont jamais fait partie du jeu de régression de clôture des lots A–G (les clôtures tournaient par suite métier : business_data, energy, fines, drivers, nofile, fuel_cards, statements). Incluses ici par le run complet `tests/`, elles échouent sur l'**état partagé de `default`**, pas sur le code Lot H.

### 4.2 Les 2 SKIP (préexistants / attendus, sans lien avec le Lot H)

**SKIP 1 — `tests/test_alerts_ocr.py::test_ocr_carte_grise_extracts_plate_and_vin`**
- **Raison (message pytest)** : « Endpoint `/carte-grise/ocr` remplacé par `/documents/scan` — couvert par `test_docscan.py` ».
- **Statut** : **préexistant / attendu** — skip permanent par décision produit (endpoint déprécié), **antérieur** au Lot H ; la couverture fonctionnelle est assurée par `test_docscan.py`.

**SKIP 2 — `tests/test_sync_integrity.py::TestRealNavixyPushReversible::test_push_color_and_restore`**
- **Raison (message pytest)** : « écriture Navixy réelle — exécuter avec `NAVIXY_WRITE_TEST=1` ».
- **Statut** : **préexistant / attendu** — skip conditionnel : l'écriture Navixy réelle reste désactivée tant que la variable d'environnement `NAVIXY_WRITE_TEST=1` n'est pas posée (protection contre des appels mutatifs réels) ; **antérieur** au Lot H.

---

## 5. Frontend

- `yarn build` : **Compiled successfully · exit 0** (`loth_yarn_build.log`, 23,38 s ; 442,45 kB JS / 13,9 kB CSS gzip).
- Testing agent it.49 (`iteration_49.json`) — retest ciblé `/mes-amendes` (driver `loth-driver@loth-ui-test.ch`) : KPI « En retard » = **1** (était 0), « À traiter » = 2, « Montant ouvert » = 160,00 CHF ; table = exactement LOTH-F3 + LOTH-F1, LOTH-F2 absente ; `GET /api/me/fines` 200, `leaked_keys = []` (0 `document_type` / `business_category` / `notes_internes` / `dossier_interne` / `driver_id`). Smoke `/mes-pleins` (3 pleins, 0 justificatif manquant) et `/mes-vehicules` (VD 800 001 présent, VD 800 002 absent). Redirections `/` et `/vehicules` → `/mes-pleins`. Nav `data-role='driver'`, 3 liens (`nav-me-fuel`, `nav-me-fines`, `nav-me-vehicles`). **0 issue, retest_needed=false.**

---

## 6. Contrôle statique Dockerfile

`LOTH_DOCKERFILE_STATIC_CHECK = PASS` (statique uniquement). Le correctif KPI ne modifie que `backend/server.py` (+ 2 fichiers de test) ; **aucun nouveau module `.py`** n'est introduit → la couverture `COPY` du `backend/Dockerfile` (déjà validée Docker VPS au Lot G) reste complète (`non copiés = []`). **Aucune exécution Docker runtime en preview** (docker absent) — pas de prétention de validation runtime/VPS pour le Lot H.

---

## 7. État dépôt (git)

- HEAD : `e660d2729fc9e196a2789e76762b10695f1b8cb0`.
- `git diff --stat 28a05b3..HEAD -- backend/` : `server.py` (+7/-1), `tests/test_drivers_phase4c.py` (+2/-1), `tests/test_rbac_lotH.py` (+42/-2).
- `git diff --stat 3dc2514..HEAD` (vue large Lot H, hors `test_reports`/`memory`) : **54 fichiers, ~1939 insertions, ~285 suppressions** (nouveaux : `frontend/src/lib/rbac.js`, `components/me/DriverShell.jsx`, `components/me/DriverPending.jsx`, `pages/My{Fuel,Fines,Vehicles}Page.jsx`, `components/admin/UserAccessFields.jsx`).
- `git status --short` : seuls des artefacts non suivis (`test_reports/iteration_49.json`, `test_reports/logs/`, `test_reports/pytest/loth_full_regression_v2.xml`). Écriture git = via « Save to GitHub » (jamais `git reset`/`revert`).

---

## 8. DIVERGENCES RESTANTES

1. **Empreintes globales `verify` (DEFAULT_UNCHANGED / OTHER_TENANTS_UNCHANGED) = FAIL.**
   - Sévérité : faible / dette de test.
   - Impact Lot H : **aucun** impact fonctionnel ou de sécurité démontré (attribution §3 : 0 enregistrement `loth-*`, 0 rôle manager/driver, 0 rôle Lot H dans `default`).
   - Bloquante : **NON**.
   - Action future : isoler les suites legacy dans des tenants dédiés et/ou empêcher les jobs planifiés (digest/Navixy) pendant les campagnes de régression, afin de rendre les fingerprints globaux déterministes.

2. **2 échecs de régression legacy (`test_alerts_ocr::test_alerts_list_structure`, `test_navixy::test_navixy_sync_imports_fleet`).**
   - Sévérité : faible / dette de test.
   - Impact Lot H : **aucun** (code et tests non touchés par le Lot H ; causes = tuple de types d'alerte obsolète + véhicule `manual` résiduel du 2026-09-01).
   - Bloquante : **NON**.
   - Action future : actualiser le tuple de types d'alerte attendus (`digest`/`document`/`amende`) et isoler les suites `test_navixy` / `test_alerts_ocr` dans des tenants dédiés (ne pas les faire dépendre de l'état partagé de `default`).

3. **2 SKIP de régression documentés (`test_alerts_ocr::test_ocr_carte_grise_extracts_plate_and_vin`, `test_sync_integrity::TestRealNavixyPushReversible::test_push_color_and_restore`).**
   - Sévérité : nulle / informatif (skips intentionnels).
   - Impact Lot H : **aucun** — skips **préexistants / attendus**, antérieurs au Lot H (endpoint `/carte-grise/ocr` déprécié et couvert par `test_docscan.py` ; écriture Navixy réelle conditionnée à `NAVIXY_WRITE_TEST=1`).
   - Attribution : décisions produit/sécurité legacy, sans rapport avec le RBAC Lot H.
   - Bloquante : **NON**.

4. **Validation Docker runtime Lot H = NON EXÉCUTÉE en preview** (docker absent). Contrôle **statique** PASS. À exécuter sur le VPS si une preuve runtime est souhaitée (comme Lots F/G).
   - Sévérité : faible. Impact Lot H : aucun module `.py` nouveau → packaging inchangé. Attribution : limite d'outillage preview. Bloquante : **NON**.

**Divergences BLOQUANTES = 0.**

---

## 9. Conclusion

```
LOT H FULL-FLOW = PASS
  · Correctif KPI /api/me/fines = PASS (document_type + business_category calc-only, jamais exposés)
  · Test ciblé KPI = PASS · Suite Lot H dédiée = 21/21 PASS
  · Régression A–H (mono-process) = 704 PASS / 2 FAIL hors Lot H non bloquants / 2 SKIP documentés (708 tests collectés, durée réelle 739,98 s ≈ 12 min 19 s)
      - FAIL : test_alerts_ocr::test_alerts_list_structure · test_navixy::test_navixy_sync_imports_fleet (déterministes, code/test non touchés par Lot H)
      - SKIP : test_alerts_ocr::test_ocr_carte_grise_extracts_plate_and_vin · test_sync_integrity::TestRealNavixyPushReversible::test_push_color_and_restore (préexistants/attendus)
  · loth_seed.py verify : LOT H isolation invariants = PASS (7/7 familles · 43/43 preuves API)
  · DEFAULT_UNCHANGED fingerprint = FAIL (hors Lot H, non bloquant)
  · OTHER_TENANTS_UNCHANGED fingerprint = FAIL (hors Lot H, non bloquant)
  · Frontend build = PASS (exit 0) · Testing agent it.49 = PASS (0 issue)
  · LOTH_DOCKERFILE_STATIC_CHECK = PASS (runtime Docker non vérifié en preview)
DIVERGENCES BLOQUANTES = 0
LOT H CLEANUP = NOT RUN  (tenant loth-ui-test conservé)
MIGRATION = NONE · DRY-RUN MIGRATION = NONE · DEPLOYMENT = NONE · DONNÉE JOURNAL RÉELLE LUE/MIGRÉE = 0
```

Le verdict Lot H est **PASS** uniquement parce que l'attribution hors Lot H est explicitement prouvée (§3, §4) et que les **7 familles d'isolation sont PASS**. `default` n'est **pas** nettoyé ni modifié pour forcer artificiellement les hashes à revenir à la baseline. Le nettoyage de `loth-ui-test` nécessite un **GO explicite séparé** ultérieur.
