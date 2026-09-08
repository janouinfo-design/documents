# Procédure de mise en production — Scanner mobile V2 + badge « à vérifier »

> **PRÉREQUIS ABSOLU : GO explicite « GO déploiement VPS Documents ».**
> Sans ce GO, ne rien exécuter sur le VPS.

## Contenu du lot
- **Scanner mobile V2** (frontend uniquement) : capture caméra mobile, multi-pages,
  rotation/suppression/réordonnancement, compression client, fallback « Ouvrir dans le
  navigateur » (`/scan/:vehicleId?type=…`, sans token), retour post-login sur la même fiche.
  Fichiers : `ScanDocumentDialog.jsx`, `ScanPage.jsx` (nouveau), `Login.jsx`,
  `DocumentScanCard.jsx`, `App.js`.
- **Badge menu Documents** : compteur de scans analysés en attente de validation.
  Fichiers : `Layout.jsx`, `api.js` + **backend** : endpoint
  `GET /api/documents/pending-review-count` dans `server.py`.

## Vérification Dockerfile (faite — rien à changer)
- Backend : seul `server.py` est modifié → déjà présent dans la ligne
  `COPY server.py storage.py extraction.py technical_data.py astra_data.py reports.py auth.py ./`
  Aucun nouveau module backend, aucune nouvelle dépendance pip.
- Frontend : `ScanPage.jsx` est dans `src/` → copié automatiquement par le build.
- Aucun changement `.env`, aucune migration DB, aucun changement Nginx.

## Étapes (sur le VPS)
1. Depuis Emergent : **Save to GitHub** (pousser le code à jour).
2. Sur le VPS :
   ```bash
   cd ~/documents            # racine du clone (celle qui contient deploy/)
   git pull
   cd deploy
   docker compose up -d --build backend web
   ```
3. Vérifications post-déploiement :
   ```bash
   docker compose ps                                  # tous les services "running"
   curl -s https://documents.logitrak.ch/api/health   # ou la route de santé habituelle
   ```
   Puis dans un navigateur :
   - Login → badge ambre éventuel sur l'onglet **Documents** (si scans en attente).
   - Fiche véhicule → Documents → « Ajouter un document » → modale scanner OK.
   - Sur téléphone : « Scanner avec l'appareil photo » → capture → recadrage → Analyser.
   - Depuis le hub/WebView : panneau « Ouvrir dans le navigateur » → reconnexion →
     retour automatique sur la même fiche.
4. En cas de problème : `docker compose logs --tail=100 backend web`

## Rollback
```bash
git log --oneline -5        # repérer le commit précédent
git checkout <commit-precedent> -- .
docker compose up -d --build backend web
```
(ou re-pull d'un tag/branche stable). Aucune donnée n'est migrée par ce lot :
le rollback code est sans risque pour la base.
