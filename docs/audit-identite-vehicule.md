# AUDIT — Identité véhicule côté FLEET ADMIN (LOGITRAK Documents)

Statut : AUDIT READ-ONLY — RIEN N'EST CODÉ dans ce document.
Périmètre : projet Documents / Fleet Admin uniquement (fournisseur du Vehicle Core).
Données chiffrées : environnement preview (la production peut différer ; un audit
Mongo read-only prod est possible via `deploy/audit-mongo-prod-readonly.js`).
Complète : `docs/audit-vehicle-core.md`, `docs/inter-project-vehicle-contract.md`.

---

## A. Inventaire des identifiants portés par `vehicles`

| Champ | Type | Rôle | Unicité | Index |
|---|---|---|---|---|
| `id` | uuid4 string | **Clé technique LOGITRAK, stable, jamais remplacée** | unique de fait (uuid) | `_id` implicite ; requêtes toujours `{id, tenant_id}` |
| `vin` | string optionnel | identification forte / contrôle | non contrainte DB ; collision bloquée applicativement | aucun |
| `navixy_tracker_id` | int optionnel | rattachement au boîtier Navixy (identité de sync) | non contrainte DB ; unique de fait | index non-unique (`create_index("navixy_tracker_id")`) |
| `navixy_vehicle_id` | int optionnel | fiche « Gestion de flotte » Navixy liée | non contrainte DB | aucun |
| `plaque` | string | affichage / recherche humaine | non unique (plaques réutilisables) | aucun |
| id métier partagé inter-projets | — | **N'EXISTE PAS** côté Fleet Admin | — | — |

---

## B. Audit VIN (FLEET ADMIN)

- **Stockage** : `vehicles.vin`, renseigné sur une partie de la flotte seulement
  (preview tenant `default` : 6 véhicules sur 15).
- **Alimentation** : OCR carte grise → review → **validation humaine obligatoire**
  (les caractères ambigus OCR ne sont jamais auto-corrigés) ; saisie manuelle.
  La sync Navixy → Documents n'écrase PAS le VIN local.
- **Sortant** : le VIN fait partie de `NAVIXY_PUSH_KEYS` (server.py:388) — poussé
  Documents → Navixy (normalisé `_norm_vin` : majuscules, alphanumérique).
- **Protection collision** : à l'application de champs OCR, un VIN appartenant à un
  autre véhicule du MÊME tenant est refusé (`VIN_BELONGS_TO_ANOTHER_VEHICLE`,
  server.py:2836/3095). Contrôle de plausibilité `vin_check` exposé (server.py:1015).
- **Limites constatées** :
  - pas d'index ni de contrainte d'unicité `(tenant_id, vin normalisé)` en base —
    la protection est applicative (chemin OCR) ; une écriture directe PATCH pourrait
    théoriquement créer un doublon ;
  - le VIN n'est pas normalisé à l'écriture partout (le resolver normalise à la lecture).
- **État des données (preview)** : 0 doublon VIN par tenant.

## C. Audit navixy_tracker_id + modélisation du traceur (FLEET ADMIN)

- **Stockage** : `vehicles.navixy_tracker_id` (int), index non-unique.
- **Alimentation** : exclusivement par la sync Navixy (`/tracker/list`), upsert par
  `{tenant_id, navixy_tracker_id}` ; jamais saisi à la main, jamais déduit d'un
  matching flou plaque/VIN (invariant projet).
