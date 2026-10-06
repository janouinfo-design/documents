# PHASE 4 — AUDIT DE PARITÉ FONCTIONNELLE Journal-de-bord → Documents

Date : 2026-10 · Périmètre : projet `janouinfo-design/documents` uniquement · **Zéro code, zéro migration, zéro déploiement.**
Baseline figée : Phases 1–3 (test_fines 20/20 · régression 254/0 · build PASS · it.39 PASS).

---

## 0. Niveau de preuve — À LIRE EN PREMIER

| Côté | Source auditée | Niveau de preuve |
|---|---|---|
| **Documents (nouveau)** | Code réel `backend/server.py`, `backend/extraction.py`, `frontend/src/**`, tests pytest, rapports testing agent it.37–39 | **VÉRIFIÉ** (références fichier:ligne ci-dessous) |
| **Journal-de-bord (ancien)** | **AUCUN accès dans cet espace de travail** : projet séparé, ni code, ni base, ni URL, ni export fourni. Les audits antérieurs (`docs/audit-vehicle-core.md` l.6, handoff « schémas coûts/carburant/amendes NON ACCESSIBLES ») le confirment. | **DÉCLARÉ — NON VÉRIFIÉ** : la colonne « État ancien » reprend l'inventaire fonctionnel fourni par l'utilisateur, considéré comme *fonction attendue*. |

Conséquence : le verdict de parité ci-dessous compare **Documents vs la fonction attendue**. Toute ligne marquée `⚠ À CONFIRMER` doit être validée sur le Journal réel avant d'être considérée comme définitive (voir §5 : intrants nécessaires). Aucun comportement du Journal n'a été inventé : lorsque sa mécanique exacte est inconnue, c'est écrit.

Légende parité : **OK** = fonction couverte · **PARTIEL** = couverte avec écart · **MANQUANT** = absente de Documents · **N/A** = sans objet.
Priorités : **P0** = bloquant avant migration historique · **P1** = à faire avant retrait du Journal · **P2** = amélioration.

---

## 1. Rappel du modèle Documents (ce qui existe réellement)

- **Pipeline unique** : fichier → OCR Claude (`extraction.py`, types `facture`, `ticket_carburant`, `amende`, …) → review humaine → `POST /api/documents/{id}/validate` (`server.py:3538`) → champs V2 du document.
- **Invariant coûts** : le DOCUMENT porte le montant (`documents.montant`, `business_category`) → `collect_costs` (`server.py:2257`) ; `fuel_transactions` n'est jamais resommé (test statique `test_energy_phase2.py::test_collect_costs_ne_lit_jamais_fuel_transactions`).
- **Énergie** : `fuel_transactions` (1 document validé = max 1 transaction, index unique partiel tenant+source_document_id, `server.py:1676`) ; `GET /api/energy` (`:2377`), `GET /api/vehicles/{id}/energy` (`:2416`) ; conso réelle tickets ΔL/Δkm (`:1710`) sous priorité CAN (`:1746`).
- **Amendes** : le document EST l'amende (`_amende_to_v2` `:1564`, dédup `:1579`), statut `A_PAYER/EN_RETARD/PAYEE` (`doc_statut` `:1793`), paiement `POST /api/documents/{id}/paid` (`:2517`), échéance via `collect_deadlines` (`:2078`, exclusion `payee=true`), suppression bloquée 409 (`:2644`).
- **Transverse** : tenant résolu du JWT (`require_auth` `:56`, read_only → 403 sur toute écriture), audit (`audit_logs`, `GET /vehicles/{id}/history` `:4524`), alertes (`run_alerts` `:3077`, e-mail **MOCKÉ** sans provider).
- **Absent du modèle** : aucune entité *conducteur / chauffeur* (grep `conducteur|driver|chauffeur` dans `server.py` = 0 occurrence) ; aucune entité *carte carburant* (seul `fuel_transactions.carte_last4`) ; aucun import CSV/XLSX ; aucune écriture métier sans document source.

---

## 2. Parité — ÉNERGIE & CARBURANT

