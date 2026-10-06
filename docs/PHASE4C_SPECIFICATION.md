# PHASE 4C — SPÉCIFICATION COMPLÈTE (SPECIFICATION ONLY)
## Reprise intégrale Énergie & Carburant + Amendes du Journal-de-bord dans Documents / FLEET ADMIN

Date : 2026-10 · Dépôt : `janouinfo-design/documents` (`/app`) · Entrées : rapport Phase 4B Journal (HEAD `4f007f8`, READ-ONLY) + audit Phase 4 Documents + bloc « IDENTIFIANTS JOURNAL ».
**Statut : SPÉCIFICATION UNIQUEMENT — zéro code, zéro migration, zéro déploiement. Phases 1–3 figées. Journal inchangé.**

```text
4C-0  AUDIT CIBLE DOCUMENTS            = FAIT (lecture seule, §0)
4C-1 → 4C-8                             = SPÉCIFIÉS (§1–§8)
PHASE 4C IMPLEMENTATION ORDER           = §9 (lots A→H, GO indépendant par lot)
DÉCISIONS UTILISATEUR                   = §10 — D1–D9 / D-E1 FIGÉES (2026-10) · amendements induits §10bis
CODE = 0 · DB WRITES = 0 · MIGRATION = 0 · DEPLOYMENT = 0
```

Conventions : `(J)` = preuve Journal (rapport 4B, section/fichier:ligne) · `(D)` = preuve Documents (fichier:ligne / requête read-only) · **P0** = requis avant tout dry-run de migration · **P1** = requis avant retrait des modules Journal · **P2** = exploitation/confort. Les IDs anonymisés du rapport 4B (`TENANT_1`, `VEHICLE_n`, …) ne sont jamais utilisés comme identifiants : seules les *clés réelles* seront extraites lors d'un GO distinct côté Journal (§4.14).

### ERRATUM audit Phase 4 (signalé par le Journal, confirmé)
Le détail E1–E16 de `docs/PHASE4_AUDIT_PARITE_JOURNAL_DOCUMENTS.md` donne **OK 4 / PARTIEL 6 / MANQUANT 5 / N/A 1** ; le total §6 indiquait à tort 4/7/4/1. Les statuts individuels font foi. Le fichier Phase 4 n'est **pas** modifié (règle zéro modification) ; l'erratum sera appliqué sur GO.

---

## §0 — 4C-0 AUDIT CIBLE DOCUMENTS (READ-ONLY, exécuté)

Méthode : lecture `backend/server.py`, `backend/auth.py`, `backend/storage.py`, `frontend/src/**` ; Mongo `list_collection_names / list_indexes / count_documents / find` uniquement (preview, `DB_NAME` courant). Aucune écriture.

### 0.1 Clés canoniques
| Entité | Clé canonique Documents | Format | Preuve (D) | Remarques |
|---|---|---|---|---|
| Véhicule | `vehicles.id` | UUID4 str | contrat `docs/inter-project-vehicle-contract.md` §1 ; index `(tenant_id, id)` ; 22 véhicules (16 `default`) | `vin` 6/22, `navixy_vehicle_id` 5/22, `navixy_tracker_id` 15/22 (évolutif, index), `plaque` 22/22. Resolver lecture seule `GET /api/vehicles/resolve` (`server.py:931`) : ordre `vehicle_id > vin > navixy_vehicle_id > navixy_tracker_id (warning) > plate (manual_review, jamais auto)` |
| Tenant | `tenants.id` | str libre, index unique (`default`, `client-test-e2e`, …) | 8 tenants ; `TenantCreate.id` optionnel (`:4804`) | **Clé technique stable disponible : `tenant_integrations.master_user_id` (Navixy) = `121349` pour `default`** (`tenant_integrations`, `users.navixy_master_user_id`) ↔ Journal `tenants.navixy_master_user_id = 121349` (J §16) |
| Utilisateur / rôle | `users.id`, `users.role ∈ {superadmin, admin, read_only}` | — | `auth.py`, DB 16 users | **Aucun rôle `manager` ni `driver`** ; superadmin = override tenant (`auth.py:103`) ; `read_only` → 403 sur toute écriture (`server.py:60-100`) |
| Conducteur | **AUCUNE entité** | — | grep `conducteur\|driver\|chauffeur` = 0 | seul `documents.responsable` / `vehicles.responsable` (texte libre) |
| Document | `documents.id` UUID4 ; index `(tenant_id, vehicle_id)` seul | — | 412 docs ; `storage_path` renseigné 412/412 (jamais null) ; `source ∈ {scan, null}` | `document_type` : null 150, assurance 100, permis 83, autre 38, vignette 35, facture 4, ticket_carburant 1, amende 1 |
| Transaction carburant | `fuel_transactions.id` ; index unique partiel `(tenant_id, source_document_id)` si string ; `(tenant_id, vehicle_id, date_heure desc)` | — | 1 tx réelle (Migrol) | 1 document validé = max 1 tx ; `created_from="document"` seul |
| Fichier | `files` (45 méta) + `documents.storage_path` ; `storage.py` `STORAGE_BACKEND ∈ {emergent, local}`, local `/data/storage` | — | `storage.py:18-19` | aucun fichier Journal n'est référencé |
| Audit | `audit_logs{id, action, entity, entity_id, vehicle_id, detail, user, ip, tenant_id, created_at}` ; index `(vehicle_id, created_at)` | — | 3 281 docs ; actions : create/modify/delete/download/scan/validate/… | `audit()` `server.py:785` ; lecture `GET /vehicles/{id}/history` ; **pas de lecture par `entity_id`** |

### 0.2 Modèle fuel actuel (D `server.py:1676` `_upsert_fuel_transaction`)
`id, tenant_id, vehicle_id, source_document_id, created_from="document", date, heure, date_heure, station, montant, devise, litres, prix_litre, type_carburant, energie ∈ {thermique, electrique}, energie_kwh, prix_kwh, kilometrage, carte_last4, plaque_mentionnee, validated_by, validated_at, created_at, updated_at, is_deleted`.
Absents : `fournisseur/provider`, `external_transaction_id`, `card_id`, `driver_id`, `montant_ht/tva`, `pays/adresse`, `fx_*`, `classification`, `commentaire/motif`, `dedup_key` persistée (calculée à la volée `:1660`), `legacy_*`, `warnings[]`, `locked/statement_id`.

### 0.3 Modèle amende actuel (D `server.py:1564` `_amende_to_v2`, `:1793` `doc_statut`, `:2517` `/paid`)
Document avec `document_type="amende"`, `business_category="AMENDE"`, `montant, devise, numero, date_debut (infraction), date_expiration (délai), fournisseur (autorité), plaque_mentionnee, frequence="unique", payee, paid_at, paid_by`, statut dérivé `A_PAYER / EN_RETARD / PAYEE`. Dédup métier n° ou autorité+date+montant (`:1579`). Suppression validée → 409. Absents : statut métier 10 valeurs, `driver_id`, `dossier_interne`, `type_infraction`, `frais_admin`, `paid_on` (date métier), `payment_ref`, pièces liées, lieu/réception, priorité, notes internes.

### 0.4 Possibilités actuelles « sans document source »
| Besoin | Possible aujourd'hui ? | Preuve (D) |
|---|---|---|
| Transaction carburant sans document | **Non** : seul chemin = `validate` d'un document (`:3538` → `_upsert_fuel_transaction`) ; index partiel autorise techniquement `source_document_id` null mais aucun endpoint ne le fait ; `collect_costs` ne lit jamais `fuel_transactions` → une tx sans document **n'aurait aucun coût** | `:2257`, test statique Phase 2 |
| Amende sans fichier | **Non** : création = upload (`File(...)` `:1146`) ou scan ; `storage_path` requis partout (UI `fileUrl(d.storage_path)` inconditionnel dans `DocumentsPage.jsx`, `DocFolderSection.jsx`) | — |
| Document sans fichier (générique) | **Non prévu** : `GET /api/files` 404 si absent ; aperçu/téléchargement/ré-analyse supposent des `pages` | `:848` |

**Conclusion 4C-0 → principe directeur retenu pour 4C-3 (à valider, D1) : « document sans fichier »** — toute donnée métier legacy/manuelle/importée est représentée par un *document* (`storage_path=null`, `source ∈ {legacy_import, manual, import}`) qui reste la **source unique du coût** et, pour le carburant, le `source_document_id` de la transaction. Ainsi : invariant « `collect_costs` ne lit jamais `fuel_transactions` » conservé, règle « 1 document = 1 transaction » conservée, pipeline `validate`/upsert réutilisé, aucun second moteur de coûts, 409 d'intégrité conservé. Alternative rejetée (sauf décision contraire D1) : `source_document_id` nullable + coûts lus dans `fuel_transactions` → casse l'invariant Phase 2.

### 0.5 Dictionnaire cible Documents (champs utiles au mapping) — voir §4.11 (table champ à champ Journal → Documents).

---

## §1 — 4C-1 CONDUCTEURS

