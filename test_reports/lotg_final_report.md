# RAPPORT FINAL — LOT G FULL-FLOW (Phase 4C / Carburant-Énergie 6B)

Date : 2026-06 (horodatages techniques UTC du 2026-10-08) · Environnement : PREVIEW uniquement · Tenant de test : `lotg-ui-test` (conservé)
Légende des preuves : **[EXEC]** = exécuté dans cette passe ou artefact persisté d'une exécution identifiée · **[INSP]** = inspecté (code/fichier lu, non ré-exécuté) · **[N/D]** = preuve non disponible.

## 0. Verdict
**LOT G FULL-FLOW = PASS** — DIVERGENCES BLOQUANTES = 0 (voir §19).

## 1. Seed `test_reports/lotg_seed.py` — modes exécutés
| Mode | Exécution | Artefact | Preuve |
|---|---|---|---|
| `baseline` | avant le 1er seed (13:36 UTC) | `test_reports/lotg_baseline_before_seed.json` (231 clés collection\|tenant, 4 sections counts/hashes/hashes_raw/tenants_ids) | [EXEC] |
| `seed` (1er) | fail-fast HTTP 500 sur force-import `G04` (collision index unique `fuel_transactions (tenant, fournisseur, external_transaction_id)`) | journal de session | [INSP] |
| `seed` (2e, après correctif fixture) | `created_now=False`, 28 cas A–AB PASS (13:39) | `test_reports/lotg_seed_result.json` | [EXEC] |
| `inventory` | 13:48 | `test_reports/lotg_inventory.json` | [EXEC] |
| `verify` | 13:40 — `LOT G SEED VERIFY = PASS`, 25/25 checks | `test_reports/lotg_verify.json` | [EXEC] |
| idempotence | re-seed sans nouvelle création : `fuel_statement/create` audits = 4 (seed) + 2 (it.47) = 6, 18 transactions seed exactement, 0 doublon | `lotg_inventory_post_agent.json` (audit by entity/action) | [EXEC] |

Tenant cible : `lotg-ui-test` (2 comptes : admin / read_only — identifiants affichés uniquement en sortie du script, non reproduits ici).

## 2. Cas A–AB (lecture de `lotg_seed_result.json` + check indépendant de `lotg_verify.json`)
`lotg_verify.json.cases` est une copie des résultats seed ; la colonne « verify » cite le check **indépendant** (re-lecture API/DB) qui recouvre le cas, ou la re-preuve it.47.

