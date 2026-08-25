# Contrat inter-projets — Vehicle Core LOGITRAK (v0.1-draft)

Statut : BROUILLON. Ce contrat sera figé APRÈS l'audit des projets New Navixy,
Journal de bord et Énergie. Le module Documents en est le fournisseur (lecture seule).

## 1. Identifiant véhicule

- `vehicle_id` = `vehicles.id` (uuid4, string) — identifiant LOGITRAK **stable**.
  Il n'est JAMAIS remplacé par le VIN, la plaque, le tracker_id ou navixy_vehicle_id.
- Le VIN est une donnée d'identification forte et de CONTRÔLE, pas une clé technique
  (renseigné sur une partie de la flotte seulement).

## 2. Resolver inter-modules — `GET /api/vehicles/resolve`

Paramètres (au moins un requis, sinon 422) :
`vehicle_id` · `navixy_vehicle_id` (int) · `navixy_tracker_id` (int) · `vin` · `plate`

Ordre de priorité RÉELLEMENT implémenté (identifiants exacts d'abord) :
1. `vehicle_id`
2. `navixy_vehicle_id`
3. `navixy_tracker_id`
4. `vin` (normalisé : majuscules, caractères non alphanumériques retirés)
5. `plate` (normalisée : majuscules, espaces/ponctuation retirés — « vd 123456 » ≡ « VD 123 456 »)

Sémantique :
- Chaque critère FOURNI est évalué dans cet ordre.
- 1 correspondance → `{"status": "found", "matched_by": <critère>, "vehicle": <identity>}`.
- \>1 correspondances → **arrêt immédiat** `{"status": "ambiguous", "matched_by", "count", "matches": [...]}`
  — jamais de rapprochement ambigu silencieux.
- 0 correspondance → critère suivant fourni ; si aucun ne correspond →
  `{"status": "not_found", "searched_by": [...]}`.
- LECTURE SEULE : le resolver ne modifie jamais aucune donnée.
- Un VIN/une plaque vide côté base ne matche jamais (normalisation vide exclue).

## 3. Fiche véhicule — `GET /api/vehicles/{vehicle_id}/core`

DTO exposé aux modules Journal de bord / Énergie :

```json
{
  "contract_version": "0.1-draft",
  "identity": {
    "vehicle_id": "…", "vin": "…|null", "plate": "…", "make": "…", "model": "…",
    "year": 2023, "category": "M1|null", "energy": "Diesel|Électrique|…|null",
    "navixy_tracker_id": 123, "navixy_vehicle_id": 456
  },
  "reference": {
    "fuel_tank_capacity_l":            { "value": null, "unit": "L", … },
    "battery_capacity_gross_kwh":      { "value": null, "unit": "kWh", … },
    "battery_capacity_usable_kwh":     { "value": null, "unit": "kWh", … },
    "reference_consumption_l_100km":   { "value": 6.4, "unit": "L/100km", "norm": "WLTP", … },
    "reference_consumption_kwh_100km": { "value": null, "unit": "kWh/100km", "norm": null, … },
    "reference_range_km":              { "value": null, "unit": "km", … }
  }
}
```

Chaque entrée `reference` porte : `value` (null si inconnue — AUCUNE valeur supposée),
`unit`, `source`, `provider`, `measurement_type`, `confidence`, `retrieved_at`,
`validated_by`, `validated_at` (depuis `vehicle_field_meta` quand disponible).

### Mapping contrat (EN) ↔ stockage interne Documents (FR)
| Contrat | Champ interne | Note |
|---|---|---|
| fuel_tank_capacity_l | capacite_reservoir_l | champ préexistant réutilisé (pas de doublon) |
| battery_capacity_gross_kwh | batterie_capacite_brute_kwh | nouveau, NULL par défaut |
| battery_capacity_usable_kwh | batterie_capacite_utile_kwh | nouveau, NULL par défaut |
| reference_consumption_l_100km | conso_officielle_l_100km | préexistant réutilisé ; INTERDIT pour les 100 % électriques |
| reference_consumption_kwh_100km | conso_officielle_kwh_100km | nouveau, NULL par défaut |
| reference_range_km | autonomie_km | nouveau, NULL par défaut |

Convention : 0 / "" internes = inconnu → exposés `null` dans le DTO.

### NON exposé (volontairement)
Fichiers/documents, chemins de stockage internes (`storage_path`), assurance détaillée,
leasing, coûts, échéances administratives, données OCR brutes.

## 4. measurement_type / nature des données

Valeurs prévues : `reference` (homologation/constructeur — ASTRA, document officiel scanné),
`manual` (saisie utilisateur), `measured` (télémétrie/calcul réel, ex. conso CAN),
`estimated` (réservé, non produit par Documents).
Le module Documents ne produit JAMAIS de mesure OBD : ses valeurs techniques sont
`reference` ou `manual` ; `measured` provient uniquement du pipeline CAN existant.
Règle Énergie : les valeurs `reference` servent de FALLBACK, jamais de remplacement
silencieux d'une donnée OBD réelle.

## 5. Sources d'enrichissement — hiérarchie inchangée

1. Document/OCR proposé (jamais appliqué sans validation humaine)
2. Validation humaine
3. ASTRA / source structurée (jamais d'invention ; donnée absente = null)
4. Saisie manuelle validée
L'IA générative n'invente JAMAIS : batterie, réservoir, consommation, autonomie, kWh, litres.
ASTRA ne fournit PAS : capacité batterie, autonomie, réservoir → ces champs restent null
jusqu'au branchement d'un provider licencié via l'interface `VehicleTechnicalDataProvider`.

## 6. TENANT — emplacement futur (décision différée)

`tenant_id` n'est PAS ajouté : les représentations tenant/client des projets New Navixy,
Journal de bord et Énergie doivent d'abord être auditées. Quand le contrat sera figé :
- place prévue : bloc `identity.tenant_id` du DTO + champ indexé sur `vehicles` ;
- le resolver devra alors filtrer par tenant AVANT tout matching ;
- migration : backfill d'un tenant unique par défaut, puis contrainte.
Décisions restant à prendre : source de vérité du tenant (hub ?), format d'id, mécanisme
d'authentification de service inter-projets (actuellement : JWT superadmin Documents).

## 7. Navixy — écriture whitelist (mise à jour : exigence « mêmes données partout »)

Depuis le lot « véhicule canonique », l'écriture Navixy est AUTORISÉE sur une whitelist
STRICTE, en read-merge-write obligatoire (`vehicle/read` → fusion → `vehicle/update`
avec `force_reassign: false`) :

| Documents (canonique) | Navixy | Sens |
|---|---|---|
| plaque | reg_number | ↔ |
| vin | vin | ↔ |
| marque + modele | model (concaténé « Marque Modèle ») | ↔ |
| annee | manufacture_year | ↔ |
| carte_grise.couleur | color | ↔ |

Règles :
- Push déclenché UNIQUEMENT par : validation d'un scan de document, édition de la fiche
  véhicule. Jamais de push massif automatique. Best effort : un échec Navixy ne bloque
  jamais la sauvegarde locale (statut retourné + log). Chaque écriture est auditée.
- Descendant : la sync importe désormais aussi `color` ; les champs validés par document
  (dont couleur) restent protégés contre l'écrasement descendant.
- Toujours INTERDITS : `vehicle/create`, réaffectation de tracker (`force_reassign: false`),
  tout champ hors whitelist (leasing, assurance détaillée, documents, conso, etc.).
- `NAVIXY_WRITE_ENABLED=false` désactive toute écriture (les données locales restent canoniques).
- Contrôle d'intégrité : `GET /api/fleet/integrity` — statuts IDENTIQUE / DIFFERENT /
  NON_DISPONIBLE / NON_SUPPORTE_PAR_NAVIXY par champ (nom, plaque, vin, marque_modele,
  annee, couleur, type, garage, departement), divergences auditées.
- Champs Navixy non modélisés côté Documents (nom/label, type/subtype, garage) : signalés
  NON_DISPONIBLE — pas de sync bidirectionnelle prétendue.
- La whitelist étendue (type, garage, tags, assurance) reste à définir après l'audit du
  projet New Navixy.