1. **Objectif** : donner à Documents une entité conducteur stable, tenant-scopée, rattachable aux transactions carburant, aux amendes et aux cartes, avec provenance legacy (`drivers.id` Journal), sans jamais résoudre par nom.
2. **Fonctions Journal couvertes** : E16, A6 (partie conducteur), E14/A14 (vue chauffeur — préparée, activée en 4C-7), G4, B3. (J §11 : `drivers` 227, `id` UUID4, `user_id` 38/227, `navixy_employee_id` 12/227, 1 doublon de nom.)
3. **Situation Documents** : aucune entité ; `responsable` texte libre (0.1).
4. **Gap exact** : MANQUANT (E16/A6) ; aucune FK conducteur sur `fuel_transactions` ni `documents`.
5. **Modèle cible** : collection `drivers` + FK optionnelle `driver_id` ; affectation véhicule↔conducteur datée `driver_assignments` (nécessaire à l'identification par date, J `assignments`), **sans** moteur BLE/GPS (données Journal uniquement → fédération transitoire, 4C-6).
6. **Collections / champs** :
   - `drivers` : `id` (UUID4), `tenant_id`, `nom`, `prenom`, `email?`, `telephone?`, `matricule_interne?`, `navixy_employee_id?` (int), `user_id?` (→ `users.id`, pour la vue chauffeur), `actif` (bool), `date_debut?`, `date_fin?`, `groupe?`, `notes?`, `legacy_source?`, `legacy_id?`, `migration_version?`, `created_at/by`, `updated_at/by`, `is_deleted`.
   - `driver_assignments` : `id`, `tenant_id`, `driver_id`, `vehicle_id`, `valid_from` (date), `valid_to?`, `principal` (bool), `source ∈ {manual, legacy_import}`, `motif?`, `created_by`, `closed_by?`, `legacy_source/legacy_id?`.
   - `fuel_transactions.driver_id?`, `documents.driver_id?` (+ `documents.driver_validated_manually` bool, `document_data.identification` libre pour les infos legacy confiance/sources).
7. **Indexes** : `drivers (tenant_id, id)` unique ; `drivers (tenant_id, email)` unique partiel (email string non vide) ; `drivers (tenant_id, legacy_source, legacy_id)` unique partiel ; `driver_assignments (tenant_id, vehicle_id, valid_from)`, `(tenant_id, driver_id, valid_from)` ; `fuel_transactions (tenant_id, driver_id)` ; `documents (tenant_id, driver_id)`.
8. **Endpoints** : `GET/POST /api/drivers`, `GET/PATCH /api/drivers/{id}`, `POST /api/drivers/{id}/archive` (soft) ; `GET/POST /api/vehicles/{id}/driver-assignments`, `POST /api/driver-assignments/{id}/close` ; `GET /api/vehicles/{id}/driver-at?date=` (lecture seule, résolution par affectation à date, retourne `candidates`) ; extension `DocumentValidate` + `DocumentUpdate` + ticket/amende : `driver_id` optionnel validé (existe, même tenant) ; `GET /api/energy`, `/api/documents` : filtre `driver_id` + enrichissement `driver_nom`.
9. **Backend** : `server.py` (nouveau bloc Drivers après Vehicles ; `_upsert_fuel_transaction`, `_amende_to_v2`, `collect_deadlines` enrichissement, `list_all_documents` filtre), index au startup (`:5110+`).
10. **Frontend** : nouvelle page `DriversPage.jsx` (`/conducteurs`, nav `nav-drivers`), `DriverPicker.jsx` (combobox, recherche nom/matricule, **jamais d'auto-sélection**), onglet « Conducteur » ou champ dans `VehicleDrawer` (affectation courante + historique), `ExtractionReviewDialog` / `DocumentEditDialog` / `FineMeta` : champ conducteur, `EnergyPage`/`EnergyTab` colonne + filtre.
11. **RBAC** : admin = écriture ; read_only = lecture ; superadmin via override tenant. Rôle `driver` : **hors 4C-1** (4C-7, D6).
12. **Tenant** : toutes requêtes `tid(request)` ; validation FK `driver_id` ∈ tenant ; 404 cross-tenant.
13. **Audit** : `create/modify/archive driver`, `create/close driver_assignment`, `modify document (driver_id)` avec avant/après dans `detail`.
14. **Compatibilité legacy** : `legacy_source="journal"`, `legacy_id=<drivers.id Journal>` ; `name` legacy conservé dans `nom` si `first/last_name` absents (84/227 ont prénom/nom) ; **aucun matching par nom** (1 doublon prouvé J §11) ; `navixy_employee_id` conservé comme attribut, pas comme clé.
15. **Tests backend** (`tests/test_drivers_phase4c.py`) : CRUD, unicité email/legacy, affectation chevauchante → 409, `driver-at` date, FK cross-tenant 404, read_only 403 + DB inchangée, `driver_id` sur validate ticket/amende, filtre energy/documents, archive non destructif.
16. **Tests frontend** : page liste/création, picker sans auto-sélection, affichage dans Énergie et Documents, read_only disabled.
17. **Non-régression** : `test_energy_phase2.py` 23, `test_fines_phase3.py` 20, régression 254 inchangés (champs optionnels).
18. **Acceptation** : un plein et une amende peuvent porter un conducteur choisi explicitement ; `driver-at` renvoie `candidates` sans jamais écrire ; rien ne change si `driver_id` absent.
19. **Dépendances** : lot A (champs legacy) souhaitable, non bloquant.
20. **Risques** : confusion `responsable` (texte) vs `driver_id` → `responsable` reste texte, affiché distinctement ; données personnelles (email/téléphone) → export masqué par défaut.
21. **Ordre** : lot C (après A/B).

---

## §2 — 4C-2 CARTES CARBURANT

1. **Objectif** : référentiel cartes + affectations datées véhicule/conducteur, cycle de vie, expiration dans Échéances, contrôle carte ≠ véhicule, sans jamais importer/exporter le fingerprint HMAC Journal.
2. **Fonctions Journal** : E3, E13, (E6 `card_inactive`), G3, B7 (J §5 : 22 + 11 champs, statuts `active|suspended|expired|blocked|replaced`, affectations `vehicle|driver|pool|other` à `valid_from/valid_to`, clôture automatique de la précédente, HMAC secret `FUEL_CARD_HMAC_SECRET`).
3. **Situation Documents** : `fuel_transactions.carte_last4` seul (0.2).
4. **Gap exact** : MANQUANT E3 ; E13 N/A → requis.
5. **Modèle cible** : `fuel_cards` + `fuel_card_assignments` ; identification par `(fournisseur, last4)` avec levée d'ambiguïté manuelle (D2) ; `fuel_transactions.card_id`.
6. **Collections / champs** :
   - `fuel_cards` : `id`, `tenant_id`, `fournisseur` (ex. Migrol), `compte_fournisseur?`, `last4` (4 chiffres), `numero_masque?` (ex. `**** **** 1234`, jamais le n° complet), `external_card_id?`, `type_affectation ∈ {vehicule, conducteur, pool, autre}`, `produits_autorises[]`, `plafond_tx?/plafond_jour?/plafond_mois?` (déclaratifs), `pays_autorises[]`, `activee_le?`, `expire_le?`, `statut ∈ {active, suspendue, expiree, bloquee, remplacee}`, `remplacee_par?`, `notes?`, `legacy_source/legacy_id/migration_version?`, `created_*`, `updated_*`, `is_deleted`. **Pas de `fingerprint`** (D2).
   - `fuel_card_assignments` : `id`, `tenant_id`, `card_id`, `type ∈ {vehicule, conducteur, pool, autre}`, `vehicle_id?`, `driver_id?`, `valid_from?`, `valid_to?`, `motif?`, `created_at/by`, `closed_at/by?`, `legacy_*?`.
   - `fuel_transactions.card_id?` ; historique statut carte : via `audit_logs` (pas de `history[]` embarqué — audit central Documents).
7. **Indexes** : `fuel_cards (tenant_id, id)` unique ; `(tenant_id, fournisseur, last4)` **non unique** + détection de collision à la saisie (avertissement + confirmation) ; `(tenant_id, legacy_source, legacy_id)` unique partiel ; `fuel_card_assignments (tenant_id, card_id, valid_from)` ; `(tenant_id, vehicle_id)` ; `fuel_transactions (tenant_id, card_id, date_heure)`.
8. **Endpoints** : `GET/POST /api/fuel-cards`, `GET/PATCH /api/fuel-cards/{id}`, `POST /api/fuel-cards/{id}/status` (motif obligatoire), `GET/POST /api/fuel-cards/{id}/assignments` (clôture auto de l'affectation ouverte du même type), `POST /api/fuel-card-assignments/{id}/close`, `GET /api/fuel-cards/resolve?fournisseur=&last4=&date=` (lecture seule : `found | ambiguous | not_found` + affectation à date) ; `collect_deadlines` : item `type="carte_carburant"`, `category="Carte carburant"`, date = `expire_le`, pour statut ≠ `remplacee/bloquee` ; `validate` ticket : résolution `carte_last4` → `card_id` si **unique** pour le fournisseur/station, avertissement `CARD_VEHICLE_MISMATCH` si la carte est affectée à un autre véhicule à la date de la tx, `CARD_INACTIVE` si statut ≠ active à date — **jamais de réaffectation**.
9. **Backend** : `server.py` (bloc Fuel cards ; `_ticket_checks` `:1623` + warnings ; `collect_deadlines` `:2078` ; `_upsert_fuel_transaction`), `extraction.py` (aucun changement de prompt : `carte_last4` déjà extrait).
10. **Frontend** : `FuelCardsPage.jsx` (`/energie/cartes`, onglet dans la page Énergie), `FuelCardDialog.jsx`, `CardAssignmentDialog.jsx`, badge carte dans `EnergyPage` lignes, `CoherenceWarnings` (codes ajoutés), Échéances : `EVENT_TYPES.carte_carburant` (`lib/status.js`), Timeline/Dashboard `tabForType("carte_carburant") → "energie"`.
11. **RBAC** : admin écriture ; read_only lecture ; aucun endpoint n'expose un n° complet.
12. **Tenant** : `tid(request)` partout ; FK `vehicle_id/driver_id` ∈ tenant.
13. **Audit** : `create/modify/status card`, `create/close card_assignment` (avant/après), warnings carte persistés en anomalie (4C-6).
14. **Compatibilité legacy** : import des cartes Journal par `fournisseur + last4 + external_card_id` et `legacy_id=fuel_cards.id Journal` ; **fingerprint non migré** (secret non portable, D2) ; `history[]` Journal → `audit_logs` (`action=legacy_history`, informatif) ou `document_data.legacy` ; affectations Journal `valid_from=null` → conservées null (= depuis toujours), signalées dans le rapport de dry-run.
15. **Tests backend** (`tests/test_fuel_cards_phase4c.py`) : CRUD, statut avec motif, affectation clôture auto, `resolve` found/ambiguous/not_found/à date, échéance expiration dans `/api/deadlines`, warnings `CARD_VEHICLE_MISMATCH`/`CARD_INACTIVE` sur validate (non bloquants, véhicule inchangé), read_only 403, cross-tenant 404, collision last4 → avertissement.
16. **Tests frontend** : page cartes, affectation, badge sur transaction, échéance visible, avertissement dans la review.
17. **Non-régression** : Énergie Phase 2 (23), Échéances (`test_deadlines_v2.py`), Coûts (aucun montant sur les cartes).
18. **Acceptation** : une carte expirée apparaît dans Échéances ; un ticket dont la carte est affectée à un autre véhicule déclenche un avertissement et reste sur le véhicule choisi.
19. **Dépendances** : 4C-1 pour `driver_id` (optionnel) ; lot A (legacy).
20. **Risques** : collisions `last4` inter-fournisseurs → résolution exige le fournisseur (station OCR ≠ émetteur de la carte : résolution proposée, jamais imposée) ; plafonds déclaratifs non contrôlés (comme Journal, J §5).
21. **Ordre** : lot E.

---

## §3 — 4C-3 DONNÉES SANS JUSTIFICATIF

1. **Objectif** : représenter transactions carburant et amendes **sans fichier** (legacy 61/62 et 47/49, relevés carte, saisie manuelle motivée) sans casser les invariants coût/traçabilité.
2. **Fonctions Journal** : E2 (saisie manuelle, motif obligatoire `fuel.py:446-447`), A9 (formulaire manuel `POST /fines`), G1, G2, B4.
3. **Situation Documents** : impossible (0.4).
4. **Gap exact** : P0 bloquant migration (B4).
5. **Modèle cible (D1)** : **document sans fichier** = enregistrement `documents` avec `storage_path=null`, `pages=[]`, `source ∈ {legacy_import, manual, import}`, `document_type ∈ {ticket_carburant, amende}`, champs V2 renseignés directement (sans OCR), `extraction_status="validated"` (saisie humaine = validation), `a_verifier=false`, `justificatif_absent=true`, `motif_saisie` (obligatoire pour `manual`), `created_from` sur la transaction ∈ `{document, manual, import, legacy_import}`. Le document porte le coût ; la transaction référence `source_document_id` (non null).
6. **Collections / champs** : `documents.storage_path` nullable ; `documents.source` enum étendu ; `documents.justificatif_absent` ; `documents.motif_saisie?` ; `fuel_transactions.created_from` enum étendu ; `fuel_transactions.motif_saisie?`.
7. **Indexes** : inchangés (index partiel `source_document_id` string conservé).
8. **Endpoints** :
   - `POST /api/vehicles/{id}/fuel-transactions` (admin) : corps = champs ticket (station, date, heure, montant, devise, litres/prix_litre ou kwh/prix_kwh, type_carburant, kilometrage, carte_last4, driver_id?, `motif` obligatoire, `duplicate_override`) → crée le document sans fichier (`document_type=ticket_carburant`, `business_category` CARBURANT/ENERGIE_ELECTRIQUE confirmée dans le formulaire) puis `_upsert_fuel_transaction` (dédup 409 `kind=transaction` conservée) ; réponse identique à `validate`.
   - `POST /api/vehicles/{id}/fines` (admin) : corps = champs amende (autorité, n°, date infraction, montant/frais, devise, délai, plaque, type_infraction, driver_id?, `motif?`) → document sans fichier `document_type=amende`, `_amende_to_v2`, dédup 409 `kind=amende`.
   - `POST /api/documents/{id}/attach-file` (admin) : ajoute **a posteriori** un justificatif à un document sans fichier (upload → `storage_path`, `justificatif_absent=false`, SHA-256 dédup) ; audit.
   - `GET /api/files` inchangé (404) ; `GET /api/documents/{id}/extraction` et scan → 409 `NO_FILE` explicite ; `DELETE` : règles Phase 2/3 inchangées (409 si tx liée / amende validée).
9. **Backend** : `server.py` (`upload_file` non modifié ; nouveaux handlers ; `with_statut`/`list_all_documents` exposent `justificatif_absent` ; `collect_costs` inchangé — lit déjà `documents.montant`).
10. **Frontend** : `ManualFuelDialog.jsx` (« Plein sans justificatif », bandeau « saisie déclarative, motif obligatoire »), `ManualFineDialog.jsx` (« Nouvelle amende sans fichier »), `DocFolderSection`/`DocumentsPage` : si `!storage_path` → masquer aperçu/téléchargement/ré-analyse, badge « Sans justificatif » (`doc-nofile-<id>`), action « Joindre le justificatif » ; `EnergyPage`/`EnergyTab` : pictogramme « déclaratif ».
11. **RBAC** : admin seul (comme Journal E2) ; read_only 403 ; superadmin override.
12. **Tenant** : `tid(request)` ; véhicule ∈ tenant (404).
13. **Audit** : `create document (sans justificatif, motif=…)`, `create fuel_transaction (created_from=manual)`, `attach-file`.
14. **Compatibilité legacy** : `source=legacy_import`, `legacy_*` (lot A), `created_from=legacy_import`, `motif_saisie` = `manual_reason` Journal ; `validated_by="import"` ; `created_at` d'origine conservé.
15. **Tests backend** (`tests/test_nofile_phase4c.py`) : plein manuel → 1 doc + 1 tx + coût compté une fois (delta = montant) ; sans motif → 422 ; doublon → 409 + override ; amende manuelle → coût + échéance + statut A_PAYER ; `attach-file` → `storage_path` posé, SHA-256 dédup ; extraction sur doc sans fichier → 409 NO_FILE ; delete → 409 (tx liée / amende validée) ; read_only 403 ; cross-tenant 404 ; `collect_costs` statique toujours sans `fuel_transactions`.
16. **Tests frontend** : dialogs, badge sans justificatif, aperçu masqué, « Joindre » fonctionne.
17. **Non-régression** : 254 + Phase 2/3 ; scan/upload inchangés (`test_scan_v2_readonly.py`, `test_documents_v2.py`).
18. **Acceptation** : un plein saisi sans ticket vaut 1 coût exactement ; une amende saisie sans fichier apparaît dans Documents/Coûts/Échéances ; aucun bouton d'aperçu cassé.
19. **Dépendances** : aucune (lot A recommandé avant pour `legacy_*`).
20. **Risques** : confusion « document » / « justificatif » dans l'UI → badge systématique ; abus de saisie sans justificatif → motif obligatoire + filtre « déclaratif » + audit.
21. **Ordre** : lot B.

---

## §4 — 4C-4 IDENTITÉS / MAPPING / IDEMPOTENCE

1. **Objectif** : contrat de correspondance Journal → Documents (tenant, véhicule, conducteur, carte) et clés d'idempotence, **sans script de migration**.
2. **Fonctions Journal** : B1, B2, B5, G5 (J §15 : `vehicles.id` UUID, VIN 0/20, tracker évolutif 6 archivés, 44/49 amendes « plaque seule » ; §16 : `tenants.id`, `navixy_master_user_id=121349` ; §18 : `id` UUID stable partout, `dedup_key` non unique, `fines.id` sans index).
3. **Situation Documents** : resolver lecture seule (0.1) ; aucun champ `legacy_*` ; `tenant_integrations.master_user_id` disponible.
4. **Gap exact** : P0 (B1/B2/B5).
5. **Modèle cible** :
   - **Tenant (B2)** : `legacy_tenant_map{ legacy_source="journal", legacy_tenant_id, tenant_id, match_key="navixy_master_user_id", match_value, confirmed_by, confirmed_at }` — clé technique `Journal tenants.navixy_master_user_id ↔ Documents tenant_integrations.master_user_id` (prouvée des deux côtés pour le tenant principal : `121349`), **confirmation humaine obligatoire**, jamais par nom, jamais de fallback `default` (D3).
   - **Véhicule (B1)** : `legacy_vehicle_map{ legacy_source, legacy_vehicle_id (UUID Journal), vehicle_id (Documents), method ∈ {manual, vin, navixy_vehicle_id, tracker_history_confirmed}, candidates[], confirmed_by, confirmed_at, note }`. Construction : pour chaque véhicule Journal (export READ-ONLY futur : `id, plate, vin, navixy_tracker_id, navixy_tracker_id_archived, model`) → appel du resolver Documents (`vin` → found ; `navixy_tracker_id` → found + warning → **candidat à confirmer** ; `plate` → manual_review) → table de candidats → **validation humaine** ligne par ligne (UI lot A). Amendes « plaque seule » (44) : résolution par `plaque_mentionnee` → `manual_review` → **quarantaine jusqu'à confirmation humaine** (D4 figée : aucun objet « véhicule inconnu », `documents.vehicle_id` reste obligatoire ; non confirmée = non importée, listée dans le rapport de dry-run).
   - **Conducteur / carte** : pas de table séparée — `drivers.legacy_id`, `fuel_cards.legacy_id`.
   - **Idempotence (B5)** : `legacy_source`, `legacy_id`, `migration_version`, `legacy_payload_sha256` sur `documents`, `fuel_transactions`, `fuel_cards`, `fuel_card_assignments`, `drivers`, `driver_assignments` ; **1 enregistrement Journal → max 1 enregistrement Documents** ; rejouer = upsert par `(tenant_id, legacy_source, legacy_id)` ; `dedup_key` Journal conservée en `legacy_dedup_key` (informative, non unique) ; `dossier_number` → `dossier_interne` (référence humaine, non clé).
6. **Collections / champs** : ci-dessus + `vehicles.legacy_ids[]?` (optionnel, pour affichage).
7. **Indexes** : unique partiel `(tenant_id, legacy_source, legacy_id)` (legacy_id string) sur les 6 collections ; `legacy_vehicle_map (legacy_source, legacy_vehicle_id)` unique ; `legacy_tenant_map (legacy_source, legacy_tenant_id)` unique.
8. **Endpoints** (lecture/validation humaine, aucune migration) : `GET /api/admin/legacy/tenant-map`, `POST …/tenant-map/confirm` (superadmin) ; `GET /api/legacy/vehicle-map`, `POST /api/legacy/vehicle-map/candidates` (corps = liste véhicules Journal anonymisée ou réelle → candidats via resolver, **aucune écriture**), `POST /api/legacy/vehicle-map/{legacy_vehicle_id}/confirm` (admin, `vehicle_id` **obligatoire** — D4 : pas de branche `unknown`) ; `GET /api/legacy/dry-run-report` : **réservé** (hors 4C, GO distinct).
9. **Backend** : `server.py` (bloc Legacy ; index startup).
10. **Frontend** : `LegacyMappingPage.jsx` (`/admin/correspondances`, admin) : tableau Journal ↔ Documents, candidats + méthode + warning tracker, boutons « Confirmer » / « Véhicule inconnu » ; console superadmin : onglet correspondance tenant.
11. **RBAC** : tenant-map = superadmin ; vehicle-map = admin ; read_only lecture.
12. **Tenant** : `legacy_vehicle_map.tenant_id = tid(request)` ; un `legacy_vehicle_id` ne peut être confirmé que vers un véhicule du même tenant.
13. **Audit** : `confirm tenant_map`, `confirm vehicle_map` (avant/après, méthode).
14. **Compatibilité legacy — identifiants réels requis plus tard (GO distinct côté Journal, READ-ONLY)** : `tenants{id, navixy_master_user_id}` ; `vehicles{id, plate, vin, navixy_tracker_id, navixy_tracker_id_archived, model}` ; `drivers{id, name, first_name, last_name, email, navixy_employee_id, internal_number, active}` ; `fuel_cards{id, provider, last4, external_card_id, status, expires_at}` ; `fuel_card_assignments{id, card_id, type, vehicle_id, driver_id, valid_from, valid_to}` ; `fuel_transactions{id, …tous champs §4.11}` ; `fines{id, …§4.11}`. **Rien n'est extrait maintenant.**
15. **Tests backend** (`tests/test_legacy_identity_phase4c.py`) : unicité `(tenant, legacy_source, legacy_id)` → `DuplicateKeyError` ; rejouer un upsert legacy = 1 enregistrement ; candidats véhicule : vin → found, tracker → warning, plaque → manual_review, 0 écriture ; confirm cross-tenant 404 ; read_only 403 ; tenant-map confirm superadmin seul.
16. **Tests frontend** : page correspondances, confirmation explicite, warning tracker visible.
17. **Non-régression** : resolver (`test_vehicle_core*.py` si présent), 254.
18. **Acceptation** : aucune correspondance véhicule/tenant n'existe sans `confirmed_by` ; un import rejoué 10× produit 1 enregistrement.
19. **Dépendances** : aucune (fondation).
20. **Risques** : tentation de mapper par plaque → interdit par code (plate = manual_review) ; `default` Journal ≠ `default` Documents par simple homonymie → confirmation obligatoire.
21. **Ordre** : lot A (premier).

### 4.11 Dictionnaire de correspondance champ à champ (Journal → Documents)
**fuel_transactions (J §4) → documents (sans fichier, `ticket_carburant`) + fuel_transactions**

| Journal | Documents | Règle |
|---|---|---|
| `id` | `legacy_id` (doc et tx) | `legacy_source=journal` |
| `tenant_id` | `tenant_id` | via `legacy_tenant_map` (confirmé) |
| `external_transaction_id` | tx.`external_transaction_id` (nouveau) · doc.`numero` | unique partiel `(tenant, fournisseur, external_transaction_id)` |
| `provider` | tx.`fournisseur` (nouveau) · doc.`fournisseur` | `manuel` → null + `created_from=manual` |
| `card_id` / `card_last4` | tx.`card_id` (via `fuel_cards.legacy_id`) / `carte_last4` | — |
| `tx_datetime` (ISO, tz parfois absente) | tx.`date`, `heure`, `date_heure`, `date_heure_source`, `date_heure_tz_assumed` | D5 figée : tz-aware → conversion `Europe/Zurich` ; **naïf → interprété heure locale `Europe/Zurich` + `date_heure_tz_assumed=true`** ; original brut toujours conservé dans `date_heure_source` ; `TENANT_TZ` Journal à confirmer read-only avant dry-run (ne bloque pas le modèle) |
| `accounting_date` | tx.`date_comptable` (nouveau) | null 62/62 |
| `station_name/address/country` | tx.`station`, `station_adresse`, `pays` (nouveaux) | lat/lng : DO NOT MIGRATE (null 62/62) |
| `product_type` | tx.`type_carburant` + `energie` | `diesel→Diesel`, `essence→Essence`, `adblue→AdBlue`, `electric→Électricité (energie=electrique)`, `other→Autre` ; **AdBlue exclu du calcul de conso** (règle à ajouter dans `_conso_from_transactions`) |
| `quantity`+`unit` | `litres` (L) / `energie_kwh` (kWh) / `quantite_unite` (unit) | jamais additionnés L+kWh |
| `unit_price` | `prix_litre` / `prix_kwh` | — |
| `amount_net/vat_amount/vat_rate` | doc.`montant_ht`, `tva_chf`, `tva_taux` (nouveau) | — |
| `amount_total/currency` | doc.`montant`, `devise` · tx.`montant`, `devise` | — |
| `amount_chf/fx_*` | doc.`montant_chf`, tx.`fx_rate/fx_rate_date/fx_source/fx_status` (nouveaux) | **D7 figée** : `devise=CHF` → `montant` ; `devise≠CHF` + `montant_chf` présent → `montant_chf` ; `devise≠CHF` sans `montant_chf` → **jamais sommé comme CHF**, ligne marquée « conversion en attente » (`fx_status=pending`) et exclue du total CHF ; montant/devise d'origine conservés ; source FX Documents = décision ultérieure distincte |
| `mileage` | tx.`kilometrage` | jamais écrit sur `vehicle.kilometrage` |
| `vehicle_hint/driver_hint` | tx.`vehicle_hint`, `driver_hint` | contexte, jamais résolution auto |
| `vehicle_id` | `vehicle_id` via `legacy_vehicle_map` | non résolu → quarantaine |
| `driver_id` | `driver_id` via `drivers.legacy_id` | — |
| `trip_id` | — | DO NOT MIGRATE (pas de trajets) |
| `classification` | tx.`classification?` | valeur conservée, non exploitée |
| `match_status/score` | `fuel_transaction_matches` | RECALCULATE (4C-6) |
| `source` | tx.`created_from` ∈ `manual/import` + doc.`source=legacy_import` | — |
| `invoice_ref` | tx.`reference_facture` | — |
| `documents[]` (45 PNG tests) | — | DO NOT MIGRATE ; si réels → pièces liées (§5) |
| `issues[]` | — | DO NOT MIGRATE (ou anomalie `signalement`, D8) |
| `comment/manual_reason/forced_import_reason/amount_check_warning` | tx.`commentaire`, `motif_saisie`, `warnings[]` | — |
| `dedup_key` | tx.`legacy_dedup_key` | informatif ; `dedup_key` Documents recalculée |
| `import_job_id` | — | DO NOT MIGRATE |
| `locked/statement_id/deferred_from_statement_id` | 4C-6b | MORE EVIDENCE REQUIRED |
| `created_at/by, updated_at/by` | `created_at` (origine), `legacy_created_by`, `validated_by="import"` | — |

**fines (J §10) → documents (`amende`)**

| Journal | Documents | Règle |
|---|---|---|
| `id` / `dossier_number` | `legacy_id` / `dossier_interne` (nouveau) | dossier = référence humaine |
| `ref_fine` | `numero` | — |
| `authority` | `fournisseur` | — |
| `country/canton/city/location` | `lieu_infraction` (nouveau, structuré `{pays, canton, ville, lieu}`) | — |
| `received_at` | `date_reception` (nouveau) | — |
| `infraction_at` | `date_debut` + `heure_infraction?` | — |
| `vehicle_id` / `vehicle_plate` | `vehicle_id` via map / `plaque_mentionnee` | 44 plaque seule → quarantaine (D4) |
| `driver_id/driver_name/driver_validated_manually/confidence/sources/gps_trip_id` | `driver_id` via map ; `driver_validated_manually` ; reste → `document_data.identification` | aucune résolution par nom |
| `infraction_type` (8) | `type_infraction` (nouveau enum identique) | — |
| `infraction_details` | `notes` | — |
| `amount` / `admin_fees` / `total_amount` | `montant_amende`, `frais_admin` (nouveaux) ; `montant = total_amount` | coût = total |
| `currency` | `devise` | — |
| `due_date` | `date_expiration` | — |
| `status` (10) | `fine_status` (§5) + `payee` dérivé | table §5.5 |
| `paid_at` | `paid_on` si format date ; `paid_at` si datetime ; 0/49 renseigné | jamais `updated_at` |
| `priority` | `priorite` (nouveau) | — |
| `case_owner` / `internal_notes` | `responsable` / `notes_internes` (masquées rôle driver) | — |
| `documents[]` (2 réels, Object Storage) | pièces liées typées (§5) ; copie binaire après GO | kind mapping identique |
| `created_*` / `updated_*` | `created_at` origine, `legacy_created_by` | — |

---

## §5 — 4C-5 AMENDES

1. **Objectif** : parité complète Amendes : 10 statuts sans perte, conducteur, pièces liées typées, historique fiche, filtres, KPIs, exports, formulaire manuel, date métier de paiement.
2. **Fonctions Journal** : A1–A3, A5–A8, A11, A12, G2, G6, G12, G13 (partie manuelle), G15, G16, G18, G19, B6.
3. **Situation Documents** : 0.3 (statuts 3, paiement booléen, page Documents générique).
4. **Gap exact** : A3 PARTIAL (10→3), A5 PARTIAL (date métier/réf.), A6 MISSING (conducteur), A7/A8/A11 PARTIAL, A12 MISSING, A9 PARTIAL (manuel).
5. **Modèle cible — statuts (G6, sans perte)** : nouveau champ `documents.fine_status` (enum 10, superset) ; `payee`/`doc_statut` **dérivés** pour compatibilité Phase 3 :

| Journal | `fine_status` Documents | `payee` | Échéance active | Coût | Badge dérivé |
|---|---|---|---|---|---|
| received | `recue` | false | oui | oui | À payer / En retard |
| to_analyze | `a_analyser` | false | oui | oui | idem |
| driver_to_identify | `conducteur_a_identifier` | false | oui | oui | idem + chip |
| awaiting_driver | `en_attente_conducteur` | false | oui | oui | idem + chip |
| disputed | `contestee` | false | oui (flag `contestée`) | oui | « Contestée » |
| to_pay | `a_payer` | false | oui | oui | À payer / En retard |
| paid | `payee` | true | non | oui | Payée |
| recharged | `refacturee` | true | non | oui (+ marqueur refacturée) | Payée · refacturée |
| closed | `cloturee` | inchangé | non | oui | Clôturée |
| cancelled | `annulee` | false | non | **non** (exclue de `collect_costs`, D9) | Annulée |

   Transitions : libres (comme Journal) mais **auditées avec avant/après** ; `POST /paid` (Phase 3) ⇔ `payee` ↔ `a_payer` (compatibilité) ; `fine_status` absent sur une amende Phase 3 = `a_payer` (dérivation, aucune migration).
6. **Collections / champs** : `documents.fine_status`, `paid_on` (date métier, P1), `payment_ref?` (P2), `montant_amende`, `frais_admin`, `type_infraction`, `lieu_infraction`, `date_reception`, `heure_infraction`, `priorite`, `notes_internes`, `dossier_interne`, `driver_id`, `driver_validated_manually` ; **pièces liées** : `documents.parent_document_id?` + `piece_type ∈ {pdf, photo, courrier, contestation, preuve_paiement, libre}` — une pièce liée n'a **ni montant ni échéance** (exclue de `collect_costs`/`collect_deadlines`/conformité).
7. **Indexes** : `documents (tenant_id, business_category, fine_status)` ; `(tenant_id, parent_document_id)` ; `(tenant_id, driver_id)`.
8. **Endpoints** : `GET /api/fines` (vue dédiée : filtres `fine_status[]`, `vehicle_id`, `driver_id`, `fournisseur`, `type_infraction`, `date_from/to` (infraction), `montant_min/max`, `q` ; tri ; pagination ≤ 200 ; totaux `total/payé/ouvert` sur l'ensemble filtré) ; `POST /api/documents/{id}/fine-status {fine_status, motif?}` ; `POST /api/documents/{id}/paid` étendu `{payee, paid_on?, payment_ref?}` ; `POST /api/documents/{id}/attachments` (upload typé, `parent_document_id`) + `GET` liste + soft-delete ; `GET /api/documents/{id}/history` (audit filtré `entity_id`, A7) ; `GET /api/fines/stats` (par statut/type, top véhicules/conducteurs, 12 mois glissants réels, à payer bientôt, en retard) ; `GET /api/reports/amendes.csv|.xlsx|.pdf` (mêmes filtres, cap 10 000, audité) ; `POST /api/vehicles/{id}/fines` (4C-3).
9. **Backend** : `server.py` (`doc_statut` + `_is_fine` + `collect_deadlines` + `collect_costs` filtre `annulee` et `parent_document_id` ; nouveau bloc Fines), `reports.py` (builders CSV/XLSX/PDF amendes ; `openpyxl` présent dans l'environnement, **à ajouter à `requirements.txt` via pip freeze**), `extraction.py` (champs OCR amende : `frais_admin`, `type_infraction` suggéré — optionnel).
10. **Frontend** : `FinesPage.jsx` (`/amendes`, nav `nav-fines`) : KPIs, onglets statut, filtres, tableau, export ; `FineDrawer.jsx`/section fiche : champs, conducteur (picker), statut (select 10 + motif), paiement (date métier + réf.), pièces liées (upload typé, liste), historique ; `DocStatutBadge` : nouveaux badges `CONTESTEE`, `CLOTUREE`, `ANNULEE`, chips statut métier ; `FineMeta.jsx` étendu ; Dashboard : KPI « Amendes à payer / en retard » (depuis `/api/fines/stats`).
11. **RBAC** : admin écriture ; read_only lecture (sans `notes_internes` ? → visibles aux admins seulement, D6) ; superadmin override.
12. **Tenant** : `tid(request)` ; pièces liées ∈ même tenant et même véhicule que le parent.
13. **Audit** : `fine_status` avant/après + motif ; `paid` avec `paid_on/payment_ref` ; `attachment add/remove` ; `driver_id` avant/après — chaque action **distincte** (supérieur à Journal, A15).
14. **Compatibilité legacy** : table §4.11 ; `fine_status` mappé 1:1 ; amendes Phase 3 existantes : dérivation sans écriture.
15. **Tests backend** (`tests/test_fines_phase4c.py`) : 10 statuts → échéance/coût/badge attendus ; `annulee` exclue des coûts ; `refacturee` payée + marqueur ; transition auditée ; `paid_on` conservé ≠ `paid_at` ; pièce liée sans coût/échéance et supprimable (soft) ; `history` par entité ; filtres/tri/pagination/totaux ; exports 3 formats (en-têtes, lignes = filtre) ; read_only 403 (status, paid, attachments) ; cross-tenant 404 ; Phase 3 : `/paid` continue de fonctionner, amende sans `fine_status` = `a_payer`.
16. **Tests frontend** : page `/amendes`, changement de statut avec motif, paiement avec date, pièce jointe, historique, export déclenché, KPIs Dashboard.
17. **Non-régression** : `test_fines_phase3.py` 20 **inchangés**, `test_deadlines_v2.py`, `test_costs_v2.py`, 254.
18. **Acceptation** : chaque amende Journal (10 statuts) est représentable sans perte ; coût compté une fois ; `annulee` hors coûts ; export filtré identique à la liste.
19. **Dépendances** : 4C-1 (conducteur), 4C-3 (formulaire manuel), lot A (legacy).
20. **Risques** : double logique statut (`fine_status` vs `payee`) → `payee` **toujours dérivé** (fonction unique) ; pièces liées comptées en conformité → exclusion explicite par `parent_document_id`.
21. **Ordre** : lot D.

---

## §6 — 4C-6 FUEL MÉTIER

### 6a — Imports, rattachement véhicule, anomalies
1. **Objectif** : imports CSV/XLSX avec mapping générique, preview, doublons, forçage motivé ; rattachement tx↔véhicule scoré et explicable ; anomalies persistées avec décision.
2. **Fonctions Journal** : E5(a), E6, E7, E8, E11, G7, G8, G10 (J §6 : CSV/XLSX, mapping libre + auto-suggestion FR/DE/EN, ≤30 MB/20 000 lignes, statuts ligne `ok|invalid|duplicate|unknown_card|amount_mismatch`, confirm + force ; §7 : règles 50/40/30/20/15, seuils 90/70, statuts `auto_matched|matched_review|unmatched|manual` ; §8 : `tank_overflow`, `card_inactive`, `double_fill`, `amount_unusual`).
3. **Situation Documents** : aucun import ; avertissements non persistés (`_ticket_checks` `:1623`) ; dédup à la volée.
4. **Gap exact** : E7/E5 MISSING, E6 PARTIAL.
5. **Modèle cible** : pipeline `job → mapping → preview → confirm/force` ; chaque ligne confirmée = **document sans fichier + transaction** (4C-3) via `_upsert_fuel_transaction` ; matching **sans trajets ni géolocalisation** (Documents n'a pas `trips`) : règles disponibles = carte affectée à date (50), `vehicle_id` legacy/colonne UUID (100 = direct), `vehicle_hint` plaque → **manual_review uniquement** (0 point auto, candidats listés), conducteur affecté à date (20), carburant compatible (+10/−40), carte inactive (−50) ; seuils tenant `score_auto=90`, `score_review=70` ; `fuel_anomalies` persistées.
6. **Collections / champs** : `fuel_import_jobs{id, tenant_id, fournisseur, filename, sha256, colonnes[], mapping{}, status ∈ {mapping, preview, confirmed}, counts{}, created_*, confirmed_at, imported_count}` ; `fuel_import_rows{id, tenant_id, job_id, row_index, raw{}, normalized{}, status ∈ {pending, ok, invalid, duplicate, unknown_card, amount_mismatch, unknown_vehicle}, errors[], imported, transaction_id, document_id, forced_reason?}` ; `fuel_import_mappings{id, tenant_id, fournisseur, mapping{}, created_*}` ; `fuel_transaction_matches{id, tenant_id, transaction_id (1-1), score, status, method, breakdown[{rule,label,points}], candidates[{vehicle_id, partial_score}], computed_at, history[], decided_by/at, reason}` ; `fuel_anomalies{id, tenant_id, transaction_id, type ∈ {depassement_reservoir, carte_inactive, double_plein, montant_inhabituel, incoherence_montant, odometre_incoherent, plaque_differente, carte_vehicule_different}, severity ∈ {critical, warning}, status ∈ {ouverte, justifiee, corrigee, rejetee}, related_transaction_id?, vehicle_id?, card_id?, explanation, context{}, detected_at, decided_by/at, decision_reason}` ; `tenant_settings.fuel{score_auto, score_review, double_window_min, amount_multiplier, amount_min_history, tank_tolerance_pct}` ; `fuel_transactions.external_transaction_id, fournisseur, card_id, dedup_key, import_job_id, match_status, match_score`.
7. **Indexes** : `fuel_import_jobs (tenant_id, sha256)` (ré-import même fichier → avertissement) ; `fuel_import_rows (tenant_id, job_id, row_index)` unique ; `fuel_transactions (tenant_id, fournisseur, external_transaction_id)` unique partiel ; `(tenant_id, dedup_key)` non unique ; `fuel_transaction_matches (tenant_id, transaction_id)` unique ; `fuel_anomalies (tenant_id, transaction_id, type)` unique ; `(tenant_id, status, severity)`.
8. **Endpoints** : `GET /api/fuel/import-fields` ; `POST /api/fuel/imports` (multipart, CSV/XLSX, ≤30 MB, ≤20 000 lignes, sniff délimiteur/encodage) ; `POST /api/fuel/imports/{job}/mapping` (min `tx_datetime` + `amount_total`) → normalisation + statuts ; `GET …/rows?status=` ; `POST …/confirm` (importe `ok` + `amount_mismatch` + `unknown_card`, met de côté `duplicate/invalid/unknown_vehicle`) ; `POST …/rows/{row}/force {reason}` ; `GET /api/fuel/imports` ; `PATCH /api/fuel-transactions/{id}/match {vehicle_id, reason}` (manuel motivé, **réaffectation explicite** = réponse à E4) ; `POST /api/fuel/match/run` ; `GET /api/fuel/anomalies?status&severity&type` ; `POST /api/fuel/anomalies/scan` ; `POST /api/fuel/anomalies/{id}/decide {decision ∈ justify|correct|reject, reason}` ; `PATCH /api/tenant-settings/fuel`.
9. **Backend** : nouveaux modules `backend/fuel_import.py`, `backend/fuel_matching.py`, `backend/fuel_anomalies.py` (**vérifier le `Dockerfile` : copie explicite des modules**, dead-end connu) ; `server.py` (routes + hooks dans `validate`/manuel/import) ; dépendance `openpyxl` (présent env, à figer dans `requirements.txt`).
10. **Frontend** : `FuelImportsPage.jsx` (upload, mapping colonnes avec suggestions, preview par statut, confirmer/forcer), `FuelAnomaliesPage.jsx` (liste, filtres, décision motivée), `MatchDialog.jsx` (explication `breakdown`, candidats, réaffectation motivée), sous-navigation Énergie (Transactions · Cartes · Imports · Anomalies · Rapprochement · Décomptes).
11. **RBAC** : import/settings = admin ; match manuel/décision anomalie = admin (pas de `manager` dans Documents, D6) ; read_only lecture.
12. **Tenant** : jobs/rows/matches/anomalies `tid(request)` ; véhicule/carte/conducteur ∈ tenant.
13. **Audit** : `import upload/mapping/confirm/force` (mapping audité — supérieur à Journal), `match manual/run`, `anomaly create/scan/decide`, `settings fuel`.
14. **Compatibilité legacy** : jobs Journal DO NOT MIGRATE ; matches RECALCULATE ; anomalies RECALCULATE + décisions `justified` réimportées si valeur (D8).
15. **Tests backend** (`tests/test_fuel_import_phase4c.py`, `test_fuel_matching_phase4c.py`, `test_fuel_anomalies_phase4c.py`) : CSV `;` / `,` / tab, XLSX, encodages ; mapping minimal 422 ; statuts ligne ; doublon ext_id / dedup_key / intra-fichier ; confirm → n docs sans fichier + n tx + coûts = Σ montants (une fois) ; force avec motif ; ré-import même fichier → avertissement, 0 doublon ; matching : carte à date → auto, plaque → review (jamais auto), score/breakdown, manuel motivé, history ; anomalies : 4 règles + muettes sans capacité, unique `(tx,type)`, décision auditée, jamais recréée ; read_only 403 ; cross-tenant 404.
16. **Tests frontend** : import bout en bout sur fixture 7 lignes (reprendre le cas Journal : ok 3, duplicate 1, unknown_card 1, invalid 1, amount_mismatch 1), anomalies, réaffectation.
17. **Non-régression** : Phase 2 (23), conso CAN prioritaire, 254.
18. **Acceptation** : import rejoué = 0 duplication ; aucune transaction importée sans coût ; aucune réaffectation sans motif.
19. **Dépendances** : 4C-2 (cartes), 4C-3 (doc sans fichier), 4C-1 (conducteur), lot A.
20. **Risques** : volume (20 000 lignes) → traitement par lots + statut job ; mémoire XLSX → `read_only=True` openpyxl ; plaque dans l'import → tentation d'auto-match → interdit par code.
21. **Ordre** : lot F.

### 6b — Rapprochement achats ↔ consommation, décomptes périodiques, exports énergie
1. **Objectif** : comparer les achats (L/kWh/CHF) à la consommation réelle, produire des décomptes mensuels clôturables/verrouillants, exporter.
2. **Fonctions Journal** : E5(b), E9, E10, E12, G9, G11, G14 (J : `energy.py:224-370` statuts `OK|A_CONTROLER|INDICATIF|IMPOSSIBLE` ; `fuel_statements` `draft/to_review/validated/closed`, versions, `locked`, tardives reportées ; exports PDF/XLSX/CSV).
3. **Situation Documents** : conso réelle CAN (Navixy) + tickets + ASTRA ; aucun rapprochement périodique ; `couts.csv` totaux par véhicule.
4. **Gap exact** : E5(b) MISSING, E10 MISSING, E9 PARTIAL, G14 NON ÉVALUÉ.
5. **Modèle cible** : **source de consommation = données Documents** (CAN Navixy `fuel_snapshots`/`conso_reelle_*`, odomètre, tickets) — **aucun appel au module Energy externe** ; si une mesure du module Energy est requise, fédération transitoire lecture seule via Journal (`/api/service/v1/**`, contrat à écrire) — D-E1 ; décomptes = instantanés versionnés des transactions d'une période.
6. **Collections / champs** : `fuel_reconciliations{id, tenant_id, vehicle_id, period_from, period_to, achats{litres, kwh, chf}, consommation{source ∈ can|tickets|unavailable, litres_estimes, km}, ecart_l, ecart_pct, status ∈ {OK, A_CONTROLER, INDICATIF, IMPOSSIBLE}, computed_at}` ; `fuel_statements{id, tenant_id, number, type ∈ {regulier, correctif}, scope, period_month, date_from, date_to, status ∈ {brouillon, a_verifier, valide, cloture}, version, versions[], totals{}, created_*, closed_*}` ; `fuel_statement_lines{tenant_id, statement_id, version, transaction_id, document_id, montant_chf, litres, kwh, blockers[]}` ; `fuel_transactions.locked, statement_id, deferred_from_statement_id` ; `tenant_settings.fuel.reconciliation{threshold_pct, threshold_l}`.
7. **Indexes** : `fuel_reconciliations (tenant_id, vehicle_id, period_from, period_to)` unique ; `fuel_statements (tenant_id, number)` unique ; `fuel_statement_lines (tenant_id, statement_id, version)`.
8. **Endpoints** : `GET /api/energy/reconciliation?period=` (calcul, cache 60 s), `POST …/reconciliation/generate` (persiste) ; `GET/POST /api/fuel/statements`, `POST …/{id}/refresh|validate|close` (clôture → `locked=true` sur les tx incluses ; tx tardive → `deferred` vers le décompte suivant), `GET …/{id}/export?fmt=pdf|xlsx|csv` ; `GET /api/reports/energie.csv|.xlsx` (lignes transactions filtrées : véhicule, période, énergie, carte, conducteur, station) ; `GET /api/energy/overview?period=` (M vs M-1 `delta_pct`, par énergie, coût/km si km disponible).
9. **Backend** : `backend/fuel_statements.py` (nouveau), `reports.py` (builders), `server.py` ; **`collect_costs` inchangé** (les décomptes n'alimentent pas les coûts : le document reste la source).
10. **Frontend** : `EnergyReconciliationPage.jsx`, `FuelStatementsPage.jsx`, `EnergyPage` : filtres période/énergie/carte/conducteur/station/texte, pagination, graphique mensuel (recharts), KPI coût/km, bouton export.
11. **RBAC** : clôture/validation = admin ; lecture read_only ; exports audités.
12. **Tenant** : `tid(request)`.
13. **Audit** : `statement create/refresh/validate/close`, `reconciliation generate`, `export` (sha256 du fichier).
14. **Compatibilité legacy** : décomptes Journal MORE EVIDENCE REQUIRED (2 brouillons tests) → non migrés par défaut ; `locked/deferred` Journal reconstruits uniquement si décomptes réels existent.
15. **Tests backend** : rapprochement OK/A_CONTROLER/INDICATIF/IMPOSSIBLE selon données ; CAN prioritaire, tickets sinon, `unavailable` jamais 0 ; décompte : création, lignes figées par version, clôture verrouille (modification tx verrouillée → 409), tardive reportée, export 3 formats, `energie.csv` = filtre ; coûts inchangés après clôture ; read_only 403 ; cross-tenant 404.
16. **Tests frontend** : pages rapprochement/décomptes, export, filtres période.
17. **Non-régression** : Phase 2 (23), Coûts, 254.
18. **Acceptation** : un décompte clôturé est immuable ; aucun total de décompte n'entre dans Coûts ; export énergie ligne à ligne disponible.
19. **Dépendances** : 6a, 4C-2, 4C-1.
20. **Risques** : double « consommation réelle » (module Energy vs Documents) → décision D-E1 ; fuseau période (`Europe/Zurich`, D5).
21. **Ordre** : lot G.

---

## §7 — 4C-7 UI / EXPLOITATION

1. **Objectif** : filtres complets, pagination/périodes, reporting, vue chauffeur, vue amendes dédiée (déjà en §5), navigation Énergie structurée.
2. **Fonctions Journal** : E8, E9, E11, A1, A2, A11, A14/E14 (driver), G17, G18, G20.
3. **Situation Documents** : `EnergyPage` filtre véhicule seul, 10 dernières tx dans l'onglet, pas de période UI ; pas de rôle `driver`.
4. **Gap exact** : PARTIAL (E8/E9/E11/A2/A11), NON VÉRIFIÉ (G20).
5. **Modèle cible** : (a) Énergie : sous-navigation (Transactions · Cartes · Imports · Anomalies · Rapprochement · Décomptes), filtres période/énergie/carte/conducteur/station/texte/anomalie, pagination serveur (`limit/offset`, ≤200), graphique mensuel, KPI coût/km ; (b) Amendes : §5 ; (c) **Vue chauffeur** : nouveau rôle `users.role="driver"` + `users.driver_id` → `GET /api/me/fuel-transactions`, `GET /api/me/fines` (sans `notes_internes`), `POST /api/me/fuel-transactions/{id}/attach-file` (justificatif), toute autre route → 403 ; pages `/mes-pleins`, `/mes-amendes`.
6. **Collections / champs** : `users.role` enum + `users.driver_id?` ; aucune autre.
7. **Indexes** : `fuel_transactions (tenant_id, driver_id, date_heure)`.
8. **Endpoints** : `GET /api/energy` étendu (`limit/offset`, filtres, `total`) ; `GET /api/vehicles/{id}/energy?limit=&offset=` ; `GET /api/energy/overview` (6b) ; `/api/me/**` (driver).
9. **Backend** : `server.py` ; **`auth.py` pour le rôle `driver` → toute modification d'auth passe obligatoirement par `integration_expert` au moment de l'implémentation** (règle projet) ; middleware read_only inchangé.
10. **Frontend** : `EnergyPage` (sous-nav, filtres, pagination, graphique), `EnergyTab` (« voir tout », période), `DriverFuelPage.jsx`, `DriverFinesPage.jsx`, `Layout.jsx` (nav conditionnelle par rôle).
11. **RBAC** : matrice cible : superadmin (override) · admin (tout) · read_only (lecture, 403 écriture) · **driver** (ses enregistrements uniquement : `driver_id = users.driver_id`, lecture + justificatif) ; pas de rôle `manager` (D6 : à créer ou non).
12. **Tenant** : `tid(request)` ; driver scoping par `driver_id` **et** tenant.
13. **Audit** : `attach-file` chauffeur ; connexion driver (existant).
14. **Compatibilité legacy** : `drivers.user_id` Journal (38/227) → lien `users.driver_id` si l'utilisateur existe côté Documents (sinon rien).
15. **Tests backend** : pagination/filtres `/api/energy` ; driver : ses tx/amendes seulement, 403 ailleurs, `notes_internes` absentes, cross-driver 404 ; read_only inchangé.
16. **Tests frontend** : sous-navigation, filtres, pagination, pages chauffeur, nav par rôle, responsive 390 px.
17. **Non-régression** : auth (`test_security_lot2.py`, `test_readonly_*`), Phase 2/3, 254.
18. **Acceptation** : un chauffeur ne voit que ses données ; un admin filtre l'énergie par période/carte/conducteur avec pagination.
19. **Dépendances** : 4C-1, 4C-2, 4C-5, 6a/6b.
20. **Risques** : rôle `driver` = surface d'attaque → tests RBAC exhaustifs + revue auth ; nav surchargée → sous-navigation.
21. **Ordre** : lot H (dernier).

---

## §8 — 4C-8 PLAN DE TESTS (consolidé)

| Domaine | Fichiers (nouveaux) | Couverture minimale | Baseline à conserver |
|---|---|---|---|
| Non-régression | existants | `test_business_data` 17 · `test_energy_phase2` 23 · `test_fines_phase3` 20 · régression 254 PASS / 0 FAIL · `yarn build` 0 warning · it.37/38/39 | **aucun test désactivé ou modifié** |
| Sécurité | tous lots | cross-tenant 404 (documents, tx, cartes, conducteurs, imports, matches, anomalies, décomptes, maps) ; read_only 403 + DB inchangée ; admin témoin ; driver : scope strict, 403 ailleurs, `notes_internes` masquées ; superadmin override tenant | `test_security_lot2`, `test_multitenant` |
| Identité | `test_legacy_identity_phase4c` | tenant-map par clé technique confirmée ; vehicle-map : vin found / tracker warning / plaque manual_review ; aucune résolution auto plaque/tracker/nom ; conducteur UUID | resolver |
| Legacy | `test_nofile_phase4c`, `test_legacy_identity_phase4c` | fuel sans fichier = doc + tx + coût ×1 ; amende sans fichier = coût + échéance ; `(tenant, legacy_source, legacy_id)` unique ; rejouer 2× = 1 enregistrement | Phase 2 invariant statique |
| Fuel | `test_fuel_cards_`, `test_fuel_import_`, `test_fuel_matching_`, `test_fuel_anomalies_`, `test_fuel_statements_phase4c` | cartes/affectations datées/expiration ; import 7 lignes (statuts), confirm/force, ré-import 0 doublon ; matching explicable, plaque jamais auto ; anomalies 4+ règles, décision ; rapprochement statuts ; décompte verrouillant ; **anti-double-counting** : Σ coûts = Σ `documents.montant` (jamais `fuel_transactions`) | Migrol 74.17 ×1 |
| Amendes | `test_fines_phase4c` | 10 statuts ↔ échéance/coût/badge ; `annulee` hors coûts ; `paid_on` ≠ `paid_at` ; pièces liées sans coût ; conducteur ; historique ; exports CSV/XLSX/PDF = filtre ; `/paid` Phase 3 intact | amende 120.00 ×1 |
| Frontend | testing agent it.40+ par lot | pages nouvelles, dialogs, badges sans justificatif, réaffectation motivée, exports, responsive 390 px, console 0 erreur (hors 403/409 volontaires) | it.39 |

Critère global de clôture Phase 4C : **31 fonctions = NONE** (Final gap) sauf celles explicitement déclarées hors périmètre par décision utilisateur (§10), puis GO distinct pour le dry-run (hors 4C).

---

## §9 — PHASE 4C IMPLEMENTATION ORDER (GO indépendant par lot)

| Lot | Contenu | Spéc. | Priorité | Dépend de | Taille | Livrables de preuve |
|---|---|---|---|---|---|---|
| **A** | Fondations identité/idempotence : champs `legacy_*`, index uniques, `legacy_tenant_map`, `legacy_vehicle_map`, candidats via resolver, UI confirmation | §4 | P0 | — | S | pytest + it.40 |
| **B** | Document sans fichier : plein manuel, amende manuelle, `attach-file`, UI badges/masquage | §3 | P0 | (A) | M | pytest + preuve coût ×1 |
| **C** | Conducteurs : `drivers`, `driver_assignments`, FK, picker, filtres | §1 | P0 | A, B | M | pytest + it. |
| **D** | Amendes : `fine_status` 10, `paid_on/payment_ref`, pièces liées, historique, page `/amendes`, KPIs, exports | §5 | P0 (statuts) / P1 (exports, KPIs) | B, C | L | pytest + it. + Phase 3 intacte |
| **E** | Cartes carburant : référentiel, affectations, expiration, avertissements carte | §2 | P0 (si cartes réelles) | A, C | M | pytest + it. |
| **F** | Fuel 6a : imports CSV/XLSX, matching explicable, anomalies persistées, réaffectation motivée | §6a | P1 | B, C, E | L | pytest (fixture 7 lignes) + it. |
| **G** | Fuel 6b : rapprochement achats↔conso, décomptes verrouillants, exports énergie, overview M/M-1 | §6b | P1 | F | L | pytest + it. |
| **H** | UI/exploitation : filtres/pagination/périodes, graphique, rôle `driver` + vues « mes… » | §7 | P1 (filtres) / P2 (driver) | C, D, F, G | M | pytest RBAC + it. |
| — | **Dry-run migration** (hors 4C) : extraction clés réelles Journal (GO distinct), rapport d'écarts, 0 écriture | — | après parité | A→H | — | rapport |

Règles communes à tous les lots : préfixe `/api` · `REACT_APP_BACKEND_URL` · `tid(request)` serveur · read_only 403 backend · **RBAC centralisé (`require_roles`, matrice §10bis) dès le lot A ; rôles `manager`/`driver` activés au lot H via `integration_expert`** · `data-testid` sur tout élément interactif/critique · aucun ObjectId exposé · `datetime.now(timezone.utc)` · `collect_costs` ne lit jamais `fuel_transactions` · aucune réaffectation automatique véhicule/conducteur · Phases 1–3 figées (tests existants intacts) · `requirements.txt` via `pip freeze` après installation · Dockerfile vérifié pour tout nouveau module backend · aucune donnée factice injectée en production.

---

## §10 — DÉCISIONS UTILISATEUR — FIGÉES (2026-10) · D1–D9 / D-E1 = DÉCIDÉES

Ces décisions figent **uniquement la spécification**. Aucun GO de lot n'en découle. Détail des options/preuves/risques : livré dans le chat (session 2026-10), repris ici sous forme figée.

| ID | Décision | Choix figé | Règles figées |
|---|---|---|---|
| **D1** | Enregistrements sans justificatif | **(a) document sans fichier** | (1) `source ∈ {legacy_import, manual}` · (2) `storage_path`/métadonnées fichier null/absents · (3) 1 document = max 1 `fuel_transaction` · (4) UI explicite « Aucun justificatif » · (5) endpoints fichier gèrent l'absence de binaire sans erreur technique · (6) création/modification auditées · (7) idempotence `tenant_id + legacy_source + legacy_id`. `source_document_id` **non** nullable en fonctionnement normal. Invariant : `collect_costs` lit le document ; `fuel_transactions` jamais resommé. |
| **D2** | Identité des cartes sans fingerprint HMAC | **(a)** | `(fournisseur, last4)` **non unique** + désambiguïsation manuelle ; aucun fingerprint Journal migré ; HMAC propre à Documents = lot ultérieur éventuel (hors 4C) pour les nouvelles cartes. |
| **D3** | Correspondance tenant | **(a)** | Mapping uniquement par clé technique Journal `tenants.navixy_master_user_id` ↔ Documents `tenant_integrations.master_user_id`, **confirmation superadmin obligatoire** ; aucun mapping par nom ; aucun fallback `default` implicite ; tenant sans clé technique = **non migré automatiquement** (ligne du rapport de dry-run). |
| **D4** | 44 amendes « plaque seule » | **(a) quarantaine** | Quarantaine jusqu'à confirmation humaine du véhicule ; `documents.vehicle_id` reste obligatoire ; aucun objet permanent « véhicule inconnu » ; plaque = indice, jamais jointure automatique. |
| **D5** | Fuseau des dates legacy | **(a) `Europe/Zurich`** | tz-aware → conversion `Europe/Zurich` ; datetime Journal **naïf** → heure locale `Europe/Zurich` supposée + `date_heure_tz_assumed=true` ; `date_heure_source` = valeur brute toujours conservée ; `TENANT_TZ` Journal à confirmer read-only **avant dry-run** (ne bloque pas le modèle). |
| **D6** | Rôles | **D6.1 driver = OUI · D6.2 manager = OUI · D6.3 notes_internes = admin uniquement** | Modèle cible 5 rôles : `superadmin` (plateforme / override tenant) · `admin` (administration complète du tenant) · `manager` (exploitation métier, **sans** imports / cartes / paramètres / suppressions) · `read_only` (consultation) · `driver` (uniquement ses propres données). `notes_internes` masquées à `read_only` et `driver` (filtrage **serveur**). Matrice : §10bis. Toute modification `auth.py` → `integration_expert`. |
| **D7** | Devises ≠ CHF dans Coûts | **(a)** | `devise=CHF` → `montant` ; `devise≠CHF` + `montant_chf` → `montant_chf` ; `devise≠CHF` sans `montant_chf` → **jamais sommé comme CHF**, marqué « conversion en attente », exclu du total CHF ; montant/devise d'origine conservés ; source FX Documents = décision ultérieure distincte. |
| **D8** | Anomalies / décisions / `issues[]` | **D8.a recalculer · D8.b réimport conditionnel · D8.c ne pas migrer** | Anomalies **recalculées** par Documents ; décision legacy `justified` réimportée **uniquement si** anomalie re-détectée par Documents, même transaction legacy, même type, donnée réelle (non test) ; `issues[]` non migrées — commentaire métier réel → `fuel_transactions.commentaire`, aucun sous-système « signalements ». |
| **D9** | Amende `annulee` | **(a)** | Exclue de `collect_costs` **et** des échéances actives ; montant et document conservés ; badge « Annulée » ; transition auditée avec motif. `cloturee` reste comptée ; `refacturee` reste comptée avec son marqueur (table §5.5). |
| **D-E1** | Consommation réelle canonique | **(a) Documents** | Priorité `CAN mesuré > fuel_transactions/tickets` (Phase 2 figée) ; ASTRA = référence officielle/comparative ; rapprochement achats↔consommation calculé dans Documents ; **aucune dépendance permanente au Journal/Energy** ; fédération éventuelle = transitoire explicite, lecture seule, **avec date de fin** ; contrat `/api/service/v1/**` non écrit par défaut. |

### §10bis — Amendements de la spécification induits par les décisions

1. **D4 → §4.5 / §4.8** : `confirm` exige `vehicle_id` ; aucune branche `unknown` ; état « non confirmé » = quarantaine (hors `documents`). Lot A : UI sans bouton « Véhicule inconnu ».
2. **D5 → §3 / §4.11 / §6a** : champ `fuel_transactions.date_heure_tz_assumed` (bool, défaut false) ; import CSV/XLSX (lot F) : colonnes date sans fuseau = heure locale `Europe/Zurich` ; `_conso_from_transactions`, `double_plein` et périodes de décompte (lot G) opèrent en `Europe/Zurich`.
3. **D6 → RBAC cible (remplace les lignes « RBAC » des §1–§7)** — `(J)` = sémantique prouvée Journal (4B §13) · `(P)` = proposition Documents, à confirmer au GO du lot concerné :

| Capacité | superadmin | admin | manager | read_only | driver |
|---|---|---|---|---|---|
| Lecture tenant (toutes pages) | ✔ override | ✔ | ✔ (J) | ✔ (J) | ✘ — ses données via `/api/me/**` (J) |
| Phases 1–3 : upload/scan/validate/édition documents & fiche véhicule | ✔ | ✔ | ✔ (P) | ✘ | ✘ |
| Suppression (documents, archive conducteur, soft-delete pièces) | ✔ | ✔ | ✘ (J : `ROLES_DELETE=admin`) | ✘ | ✘ |
| Plein / amende sans justificatif (4C-3) | ✔ | ✔ | amende ✔ (J) · plein ✔ (P — Journal : admin seul) | ✘ | ✘ |
| Amendes : statut, paiement, conducteur, pièces (4C-5) | ✔ | ✔ | ✔ (J) | ✘ | ✘ |
| `notes_internes` (lecture) | ✔ | ✔ | ✔ (P) | ✘ (D6.3) | ✘ (J) |
| Conducteurs : référentiel (4C-1) | ✔ | ✔ | ✘ (P) | ✘ | ✘ |
| Affectations véhicule↔conducteur (4C-1) | ✔ | ✔ | ✔ (P) | ✘ | ✘ |
| Cartes : création/édition/statut/affectations (4C-2) | ✔ | ✔ | ✘ (J) | ✘ | ✘ |
| Imports CSV/XLSX, mappings (4C-6a) | ✔ | ✔ | ✘ (J) | ✘ | ✘ |
| Match manuel motivé, run, décisions anomalies (4C-6a) | ✔ | ✔ | ✔ (J : `MATCH_ROLES`) | ✘ | ✘ |
| Paramètres tenant (`tenant-settings.fuel`, intégrations) | ✔ | ✔ | ✘ (J) | ✘ | ✘ |
| Rapprochement (lecture/generate), décomptes : création/refresh (4C-6b) | ✔ | ✔ | ✔ (P) | lecture | ✘ |
| Décomptes : validate/close (verrou) (4C-6b) | ✔ | ✔ | ✘ (P) | ✘ | ✘ |
| Exports CSV/XLSX/PDF | ✔ | ✔ | ✔ (P) | ✔ (P) | ses données (P) |
| Correspondances legacy véhicule (lot A) | ✔ | ✔ | ✘ (P) | lecture | ✘ |
| Correspondance tenant (lot A) | ✔ seul | ✘ | ✘ | ✘ | ✘ |
| Justificatif sur ses propres transactions | — | — | — | — | ✔ (J) |

   Implémentation : helper central `require_roles(*roles)` dès le **lot A** ; matrice limitée à `superadmin/admin/read_only` jusqu'au lot H (middleware read_only Phase 1–3 inchangé) ; `manager` et `driver` **créés au lot H** (`users.role` enum + `users.driver_id`, `auth.py` via `integration_expert`) → aucune reprise des endpoints, seule la matrice s'étend. Phases 1–3 : `manager` = écriture sauf DELETE → **une garde ajoutée** sur les DELETE existants au lot H (tests existants inchangés : admin). Migration des comptes Journal (hors 4C, dry-run) : `lecture_seule → read_only`, `manager → manager`, `driver → driver` (si `drivers.user_id` résolu), `admin → admin`.
4. **D7 → §5.9 / §6b** : `collect_costs` = une seule modification (3 cas) ; réponse enrichie `pending_fx[]` (lignes exclues, pour affichage « conversion en attente ») ; totaux de décomptes (lot G) suivent la même règle ; tests Phase 1 CHF inchangés.
5. **D8 → §6a.14** : réimport des décisions = étape du dry-run (pas du lot F) ; conditions figées ; `issues[]` → `commentaire` uniquement si réel.
6. **D9 → §5.5 / §5.9** : `collect_costs` et `collect_deadlines` filtrent `fine_status="annulee"` ; amende Phase 3 sans `fine_status` = `a_payer` (dérivation, aucune migration) ; `/paid` Phase 3 intact.
7. **D-E1 → §6b.5** : aucune route de fédération Journal/Energy spécifiée dans 4C ; si un besoin transitoire est exprimé → spécification distincte (contrat, date de fin, lecture seule) avant tout GO.
8. **D2 / D3** : §2 et §4 déjà conformes ; précision D3 : rapport de dry-run liste les tenants Journal sans clé technique comme « non migrés ».

---

## RAPPORT FINAL

```text
PHASE 4C — SPECIFICATION

4C-0 AUDIT CIBLE DOCUMENTS   = DONE (read-only ; clés : vehicles.id UUID, tenants.id + master_user_id 121349, aucun conducteur, aucun doc sans fichier)
4C-1 CONDUCTEURS             = SPECIFIED (lot C)
4C-2 CARTES CARBURANT        = SPECIFIED (lot E)
4C-3 SANS JUSTIFICATIF       = SPECIFIED (lot B, principe « document sans fichier », D1)
4C-4 IDENTITÉS / IDEMPOTENCE = SPECIFIED (lot A ; clés réelles Journal listées §4.14 — non extraites)
4C-5 AMENDES                 = SPECIFIED (lot D ; 10 statuts sans perte)
4C-6 FUEL MÉTIER             = SPECIFIED (lots F, G)
4C-7 UI / EXPLOITATION       = SPECIFIED (lot H)
4C-8 PLAN DE TESTS           = SPECIFIED
IMPLEMENTATION ORDER         = A → B → C → D → E → F → G → H (GO indépendant par lot)
DÉCISIONS                    = D1–D9, D-E1 FIGÉES (§10, 2026-10) — lots A–H : GO distinct requis par lot
ERRATUM PHASE 4              = signalé (OK 4 / PARTIEL 6 / MANQUANT 5 / N/A 1), fichier non modifié

FILES MODIFIED (applicatifs) = 0
FILES CREATED (applicatifs)  = 0
FILES CREATED (documentation) = 2  (docs/PHASE4C_SPECIFICATION.md · docs/inputs/PHASE_4C_INPUT_COMPLET.txt = copie des entrées fournies)
DB WRITES = 0 · MIGRATION = NONE · DEPLOYMENT = NONE
PHASES 1–3 = FIGÉES · JOURNAL = INCHANGÉ
PHASE 4C = SPECIFICATION ONLY
```

**STOP.** Décisions D1–D9 / D-E1 figées. En attente du GO explicite **par lot** (A → H) avant toute ligne de code. Aucun GO lot n'est implicite.