| Case | Description | Seed | Verify (check indépendant) | Verdict |
|---|---|---|---|---|
| A | CAN présent + achats égaux (V1 avril : 50 L / 50 L → écart 0, source can, INDICATIF) | PASS | `thresholds null ⇒ INDICATIF` (V1 avril) + `thresholds 5/5 ⇒ V1avr=OK` | PASS |
| B | CAN présent + achats > CAN (V1 mai : 110 L vs CAN 100 L → +10 L / +10 %, tickets 50 L ≠ conso) | PASS | `CAN priority` PASS (ecart=10.0, tickets=50.0) | PASS |
| C | CAN présent + achats < CAN (V2 mai : 60 L vs 80 L → −20 L / −25 %) | PASS | `thresholds 5/5 ⇒ V2=A_CONTROLER` ; curl §10 : ecart −20.0 / −25.0 | PASS |
| D | CAN absent (V3 mai : source unavailable, ecart None, INDICATIF, tickets 73 L indicatif) | PASS | `CAN absent → aucune consommation inventée (V3)` PASS | PASS |
| E | ASTRA 6.5 WLTP = référence comparative, réelle 6.7 conservée | PASS | `ASTRA comparative` PASS | PASS |
| F | Seuils null → INDICATIF (V1/V2 mai, V1 avril) | PASS | `thresholds null ⇒ INDICATIF` PASS (`{pct: None, l: None}`) | PASS |
| G | Seuils 5 % / 5 L → A_CONTROLER / A_CONTROLER / OK, puis retour null → INDICATIF | PASS | `thresholds configured` PASS `('A_CONTROLER','A_CONTROLER','OK')` ; it.47 sc.1b/1c | PASS |
| H | Justification (explique, ne corrige pas : achats 110 / CAN 100 / écart 10 inchangés, audit) | PASS | `justification persistée` PASS | PASS |
| I | Décompte sans blocker → clôturable (DEC-2026-04-001, blocker_count 0) | PASS | `close normal = 0 blocker (avril)` PASS | PASS |
| J | Blocker `pending_fx` (EUR sans montant_chf) | PASS | `all blocker types covered` PASS | PASS |
| K | Blocker `matched_review` | PASS | idem | PASS |
| L | Blocker `unmatched` | PASS | idem | PASS |
| M | Blocker `open_anomaly` | PASS | idem | PASS |
| N | Blocker `forced_duplicate` (+ anomalie double_plein D8) | PASS | idem + `blocker_count 7 / blocked_line_count 6 cohérents` PASS | PASS |
| O | Close normal → verrou (locked=true) | PASS | `closed transactions locked` PASS (15 tx à 13:40) | PASS |
| P | Close normal avec blockers → 409 `CLOSE_BLOCKED` (7 blockers / 6 lignes détaillées) | PASS | non re-sondable après clôture (copie seed) ; **re-prouvé it.47 sc.5** sur DEC-2026-10-001 | PASS |
| Q | Close exception (motif, acteur, date, snapshot 7 blockers = totals 7, lignes verrouillées) | PASS | `close_exception blockers preserved` PASS | PASS |
| R | Declared complet (avril : 100 CHF / 50 L / 0 kWh / 1 ligne) | PASS | `declared preserved` PASS | PASS |
| S | Declared partiel (mai : montant 1000 CHF, volume/kwh/nb_lignes null = N/A) | PASS | idem | PASS |
| T | Écarts declared (mai Δ +114 CHF / +11.4 %, Δ volume/kWh/lignes None ; avril 4 deltas = 0) | PASS | idem (`mai deltas=…delta_volume_l: None`) | PASS |
| U | Transaction verrouillée après clôture (locked, statement_id, locked_at = closed_at) | PASS | `closed transactions locked (locked_at == closed_at)` PASS | PASS |
| V | Mutations verrouillées → 409 `STATEMENT_LOCKED` ×9 (match, card, doc montant, doc mixte notes+montant, delete, validate, declared clôturé, recalcul clôturé, suppression véhicule) ; notes seules → 200 | PASS | `STATEMENT_LOCKED 409 ×6 sondes` PASS | PASS |
| W | Décision d'anomalie non destructive après clôture (justifiee, tx identique, snapshot 7 == 7) | PASS | `anomaly decision after lock` PASS | PASS |
| X | Correctif : transaction tardive incluse (COR-2026-05-001, late=true) | PASS | `corrective excludes locked (tardive incluse)` PASS | PASS |
| Y | Correctif : transactions verrouillées du parent exclues (intersection 0, parent inchangé) | PASS | idem | PASS |
| Z | read_only : 5 lectures 200 (reco, statements, statement, settings, export) · 9 mutations 403 | PASS | copie seed ; **re-prouvé it.47 sc.12** (9×403, export 200, UI 0 bouton mutant) + curl §10 | PASS |
| AA | Cross-tenant fail-closed : 5 sondes 404, tx→véhicules du tenant, décomptes du seul tenant | PASS | `no cross-tenant writes` PASS | PASS |
| AB | 8 exports audités SHA-256 (statement csv/xlsx/pdf, reconciliations csv/xlsx/pdf, transactions csv/xlsx : hash recalculé = en-tête = audit) | PASS | copie seed ; **re-prouvé it.47 sc.11** (3 formats `X-Content-SHA256` = sha256(bytes)) + inventaire §6 (28/28 audits avec sha256) | PASS |

**A_AB_PASS = 28/28 · A_AB_FAIL = 0 · A_AB_BLOCKED = 0 · A_AB_MISSING = 0**

## 3. Recherche reopen / unlock [EXEC]
Commande : `rg -n -i 'reopen|réouvrir|unlock|déverrouiller|rouvrir|reset close' frontend/src`
Hits : **1**
| Fichier:ligne | Extrait | Classification |
|---|---|---|
| `frontend/src/components/energy/StatementDrawer.jsx:20` | `// Fiche décompte : … — actions admin selon statut, aucun reopen` | commentaire |