- **Modélisation : ATTRIBUT FIXE du véhicule — PAS une affectation évolutive.**
  - Aucune collection d'historique d'affectation (`tracker_assignments` ou
    équivalent : inexistante).
  - Aucune trace datée « tracker X posé sur véhicule Y du … au … ». Seuls
    `audit_logs` (liaisons, `navixy_absent`) donnent une trace événementielle
    partielle, non structurée pour la jointure.
  - Conséquence documentée : si un client **réaffecte physiquement un boîtier** à un
    autre véhicule dans le même compte Navixy, la sync (upsert par tracker_id) fera
    « suivre » la fiche LOGITRAK au boîtier, pas au véhicule physique — les documents
    (assurance, CG) resteraient attachés à la mauvaise identité. Risque réel, non
    couvert aujourd'hui.
  - Couvert depuis 2026-09 : tracker **disparu du compte** → marquage
    `navixy_absent` (jamais de suppression auto), suppression manuelle, archive,
    transfert inter-comptes, restauration.
- **État des données (preview)** : `default` 14/15 avec tracker, 0 doublon
  `(tenant, tracker_id)` ; `navixy_vehicle_id` : 5/15.

## D. Ordre de jointure inter-projets — exigence et écarts

### D.1 Exigence (règle cible)
Jointure d'identité véhicule entre projets, dans cet ordre strict :

1. **UUID commun** (`vehicle_id` LOGITRAK) ;
2. **VIN** (normalisé) ;
3. **id métier partagé** (numéro de flotte commun aux projets) ;
4. **tracker_id** — **uniquement si un historique d'affectation est maintenu** ;
5. **plaque** — **rapprochement MANUEL uniquement**, jamais automatique.

### D.2 Ordre réellement implémenté (`GET /api/vehicles/resolve`, server.py:930)
`vehicle_id` → `navixy_vehicle_id` → `navixy_tracker_id` → `vin` → `plate`,
ambiguïté (>1 résultat) = arrêt immédiat `ambiguous`, lecture seule stricte.

### D.3 Écarts constatés (règle cible vs implémentation)

| # | Écart | Gravité |
|---|---|---|
| 1 | Le VIN passe APRÈS `navixy_vehicle_id`/`navixy_tracker_id` dans le resolver, alors que la règle cible le place juste après l'UUID | moyen |
| 2 | `tracker_id` est utilisé comme clé de jointure automatique **sans historique d'affectation** (C) — la règle cible l'interdit dans ce cas | **élevé** (risque de jointure sur boîtier réaffecté) |
| 3 | La `plaque` est matchée automatiquement (dernier critère) — la règle cible la réserve au rapprochement **manuel** | moyen |
| 4 | Aucun « id métier partagé » n'existe côté Fleet Admin (pas de champ type `fleet_number`) — le niveau 3 de la règle est inapplicable en l'état | info |

### D.4 Mise en conformité (décision : point 1 APPLIQUÉ le 2026-09 ; 2-4 au backlog)

1. **Resolver — APPLIQUÉ** : ordre `vehicle_id` → `vin` → `navixy_vehicle_id` →
   `navixy_tracker_id` (réponse `found` assortie de
   `"warning": "tracker_join_no_assignment_history"`) → `plate` retirée du match
   automatique : réponse `manual_review` avec candidats, jamais `found`.
   Contrat `inter-project-vehicle-contract.md` §2 mis à jour en conséquence.
2. **Historique d'affectation traceur** (si souhaité) : collection
   `tracker_assignments` `{tenant_id, tracker_id, vehicle_id, from, to}` alimentée
   par la sync quand `navixy_tracker_id` apparaît/disparaît/change de véhicule —
   condition pour ré-autoriser la jointure automatique par tracker.
3. **VIN** : normalisation à l'écriture + index `(tenant_id, vin_normalisé)` partiel
   unique (vin non vide) pour transformer la garde applicative en contrainte DB.
4. **Id métier partagé** : à définir dans le contrat inter-projets (v0.1-draft, non
   figé) AVANT introduction d'un champ — pas de champ inventé unilatéralement.

⚠️ Le contrat `inter-project-vehicle-contract.md` est en v0.1-draft (« sera figé
APRÈS l'audit des projets ») : modifier l'ordre du resolver est encore possible sans
casser de consommateur figé, mais doit être répercuté dans le contrat et annoncé aux
projets Journal de bord / Énergie / New Navixy.
