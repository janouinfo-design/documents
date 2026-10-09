# Dossier d'entrée du dry-run de migration Journal → Documents

Déposer ICI l'export Journal **READ-ONLY** (option A), un fichier JSON par entité, au schéma décrit dans
`test_reports/migration_journal_export_spec.md` :

- `tenants.json` (OBLIGATOIRE)
- `vehicles.json` (OBLIGATOIRE)
- `fuel_transactions.json` (OBLIGATOIRE)
- `fines.json` (OBLIGATOIRE)
- `drivers.json`, `vehicle_assignments.json`, `fuel_cards.json`, `fuel_card_assignments.json`,
  `documents_costs.json` (optionnels)

Générer ces fichiers avec `test_reports/journal_export_readonly.py` exécuté **côté Journal** (jamais ici).

Puis lancer le dry-run :

    cd /app/test_reports/migration && python3 migration_harness.py dryrun /app/test_reports/migration_input

Tant que ce dossier ne contient pas les fichiers obligatoires, le harness **refuse** de démarrer
(`JOURNAL DATA EXTRACTION = NOT RUN`). Aucune donnée Journal n'est inventée.