Backend (`rg … backend/server.py backend/fuel_statements.py`) : 3 hits, tous la garde `_ensure_tx_unlocked(tx)` (`server.py:860` : `if tx.get("locked"): raise HTTPException(409, …)`) = protection, pas une action. `lotg_verify.json` check `aucun endpoint de réouverture` PASS (`POST …/reopen`, `POST …/unlock`, `DELETE /fuel/statements/{id}` → 404/405) ; pytest `test_no_reopen_endpoint_or_equivalent` PASS.
**REOPEN_UI_ACTIONS = 0**

## 4. Inventaire post-testing-agent `lotg-ui-test` [EXEC] (`test_reports/lotg_post_agent_inventory.py` → `lotg_inventory_post_agent.json`, lecture seule)
| Collection | Post-seed (13:48) | Post-it.47 (maintenant) | Δ (attribué à it.47) |
|---|---|---|---|
| audit_logs | 96 | 127 | +31 |
| documents | 19 | 21 | +2 (2 pleins oct. 2026) |
| fuel_anomalies | 3 | 3 | — |
| fuel_card_assignments / fuel_cards | 5 / 5 | 5 / 5 | — |
| fuel_import_jobs / fuel_import_rows | 4 / 7 | 4 / 7 | — |
| fuel_reconciliations | 1 | 2 | +1 (justification V2) |
| fuel_snapshots | 7 | 7 | — |
| fuel_statement_lines | 18 | 20 | +2 (recalcul DEC-2026-10-001) |
| fuel_statements | 4 | 6 | +2 (DEC-2026-03-001, COR-2026-05-002) |
| fuel_transaction_matches / fuel_transactions | 18 / 18 | 20 / 20 | +2 / +2 |
| tenant_settings · users · vehicle_field_meta · vehicles | 1 · 2 · 3 · 5 | 1 · 2 · 3 · 5 | — |
| tenants | (non compté par le script seed) | 1 | — |
Toutes les variations correspondent au `seed_data_creation` déclaré par it.47.

## 5. Statements (6)
| N° | Type | Kind | Parent | Période | Scope | Status | Lignes | Blockers (count/lines) | Exception | Declared | closed_at / by |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEC-2026-03-001 | regulier | **clôturé normal** | — | 2026-03 | tenant | cloture | 0 | 0/0 | non | null | 13:55:50 / lotg-admin |
| DEC-2026-04-001 | regulier | **clôturé normal** | — | 2026-04 | tenant | cloture | 1 | 0/0 | non | 100 CHF · 50 L · 0 kWh · 1 | 13:38:54 / lotg-admin |
| DEC-2026-05-001 | regulier | **clôturé exception** | — | 2026-05 | tenant | cloture | 14 | 7/6 `{pending_fx 1, matched_review 1, unmatched 1, open_anomaly 3, forced_duplicate 1}` | oui (« Clôture mensuelle imposée par la comptabilité… ») | 1000 CHF · volume/kWh/lignes N/A | 13:38:55 / lotg-admin |
| DEC-2026-10-001 | regulier | **clôturé exception** | — | 2026-10 | tenant | cloture | 4 | 1/1 `{pending_fx 1}` | oui (« Clôture octobre imposée (test agent) ») | 170 CHF · 85 L · 0 kWh · 2 | 13:54:54 / lotg-admin |
| COR-2026-05-001 | correctif | **correctif clôturé normal** | DEC-2026-05-001 | 2026-05 | tenant | cloture | 1 (tardive) | 0/0 | non | null | 13:57:27 / lotg-admin |
| COR-2026-05-002 | correctif | **correctif brouillon** | DEC-2026-05-001 | 2026-05 | tenant | brouillon | 0 | 0/0 | non | null | — |
Lignes : total 20 = 14 (DEC-05) + 4 (DEC-10) + 1 (DEC-04) + 1 (COR-001). Blockers par décompte : DEC-05 `{open_anomaly 3, unmatched 1, pending_fx 1, forced_duplicate 1, matched_review 1}` · DEC-10 `{pending_fx 1}` · autres `{}`.

