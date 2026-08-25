# AUDIT ÉTAPE 2 — État complet avant Console Super Admin & Documents V2
Date : 2026-08-25 · Lecture seule (aucun code, aucune écriture Mongo) · Complète et actualise `audit-documents-conformite-v2.md` (933 l., toujours valide pour le détail)

## 0. Contexte
- Production : `d2daec2` déployé et validé (auth 401 partout sans token, Lot 3 Télématique inclus).
- Preview : même code + compteurs actualisés ci-dessous.
- Décision utilisateur : ÉTAPE 2 (cet audit) → Lot 4 Console Super Admin → Lot 5 Documents V2 Phase 1.

## 1. Modèles Mongo actuels (preview actualisé / prod entre parenthèses)
| Collection | Preview | Prod | Structure clé |
|---|---:|---:|---|
| vehicles | 12 | 12 | uuid `id`, tenant_id, ~40 champs techniques + sous-objets `leasing` / `assurance` / `carte_grise` / `controle_technique` + `integrations.navixy` (+ alias racine legacy) |
| documents | 135 (39 actifs) | 5 (1 actif) | id, vehicle_id, tenant_id, **folder** (chaîne), original_filename, storage_path, content_type, size, is_deleted, created_at + sous-ensemble scan : pages[], document_type, extraction_status, source, extracted_fields, validated_fields, document_data |
| files | 15 | 1 | uploads génériques (photos/inspections) |
| inspections | 3 (orphelines) | 2 (orphelines) | états des lieux |
| alerts | 61 | 125 | journal notifications (100 % mocked), dédup non unique |
| audit_logs | 499 | 7 | trace actions |
| vehicle_field_meta | 36 | 0 | provenance par champ (unique vehicle_id+field, non tenantisé) |
| users | 1 (superadmin) | 1 (superadmin) | email unique GLOBAL, bcrypt, token_version, password_changed_in_app |
| tenants | 1 (`default`) | 1 | référentiel tenants |
| tenant_integrations | 1 (navixy/default) | 1 | enabled, base_url, api_hash (jamais exposé), write_enabled, last_sync_at — unique tenant+provider |
- Dates : 100 % chaînes ISO. IDs : 100 % uuid string. Aucun ObjectId exposé.

## 2. Endpoints (contrat de compatibilité à préserver)
- **Documents** : GET/POST `/vehicles/{id}/documents`, DELETE `/documents/{id}` (soft), POST `/vehicles/{id}/documents/scan`, POST `/documents/{id}/validate`, GET `/document-types` (8 types codés en dur), GET `/files/{path}` (tenant + file-token), POST `/upload`.
- **Leasing / Assurance / Contrôle technique** : AUCUN endpoint dédié — lecture via GET `/vehicles/{id}` (sous-objets), écriture via PUT `/vehicles/{id}` (fusion pointée NESTED_SUBDOCS l.734) et POST `/documents/{id}/validate` (OCR→fiche). Consommateurs : `/dashboard`, `/timeline`, `/alerts[/log|/run]`, 3 rapports PDF/CSV, `/vehicles/{id}/history`, `field-meta`.
- FOLDERS backend l.987 = 8 dossiers (SANS « Vignette ») ; UI DocumentsTab = 9 dossiers (AVEC Vignette) → fallback « Divers » = bug connu, corrigé par V2.

## 3. Stockage fichiers
- `STORAGE_BACKEND` : local (VPS `/data/storage`, volume dédié) / emergent (preview). Réfs : `documents.storage_path` + `pages[].storage_path`, `files`, `inspections.photos`.
- SEC-002 actif : allowlist + 25 Mo + tenant check + nosniff + inline restreint + file-token 10 min (JWT session interdit en query).
- ⚠ binaires des documents soft-supprimés jamais purgés (70 preview) — décision V2 : statut ARCHIVED vs purge (plus tard).

## 4. Alertes / Échéances / Dashboard
- Échéances : CALCULÉES à la lecture depuis `vehicles` (aucune collection). 5 dates fixes : leasing.date_fin, assurance.date_echeance, controle.date_prochain, prochaine_expertise, prochaine_maintenance.
- Seuils codés en dur `ALERT_THRESHOLDS` l.358 : leasing [180,90,30], assurance [90,60,30], contrôle [90,60,30,7]. E-mail : MOCKED.
- Dashboard `/api/dashboard` : KPI leasing expirés/bientôt, assurances à renouveler, contrôles à venir, docs manquants (REQUIRED_FOLDERS), coût leasing mensuel, coût assurance annuel, conformité — tout depuis `vehicles.*`.

## 5. Permissions / logique tenant (fondations Console)
- Auth : `require_auth` GLOBAL (JWT Bearer 24 h, bcrypt, token_version/logout, lockout 5×15 min). Seule route publique : POST `/auth/login`.
- **AUCUN contrôle de rôle** : `role` stocké (« superadmin ») mais jamais vérifié ; pas de require_role, pas d'endpoint /tenants ni /users, pas de notion de module. Login = single-account.
- Tenant : TOUJOURS déduit du JWT (request.state), jamais du frontend ; `find_tenant_vehicle` 404 cross-tenant ; isolation testée 10/10 ; intégration Navixy PAR TENANT (fallback env uniquement « default »).
- Réutilisable tel quel pour la Console : tenants, tenant_integrations, isolation, scheduler par tenant.

