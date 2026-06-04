# Déploiement VPS — LogiTrak · Gestion administrative de flotte

Stack **isolé et autonome** (Docker Compose) : frontend (React build servi par Nginx) +
backend (FastAPI) + MongoDB **dédié** + stockage fichiers sur **disque local**.
Tout est préfixé `logitrak-fleet_` → **aucun conflit** avec vos autres apps (Navixy, dashboard…).

```
┌─────────────── VPS ───────────────┐
│ Nginx hôte (flotte.VOTRE_DOMAINE) │
│        │ proxy → 127.0.0.1:8090   │
│  ┌─────▼──── docker (logitrak-fleet) ─────┐
│  │  web (Nginx+SPA)  →  backend (FastAPI) │
│  │                         │     │        │
│  │                       mongo  volume    │
│  │                     (dédié) (stockage) │
│  └────────────────────────────────────────┘
└────────────────────────────────────────────┘
```

## 1. Prérequis (sur le VPS)
- Docker + plugin Compose : `docker --version` et `docker compose version`
- Nginx hôte déjà en place (vos autres apps l'utilisent)
- Un sous-domaine **libre** pointant vers le VPS (ex : `flotte.VOTRE_DOMAINE`)

## 2. Récupérer le code
Poussez le projet sur GitHub depuis Emergent (bouton **Save to GitHub**) puis :
```bash
git clone <votre-repo> logitrak-flotte
cd logitrak-flotte/deploy
```

## 3. Configurer
```bash
cp .env.example .env
nano .env
```
- `APP_PORT` : un port **libre** (par défaut 8090)
- `DB_NAME` : laissez `logitrak_fleet` (base dédiée)
- `NAVIXY_API_HASH` : votre clé Navixy (région EU par défaut)
- `EMERGENT_LLM_KEY` : (optionnel, pour l'OCR carte grise) — à remplir plus tard
- `EMAIL_*` : (optionnel) pour l'envoi réel des alertes

## 4. Démarrer
```bash
docker compose up -d --build
```
Vérifier :
```bash
docker compose ps
curl http://127.0.0.1:8090/api/vehicles   # doit répondre du JSON
```

## 5. Exposer via votre Nginx hôte
```bash
sudo cp nginx-host.conf.example /etc/nginx/sites-available/flotte
sudo nano /etc/nginx/sites-available/flotte      # remplacez flotte.VOTRE_DOMAINE + APP_PORT
sudo ln -s /etc/nginx/sites-available/flotte /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d flotte.VOTRE_DOMAINE     # SSL Let's Encrypt
```
➡️ L'app est accessible sur `https://flotte.VOTRE_DOMAINE`.

## 6. Isolation garantie
| Élément | Nom dédié |
|--------|-----------|
| Conteneurs | `logitrak-fleet_web`, `_backend`, `_mongo` |
| Réseau Docker | `logitrak-fleet_net` |
| Volume base de données | `logitrak-fleet_mongo_data` |
| Volume fichiers/photos | `logitrak-fleet_storage_data` |
| Port hôte | `APP_PORT` (un seul, configurable) |

Rien n'est partagé avec vos autres apps. MongoDB et le stockage ne sont **pas** exposés publiquement (réseau interne uniquement).

## 7. Exploitation
```bash
docker compose logs -f backend        # logs backend
docker compose restart backend        # redémarrer
docker compose up -d --build          # mettre à jour après git pull
docker compose down                   # arrêter (conserve les données)
```

### Sauvegardes
```bash
# Base de données
docker exec logitrak-fleet_mongo sh -c 'mongodump --archive' > backup_$(date +%F).archive
# Fichiers
docker run --rm -v logitrak-fleet_storage_data:/data -v $PWD:/out alpine \
  tar czf /out/storage_$(date +%F).tgz -C /data .
```

## 8. Activer l'OCR (plus tard)
1. Renseignez `EMERGENT_LLM_KEY` (Profil → Universal Key) dans `.env`.
2. `docker compose up -d --build backend`.
L'onglet « Carte grise » lira alors automatiquement plaque, VIN, date, poids, places.

## 9. Activer l'e-mail réel (optionnel)
Renseignez dans `.env` : `EMAIL_PROVIDER` (resend|sendgrid), `EMAIL_API_KEY`,
`EMAIL_FROM` (expéditeur vérifié), `ALERT_RECIPIENTS` (séparés par des virgules),
puis `docker compose up -d backend`. Les alertes passent de « simulé » à « envoyé ».

## Notes techniques
- Le backend bascule automatiquement sur le **stockage disque** via `STORAGE_BACKEND=local`
  (défini dans `docker-compose.yml`) — indépendant de l'object storage Emergent.
- Le frontend appelle l'API en **same-origin** (`/api`), proxifié par le gateway Nginx du stack.
- Synchronisation Navixy automatique **1×/jour** + au démarrage du backend.