## 6. Locks transactions
`fuel_transactions` : total **20** · `locked=true` **20** · `locked=false` **0** (toutes les transactions appartiennent à un décompte clôturé ; le seul brouillon, COR-2026-05-002, a 0 ligne).
| Statement | Type | Status | Tx snapshot | Tx locked (par ce décompte) | Verdict |
|---|---|---|---|---|---|
| COR-2026-05-002 | correctif | brouillon | 0 | 0 | PASS (brouillon : 0 lock) |
| DEC-2026-03-001 | regulier | cloture (normal) | 0 | 0 | PASS |
| DEC-2026-04-001 | regulier | cloture (normal) | 1 | 1 | PASS |
| DEC-2026-05-001 | regulier | cloture (exception) | 14 | 14 | PASS |
| DEC-2026-10-001 | regulier | cloture (exception) | 4 | 4 | PASS |
| COR-2026-05-001 | correctif | cloture (normal) | 1 | 1 · ∩ parent = 0 | PASS |
Pour les 20 transactions : `statement_id` = décompte clôturant, `locked_at` **=** `closed_at` du décompte (04 : 13:38:54.710355 · 05 : 13:38:55.703582 · 10 : 13:54:54.190445 · COR-001 : 13:57:27.724209), `source_document_id` présent sur 20/20 (liste complète id/statement/locked_at/document/vehicle/date dans `lotg_inventory_post_agent.json`).
Preuve « brouillon → pas de lock » : verify 13:40 (`3 transaction(s) de brouillon, aucune verrouillée` sur COR-001 + DEC-10 alors brouillons) + it.47 sc.4 (recalcul +2 lignes sans lock) puis sc.6 (lock à la close-exception uniquement, `locked_at` = `closed_at`).
**DRAFT_LOCKS = PASS · CLOSED_LOCKS = PASS · CLOSE_EXCEPTION_LOCKS = PASS · CORRECTIVE_EXCLUDES_LOCKED = PASS**

## 7. Rapprochements (`fuel_reconciliations` = justifications persistées : 2)
| Période | Véhicule | status_at | source_consumption_at | ecart_l_at | Justification | Par |
|---|---|---|---|---|---|---|
| 2026-05 | V1 `84b79d21…` (VD 700 001) | INDICATIF | can | +10.0 | « Jerrican de 10 L pour la tondeuse du dépôt… » | lotg-admin |
| 2026-05 | V2 `42627572…` (VD 700 002) | INDICATIF | can | −20.0 | « Plein jerrican chantier (justification agent) » | lotg-admin |
Rapprochements calculés mai 2026 (curl §10) : 5 véhicules, `by_status {OK 0, A_CONTROLER 0, INDICATIF 5, IMPOSSIBLE 0}`, justified 2, with_blockers 1 (V4, 5 blockers).

## 8. Audit Lot G (`audit_logs` tenant : 127)
`fuel_statement/create` 6 · `/declared` 4 · `/recalculate` 1 · `/close` 3 · `/close_exception` 2 · `fuel_reconciliation/justify` 2 · `tenant_settings/settings` 6 (seuils 5/5 ↔ null, seed + verify + it.47) · `fuel_export/download` **28 — 28/28 avec `sha256`, `size`, `format`, `export_type`, `filters`, `statement_id`, `period_month`, acteur** (statement csv ×13 / xlsx ×4 / pdf ×4, reconciliations csv/xlsx/pdf ×2 chacun, transactions csv/xlsx ×2 chacun ; dont 2 par le compte read_only). Autres : document/create 20, fuel_transaction/create 20, fuel_import upload/mapping/confirm 4+4+4, force 1, match_run 2, fuel_anomaly create 3 / decide 2, document/modify 2, admin tenant/user create 1+2. Les CSV du même décompte clôturé ont un hash identique (`3328f3d1…`, snapshot immuable) ; XLSX/PDF varient par métadonnées d'horodatage internes (hash des octets finaux audité à chaque téléchargement, conforme).