| # | Fonction Journal | État ancien | État Documents (preuve) | Parité | Écart | Action recommandée | Priorité |
|---|---|---|---|---|---|---|---|
| E1 | Consommation (calcul L/100, kWh/100) | Déclaré ⚠ À CONFIRMER (méthode de calcul, par plein ou par période) | Conso réelle tickets Σ L/Δ km ≥ 100 km, 2–60 L/100 (`:1710`) ; kWh/100 recharges (`:1728`) ; CAN prioritaire (`:1746`) ; officielle ASTRA + écart % ; classement flotte (`:4494`) | **OK** | Méthode Documents = mesurée uniquement (jamais d'estimation) ; si le Journal affichait une conso *par plein*, Documents ne la montre pas (seulement cumul) | Confirmer la méthode Journal ; si « par plein » utilisé par le métier → ajouter colonne L/100 par plein (lecture seule) | P2 |
| E2 | Approvisionnements (pleins / recharges) | Déclaré ⚠ (saisie manuelle probable) | Création **uniquement** depuis un ticket OCR validé (`created_from=document`, `:1676`) ; aucune saisie manuelle sans justificatif | **PARTIEL** | Pas de plein « sans ticket » (perte de ticket, plein hors réseau, relevé carte) | Décider : saisie manuelle autorisée ? Si oui → endpoint + UI « Plein sans justificatif » avec `created_from=manual`, audit, marquage visuel | **P0 pour la migration** (données historiques sans fichier) · P1 produit |
| E3 | Cartes carburant (référentiel, affectation véhicule/conducteur, n°) | Déclaré ⚠ À CONFIRMER (existence d'un référentiel) | Seulement `carte_last4` sur la transaction (`:1693`) ; aucun référentiel, aucune affectation | **MANQUANT** | Impossible de rattacher une transaction à une carte connue, ni de détecter une carte utilisée sur le mauvais véhicule | Si le Journal a un référentiel : modéliser `fuel_cards` (tenant, last4/numéro masqué, véhicule, conducteur, validité) + contrôle carte ≠ véhicule (avertissement) | **P0 si le Journal porte des cartes** (sinon P2) |
| E4 | Transactions (liste, détail, édition, suppression) | Déclaré ⚠ | Liste page `/energie` + onglet véhicule (`EnergyPage.jsx`, `EnergyTab.jsx`) ; édition = revalidation du document (upsert) ; suppression de la transaction **non exposée** (document source protégé 409) | **PARTIEL** | Pas d'édition directe d'une transaction ni d'annulation explicite (ex. ticket attribué au mauvais véhicule) | Ajouter « Annuler la transaction » (soft-delete audité, document conservé) + « Réaffecter au véhicule X » explicite | P1 |
| E5 | Rapprochements (relevé carte ↔ tickets) | Déclaré ⚠ À CONFIRMER | Aucun | **MANQUANT** | Aucun import de relevé, aucun matching ticket/relevé | Dépend de E3 + E7 ; spécifier le format relevé (fournisseur carte) avant tout code | P1 (après E3/E7) |
| E6 | Anomalies (incohérences, suspicions) | Déclaré ⚠ | Avertissements **au moment de la validation** : `AMOUNT_MISMATCH`, `ODOMETER_INCONSISTENT`, `PLATE_MISMATCH`, doublon 409 (`:1623`, `:1660`) ; non persistés, pas de liste | **PARTIEL** | Aucune vue « anomalies ouvertes », aucun suivi/résolution | Persister les avertissements sur la transaction (`warnings[]`) + filtre « avec anomalie » dans `/energie` | P1 |
| E7 | Imports CSV/XLSX (relevés cartes, historiques) | Déclaré ⚠ (format inconnu) | Aucun (NOT STARTED, PRD) | **MANQUANT** | Aucune voie d'entrée en masse ; `created_from` ne connaît que `document` | Contrat d'import : colonnes, clé idempotente `(tenant, legacy_source, legacy_id)`, véhicule résolu par UUID/VIN (jamais plaque auto), dry-run obligatoire | **P0** |
| E8 | Historique (par véhicule, par période) | Déclaré ⚠ | Onglet véhicule : 10 dernières (`EnergyTab.jsx`) ; API `date_from/date_to` existe (`:2377`) mais **aucun filtre période en UI** ; pas de pagination | **PARTIEL** | Historique long tronqué (10) ; pas de sélection de période à l'écran | Filtre période + pagination/« voir tout » dans `/energie` et l'onglet | P1 |
| E9 | Reporting (totaux, moyennes, évolutions) | Déclaré ⚠ | KPIs Dépenses/Volume/Prix moyen/Conso (`EnergyPage.jsx`) ; `by_vehicle` ; pas d'évolution mensuelle, pas de comparaison période | **PARTIEL** | Pas de série temporelle, pas de coût/km énergie | KPI coût/km + graphique mensuel (réutiliser recharts déjà présent sur Coûts) | P2 |
| E10 | Exports (CSV/XLSX des transactions) | Déclaré ⚠ | Aucun export ligne à ligne ; `couts.csv` = totaux par véhicule (`:4026`) | **MANQUANT** | Comptabilité ne peut pas extraire les pleins | `GET /api/reports/energie.csv` (filtres véhicule/période, BOM UTF-8, `;`) — spec seulement, déjà listé hors Phase 3 | P1 |
| E11 | Filtres et recherches | Déclaré ⚠ | Filtre véhicule uniquement (UI) ; API période | **PARTIEL** | Pas de filtre énergie (thermique/électrique), station, carte, montant, texte | Filtres énergie/station/période + recherche texte | P2 |
| E12 | Coûts (intégration) | Déclaré ⚠ | Montant porté par le document → Coûts une seule fois (preuve réelle Migrol +74.17) | **OK** | — | — | — |
| E13 | Échéances | N/A pour les pleins ⚠ (sauf si cartes à expiration) | — | **N/A** | Si cartes carburant à date de validité → échéance manquante | Couvert par E3 si référentiel cartes | P2 |
| E14 | RBAC | Déclaré ⚠ (rôles Journal inconnus) | Lecture read_only OK, écriture 403 backend, isolation tenant (23 tests `test_energy_phase2.py`) | **OK** | Rôles intermédiaires du Journal (ex. conducteur ne voyant que ses pleins) **inexistants** | Confirmer la matrice de rôles du Journal | ⚠ P0 si rôle « conducteur » requis |
| E15 | Audit | Déclaré ⚠ | Audit `create fuel_transaction` à la validation + audit document ; `GET /vehicles/{id}/history` | **OK** | Pas d'audit d'annulation (fonction E4 absente) | Suivra E4 | — |
| E16 | **Conducteur** (attribution d'un plein à un chauffeur) | Déclaré (le Journal est un *livre de bord* chauffeur) ⚠ À CONFIRMER | **Aucune notion de conducteur** dans Documents (0 occurrence) | **MANQUANT** | Perte d'information à l'import ; impossible d'analyser par conducteur | Décision de modèle : `drivers` (tenant, nom, matricule, véhicule(s)) + `fuel_transactions.driver_id` optionnel ; **jamais** déduit automatiquement | **P0** |

## 3. Parité — AMENDES

| # | Fonction Journal | État ancien | État Documents (preuve) | Parité | Écart | Action recommandée | Priorité |
|---|---|---|---|---|---|---|---|
| A1 | Liste et recherche | Déclaré ⚠ | Page `/documents` (recherche nom/fournisseur/n°/responsable/plaque, `:2548`) ; amendes mêlées aux autres documents (dossier « Divers ») | **PARTIEL** | Pas de vue dédiée « Amendes » ; le dossier Divers mélange | Filtre « Amendes » (sur `business_category=AMENDE`) ou dossier système « Amendes » — décision produit (FOLDERS figés) | P1 |
| A2 | Filtres | Déclaré ⚠ | Véhicule, catégorie (dossier), statut (`A_PAYER/EN_RETARD/PAYEE`), échéance, à valider | **PARTIEL** | Pas de filtre autorité / montant / période d'infraction / conducteur | Ajouter filtres autorité + période ; conducteur dépend de A6 | P2 |
| A3 | Statuts (à payer / payée / en retard) | Déclaré ⚠ | `doc_statut` (`:1793`) → badges UI (`DocStatutBadge.jsx`) ; preuve réelle it.39 | **OK** | Pas de statut « contestée / transmise au conducteur » | Confirmer si le Journal gère la contestation ; sinon rien | P2 |
| A4 | Échéances (délai de paiement) | Déclaré ⚠ | `date_expiration` → moteur central (`:2078`), label « Amende … · 120.00 CHF », exclusion payées, « En retard · à payer » (Timeline/Dashboard) ; alertes via `run_alerts` seuils tenant 30/90 j | **OK** | Pas de rappel spécifique J-7 (seuils génériques) ; e-mail mocké | Rappel J-7 = hors Phase 3 (listé, non lancé) | P2 |
| A5 | Paiement et annulation du paiement | Déclaré ⚠ | `POST /documents/{id}/paid` payee/paid_at/paid_by + audit, réversible (`:2517`) ; coût et document conservés | **OK** | Pas de référence de paiement / date de paiement saisissable (paid_at = horodatage de l'action) ; pas de justificatif de paiement attaché | Ajouter `paid_on` (date réelle) + `payment_ref` optionnels ; pièce jointe reçu → A8 | P1 (import historique : date de paiement réelle à conserver) |
| A6 | Conducteur / véhicule | Déclaré (⚠ désignation du conducteur très probable dans un livre de bord) | Véhicule : OK (rattachement explicite, plaque ≠ = avertissement, jamais de réaffectation). **Conducteur : absent** ; seul champ texte `responsable` (libre) | **PARTIEL → MANQUANT (conducteur)** | Impossible d'attribuer/désigner un conducteur ni de refacturer | Même décision de modèle que E16 (`drivers`) + `documents.driver_id` ; procédure « désignation conducteur » = phase ultérieure | **P0** |
| A7 | Historique (actions sur l'amende) | Déclaré ⚠ | `audit_logs` (validation, paiement, annulation) via `/vehicles/{id}/history` ; pas de vue par amende | **PARTIEL** | Historique accessible par véhicule, pas depuis la fiche de l'amende | Onglet/section « Historique » dans la fiche document (lecture de l'audit filtré `entity_id`) | P2 |
| A8 | Pièces jointes | Déclaré ⚠ (PV, photos radar, reçu de paiement) | Le document validé EST la pièce (PDF multi-pages OK) ; **aucune pièce additionnelle** rattachable à la même amende | **PARTIEL** | Reçu de paiement, correspondance, photo radar séparée non rattachables | `documents.parent_document_id` (pièces liées) — spec seulement | P1 |
| A9 | OCR + validation humaine | Déclaré ⚠ (probablement saisie manuelle au Journal) | OCR Claude type `amende` 0.99 (7/7 champs sur fixture réelle), review obligatoire, champs éditables, suggestion AMENDE confirmée | **OK (supérieur)** | Saisie **manuelle** d'une amende sans scan : possible seulement via upload d'un fichier puis fiche (PATCH) — pas de formulaire « Nouvelle amende » | Formulaire manuel (crée un document sans OCR) si le métier en a besoin ; nécessaire pour l'import d'amendes sans fichier | **P0 pour la migration** (amendes historiques sans scan) |
| A10 | Coûts | Déclaré ⚠ | Document → `collect_costs` catégorie Amende, une seule fois (preuve réelle +120.00) | **OK** | — | — | — |
| A11 | Reporting | Déclaré ⚠ | Coûts par catégorie (page Coûts) ; **aucun KPI amendes** (nb à payer / en retard / total période) | **PARTIEL** | Pas de pilotage spécifique | KPI amendes (Dashboard ou page Documents) — hors Phase 3, non lancé | P2 |
| A12 | Exports | Déclaré ⚠ | `couts.csv` = totaux par véhicule ; pas d'export ligne à ligne des amendes | **MANQUANT** | Comptabilité / RH sans liste exportable | `GET /api/reports/amendes.csv` (statut, autorité, n°, dates, montant, payée le) — spec | P1 |
| A13 | Doublons | Déclaré ⚠ | SHA-256 fichier + métier n° (ou autorité+date+montant) → 409 kind=amende + override (`:1579`, 20 tests) | **OK** | — | Réutiliser la même clé pour l'import historique | — |
| A14 | RBAC | Déclaré ⚠ | read_only 403 (validate/paid/delete/patch) ; cross-tenant 404 ; admin seul écrit | **OK** | Rôles Journal inconnus (cf. E14) | Confirmer la matrice Journal | ⚠ P0 si rôle conducteur |
| A15 | Audit | Déclaré ⚠ | Audit validation / paiement / annulation / suppression bloquée | **OK** | — | — | — |

---

## 4. BLOQUANTS AVANT MIGRATION HISTORIQUE

Uniquement les écarts qui doivent être corrigés **avant** d'envisager l'import des anciennes données (sinon : perte d'information ou données non représentables).

| ID | Bloquant | Pourquoi bloquant | Préalable / décision attendue |
|---|---|---|---|
| **B1** | **Jointure véhicule non prête** (`JOIN_NOT_READY`, `docs/audit-identite-vehicule.md`) : pas d'UUID commun, VIN renseigné sur 6/15 véhicules, tracker = affectation évolutive sans historique, plaque = manuel uniquement | Impossible de rattacher de façon fiable chaque plein/amende historique au bon véhicule canonique | Table de correspondance **explicite** `journal_vehicle_id → documents.vehicle_id` validée humainement (export Journal des véhicules : id, plaque, VIN, période d'activité) |
| **B2** | **Mapping tenant inconnu** | Risque de fuite inter-clients ou d'import dans le mauvais tenant | Correspondance `compte Journal → tenant_id` explicite ; interdiction de fallback `default` |
| **B3** | **Aucune entité conducteur** (E16, A6) | Pleins et amendes historiques sont attribués à des chauffeurs dans un livre de bord ; l'import les perdrait ou les écraserait dans un champ texte | Décision de modèle `drivers` + `driver_id` optionnel sur `fuel_transactions` et `documents` (aucune déduction automatique) |
| **B4** | **Aucune écriture métier sans document source** (E2, A9) : une transaction exige un document validé ; une amende EST un document avec fichier | Les données historiques n'ont généralement pas de scan ; les règles actuelles (409 suppression, « pièce justificative », validate) supposent un fichier | Contrat d'import : `fuel_transactions.created_from=legacy_import` (`source_document_id=null`, autorisé par l'index partiel) ; amendes historiques = document **sans fichier** (`storage_path=null`, `source=legacy_import`) à valider côté UI (aperçu/téléchargement désactivés proprement) |
| **B5** | **Aucune clé d'idempotence legacy** sur `fuel_transactions` / `documents` | Un import rejoué créerait des doublons ou serait non rejouable | Champs `legacy_source`, `legacy_id`, `migration_version` + index unique partiel `(tenant_id, legacy_source, legacy_id)` ; dry-run + rapport d'écarts obligatoires (même principe que l'audit V2 M0–M10) |
| **B6** | **Date/référence de paiement réelle non modélisée** (A5) | `paid_at` = horodatage de l'action ; un import marquerait toutes les amendes historiques « payées aujourd'hui » | Champs `paid_on` (date métier) + `payment_ref` optionnels, `paid_by=import` tracé |
| **B7** | **Référentiel cartes carburant** (E3) — *conditionnel* | Si le Journal porte des cartes (n°, affectation), l'import n'a pas de cible | À CONFIRMER sur le Journal ; si oui → `fuel_cards` avant import |
| **B8** | **Format et sémantique des données Journal inconnus** | Impossible de garantir « aucune valeur inventée » sans connaître les champs (unités, devises, TVA incluse ?, statuts) | Export d'échantillon anonymisé (CSV/JSON) + dictionnaire de données du Journal |

Non bloquants (P1/P2, à traiter avant le retrait du Journal ou après) : E4 annulation/réaffectation, E5 rapprochements, E6 anomalies persistées, E8 période/pagination, E9 reporting, E10/A12 exports CSV, E11/A2 filtres, A1 vue Amendes, A7 historique fiche, A8 pièces liées, A11 KPI amendes, rappel J-7.

---

## 5. Intrants nécessaires pour passer de « DÉCLARÉ » à « VÉRIFIÉ » (côté Journal)

Sans l'un de ces éléments, la colonne « État ancien » restera non vérifiée :
1. Accès **lecture seule** au Journal (URL + compte démo) **ou** captures d'écran de chaque module (listes, filtres, fiche plein, fiche amende, exports, paramètres de rôles).
2. Export d'échantillon anonymisé : pleins/transactions, cartes, amendes, conducteurs, véhicules (avec identifiants internes).
3. Dictionnaire de données / schéma (collections ou tables, champs, unités) et documentation API V1 si elle existe.
4. Matrice des rôles du Journal (qui voit/écrit quoi, notamment « conducteur »).
5. Volumétrie (nb pleins, amendes, années couvertes) pour dimensionner le dry-run.

---

## 6. Verdict

```text
PARITÉ ÉNERGIE & CARBURANT : OK 4 · PARTIEL 7 · MANQUANT 4 · N/A 1   (16 fonctions)
PARITÉ AMENDES             : OK 8 · PARTIEL 5 · MANQUANT 2           (15 fonctions)
ÉTAT ANCIEN (Journal)      : NON VÉRIFIÉ — inventaire déclaré, accès indisponible
BLOQUANTS MIGRATION        : B1 jointure véhicule · B2 tenant · B3 conducteur · B4 écriture sans document
                             B5 idempotence legacy · B6 date de paiement réelle · B7 cartes (conditionnel) · B8 format Journal
MIGRATION HISTORIQUE       : NOT READY (aucun script préparé — volontaire)
BASELINE PHASES 1–3        : INCHANGÉE (0 fichier applicatif modifié par cet audit)
DEPLOYMENT                 : NONE
```

Ordre recommandé : (1) fournir les intrants §5 → (2) confirmer/infirmer les lignes ⚠ et B7 → (3) décisions de modèle B3/B4/B5/B6 → (4) GO pour un lot « pré-migration » strictement limité à ces bloquants → (5) dry-run d'import → (6) migration. Rien de tout cela n'est lancé sans GO explicite.
