# Spécification d'export Journal (READ-ONLY) pour le dry-run de migration

- `legacy_source = "journal"` · clé de correspondance tenant (D3) : `navixy_master_user_id` ↔ Documents `tenant_integrations.master_user_id`
- Clé d'idempotence cible : `(tenant_id Documents, legacy_source, legacy_id)`
- Format : un fichier JSON par entité (racine = tableau d'objets), encodage UTF-8, dates ISO-8601.
- **Ne rien inventer** : un champ absent est omis (ou `null`) ; aucune valeur par défaut fabriquée.
- Fichiers OBLIGATOIRES : `tenants.json`, `vehicles.json`, `fuel_transactions.json`, `fines.json`.

## `tenants.json` — tenant (OBLIGATOIRE)
- Identifiant legacy : `legacy_tenant_id` · Décision figée : D3 — mapping par clé technique uniquement ; name jamais utilisé ; aucun fallback default.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_tenant_id` 🔑 | string | oui |  |  | UUID/clé tenant Journal — identifiant legacy |
| `navixy_master_user_id` | int |  |  |  | D3 : clé de correspondance → tenant_integrations.master_user_id ; absent = tenant NON migré |
| `name` | string |  |  |  | affichage seulement — JAMAIS utilisé pour la correspondance |

## `vehicles.json` — vehicle (OBLIGATOIRE)
- Identifiant legacy : `legacy_vehicle_id` · Décision figée : Lot A — resolver vin > navixy_vehicle_id > tracker(warning) > plate(manual_review) ; aucun match auto par plaque/nom/label.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_vehicle_id` 🔑 | string | oui |  |  | UUID véhicule Journal — identifiant legacy |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  | tenant propriétaire (contexte de résolution) |
| `plate` | string |  |  |  | indice uniquement → manual_review ; jamais jointure automatique |
| `vin` | string |  |  |  | critère fort (resolver) |
| `navixy_vehicle_id` | int |  |  |  | critère fort (resolver) |
| `navixy_tracker_id` | int |  |  |  | critère évolutif → candidate_warning (tracker_join_no_assignment_history) |
| `navixy_tracker_id_archived` | int |  |  |  | historique tracker (contexte) |
| `model` | string |  |  |  | contexte |

## `drivers.json` — driver (optionnel)
- Identifiant legacy : `legacy_driver_id` · Décision figée : Lot C — identité par id canonique UNIQUEMENT ; jamais le nom comme clé ; association insuffisante → REVIEW_REQUIRED.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_driver_id` 🔑 | string | oui |  |  | UUID conducteur Journal — identifiant legacy |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `name` | string |  |  |  |  |
| `first_name` | string |  |  |  |  |
| `last_name` | string |  |  |  |  |
| `email` | string |  |  |  | contexte RH, non clé d'identité |
| `navixy_employee_id` | int |  |  |  |  |
| `internal_number` | string |  |  |  |  |
| `active` | bool |  |  |  | statut actif/inactif |

## `vehicle_assignments.json` — vehicle_assignment (optionnel)
- Identifiant legacy : `legacy_assignment_id` · Décision figée : Affectation datée — migrée seulement si relations résolues sans ambiguïté ; jamais inventée.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_assignment_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `legacy_vehicle_id` | string | oui | vehicles.legacy_vehicle_id |  |  |
| `legacy_driver_id` | string | oui | drivers.legacy_driver_id |  |  |
| `valid_from` | date |  |  |  | D5 — fuseau Europe/Zurich |
| `valid_to` | date |  |  |  | null = en cours |
| `principal` | bool |  |  |  |  |

## `fuel_cards.json` — fuel_card (optionnel)
- Identifiant legacy : `legacy_card_id` · Décision figée : D2/Lot E — identité (provider,last4) NON unique ; aucun HMAC Journal migré ; found/ambiguous/not_found.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_card_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `provider` | string |  |  |  | → fournisseur |
| `last4` | string |  |  |  | 4 derniers chiffres — (provider,last4) non unique |
| `external_card_id` | string |  |  |  |  |
| `status` | string |  |  |  |  |
| `expires_at` | date |  |  |  |  |

## `fuel_card_assignments.json` — fuel_card_assignment (optionnel)
- Identifiant legacy : `legacy_card_assignment_id` · Décision figée : Lot E — affectation datée migrée seulement si déterminable sans ambiguïté.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_card_assignment_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `legacy_card_id` | string | oui | fuel_cards.legacy_card_id |  |  |
| `type` | string |  |  | vehicule, conducteur | type d'affectation |
| `legacy_vehicle_id` | string |  | vehicles.legacy_vehicle_id |  |  |
| `legacy_driver_id` | string |  | drivers.legacy_driver_id |  |  |
| `valid_from` | date |  |  |  |  |
| `valid_to` | date |  |  |  |  |

## `fuel_transactions.json` — fuel_transaction (OBLIGATOIRE)
- Identifiant legacy : `legacy_transaction_id` · Décision figée : §4.11 — document = source canonique du coût ; fuel_transaction JAMAIS resommé ; D5 dates ; D7 FX ; D8 anomalies recalculées.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_transaction_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `external_transaction_id` | string |  |  |  | → tx.external_transaction_id · doc.numero ; unique partiel (tenant,fournisseur,ext_id) |
| `provider` | string |  |  |  | → fournisseur ; 'manuel' → null + created_from=manual |
| `legacy_card_id` | string |  | fuel_cards.legacy_card_id |  | → tx.card_id via fuel_cards.legacy_id |
| `card_last4` | string |  |  |  | → tx.carte_last4 |
| `tx_datetime` | datetime | oui |  |  | D5 : tz-aware→Europe/Zurich ; naïf→heure locale Europe/Zurich + date_heure_tz_assumed=true ; brut conservé dans date_heure_source |
| `accounting_date` | date |  |  |  | → tx.date_comptable |
| `station_name` | string |  |  |  |  |
| `station_address` | string |  |  |  |  |
| `station_country` | string |  |  |  |  |
| `station_lat` ⛔DO NOT MIGRATE | float |  |  |  | DO NOT MIGRATE |
| `station_lng` ⛔DO NOT MIGRATE | float |  |  |  | DO NOT MIGRATE |
| `product_type` | string |  |  | diesel, essence, adblue, electric, other | diesel→Diesel, essence→Essence, adblue→AdBlue (exclu conso), electric→Électricité(energie=electrique), other→Autre |
| `quantity` | float |  |  |  | → litres(L) / energie_kwh(kWh) / quantite_unite(unit) ; jamais L+kWh additionnés |
| `unit` | string |  |  | L, kWh, unit |  |
| `unit_price` | float |  |  |  | → prix_litre / prix_kwh |
| `amount_net` | float |  |  |  | → doc.montant_ht |
| `vat_amount` | float |  |  |  | → doc.tva_chf |
| `vat_rate` | float |  |  |  | → doc.tva_taux |
| `amount_total` | float | oui |  |  | → doc.montant / tx.montant |
| `currency` | string | oui |  |  | → devise |
| `amount_chf` | float |  |  |  | D7 : utilisé seulement si devise≠CHF ; absent + devise≠CHF → fx_status=pending, exclu du total CHF |
| `fx_rate` | float |  |  |  |  |
| `fx_rate_date` | date |  |  |  |  |
| `fx_source` | string |  |  |  |  |
| `mileage` | int |  |  |  | → tx.kilometrage ; JAMAIS écrit sur vehicle.kilometrage |
| `vehicle_hint` | string |  |  |  | contexte — jamais résolution auto |
| `driver_hint` | string |  |  |  | contexte — jamais résolution auto |
| `legacy_vehicle_id` | string |  | vehicles.legacy_vehicle_id |  | → vehicle_id via legacy_vehicle_map CONFIRMÉ ; non résolu → quarantaine (REVIEW_REQUIRED) |
| `legacy_driver_id` | string |  | drivers.legacy_driver_id |  | → driver_id via drivers.legacy_id |
| `trip_id` ⛔DO NOT MIGRATE | string |  |  |  | DO NOT MIGRATE (pas de trajets) |
| `classification` | string |  |  |  | conservée, non exploitée |
| `match_status` ⛔DO NOT MIGRATE | string |  |  |  | RECALCULATE (D8) — jamais migré tel quel |
| `match_score` ⛔DO NOT MIGRATE | float |  |  |  | RECALCULATE (D8) |
| `anomaly_decision` | string |  |  |  | D8 : réimporté UNIQUEMENT si anomalie re-détectée (même tx, même type, donnée réelle) |
| `source` | string |  |  | manual, import | → tx.created_from + doc.source=legacy_import |
| `commentaire` | string |  |  |  | D8 : issues[] NON migrées ; commentaire métier réel → tx.commentaire |

## `fines.json` — fine (OBLIGATOIRE)
- Identifiant legacy : `legacy_fine_id` · Décision figée : Lot D + D4 + D9 — vehicle_id obligatoire ; plaque seule → REVIEW_REQUIRED (quarantaine) ; annulee conservée hors coûts/délais ; 10 statuts ; type_infraction enum.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_fine_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `legacy_vehicle_id` | string |  | vehicles.legacy_vehicle_id |  | D4 : via legacy_vehicle_map CONFIRMÉ ; absent → voir plaque_mentionnee |
| `plaque_mentionnee` | string |  |  |  | D4 : plaque seule → manual_review → REVIEW_REQUIRED (quarantaine), jamais jointure auto |
| `legacy_driver_id` | string |  | drivers.legacy_driver_id |  |  |
| `numero_amende` | string |  |  |  | → numero |
| `autorite` | string |  |  |  |  |
| `date_infraction` | date | oui |  |  | D5 Europe/Zurich |
| `montant` | float | oui |  |  |  |
| `devise` | string | oui |  |  | D7 identique aux pleins |
| `amount_chf` | float |  |  |  | D7 |
| `delai_paiement` | date |  |  |  | échéance ; D9 : inactive si annulee/payee/refacturee/cloturee |
| `motif` | string |  |  |  |  |
| `type_infraction` | string |  |  | speeding, parking, red_light, toll, forbidden_zone, phone, seatbelt, other | enum 8 valeurs ; inconnu → REVIEW_REQUIRED |
| `fine_status` | string |  |  | recue, a_analyser, conducteur_a_identifier, en_attente_conducteur, contestee, a_payer, payee, refacturee, cloturee, annulee | 10 statuts (ou alias EN) ; absent → a_payer (lecture) ; annulee exclue coûts+délais (D9) |
| `lieu_infraction` | object |  |  |  | {lieu, ville, canton} — jamais texte brut |
| `notes_internes` | string |  |  |  | D6.3 : masquées read_only/driver (RBAC serveur) — conservées, jamais exposées au driver |
| `dossier_number` | string |  |  |  | → dossier_interne (référence humaine, NON clé) |

## `documents_costs.json` — document_cost (optionnel)
- Identifiant legacy : `legacy_document_id` · Décision figée : Documents/coûts associés éventuels — document = source canonique du coût ; compté une fois.

| Champ | Type | Obligatoire | Relation | Enum | Note |
|---|---|---|---|---|---|
| `legacy_document_id` 🔑 | string | oui |  |  |  |
| `legacy_tenant_id` | string | oui | tenants.legacy_tenant_id |  |  |
| `legacy_vehicle_id` | string |  | vehicles.legacy_vehicle_id |  |  |
| `type` | string |  |  |  |  |
| `montant` | float |  |  |  |  |
| `devise` | string |  |  |  |  |
| `amount_chf` | float |  |  |  |  |
| `date` | date |  |  |  |  |
| `categorie` | string |  |  |  |  |

## Relations entre fichiers

- `tenants.legacy_tenant_id` ← référencé par tous les autres fichiers (`legacy_tenant_id`).
- `vehicles.legacy_vehicle_id` ← `fuel_transactions`, `fines`, `vehicle_assignments`, `fuel_card_assignments`.
- `drivers.legacy_driver_id` ← `fuel_transactions`, `fines`, `vehicle_assignments`, `fuel_card_assignments`.
- `fuel_cards.legacy_card_id` ← `fuel_card_assignments`, `fuel_transactions`.

## Dépôt attendu

Déposer les fichiers dans `/app/test_reports/migration_input` puis lancer `migration_harness.py dryrun <dir>`.