## 9. Testing agent
- **it.46** (`test_reports/iteration_46.json`) : pytest 24/24 + 11/11 API smoke + smoke UI (login, pages, drawer, 404, read_only) — [EXEC, lu].
- **it.47** (`test_reports/iteration_47.json`) : **13/13 scénarios UI avec mutations réelles, 0 bug** (422 seuil négatif inline & saisie conservée · seuils 5/5 → « À contrôler » ×2, KPI 2 · seuils remis à null · justification V2 · declared 422 / 170 CHF persisté Δ +10,25 CHF (+6 %) · recalcul +2/−0 → 4 lignes, blocker FX · close normal refusé 409 `fuel-statement-close-blocked`, pas de faux succès · close_exception : confirm disabled sans motif/ack, toast, badges, boutons mutants absents, `corrective-btn` présent, API tx G10 locked · close normal DEC-2026-03-001 + 409 `STATEMENT_EXISTS` → drawer existant · 409 `CORRECTIVE_OPEN` inline · lien correctif, clôture COR-001, parent immuable (7 blockers) · COR-002 créé 0 ligne · anomalie justifiée après clôture (tx 200 CHF inchangée, snapshot inchangé) · tx verrouillée UI (badge, boutons disabled, `/energie` badge) · 8 exports toasts + `X-Content-SHA256` = sha256(bytes) ×3 + `Content-Disposition` + statement inchangé · read_only UI 0 bouton mutant / 9 mutations API 403 / export 200 · 404 → `fuel-statement-drawer-error`). `backend_issues`/`frontend_issues` vides, `action_items` vide.

## 10. Curl read-only de contrôle [EXEC] (tenant `lotg-ui-test`, token masqué)
| # | Commande | HTTP | Résultat |
|---|---|---|---|
| 1 | `GET /api/tenant-settings/fuel/reconciliation` (admin) | 200 | `{"reconciliation":{"threshold_pct":null,"threshold_l":null},"rule":{"code":"single_or_both",…}}` — null réel, aucun défaut injecté |
| 2 | `GET /api/fuel/reconciliations?period_month=2026-05&vehicle_id=84b79d21-…` (admin) | 200 | item : `vehicle_id, period_month, achats.litres 110.0 (=purchased_l), consommation.{source can, litres 100.0} (=CAN), estimation_tickets.litres 50.0, astra.conso_officielle_l_100km 6.5 (=référence), ecart_l 10.0 (=delta_l), ecart_pct 10.0 (=delta_pct), source_consumption can, status INDICATIF, status_reason, thresholds{null,null,configured false}, blockers{count 0}, justification{…}, transaction_ids, breakdown, justification_history` |
| 2b | `GET /api/fuel/reconciliations?period_month=2026-05` (admin) | 200 | 5 items, `stats.by_status {OK 0, A_CONTROLER 0, INDICATIF 5, IMPOSSIBLE 0}` ; V3/V4/V5 `source unavailable`, `ecart None` (aucune consommation inventée) |
| 2c | `GET /api/fuel/reconciliations` sans `period_month` | 422 | obligatoire |
| 3 | `GET /api/fuel/statements/ef7c3c02-…` (DEC-2026-05-001, admin) | 200 | `id, number, type regulier, parent_statement_id null, period_month 2026-05, scope{tenant}, status cloture, declared{1000 CHF, null×3}, totals{n_lignes 14, montant_chf 1114, litres 501, kwh 50, pending_fx 1, blocker_count 7, blocked_line_count 6, blockers_by_type, n_vehicules 5}, deltas{+114 / 11.4 %, comparable true, null×3}, close_exception true, closed_at, closed_by, exception{reason, by, at, blockers_snapshot}, lines[14] (chaque ligne : blockers[], locked true, locked_at, statement_id), history, correctifs, corrective_eligible, blocker_labels, *_label` |
| 4a–d | read_only : `GET reconciliations 2026-05` · `GET settings` · `GET statements/3d4c1b23-…` (DEC-2026-10-001) · `GET statements` | 200 ×4 | 5 items ; null/null ; cloture exception, 4 lignes, 1/1 blocker, declared 170, deltas +71.75 / 42.2 %, Δ volume 50 L, Δ lignes 2, lignes 20/20 locked ; liste 6 décomptes |
Périodes « avec seuils » : non re-testées en curl (nécessiterait un PATCH = mutation) — couvert par seed G, verify et it.47 sc.1b (5 %/5 L → `A_CONTROLER` ×2, KPI 2).
**CURL_RECONCILIATION_SHAPE = PASS · CURL_THRESHOLDS = PASS · CURL_STATEMENT_DETAIL = PASS · CURL_READ_ONLY = PASS**

