# Audit Étape 4 — Échéances documentaires + alertes centralisées (lecture seule, avant code)

Date : 2026-06 · Base : worktree courant (post V2 étapes 1–3, préview uniquement)

## 1. Producteurs de calculs d'échéances existants (AVANT étape 4)

| # | Producteur | Fichier / lignes | Seuils | Source de données |
|---|---|---|---|---|
| 1 | `days_until` | server.py l.726 | — | helper date→jours, null-safe (None) |
| 2 | `level_from_days` | server.py l.736 | 30/90 codés en dur | expired/critical/warning/ok/unknown |
| 3 | `compute_metrics` | server.py l.759 | via level_from_days | sous-objets legacy `leasing.date_fin`, `assurance.date_echeance`, `controle_technique.date_prochain` |
| 4 | `GET /api/dashboard` | server.py l.1584 | 30/90 en dur, calcul INLINE indépendant | documents V2 seuls (docs_expires/30/31-90) + compute_metrics + conformité |
| 5 | `GET /api/timeline` | server.py l.1664 | via level_from_days | legacy uniquement + prochaine_expertise/maintenance — les documents V2 étaient INVISIBLES |
| 6 | `GET /api/alerts` | server.py l.2036 | via compute_metrics | legacy uniquement |
| 7 | `run_alerts` | server.py l.1963 | ALERT_THRESHOLDS en dur (l.528) | legacy uniquement, dédup {vehicle_id,type,threshold,due_date} |
| 8 | `GET /api/documents?echeance=` | server.py l.1481 | 30/90 en dur INLINE | documents V2 |
| 9 | `doc_statut` (fiche V2) | server.py l.1191 | preavis_jours (défaut 30) | statut de fiche (VALIDE/EXPIRE_BIENTOT/…) — concept distinct de l'urgence |
| 10 | Conformité (`manquants`) | server.py l.1375 + dashboard | — | catégories requises ; manquant ≠ expiré (déjà séparés) |

Consommateurs frontend : Dashboard.jsx (getDashboard + getTimeline ≤90 en dur), TimelinePage.jsx (getTimeline legacy), AlertsPage.jsx (getAlerts, libellés seuils en dur), DocumentsPage.jsx (filtre échéance libellés en dur), VehicleDrawer/Vehicles (metrics), reports (PDF/CSV via compute_metrics).

## 2. Écarts constatés

- Au moins **4 calculs indépendants** (dashboard inline, filtre documents, timeline, alertes) au lieu d'un moteur unique.
- Les échéances des **documents V2 n'apparaissaient ni dans la page Échéances, ni dans les alertes**.
- Aucun seuil configurable par tenant ; 30/90 et ALERT_THRESHOLDS codés en dur.
- Aucun affichage du responsable.
- Pas de dual-read : dashboard docs_* comptait V2 seul ; timeline/alertes legacy seul.

## 3. Décisions d'architecture (Étape 4)

### Moteur unique
`collect_deadlines(tenant_id, th)` (server.py, section « Étape 4 ») = SOURCE DE VÉRITÉ.
Statuts : `EXPIRE` / `URGENT` (≤ urgent_days) / `A_PLANIFIER` (≤ warning_days) / `OK` / `SANS_ECHEANCE` (date absente — jamais interprétée comme 0) / `DATE_INVALIDE` (date non parsable). Tri : urgence d'abord puis chronologique.

### Dual-read / anti-doublon
- Clés canoniques : `doc:{document_id}` (V2) et `legacy:{vehicle_id}:{type}` (sous-objets véhicule).
- Équivalent V2 = document actif (non supprimé, non archivé) du même véhicule ET de la même catégorie AVEC une date d'expiration valide → masque la source legacy de cette catégorie.
- Document V2 sans date ou à date invalide ne masque PAS le legacy (aucune perte d'échéance).
- Legacy → catégories : leasing→Leasing, assurance→Assurance, controle→Contrôle technique (+ expertise/maintenance racine, `is_document_deadline=false`, jamais comptés dans les KPIs documents).
- Aucune suppression ni migration des champs legacy.

### Seuils par tenant
Collection `tenant_settings` {tenant_id, deadline_urgent_days, deadline_warning_days}. Défauts préservés : 30/90. `GET/PUT /api/settings/deadlines` (PUT admin/superadmin, validation 1 ≤ urgent < warning ≤ 730). `level_from_days`/`compute_metrics`/`doc_statut` paramétrés par ces seuils → fiche véhicule alignée moteur.

### Consommateurs rebranchés (aucun calcul indépendant restant)
- `GET /api/deadlines` (nouveau) : items + summary + thresholds, filtres vehicle_id/category/statut/days.
- `GET /api/dashboard` : docs_expires/docs_expire_30/docs_expire_31_90 = summary.documents du moteur ; documents_missing inchangé (conformité, jamais mélangé aux expirés).
- `GET /api/timeline` : adaptateur rétro-compatible sur le moteur (items datés, tri chronologique).
- `GET /api/alerts` + `run_alerts` : alimentés par le moteur. Legacy : seuils ALERT_THRESHOLDS + clé dédup historique inchangée (aucune ré-alerte en double). Documents V2 : seuils tenant, clé canonique {vehicle_id, type:"document", document_id, category, threshold, due_date}. Emails restent MOCKÉS.
- `GET /api/documents?echeance=` : bornes = seuils tenant.

### Interdits respectés
Pas de coûts historisés, pas de migration destructive legacy, pas d'e-mail/SMS réel, pas de déploiement production.
