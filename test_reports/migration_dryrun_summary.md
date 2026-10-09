# Dry-run migration Journal → Documents — SYNTHÈSE

- Généré : 2026-10-09T13:52:37.998720+00:00 · `legacy_source = journal`
- Entrée : `/app/test_reports/migration_input`
- DOCUMENTS_UNCHANGED : PASS

## Totaux par catégorie

| READY | ALREADY_PRESENT | REVIEW_REQUIRED | BLOCKED | DUPLICATE | IGNORED |
|---|---|---|---|---|---|
| 8 | 0 | 26 | 9 | 0 | 0 |

## Par type

| Type | READY | ALREADY_PRESENT | REVIEW_REQUIRED | BLOCKED | DUPLICATE | IGNORED |
|---|---|---|---|---|---|---|
| driver | 6 | 0 | 0 | 9 | 0 | 0 |
| fine | 0 | 0 | 2 | 0 | 0 | 0 |
| fuel_card | 0 | 0 | 4 | 0 | 0 | 0 |
| fuel_card_assignment | 0 | 0 | 3 | 0 | 0 | 0 |
| fuel_transaction | 2 | 0 | 14 | 0 | 0 | 0 |
| vehicle_assignment | 0 | 0 | 3 | 0 | 0 | 0 |

- pending_fx (devise≠CHF sans montant_chf, exclues du total CHF) : 0
- tenants : 1 MATCHED / 0 AMBIGUOUS / 2 UNMAPPED / 0 CONFLICT
- véhicules : 0 CONFIRMED / 15 REVIEW / 18 UNMATCHED / 0 CONFLICT

> Rappel : un dry-run PASS ne signifie PAS que toutes les lignes sont READY. REVIEW_REQUIRED / BLOCKED sont attendus et listés dans les manifests dédiés.