## 11. Revue frontend
- **Shapes** [EXEC] : champs rapprochement consommés (`achats`, `consommation`, `astra`, `ecart_l`, `ecart_pct`, `source_consumption`, `blockers`, `justification`, `plaque`, `vehicule_label`, `period_month`) ⊂ clés API ; côté décompte, seuls `added`/`removed`/`already_closed` ne sont pas dans le détail — ce sont les réponses des mutations `recalculate`/`close` (`server.py:5713-5801`), conformes. Noms théoriques (`purchased_l`, `can_consumption_l`, `delta_l`…) absents des deux côtés : le contrat réel est le contrat français ci-dessus, **0 divergence frontend ↔ API**.
- **Enums** [INSP] : `lib/fuelStatements.js` = miroir exact de `fuel_statements.py` (`OK/A_CONTROLER/INDICATIF/IMPOSSIBLE`, `brouillon/cloture`, `regulier/correctif`, 5 blockers avec libellés = `blocker_labels` backend), aucun mapping silencieux.
- **Erreurs** [INSP + it.47] : `apiError` → 403 message métier · 404 détail ou « introuvable » (drawer `fuel-statement-drawer-error`, sc.13) · 409 `STATEMENT_LOCKED` avec `statement_number/id · period_month · blocked_fields` ; 409 `CLOSE_BLOCKED` liste détaillée (sc.5), `STATEMENT_EXISTS` → ouverture du drawer existant (sc.7), `CORRECTIVE_OPEN` inline (sc.8a) · 422 champ : message inline, saisie conservée (sc.1a, 3a).
- **read_only** [it.47 sc.12 + curl §10] : boutons mutants absents du DOM, `declared-amount` disabled, exports présents, API 403 ×9.
- **Test IDs** [EXEC] : scan statique `lotg_testid_check.py` → 160 statiques + 29 patterns dynamiques = 189, **0 doublon**.
- **reopen** : §3. **Console** [EXEC smoke] : `test_reports/lotg_smoke_console.log` — uniquement le warning Recharts `width(-1)/height(-1)` préexistant (dashboard) + `cdn-cgi/rum` aborted (plateforme) ; 0 erreur React.
- **`yarn build`** [EXEC, artefact] : `test_reports/lotg_yarn_build.log` → `Compiled successfully`, `Done in 17.84s`, `BUILD_EXIT=0` ; aucun fichier `frontend/src` plus récent que ce log.

## 12. Screenshot smoke [EXEC]
`test_reports/lotg_smoke_statement_drawer.jpeg` (sha256 `dbfff571…`, 58 926 o) — route `/energie/releves?id=ef7c3c02-…`, drawer `DEC-2026-05-001` : badges `Clôturé · Régulier · Clôturé avec exception · Immuable — aucune réouverture`, snapshot 1 114 CHF / 501 L / 50 kWh / 14 tx (5 véhicules) / 1 en attente FX, declared 1000 CHF (champs disabled), Δ montant +114 CHF (+11.4 %), Δ volume/kWh/lignes N/A, « 7 blocker(s) sur 6 ligne(s) » avec pills par type, boutons `Créer un correctif · Export CSV/XLSX/PDF`. KPIs page : 6 décomptes · 1 brouillon · 5 clôturés. *Le chemin `.png` annoncé lors de la passe précédente n'avait pas été persisté (outil de capture hors dépôt) ; capture refaite et persistée en `.jpeg`.*

## 13. Tests pytest
| Suite | Résultat | Artefact |
|---|---|---|
| `tests/test_fuel_statements_phase4c.py` | **24 PASS / 0 FAIL / 0 SKIP** (86.0 s, 13:43:57) | `test_reports/pytest/lotg_phase4c.xml` |
| Non-régression A–G (13 suites : legacy A 20 · nofile 22 · drivers 19 · fines 4C 27 · fuel_cards 22 · business_data 17 · energy 23 · fines Phase 3 20 · import 24 · matching 16 · anomalies 13 · guardrails 12 · statements 24 = 259 collectés) | **259 PASS / 0 FAIL / 0 SKIP**, 1 warning (PendingDeprecation `multipart`), 423.74 s | `test_reports/lotg_full_regression.log` (13:03) |
Validité : tous les fichiers `backend/*.py` ont un mtime ≤ 12:47 UTC < 13:03 (aucun fichier backend plus récent que le log) → le run reste la preuve de référence. **Correctif factuel** : le chiffre « 315 passed / 2 skipped » cité en passation est celui de la régression historique it.32 (carte grise OCR, CHANGELOG l.410), pas du Lot G ; l'artefact Lot G persisté est 259 PASS. Aucun fichier backend modifié dans cette passe → pas de re-run requis.

