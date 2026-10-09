# Rapport d'extraction Journal (READ-ONLY) — 2026-10-09

## Verdict
**`JOURNAL EXPORT READ-ONLY = FAIL`** — motif : `SOURCE_JOURNAL_INACCESSIBLE`.
L'extraction **n'a pas pu démarrer** : il n'existe aucune source Journal dans cet espace de travail. Aucune donnée n'a été fabriquée.

## Base Journal lue
**Aucune.** L'extraction nécessite `JOURNAL_MONGO_URL` + `JOURNAL_DB_NAME` (base Journal READ-ONLY) — ces variables sont **absentes** (ni `backend/.env`, ni environnement shell). Aucune URI/secret n'est affichée ici (aucune n'existe).

## Collections réellement trouvées / absentes
- Serveur Mongo accessible : bases `admin`, `config`, `local`, `test_database`.
- `test_database` = **base applicative Documents** (`DB_NAME=test_database`, 39 collections). **Aucune collection journal-like** (`journal*`, `logbook`, `carnet`, `navixy_master*`).
- **Aucune base Journal séparée** sur ce serveur.
- Collections Journal attendues (`tenants`, `vehicles`, `drivers`, `vehicle_assignments`, `fuel_cards`, `fuel_card_assignments`, `fuel_transactions`, `fines`, `documents`) : **toutes ABSENTES** (source non raccordée).
- Dossier de dépôt `test_reports/migration_input/` : contient uniquement `README.md` — **aucun fichier d'export fourni**.

## Correspondances COLLECTION_MAP / FIELD_MAP
Définies dans `journal_export_readonly.py` (template) mais **non exécutées** (aucune base à lire). À adapter aux noms réels **côté Journal** avant exécution là-bas.

## Nombre de lignes par entité
Toutes entités : `NOT_AVAILABLE` (0 source lue).

## Champs source manquants / anomalies de schéma
Non applicable (aucune donnée source lue). Aucune transformation, aucun mapping incertain, donc aucun `REVIEW_REQUIRED` d'extraction.

## Tenants détectés
`NOT_AVAILABLE` (0).

## Erreurs
`SOURCE_JOURNAL_INACCESSIBLE` : le Journal-de-bord est un projet séparé, sans base/URL/export dans cet espace (cf. `docs/PHASE4_AUDIT_PARITE_JOURNAL_DOCUMENTS.md` l.13 ; `PHASE4C_SPECIFICATION.md` §4.14 « extraction lors d'un GO distinct **côté Journal** »).

## Preuve qu'aucune mutation n'a été exécutée
- Contrôle statique §8 sur `journal_export_readonly.py` : **aucune** opération `insert/insert_one/insert_many/update/update_one/update_many/replace/delete/delete_one/delete_many/find_one_and_update/find_one_and_delete/bulk_write/drop` — **`find()` uniquement**. ✔
- Aucune connexion Journal ouverte (source absente) → 0 lecture, 0 écriture Journal.
- Base Documents (`test_database`) : seules des lectures de contrôle ont eu lieu (recensement des bases/collections) ; **aucune écriture** (le harness utilise l'enveloppe `ReadOnlyDB`). `documents_untouched = true`.

## Comment débloquer (option A — au choix)
1. **Fichiers** : exécuter `journal_export_readonly.py` **côté Journal** (après adaptation `COLLECTION_MAP`/`FIELD_MAP`), puis déposer les JSON produits dans `/app/test_reports/migration_input/`.
2. **Connexion** : fournir des identifiants Mongo **READ-ONLY** vers la base Journal (`JOURNAL_MONGO_URL`, `JOURNAL_DB_NAME`) ; je lancerai l'extraction en lecture seule depuis cet espace.

Dès réception, je relance l'extraction → `journal_export_manifest.json` réel + `EXPORT_SET_SHA256` déterministe, puis (sur GO) le dry-run Documents.

## Résultats
```
JOURNAL EXPORT READ-ONLY = FAIL (SOURCE_JOURNAL_INACCESSIBLE)
```
| Entité | Collection réelle | Lignes | SHA256 | Statut |
|---|---|---|---|---|
| tenant | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| vehicle | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| driver | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| vehicle_assignment | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| fuel_card | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| fuel_card_assignment | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| fuel_transaction | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| fine | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |
| document_cost | ABSENTE | NOT_AVAILABLE | NOT_AVAILABLE | NOT_AVAILABLE |

```
TOTAL_TENANTS = NOT_AVAILABLE
TOTAL_VEHICLES = NOT_AVAILABLE
TOTAL_DRIVERS = NOT_AVAILABLE
TOTAL_FUEL_CARDS = NOT_AVAILABLE
TOTAL_FUEL_CARD_ASSIGNMENTS = NOT_AVAILABLE
TOTAL_FUEL_TRANSACTIONS = NOT_AVAILABLE
TOTAL_FINES = NOT_AVAILABLE
TOTAL_DOCUMENTS_COSTS = NOT_AVAILABLE
EXPORT_SET_SHA256 = e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  (ensemble vide)
```
MIGRATION = NONE · DRY-RUN DOCUMENTS = NOT RUN · DEPLOYMENT = NONE.
