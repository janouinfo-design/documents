# Tenant démo commercial `demo-logitrak` — rapport

- Tenant : **Démo LogiTrak** (`demo-logitrak`) · marquage `demo_seed=true`, `demo_seed_version=2026-10`, `demo_seed_group=commercial-demo`
- Méthode : création via l'API du compte admin du tenant (règles métier + isolation). Aucun déploiement. Aucune migration.

## Counts par entité
- `audit_logs` : 88
- `documents` : 33
- `driver_assignments` : 7
- `drivers` : 6
- `fuel_anomalies` : 2
- `fuel_card_assignments` : 4
- `fuel_cards` : 4
- `fuel_transaction_matches` : 16
- `fuel_transactions` : 16
- `inspections` : 1
- `users` : 3
- `vehicle_field_meta` : 2
- `vehicles` : 10

## Comptes créés (mots de passe : voir `memory/test_credentials.md`, non affichés)
- `admin@demo-logitrak.ch` · rôle `admin`
- `driver@demo-logitrak.ch` · rôle `driver` · lié à un conducteur
- `readonly@demo-logitrak.ch` · rôle `read_only`

## Véhicules par carburant
- {"Diesel": 4, "Essence": 1, "Électrique": 3, "Hybride rechargeable": 2}

## Cartes carburant
- Avia ••3651 · statut `suspendue` · expire 2027-08-05
- Tamoil ••7290 · statut `active` · expire 2026-09-19
- Migrol ••1182 · statut `active` · expire 2028-03-12
- Shell ••4473 · statut `active` · expire 2028-06-10

## Amendes par statut
- {"a_payer": 2, "contestee": 1, "payee": 1}

## Scénarios démo disponibles
- EV avec recharges (Tesla Model 3, historique multi-mois) · véhicule sans conducteur (Škoda Octavia, Hyundai Ioniq 5)
- Ancienne affectation terminée (Daniel Keller · Toyota Corolla) · conducteur sans véhicule (Elena Schneider)
- Carte Tamoil expirée · carte Avia suspendue · transaction non rapprochée (Toyota Corolla)
- Document expiré (contrôle BMW) · échéance <30j (assurance Passat) · document en attente (Mégane) · document requis manquant (Ioniq 5)
- Amendes : ouverte · payée · en retard · contestée · plusieurs factures (entretien/pneus/réparation/assurance/leasing/énergie)

## Vérification API
- Verdict : **PASS**
  - [PASS] login admin/driver/read_only
  - [PASS] rôles corrects (admin/driver/read_only) + tenant demo-logitrak
  - [PASS] véhicules : 10 au total (4 thermiques · 3 électriques · 2 hybrides · 1 utilitaire)
  - [PASS] conducteurs : 6, dont au moins 1 sans véhicule
  - [PASS] cartes carburant : 4, dont ≥1 expirée et ≥1 non-active (suspendue)
  - [PASS] énergie : ≥4 recharges EV + ≥1 transaction non rapprochée (sans carte)
  - [PASS] amendes : payée + ouverte + contestée présentes (en retard dérivée du délai)
  - [PASS] coûts/factures : plusieurs catégories présentes (entretien/pneus/réparation/assurance/leasing/énergie)
  - [PASS] dashboard : KPIs calculés (véhicules + échéances)
  - [PASS] échéances documentaires : ≥1 expirée et ≥1 urgente (<30j)
  - [PASS] vue chauffeur : ≥1 véhicule, ≥1 plein, ≥1 amende visibles
  - [PASS] read_only : lecture 200, mutations 403
  - [PASS] DEFAULT_UNCHANGED (default identique avant/après)
  - [PASS] OTHER_TENANTS_UNCHANGED (26 autres tenants identiques)
  - [PASS] TARGET_TENANT_PRESENT (demo-logitrak existe)
  - [PASS] MARQUAGE demo_seed appliqué aux véhicules

## Isolation
- `default` inchangé · 26 autres tenants inchangés (fingerprint avant/après, cf. verify).

## VERDICT : DEMO TENANT = READY