## 14. Exports & SHA-256
Seed AB : 8/8 (hash recalculé = en-tête = audit). it.47 sc.11 : `X-Content-SHA256` = sha256(bytes) pour csv/xlsx/pdf, `Content-Disposition attachment; filename="decompte-DEC-2026-05-001.<ext>"`, statement inchangé après exports. Inventaire : 28 audits `fuel_export/download`, **28/28** avec sha256/size/format/filters/acteur.

## 15. `default` et autres tenants (baseline 13:36 vs maintenant) [EXEC]
- `counts` : **231/231 clés identiques** (dont `default` 15/15 : alerts 94 · audit_logs 2514 · doc_categories 9 · doc_requirements 6 · documents 444 · files 47 · fuel_transactions 1 · inspections 3 · tenant_integrations 1 · tenant_settings 1 · tenants 1 · users 4 · vehicle_field_meta 96 · vehicles 16 · vehicles_archive 92) ; `tenants_ids` identiques (aucun tenant créé/supprimé hors cible).
- `hashes` (stable) : 229/231 identiques ; **2 différences, toutes `default`** : `vehicles|default` et `tenant_integrations|default`. Cause établie : job horaire Navixy préexistant (`apscheduler … navixy_sync_job` 13:47:41 → 13:47:47 UTC, log supervisor), 14 véhicules `source=navixy` avec `updated_at` = `tenant_integrations.last_sync_at` = `13:47:42.395077` ; `audit_logs|default` +0 ; collections Lot G de `default` (`fuel_transactions` 1, aucune `fuel_statements`/`fuel_reconciliations`) identiques. Le verify (13:40) avait constaté « diff = aucune » **avant** cette exécution planifiée. → hors périmètre Lot G, non bloquant (§19).
- Autres tenants (`client-test-e2e`, `platform`, `pytest-*`) : counts et hashes **identiques**.

## 16. Git [EXEC]
```
$ git rev-parse HEAD
1684adfc923890989d233c70e1e529dbd4b5e4e2
$ git log -1 --oneline
1684adf checkpoint before testing_agent_full_stack
$ git status --short          (avant la mise à jour documentaire de cette passe)
?? test_reports/iteration_47.json
?? test_reports/lotg_inventory_post_agent.json
?? test_reports/lotg_post_agent_inventory.py
?? test_reports/lotg_smoke_statement_drawer.jpeg
$ git diff --stat
(vide — aucun fichier suivi modifié)
```
Après mise à jour PRD/CHANGELOG/ROADMAP/test_credentials (post-verdict) : voir §20 (sortie exacte finale). Aucun commit manuel, aucun reset ; tout le code Lot G est déjà dans les checkpoints plateforme `1291b22` / `1684adf`. `*.log` ignorés par `.gitignore`.

## 17. Fichiers de preuve (présents)
`test_reports/lotg_seed.py` · `lotg_baseline_before_seed.json` · `lotg_seed_result.json` · `lotg_inventory.json` · `lotg_verify.json` · `lotg_post_agent_inventory.py` · `lotg_inventory_post_agent.json` · `lotg_testid_check.py` · `lotg_yarn_build.log` · `lotg_full_regression.log` · `pytest/lotg_phase4c.xml` · `iteration_46.json` · `iteration_47.json` · `lotg_smoke_statement_drawer.jpeg` · `lotg_smoke_console.log` · `lotg_final_report.md`. Non présent : `lotg_smoke_statement_drawer.png` (remplacé par `.jpeg`).