## 6. Coûts
- MODULE ABSENT. Champs épars : leasing.mensualite_chf/cout_total/cout_mensuel/valeur_residuelle, assurance.prime_annuelle/franchise — agrégés en lecture (dashboard/rapports). `document_data.prix_chf` existe (vignettes) mais non relié.

## 7. Données legacy À PRÉSERVER (règle impérative)
1. `vehicles.assurance/leasing/carte_grise/controle_technique` — **prod : 12/12 signatures DEMO_PROUVÉE (LSG-2022-45xx / POL-78xxxx)** → JAMAIS migrées comme réelles, JAMAIS supprimées sans arbitrage.
2. `documents` existants + storage_path (et binaires) — aucun delete physique.
3. Journal `alerts`, `audit_logs`, `vehicle_field_meta` (provenance) — intacts.
4. Contrat endpoints §2 — dual-read tant que la bascule V2 n'est pas décidée.
5. Le 12e véhicule preview (assurance hors signature seed + divergence active) = artefact de test documenté — ne pas « corriger » silencieusement.

## 8. GAP Console Super Admin (NON RÉALISÉ — à construire au Lot 4)
Manquant : rôles appliqués (require_role), CRUD tenants (créer/désactiver/renommer), CRUD users par tenant (admin client, reset), config intégration Navixy par tenant via UI (api_hash chiffré côté serveur, jamais renvoyé), modules activables par tenant (« documents », extensible), dashboard global par client (véhicules/documents/état intégration), UI /admin réservée superadmin.
Décision utilisateur : compte plateforme dédié `superadmin@logitrak.ch` ; `admin@logitrak.ch` devient admin du client « default » (les 12 véhicules restent chez lui). Accès clients : hub Navixy (iframe) ET documents.logitrak.ch.
⚠ Toute modification d'authentification/rôles passera par `integration_expert` AVANT code.

## 9. Stratégie compatibilité Leasing/Assurance (avant toute modification)
- Phase 1 V2 : documents V2 EN PARALLÈLE — les onglets Leasing/Assurance continuent de lire `vehicles.*` ; AUCUNE migration (données démo prouvées).
- Moteur d'échéances unifié (3.10) : lit (a) documents V2 actifs avec expiry_date, (b) dates legacy `vehicles.*` comme « échéances legacy ». **Anti-double-comptage proposé** : par (véhicule, nature d'échéance), si un document V2 ACTIF de la catégorie correspondante porte une expiry_date, elle remplace la date legacy dans le moteur ; sinon la date legacy reste affichée. → à valider par l'utilisateur.
- Migration réelle assurance/leasing → documents V2 : phase ultérieure, après nettoyage démo arbitré (registre de risques RM1-RM6 de l'audit V2 inchangé).

## 10. Découpage proposé (chaque lot validé séparément, jamais déployé sans GO)
- **Lot 4 — Console Super Admin** : integration_expert (rôles/JWT) → backend require_role + /api/admin/* (tenants, users, integrations, modules, dashboard global) → seed superadmin dédié + bascule admin@logitrak.ch en client default → UI /admin → tests backend+frontend+isolation → validation preview → GO déploiement utilisateur.
- **Lot 5 — Documents V2 Phase 1** (spec utilisateur Étape 3) : document_categories génériques (13 défauts, système+custom par tenant, activer/désactiver/renommer/ordonner/sous-catégories, jamais de suppression physique si utilisée) → modèle document étendu (~23 champs, tous optionnels sauf identité) → moteur statut backend (VALID/EXPIRING_SOON/EXPIRED/MISSING/TO_REVIEW/ARCHIVED) → config centrale seuils (30/60/90 par défaut) → profils documentaires configurables (standard/leasing/acheté/électrique/poids lourd) → versioning remplacement (jamais d'écrasement) → dashboard KPI (sans double comptage) → page Documents centrale (colonnes+filtres+tri+pagination) → section fiche véhicule (présents/requis/manquants/conformité n/m) → moteur échéances unifié §9 → champs coûts (sans module comptable) → tests Étape 4 → rapport Étape 6 → STOP avant déploiement.
- Interdits Phase 1 (rappel utilisateur 3.13) : OCR auto nouveaux, e-mails réels, comptabilité, connexions fournisseurs, workflows validation complexes, suppression legacy.

## 11. Décisions à trancher AVANT d'écrire du code
1. Règle anti-double-comptage échéances legacy vs V2 (§9) — OK ?
2. KPI coûts actuels du dashboard continuent d'afficher les montants DÉMO du tenant default tant que rien n'est nettoyé — assumé ?
3. Lot 4 : le seed du superadmin plateforme (variables env dédiées vs création manuelle) sera arbitré avec le playbook integration_expert — d'accord ?
4. Profils documentaires (3.5) : affectation d'un profil PAR VÉHICULE (champ profil sur le véhicule) ou déduction par attributs (type carburant/leasing présent) ? Recommandation : champ explicite + suggestions, jamais de déduction silencieuse.
