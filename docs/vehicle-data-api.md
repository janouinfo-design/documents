# Vehicle Data API — Données techniques véhicules (ASTRA/OFROU)

## Vue d'ensemble

LogiTrak intègre une **Vehicle Data API interne** fondée sur les jeux de données officiels
**ASTRA/OFROU** (opendata.astra.admin.ch/ivzod), stockés en **copie locale** dans MongoDB.

- **Gratuit** : aucune clé API, aucun fournisseur externe requis.
- **Traçable** : provenance par champ (`vehicle_field_meta`), audit complet, conflits conservés.
- **Validation humaine obligatoire** : aucun enrichissement n'écrit directement la fiche
  véhicule — aperçu, conflits, choix explicite de l'utilisateur, puis application.
- **SwissCarInfo est retiré du chemin actif** : le code (`technical_data.py`) et les
  variables `SWISSCARINFO_*` sont conservés uniquement pour compatibilité historique.

## Jeux de données importés (Phase 1)

| Dataset | Fichier source | Collection Mongo | Contenu |
|---|---|---|---|
| `tas` | `TAS_Automobil.csv` (~353 Mo, CSV `;`, UTF-8-BOM) | `astra_tas` | Homologations automobiles : marque, type, carburant, cylindrée, puissance, poids, places, boîtes |
| `tas_emission` | `TAS_Emission.csv` (~92 Mo) | `astra_tas_emissions` | Consommation & CO₂ WLTP/NEDC par boîte de vitesses |
| `tg` | `TG-Automobil.txt` (~323 Mo, TSV, Latin-1) | `astra_tg` | Homologations historiques TG/TARGA dès 1995 |
| `tg_verbrauch` | `verbrauch.txt` (~19 Mo, TSV, Latin-1) | `astra_tg_verbrauch` | Consommation, CO₂, classe énergie des TG |

L'import est **streaming** (jamais de fichier complet en mémoire) : lecture ligne à ligne,
lots de 1000 `ReplaceOne` upserts, suivi dans `astra_import_runs` (statut, lignes lues,
durée, erreurs). Les documents d'un run précédent sont purgés à la fin d'un run réussi
(gestion des suppressions upstream). Seuls les champs utiles sont stockés (~20 champs/ligne).

Codes carburant traduits selon la documentation officielle TARGA (B=Essence, D=Diesel,
E=Électrique, C=Essence/Électrique, F=Diesel/Électrique, N=CNG, etc.). CO₂ = 0 accepté
uniquement pour les motorisations électriques/hydrogène (E, W, X).

## Ordre de résolution (Phase 2 — `astra_data.resolve_vehicle_data`)

1. **ASTRA TAS local** (recherche par n° d'homologation normalisé)
2. **ASTRA TG local** (historique dès 1995)
3. *(réservé, désactivé)* AutoRef — uniquement si configuré un jour ; aucun appel implémenté
4. *(réservé, désactivé)* NHTSA vPIC — jamais présenté comme homologation suisse
5. Données du scan Claude (carte grise) — flux existant, extrait le n° d'homologation
6. Saisie manuelle

### Limitations explicites

- **Plaque seule : indisponible.** Sans fournisseur externe payant, aucun lien public
  gratuit plaque → véhicule n'existe en Suisse. L'API répond :
  `{"found": false, "reason": "plate_lookup_unavailable_without_external_provider"}`.
  L'UI explique : utiliser le n° d'homologation (case 24), le VIN ou scanner la carte grise.
- **VIN : phase 3.** Le dataset eDatenblatt (~807 Mo, VIN → homologation) sera importé en
  phase 3. En attendant : `{"found": false, "reason": "vin_lookup_requires_edatenblatt"}`.

## Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/astra/status` | État détaillé : datasets, nb documents, fichiers, derniers runs, import en cours |
| POST | `/api/astra/import` | Lance l'import en arrière-plan. Query : `datasets=tas,tg` (défaut tous), `download` (déf. true), `force` (re-télécharge). 409 si déjà en cours |
| GET | `/api/astra/search?homologation=1AA101` | Recherche directe → `{found, provider, fields, variantes, match}` |
| GET | `/api/astra/search?plate=…` / `?vin=…` | Réponses de limitation explicites (voir ci-dessus) |
| POST | `/api/vehicles/{id}/enrich-technical` | Resolver complet pour un véhicule : 200 avec champs à valider, **422** si pas d'homologation, **404** si introuvable, **503** si données non importées |
| POST | `/api/vehicles/{id}/enrich-technical/apply` | Application **après validation utilisateur** uniquement (payload : fields choisis, provider, matched_by) |
| GET | `/api/technical-data/status` | `{configured, provider: "astra"}` selon présence des données |

### Format de résultat de recherche

```json
{
  "provider": "astra_tas",             // ou astra_tg
  "matched_by": "homologation",
  "retrieved_at": "…",
  "lookup_ms": 4.2,                    // objectif < 500 ms (local)
  "match": {"approval_no": "1AA101", "make": "ALFA ROMEO", "model": "145 1.9 TD", "dataset": "TAS"},
  "fields": {"type_carburant": "Diesel", "cylindree_cm3": 1929, "puissance_kw": 66, …},
  "variantes": [ {"label": "Boîte manuelle (5 rapports)", "fields": {…}} ]   // si plusieurs boîtes divergent
}
```

## Règles de fusion / garde-fous (inchangés)

- **Garde CAN/OBD** : tout champ avec `vehicle_field_meta.provider = navixy_can` est exclu
  du lookup ET bloqué à l'apply — une mesure réelle n'est jamais écrasée par une fiche constructeur.
- **Variantes** : si plusieurs lignes d'émissions divergent sans correspondance de boîte,
  la conso/CO₂ est exclue et l'utilisateur doit choisir la variante dans l'UI.
- **Provenance** : à l'apply, `vehicle_field_meta` enregistre `source=external_vehicle_database`,
  `provider=astra_tas|astra_tg`, `retrieved_at`, `validated_by=utilisateur` + entrée d'audit
  « … (source: Base officielle ASTRA/OFROU) ».

## Synchronisation

- **Au démarrage** : si `ASTRA_SYNC_ENABLED=true` (défaut) et collections vides →
  téléchargement + import automatique en arrière-plan.
- **Mensuelle** : job APScheduler (`astra-monthly-sync`, 30 jours) re-télécharge et ré-importe.
- Les fichiers de moins de 25 jours ne sont pas re-téléchargés (sauf `force`).

## Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `ASTRA_DATA_DIR` | `backend/astra_data` | Répertoire des fichiers téléchargés (volume Docker `logitrak-fleet_astra_data` sur VPS) |
| `ASTRA_SYNC_ENABLED` | `true` | Active l'import auto au démarrage + le job mensuel |

Les fichiers sources (~790 Mo) sont exclus de Git (`backend/astra_data/` dans .gitignore)
et du contexte Docker (`.dockerignore`) : sur le VPS ils sont re-téléchargés au premier
démarrage dans le volume dédié.

## Déploiement VPS

1. Save to GitHub → `cd ~/documents && git pull`
2. `cd deploy && docker compose up -d --build`
3. Au premier démarrage, le backend télécharge (~790 Mo) puis importe (~5-10 min).
   Suivi : `curl http://127.0.0.1:8090/api/astra/status`

## Phase 3 (roadmap, non implémentée)

- Import `eDatenblatt.csv` (~807 Mo) → recherche par VIN exact.
- Fallbacks optionnels AutoRef (`AUTOREF_ENABLED`) / NHTSA vPIC (`NHTSA_ENABLED`) —
  uniquement si l'utilisateur fournit accès/documentation fiable.