## 18. Issues rencontrées (cycle Lot G)
| # | Sévérité | Symptôme | Cause | Correction | Re-test |
|---|---|---|---|---|---|
| 1 | Moyenne (seed) | 1er `seed` : HTTP 500 sur force-import ligne `G04` | collision index unique `fuel_transactions (tenant, fournisseur, external_transaction_id)` : la ligne forcée réutilisait l'identifiant externe de l'original | `lotg_seed.py` : identifiant externe distinct pour le doublon forcé | re-seed OK (`created_now=False`), cas N PASS, verify PASS |
| 2 | Basse (export) | `ValueError: Invalid character / found in sheet title` (XLSX) | OpenPyXL interdit `/` dans un titre de feuille | titre de feuille sans `/` dans `fuel_statements.py` | pytest exports 24/24, AB 8/8, it.47 sc.11 |
| 3 | Basse (dev) | `ruff` F821 (`ensure_fuel_statement_indexes`, `DuplicateKeyError`, `_with_doc_fx`) | imports/définitions manquants pendant l'intégration | corrigés → `All checks passed!` | régression 259 PASS |
| 4 | Documentaire | « 315 passed » cité en passation | confusion avec la régression it.32 | rapport et CHANGELOG corrigés (259 PASS A–G) | — |
| 5 | Documentaire | `.png` smoke annoncé mais absent | capture non persistée par l'outil | capture refaite, `.jpeg` persisté | — |

## 19. DIVERGENCES RESTANTES
| # | Divergence | Impact | Périmètre | Bloquant |
|---|---|---|---|---|
| D1 | Hash stable `vehicles|default` / `tenant_integrations|default` ≠ baseline après le verify (job horaire Navixy 13:47 UTC ; counts identiques, 0 audit, 0 collection Lot G) | aucun sur Lot G ; le filtre `VOLATILE` de `lotg_seed.py` ne couvre pas `carburant_niveau_*`, `tracker_gps`, `integrations`, `last_sync_at` → à élargir pour le futur cleanup/verify | outillage de preuve | **NON** |
| D2 | Chiffre « 315 passed » de la passation ≠ artefact Lot G (259 PASS = 13 suites A–G, 0 FAIL) | documentaire uniquement | documentation | **NON** |
| D3 | Statut `IMPOSSIBLE` (ni achat ni CAN) : présent dans les enums backend/frontend et dans `stats.by_status`, mais sans cas A–AB ni test unitaire dédié | couverture de preuve d'un cas limite | tests | **NON** |
| D4 | État courant : 0 brouillon avec lignes (toutes les 20 tx verrouillées) — la preuve « brouillon ⇒ 0 lock » repose sur verify 13:40 + it.47 sc.4/6 (`locked_at` = `closed_at` 20/20), pas sur l'état instantané | aucun | preuve | **NON** |
| D5 | Screenshot persisté en `.jpeg` et non `.png` ; capture réalisée après it.47 (état DEC-2026-05-001 inchangé depuis 13:38:55) | aucun | preuve | **NON** |
| D6 | Dettes connues hors Lot G : warning Recharts dashboard, overlay CRA ResizeObserver (dev), `server.py` 8 663 lignes (refactor P3), `lotg-ui-test` conservé par consigne (cleanup = lot séparé), Dockerfile à vérifier (`fuel_statements.py` copié) avant tout futur déploiement | dette | hors lot | **NON** |
**DIVERGENCES BLOQUANTES = 0**

## 20. Résumé compact
```
REOPEN_UI_ACTIONS = 0
A_AB_PASS = 28/28 · A_AB_FAIL = 0 · A_AB_BLOCKED = 0 · A_AB_MISSING = 0
DRAFT_LOCKS = PASS
CLOSED_LOCKS = PASS
CLOSE_EXCEPTION_LOCKS = PASS
CORRECTIVE_EXCLUDES_LOCKED = PASS
CURL_RECONCILIATION_SHAPE = PASS · CURL_THRESHOLDS = PASS · CURL_STATEMENT_DETAIL = PASS · CURL_READ_ONLY = PASS
GIT_HEAD = 1684adfc923890989d233c70e1e529dbd4b5e4e2
GIT_WORKTREE = DIRTY (uniquement artefacts test_reports non suivis + memory/*.md mis à jour post-verdict ; 0 fichier code modifié)
DIVERGENCES = 6 non bloquantes (D1–D6), 0 bloquante

LOT G FULL-FLOW = PASS
DIVERGENCES BLOQUANTES = 0
LOT G CLEANUP = NOT RUN
LOT G FINAL CLOSE = NOT DONE
LOT H = NOT AUTHORIZED
MIGRATION = NONE
DRY-RUN MIGRATION = NONE
DEPLOYMENT = NONE
```
