# MIGRATION HARNESS = READY — dry-run Journal → Documents (préparation uniquement)

> **Aucun dry-run réel n'a été exécuté** (aucune donnée Journal présente dans cet espace de travail).
> `JOURNAL DATA EXTRACTION = NOT RUN · MIGRATION DRY-RUN = NOT RUN · MIGRATION APPLY = NOT AUTHORIZED · DEPLOYMENT = NONE`.
> Cette étape prépare et auto-teste le moteur ; le dry-run réel aura lieu à réception de l'export Journal (option A).

- Date : 2026-10-09 · `legacy_source = "journal"` · clé d'idempotence cible : `(tenant_id Documents, legacy_source, legacy_id)`

## 1. Composants livrés
| Fichier | Rôle |
|---|---|
| `migration/migration_schema.py` | Schéma d'export Journal (source unique) : fichiers, champs, types, relations, décisions figées. |
| `migration/migration_harness.py` | Validateur + moteur de dry-run + empreinte Documents + livrables (LECTURE SEULE stricte). |
| `migration_journal_export_spec.md` / `.json` | Spécification exacte de l'export Journal à produire (humain + machine). |
| `journal_export_readonly.py` | Script d'extraction **READ-ONLY à exécuter côté Journal** (jamais ici). |
| `migration_input/` | Dossier de dépôt de l'export Journal (option A). |
| `migration_dryrun_summary.md` / `migration_dryrun_manifest.json` | Livrables générés par le dry-run (ici : run à vide, 0 ligne). |
| `migration_tenant_mapping.json` / `migration_vehicle_mapping.json` | Tables de correspondance (vides tant qu'aucun export). |
| `migration_review_required.json` / `migration_blocked.json` | Détail des objets à revoir / bloqués. |
| `migration_fingerprints.json` | Empreinte Documents (baseline « avant »). |

## 2. Conformité aux décisions figées (implémentées, réutilisant `backend/legacy_identity.py`)
- **D3 tenant** : `tenants.navixy_master_user_id` ↔ `tenant_integrations.master_user_id` (via `LI.tenant_candidates`) ; nom jamais utilisé ; aucun fallback `default` ; statuts **MATCHED / AMBIGUOUS / UNMAPPED / CONFLICT** (collision = plusieurs tenants Journal → même tenant Documents). Tenant sans clé technique → UNMAPPED (non migré).
- **Lot A véhicule** (via `LI.vehicle_candidates`) : ordre vin > navixy_vehicle_id > tracker(warning) > plate(manual_review) ; **aucun** match auto par plaque/nom/label ; statuts **CONFIRMED** (déjà dans `legacy_vehicle_map`) / **REVIEW_REQUIRED** / **CONFLICT** (ambigu) / **UNMATCHED**. Aucune confirmation automatique nouvelle.
- **Lot C conducteurs** : identité par id canonique uniquement ; identité insuffisante → REVIEW_REQUIRED ; jamais le nom comme clé ; jamais d'affectation inventée.
- **D2 / Lot E cartes** : identité `(fournisseur, last4)` **non unique** ; aucun HMAC migré ; **aucune création auto** → found(1)=ALREADY_PRESENT(résolue) / ambiguous=REVIEW_REQUIRED / not_found=REVIEW_REQUIRED. Affectations datées = REVIEW_REQUIRED sauf résolution non ambiguë.
- **§4.11 carburant** : document = source canonique du coût ; `fuel_transaction` **jamais** resommé ; mapping champ à champ (external_transaction_id, fournisseur, carte, station, product_type, quantités L/kWh jamais additionnées, kilométrage jamais écrit sur le véhicule, hints jamais résolus auto, trip/lat/lng/match ⛔ DO NOT MIGRATE).
- **D5 dates** : tz-aware → `Europe/Zurich` ; naïf → heure locale `Europe/Zurich` + `date_heure_tz_assumed=true` ; brut conservé dans `date_heure_source`.
- **D7 FX** : `CHF`→montant ; `≠CHF`+`montant_chf`→montant_chf ; `≠CHF` sans `montant_chf` → `fx_status=pending`, exclu du total CHF (listé dans `pending_fx`).
- **D8 anomalies** : `match_status`/`score`/anomalies **recalculés** à l'APPLY ; `issues[]` non migrées ; décision legacy réimportée seulement si re-détectée.
- **Lot D / D4 / D9 amendes** : `vehicle_id` obligatoire ; plaque seule → **REVIEW_REQUIRED** (quarantaine) ; véhicule inconnu non confirmable → **BLOCKED** ; 10 statuts (+ alias EN) ; `type_infraction` enum 8 valeurs ; `annulee` conservée mais exclue des coûts/délais ; `notes_internes` masquées read_only/driver.
- **Idempotence / dédoublonnage** : clé stable `(tenant, legacy_source, legacy_id)` ; déjà présent → ALREADY_PRESENT ; même legacy_id dans l'export → DUPLICATE ; rejouer le dry-run = **même plan** (déterministe).
- **Classification** : chaque ligne finit dans **exactement une** catégorie `READY / ALREADY_PRESENT / REVIEW_REQUIRED / BLOCKED / DUPLICATE / IGNORED` + `reason_code` + `reason_text` + `source_id` (+ `target_id`).

## 3. Validateur d'entrée (refus de démarrer)
Refuse si : **fichier obligatoire absent** · **schéma invalide** (racine ≠ liste, objet mal formé) · **legacy_id manquant** · **tenant non identifiable** (`legacy_tenant_id` absent de `tenants.json`) · **incohérence source** (`legacy_vehicle_id` référencé mais absent de `vehicles.json`). Prouvé par le selftest.

## 4. Lecture seule stricte (§12 — aucune écriture indirecte)
Le harness n'accède à Mongo qu'au travers d'une enveloppe `ReadOnlyDB` : seules `find/find_one/count_documents/distinct/aggregate` sont exposées ; `insert/update/delete/drop` **lèvent** `PermissionError` (prouvé par le selftest). Aucun endpoint FastAPI, aucun scheduler, aucun job de sync/import/alerte/audit n'est déclenché (script autonome pymongo hors application).

## 5. Auto-test (`python3 migration_harness.py selftest`) = **PASS**
1. `validate()` refuse une entrée incomplète (fichiers obligatoires absents).
2. `validate()` refuse un `legacy_id` manquant.
3. Dry-run sur **entrée vide bien formée** (0 donnée Journal inventée) → `validated=True`, `DOCUMENTS_UNCHANGED=True`, 0 ligne.
4. Lecture seule stricte : insert/update/delete/drop interdits.

## 6. Empreinte Documents (preuve « avant »)
`migration_fingerprints.json` : **126 (collection|tenant), 947 enregistrements** sur les collections cibles (`documents, fuel_transactions, fuel_cards, fuel_card_assignments, drivers, driver_assignments, fuel_transaction_matches, fuel_anomalies, fuel_reconciliations, vehicles, tenant_integrations, tenants, legacy_vehicle_map, legacy_tenant_map, vehicles_archive`). Après le dry-run réel, le harness recapture et compare → `DOCUMENTS_UNCHANGED`.

## 7. Tableau global (état actuel — source Journal absente)
| Type | Source | READY | ALREADY_PRESENT | REVIEW_REQUIRED | BLOCKED | DUPLICATE | IGNORED |
|---|---|---|---|---|---|---|---|
| tenant | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vehicle | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| driver | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| vehicle_assignment | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fuel_card | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fuel_card_assignment | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fuel_transaction | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| fine | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| document_cost | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

`JOURNAL DATA EXTRACTION = NOT RUN` → aucune ligne source à classer (attendu). Les comptes réels seront produits au dry-run (option A).

## 8. Étape suivante (option A)
1. Côté Journal, adapter `COLLECTION_MAP`/`FIELD_MAP` de `journal_export_readonly.py` aux noms réels, puis l'exécuter **READ-ONLY** : `JOURNAL_MONGO_URL=... JOURNAL_DB_NAME=... python3 journal_export_readonly.py ./migration_input`.
2. Déposer les JSON produits dans `/app/test_reports/migration_input/`.
3. Lancer `migration_harness.py dryrun /app/test_reports/migration_input` → génère tous les livrables + verdict `MIGRATION DRY-RUN = PASS/FAIL` (un PASS n'implique pas que tout est READY ; REVIEW_REQUIRED/BLOCKED attendus).

## 9. Verdict
```
MIGRATION HARNESS = READY
JOURNAL DATA EXTRACTION = NOT RUN
MIGRATION DRY-RUN = NOT RUN
MIGRATION APPLY = NOT AUTHORIZED
DEPLOYMENT = NONE
```
