# AUDIT — Documents (LOGITRAK) · Vehicle Core, Sync Navixy, OCR, Enrichissement VIN
Date : 2026-06 (session audit). Périmètre : UNIQUEMENT le projet Documents. Aucun code modifié.
Méthode : lecture du code backend/frontend, inspection Mongo réelle, appel LECTURE SEULE à l'API
Navixy du compte (vehicle/list), vérification de la documentation officielle Navixy vehicle/update.

⚠️ Limite de périmètre : « New Navixy », « Journal de bord » et « Énergie » sont des projets
Emergent SÉPARÉS. Leur code/BDD ne sont pas accessibles depuis ce projet. Tout ce qui les
concerne est indiqué comme NON VÉRIFIABLE ICI — rien n'est inventé.

---

## 1. ARCHITECTURE EXISTANTE — RÉALISÉ (audit)

- Backend : FastAPI monolithique (`backend/server.py`, ~2150 lignes) + modules :
  `auth.py` (JWT superadmin), `extraction.py` (OCR Claude), `astra_data.py` (base officielle
  ASTRA/OFROU locale), `technical_data.py` (ex-SwissCarInfo, INACTIF, conservé),
  `reports.py` (PDF/CSV).
- Base : MongoDB unique (`MONGO_URL`/`DB_NAME`). PostgreSQL : ABSENT.
- Frontend : React (CRA/CRACO), API via `REACT_APP_BACKEND_URL` + `/api`, JWT Bearer 24 h.
- Auth : superadmin unique, TOUTES les routes /api protégées. `tenant_id` : ABSENT partout.
- Sync Navixy : UNIDIRECTIONNELLE Navixy → Documents (lecture seule). Aucun write vers Navixy.
- Planificateur : APScheduler — sync Navixy + alertes 1×/jour, sync ASTRA mensuelle.
- Prod : VPS Docker (~/documents/deploy, port 8090), Nginx same-origin /api.

## 2. COLLECTIONS / MODÈLES EXISTANTS — RÉALISÉ (audit)

Collections Mongo (comptages réels au moment de l'audit) :
| Collection | Docs | Rôle |
|---|---|---|
| vehicles | 12 | LE modèle véhicule unique (1 doc = 1 véhicule, id = uuid4 string) |
| documents | 76 | documents scannés/importés (vehicle_id, folder, storage_path, extraction) |
| files | 8 | fichiers uploadés hors documents (photos etc.) |
| vehicle_field_meta | 35 | PROVENANCE par champ (source, provider, confidence, validated_by/at, previous_value) |
| audit_logs | 255 | trail « ancien → nouveau (source: …) » |
| inspections | 3 | états des lieux |
| alerts | 57 | alertes échéances |
| users / login_attempts | 1 / 0 | auth superadmin |
| fuel_snapshots | — | snapshots litres CAN + km pour conso réelle mesurée |
| astra_tas / _emissions / _tg / _tg_verbrauch / _edatenblatt | ~1,1 M au total | base officielle ASTRA locale |

Modèle Vehicle (UN SEUL — pas de doublon) : Pydantic `VehicleBase/Create/Update` + sous-objets
`Leasing`, `Assurance`, `CarteGrise`, `ControleTechnique`. `vehicle_admin` : N'EXISTE PAS
(le véhicule EST le document administratif).

Identité actuelle du véhicule :
| Clé | État | Détail réel |
|---|---|---|
| vehicle_id interne | EXISTANT | `vehicles.id` = uuid4, stable, utilisé par toutes les collections liées |
| tenant_id | ABSENT | aucune occurrence backend/frontend |
| navixy_tracker_id | EXISTANT | int, clé de matching de la sync (12/12 renseignés) |
| tracker_gps | EXISTANT | device_id / IMEI (string) — champ distinct du tracker_id |
| navixy_vehicle_id | PARTIEL | renseigné sur 3/12 seulement (voir §7) |
| VIN | PARTIEL | 5/12 renseignés ; utilisé pour enrichissement, PAS comme clé technique |
| plaque (immatriculation) | EXISTANT | 12/12 ; parsée depuis le label tracker (regex plaque suisse) si vehicle Navixy absent |
| numero_homologation | PARTIEL | 3/12 (clé d'enrichissement ASTRA prioritaire) |

## 3. ENDPOINTS EXISTANTS — RÉALISÉ (audit)

- Auth : POST /api/auth/login · GET /api/auth/me · POST /api/auth/change-password · POST /api/auth/logout
- Véhicules : GET/POST /api/vehicles · GET/PUT/DELETE /api/vehicles/{id} · GET /api/vehicles/{id}/live
- Navixy : GET /api/navixy/status · POST /api/navixy/sync (import/refresh une direction)
- Documents : GET/POST /api/vehicles/{id}/documents · DELETE /api/documents/{id} ·
  POST /api/vehicles/{id}/documents/scan (OCR) · POST /api/documents/{id}/validate ·
  GET /api/document-types · POST /api/upload · GET /api/files/{path}
- Provenance/historique : GET /api/vehicles/{id}/field-meta · GET /api/vehicles/{id}/history
- Enrichissement : POST /api/vehicles/{id}/enrich-technical (+/apply, +/revert) ·
  POST /api/vehicles/enrich-technical/batch · GET /api/astra/status|search · POST /api/astra/import
- Dashboard/alertes/rapports : /api/dashboard · /api/timeline · /api/alerts(+/run,/log) ·
  /api/reports/conformite.pdf · /api/reports/couts.csv · /api/reports/vehicule/{id}.pdf ·
  /api/fleet/consumption-ranking · /api/config/status · /api/technical-data/status
- API D'EXPOSITION POUR LES AUTRES MODULES (Journal de bord / Énergie) : NON RÉALISÉ
  (aucun endpoint de résolution d'identité type « GET vehicle by vin/plate/tracker » pensé pour
  la consommation inter-projets ; les endpoints existants exigent le JWT superadmin Documents).

## 4. TABLEAU DES CHAMPS DOCUMENTS (modèle réel) — RÉALISÉ (audit)

Racine vehicle : photo_url, plaque, marque, modele, annee, vin, type_carburant, cylindree_cm3,
puissance_kw, variante, numero_homologation, categorie, poids_vide, co2_g_km,
conso_officielle_l_100km, conso_officielle_norme, co2_norme, capacite_reservoir_l,
conso_reelle_l_100km, conso_reelle_source, carburant_niveau_pct, carburant_niveau_date,
kilometrage, groupe, base, responsable, tracker_gps, prochaine_maintenance, prochaine_expertise,
source, navixy_tracker_id, navixy_vehicle_id, created_at, updated_at.

Sous-objets :
- leasing : societe, numero_contrat, date_debut, date_fin, mensualite_chf, duree_mois,
  km_contractuel, km_annuel, option_achat, valeur_residuelle, cout_total, cout_mensuel, commentaires
- assurance : compagnie, numero_police, type_couverture, prime_annuelle, franchise, assistance,
  contact_sinistre, date_debut, date_echeance
- carte_grise : date_mise_circulation, poids_total, nombre_places
  (⚠️ `couleur` est extraite par l'OCR vers carte_grise mais ABSENTE du modèle Pydantic — voir §10/§11)
- controle_technique : date_dernier, date_prochain, centre, resultat
- vignette : PAS un champ véhicule — données portées par le DOCUMENT (annee, type_vignette,
  plaque, date_achat, date_expiration, prix_chf, statut)

Champs demandés dans la mission :
| Champ demandé | État Documents |
|---|---|
| type / sous-type véhicule | PARTIEL — `categorie` (catégorie carte grise, ex. M1) existe ; type/subtype au sens Navixy (car/truck… + sedan/suv…) ABSENTS |
| couleur | PARTIEL — extraite par OCR, stockée en Mongo, mais absente du modèle Pydantic (risque d'effacement à l'édition, §11-R8) |
| motorisation/énergie | EXISTANT — `type_carburant` (libellés officiels TARGA, y c. électrique/hybride) |
| kilométrage | EXISTANT — odomètre Navixy (source unique, sync) |
| assurance / leasing / révision (contrôle) | EXISTANT — détaillés + alertes |
| vignette | EXISTANT — type de document dédié |
| batterie kWh (brute/utile), conso kWh/100, autonomie | ABSENTS (voir §9) |
| réservoir litres | PARTIEL — `capacite_reservoir_l` existe mais saisie MANUELLE uniquement (aucune source d'enrichissement branchée) |

## 5. TABLEAU DES CHAMPS COMMUNS NAVIXY ↔ DOCUMENTS — RÉALISÉ (audit)

Vérification RÉELLE : vehicle/list appelé sur votre compte (8 véhicules Navixy) + doc officielle
vehicle/update (l'endpoint EXISTE, droit sous-utilisateur `vehicle_update` requis, il prend
l'OBJET COMPLET — pas de PATCH partiel).

| Navixy (API réelle) | Documents | Sens possible | Écriture API Navixy prouvée ? |
|---|---|---|---|
| reg_number | plaque | ↔ | OUI (vehicle/update) |
| vin | vin | ↔ | OUI |
| model (string unique) | marque + modele (2 champs) | ↔ avec PERTE (concat/split heuristique) | OUI |
| manufacture_year | annee | ↔ | OUI |
| color | (carte_grise.couleur — hors modèle) | ↔ possible APRÈS fix couleur | OUI |
| type (enum car/truck/bus/special) | ABSENT côté Documents | → import possible ; ↔ après ajout champ | OUI (enum strict) |
| subtype (enum fermé par type) | ABSENT | idem | OUI (enum strict) |
| garage_id (+garage_organization_name) | `base`/`groupe` (strings libres) | mapping à construire (registre garages Navixy) | OUI (int id, pas un texte libre) |
| tags (int array = IDs de mots-clés) | ABSENT | mapping à construire (API tags) | OUI (IDs seulement) |
| fuel_type (enum petrol/diesel/gas UNIQUEMENT) | type_carburant (libellés riches, y c. Électrique/Hybride) | → import OK ; ← EXPORT IMPOSSIBLE pour EV/hybride (pas de valeur enum) | OUI mais enum TROP PAUVRE |
| fuel_tank_volume (int L) | capacite_reservoir_l | ↔ | OUI |
| norm_avg_fuel_consumption (L/100) | conso_officielle_l_100km | ↔ (attention norme/unité, §11-R5) | OUI |
| liability_insurance_policy_number / _valid_till | assurance.numero_police / date_echeance | ↔ PARTIEL (2 champs sur 9) | OUI |
| free_insurance_policy_number / _valid_till | (casco — pas de champ dédié distinct) | PARTIEL | OUI |
| chassis_number / frame_number | ABSENTS (VIN seul) | — | OUI |
| gross_weight | carte_grise.poids_total | ↔ | OUI |
| passengers | carte_grise.nombre_places | ↔ (sémantique ≈) | OUI |
| max_speed, payload_*, tyre_*, wheel_arrangement, trailer, fuel_grade, fuel_cost, additional_info | ABSENTS côté Documents | import possible si besoin | OUI |
| label | — (utilisé en lecture pour parser la plaque) | lecture seule conseillée | OUI |
| icon_id | photo_url | NON ÉQUIVALENT (icon via avatar/assign uniquement) | NON (endpoint séparé) |
| tracker_id (association traceur) | navixy_tracker_id | SENSIBLE — voir §11-R9 | OUI (erreurs 247/261 documentées) |

Champs NON modifiables par vehicle/update : icon_id (endpoint avatar/assign), tracker_label,
avatar_file_name. Odomètre : compteur tracker, PAS un champ vehicle (lecture via
tracker/counter — l'écriture d'un compteur passe par une autre API et n'est PAS auditée ici :
NON PROUVÉ).

## 6. CHAMPS DOCUMENTS UNIQUEMENT (ne JAMAIS envoyer à Navixy) — RÉALISÉ (audit)

Leasing complet (13 champs), assurance détaillée (type_couverture, prime, franchise, assistance,
contact_sinistre, date_debut), carte grise (date 1re mise en circulation, catégorie, poids vide,
homologation, variante), contrôle technique (dates/centre/résultat), vignette, factures, amendes,
documents/PDF (storage_path — les fichiers ne quittent JAMAIS le stockage LOGITRAK),
données OCR (confidence, status, detected_type, quality_warnings), provenance vehicle_field_meta,
audit_logs, CO₂ + normes, conso officielle + norme, conso réelle mesurée + source, niveau
carburant télémétrie, kilométrage contractuel, groupe/base/responsable, échéances maintenance/
expertise, photo_url, alertes, états des lieux.

## 7. POSSIBILITÉS RÉELLES DE SYNCHRONISATION — état PARTIEL

EXISTANT (prouvé, en prod) :
- Navixy → Documents : tracker/list + vehicle/list + odomètre + readings carburant.
  Matching par navixy_tracker_id. Champs importés : plaque, marque/modele (split heuristique),
  vin, annee, kilometrage, tracker_gps, navixy_vehicle_id, niveau carburant, litres CAN.
- Garde anti-écrasement : plaque/marque/modele/vin/annee validés par scan NE SONT PLUS écrasés
  par la sync. Le reste = « Navixy gagne » à chaque sync.
- CONSTAT COMPTE RÉEL : 12 trackers ; seulement 8 objets vehicle côté Navixy ; seulement 3
  liés à un tracker → 9 véhicules Documents n'ont PAS d'objet vehicle Navixy à mettre à jour
  (il faudrait vehicle/create + association, opération sensible).

NON RÉALISÉ :
- Écriture Documents → Navixy (aucun appel vehicle/update dans le code).
- Whitelist de champs synchronisables (aucune table de mapping).
- Read-merge-write obligatoire (vehicle/update = objet complet : un update naïf EFFACERAIT
  les champs non renvoyés).
- Gestion de conflits bidirectionnelle datée (voir §11-R6/R7).

## 8. ARCHITECTURE OCR / EXTRACTION CARTE GRISE — RÉALISÉ

- Provider : Claude Sonnet 4.6 (vision) via emergentintegrations (clé Anthropic backend/.env),
  secours GPT/Emergent. Abstraction provider extensible.
- Pipeline : capture caméra/webcam/PDF multi-pages → recadrage/perspective (jscanify/OpenCV) →
  contrôle qualité pré-analyse NON-LLM (blocage 422 seulement si inexploitable) → extraction.
- 8 types de documents ; carte grise (permis_circulation) extrait : plaque, VIN, marque, modele,
  variante/type, numero_homologation, date 1re mise en circulation, type_carburant, cylindree_cm3,
  puissance_kw, poids_vide, poids_total, categorie, couleur, nombre_places, co2_g_km.
- Par champ : value + confidence + status (found/uncertain/missing) + current_value + conflict.
  Détection d'incohérence de type (« semble être X et non Y »).
- AUCUNE écriture automatique : validation humaine explicite (Conserver/Utiliser, défaut =
  conserver), provenance vehicle_field_meta (source=document_scan, source_document_id,
  confidence, validated_by/at) + audit « ancien → nouveau ». L'original n'est jamais altéré.
- Exigences Phase 4 : COUVERTES, sauf présentation formelle « source » comme champ séparé
  (la source = type de document, tracée en meta/audit) — sémantiquement équivalent.

## 9. POSSIBILITÉS RÉELLES D'ENRICHISSEMENT VIN — PARTIEL

EXISTANT (prouvé, base officielle LOCALE — aucune invention générative possible) :
- ASTRA/OFROU importé localement (~1,1 M docs) : TAS + émissions + TG + conso + eDatenblatt.
- Resolver : numero_homologation (TAS→TG) puis repli VIN (préfixe 10 car. eDatenblatt,
  variantes si configs divergentes, 409 si >12 configs). Plaque seule : indisponible sans
  fournisseur externe (message explicite — voulu).
- Champs enrichissables : type_carburant, cylindree_cm3, puissance_kw, conso_officielle_l_100km
  (+norme WLTP/NEDC), co2_g_km (+norme), poids_vide, poids_total, nombre_places, date_prochain.
- Garanties : aperçu + conflits + validation humaine, garde CAN/OBD (provider=navixy_can jamais
  écrasé), provenance provider=astra_tas/astra_tg/astra_edatenblatt, previous_value + revert,
  lookup_ms mesuré. LLM JAMAIS utilisé pour les caractéristiques techniques.

ABSENT / NON RÉALISÉ (champs Phase 5 demandés) :
| Champ demandé | État |
|---|---|
| fuel_tank_capacity_l | PARTIEL — champ existe (capacite_reservoir_l), AUCUNE source d'enrichissement (ASTRA ne fournit pas le réservoir) → manuel/NULL |
| battery_capacity_gross_kwh | ABSENT (champ + source) |
| battery_capacity_usable_kwh | ABSENT |
| reference_consumption_l_100 | RÉALISÉ (conso_officielle_l_100km + norme + provenance) |
| reference_consumption_kwh_100 | ABSENT — ⚠️ pour un BEV, la valeur WLTP eDatenblatt (kWh/100) atterrirait dans le champ nommé « l_100km » : ambiguïté d'unité (§11-R5) |
| reference_range_km (autonomie) | ABSENT (ASTRA ne le fournit pas dans les datasets importés) |
| measurement_type=REFERENCE explicite | PARTIEL — la distinction existe via noms de champs (officielle vs reelle) + meta source/provider, pas via un attribut normé measurement_type/source_type/retrieved_at |

Conclusion Phase 5 : pour batterie kWh / autonomie / réservoir, AUCUNE source structurée n'est
intégrée aujourd'hui. Conforme à la règle : ces valeurs resteraient NULL tant qu'une source
fiable (constructeur/fournisseur licencié) n'est pas branchée. L'interface provider
(`VehicleTechnicalDataProvider`) existe pour brancher une telle source sans refonte.

## 10. DOUBLONS DÉTECTÉS

1. AUCUN doublon de modèle Vehicle : un seul modèle, une seule collection. ✔
2. `tracker_gps` (IMEI string) vs `navixy_tracker_id` (int) : redondance partielle assumée
   (affichage vs clé technique) — à documenter, pas à supprimer.
3. `couleur` : définie dans l'OCR (FIELD_DEFS) mais absente du modèle CarteGrise → champ
   « fantôme » stocké en Mongo hors schéma (risque R8).
4. `technical_data.py` (SwissCarInfo) : chemin mort conservé volontairement — pas un doublon
   actif, mais 2 définitions de champs techniques coexistent (TECH_FIELD_DEFS y vit et est
   importé par server.py : c'est LA liste active, le provider est inactif).
5. `conso_reelle_source` (racine) duplique partiellement vehicle_field_meta.provider — cohérents
   aujourd'hui, à garder synchronisés.
6. Split marque/modele recalculé à chaque sync depuis label/model Navixy — heuristique, pas un
   doublon mais une double source de vérité potentielle.

## 11. RISQUES

- R1 vehicle/update Navixy = OBJET COMPLET : un update partiel efface les champs omis côté
  Navixy. Toute écriture DOIT faire read → merge → update. (Prouvé par la doc officielle.)
- R2 enum fuel_type Navixy = petrol|diesel|gas UNIQUEMENT : votre flotte contient des
  ÉLECTRIQUES (Zoe, Enyaq) → export motorisation impossible pour ces véhicules ; ne jamais
  forcer une valeur fausse.
- R3 Pas de champ « marque » chez Navixy (model = string unique) : mapping marque+modele ↔
  model avec perte ; règle de concat/split à figer dans la whitelist.
- R4 9/12 véhicules sans objet vehicle Navixy lié : la sync montante exigerait vehicle/create
  + association tracker (opération sensible, erreurs 247/261).
- R5 Ambiguïté d'unité conso pour BEV/PHEV : conso_officielle_l_100km peut recevoir des kWh/100
  (eDatenblatt WLTP électrique) — séparer L/100 et kWh/100 avant tout export vers
  norm_avg_fuel_consumption (défini en L/100 chez Navixy).
- R6 Sync actuelle « Navixy gagne » pour les champs non protégés par un scan validé : une
  correction manuelle locale (ex. plaque corrigée à la main SANS scan) est ré-écrasée à la
  sync suivante. Le mécanisme de protection existe (vehicle_field_meta) mais n'est branché
  que sur source=document_scan.
- R7 Aucun mécanisme de conflit daté Navixy↔LOGITRAK (valeur des 2 côtés + date + résolution
  manuelle) : NON RÉALISÉ — nécessaire avant toute écriture bidirectionnelle sur VIN/plaque.
- R8 `couleur` : une édition de l'onglet Carte grise (PUT avec le sous-objet CarteGrise complet)
  REMPLACE le sous-document et efface la couleur scannée. Perte de donnée réelle possible.
- R9 Association tracker = sensible : aujourd'hui implicite (1 véhicule créé par tracker à la
  sync). Aucune UI/procédure de ré-association contrôlée.
- R10 tenant_id absent : toute mutualisation multi-clients future imposera une migration.
- R11 Identité inter-projets : VIN renseigné sur 5/12 seulement → le VIN seul NE PEUT PAS être
  la clé de correspondance aujourd'hui ; navixy_tracker_id est la seule clé fiable à 100 %.
- R12 Droit API : l'écriture vehicle/update exige le droit `vehicle_update` sur le hash utilisé
  (à vérifier sur le compte au moment de l'implémentation — non testé pour ne rien écrire).

## 12. MODIFICATIONS NÉCESSAIRES (proposition — RIEN N'EST CODÉ)

P0 — Identité commune (Phase 2)
1. Officialiser le bloc identité : vehicle_id (=vehicles.id uuid existant, NE PAS changer),
   tenant_id (nouveau, défaut unique, indexé), navixy_vehicle_id, navixy_tracker_id, vin
   (normalisé, contrôle de cohérence, jamais clé unique), plaque. Zéro doublon créé.
2. Endpoint de résolution inter-modules : GET /api/vehicles/resolve?vin=|plate=|tracker_id=
   (+ clé d'accès service dédiée) pour Journal de bord / Énergie / hub.
3. Backfill VIN par scan carte grise (OCR existant) — le VIN devient donnée de contrôle forte.

P0 — Corrections de fond
4. Ajouter `couleur` au modèle CarteGrise (fix R8).
5. Séparer conso L/100 et kWh/100 (nouveaux champs reference_consumption_kwh_100,
   battery_capacity_gross/usable_kwh, reference_range_km — NULL par défaut, source structurée
   obligatoire, measurement_type/source_type/retrieved_at dans vehicle_field_meta).

P1 — Sync Navixy ↔ Documents (Phase 3)
6. Table de mapping WHITELIST versionnée (champ Documents ↔ champ Navixy, direction, transform,
   condition d'export — ex. fuel_type exporté seulement si mappable dans l'enum).
7. Écriture montante : read (vehicle/read) → merge whitelist → vehicle/update ; dry-run + revue
   avant application ; jamais d'envoi des champs Documents-only.
8. Étendre la protection anti-écrasement aux champs édités manuellement (meta source=manual),
   pas seulement document_scan (fix R6).
9. Conflits sensibles (VIN, plaque, association tracker) : file de conflits avec valeur Navixy,
   valeur LOGITRAK, sources, dates, résolution manuelle (Phase 7). Association tracker = action
   explicite dédiée, jamais silencieuse.

P2 — Enrichissement (Phase 5/6)
10. Brancher une source structurée pour batterie/autonomie/réservoir via l'interface provider
    existante (constructeur/fournisseur licencié — à choisir ; ASTRA ne les fournit pas).
11. Exposer les valeurs REFERENCE aux autres projets (fallback Énergie) via l'endpoint §12.2,
    avec provenance — jamais en remplacement silencieux d'une donnée OBD réelle (la garde
    CAN/OBD existe déjà côté Documents).

---

## SYNTHÈSE PAR PHASE
| Phase | Statut |
|---|---|
| 1 Audit | RÉALISÉ (ce document) |
| 2 Vehicle Core / identité commune | PARTIEL — id interne stable + clés Navixy existent ; tenant_id ABSENT ; endpoint inter-modules ABSENT |
| 3 Sync Navixy ↔ Documents | PARTIEL — descendante réelle en prod ; montante NON RÉALISÉE ; whitelist NON RÉALISÉE |
| 4 IA/OCR carte grise | RÉALISÉ (confiance, statut, conflits, validation humaine, zéro écriture auto) |
| 5 Enrichissement VIN | PARTIEL — ASTRA local réel (conso/CO₂/poids/puissance…) ; batterie kWh, autonomie, réservoir : ABSENTS faute de source structurée (valeurs NULL, conformément à la règle) |
| 6 Priorité des sources | RÉALISÉ côté Documents (REFERENCE vs mesuré, garde CAN/OBD, provenance) ; PARTIEL inter-projets (pas d'API de fallback) |
| 7 Conflits Navixy↔LOGITRAK | PARTIEL — conflits/validation humaine INTRA-Documents réalisés ; résolution datée bidirectionnelle NON RÉALISÉE |
