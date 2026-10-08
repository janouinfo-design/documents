#!/usr/bin/env bash
# Validation PRODUCTION du conteneur backend (clôture Lot F, étendu Lot G) — à exécuter SUR LE VPS, dans un environnement Docker-capable.
# 100 % isolé : image taguée `:validate`, Mongo éphémère, réseau/conteneurs préfixés `logitrak-validate_`, base jetable.
# NE TOUCHE PAS au stack `logitrak-fleet_*` en production, ni à ses volumes, ni à sa base. Aucune donnée réelle.
#
# Contrôles : build image · imports Python des modules Lot A-F dans l'image (0 ModuleNotFoundError) · démarrage uvicorn sans erreur
# ("Application startup complete") · smoke runtime sur des GET existants non destructifs (pas d'endpoint /api/health dédié à ce jour) :
#   GET /api/vehicles sans jeton → 401 · POST /api/auth/login (superadmin seedé depuis ADMIN_EMAIL/ADMIN_PASSWORD jetables) → 200
#   GET /api/fuel-cards (Lot E) · GET /api/fuel/import-fields · GET /api/fuel/imports · GET /api/fuel/anomalies · GET /api/tenant-settings/fuel (Lot F) → 200
# Usage : bash deploy/validate-backend-docker.sh            (depuis la racine du dépôt cloné sur le VPS)
#         KEEP=1 bash deploy/validate-backend-docker.sh     (conserver les conteneurs pour inspection)
set -uo pipefail
cd "$(dirname "$0")/.."

TAG="logitrak-fleet_backend:validate"
NET="logitrak-validate_net"
MONGO="logitrak-validate_mongo"
BACK="logitrak-validate_backend"
PORT="${VALIDATE_PORT:-18001}"
ADMIN_EMAIL="validate-$(date +%s)@validate.local"
ADMIN_PASSWORD="$(openssl rand -hex 12)"
JWT_SECRET="$(openssl rand -hex 32)"
PASS=0; FAIL=0
ok()   { echo "  [PASS] $*"; PASS=$((PASS+1)); }
ko()   { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    docker rm -f "$BACK" "$MONGO" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
  else
    echo "KEEP=1 : conteneurs $BACK / $MONGO conservés (docker logs $BACK)."
  fi
}
trap cleanup EXIT

echo "== 0. Pré-requis"
command -v docker >/dev/null 2>&1 || { echo "DOCKER PRODUCTION RUNTIME = NON VÉRIFIABLE DANS CET ENVIRONNEMENT (docker absent)"; exit 3; }
docker info >/dev/null 2>&1 || { echo "Docker présent mais daemon inaccessible (droits ?) — validation impossible."; exit 3; }
echo "  docker: $(docker --version)"

echo "== 1. Build image backend ($TAG)"
if docker build -t "$TAG" backend/ > /tmp/logitrak-validate-build.log 2>&1; then ok "docker build OK (log : /tmp/logitrak-validate-build.log)"; else ko "docker build KO — voir /tmp/logitrak-validate-build.log"; tail -30 /tmp/logitrak-validate-build.log; exit 1; fi

echo "== 2. Modules présents dans l'image + imports Python (sans démarrer l'app)"
EXPECTED_FILES="server.py storage.py extraction.py technical_data.py astra_data.py reports.py auth.py legacy_identity.py nofile.py drivers.py fines.py fuel_cards.py fuel_import.py fuel_matching.py fuel_anomalies.py fuel_statements.py"
MISSING=$(docker run --rm "$TAG" sh -c "cd /app && for f in $EXPECTED_FILES; do [ -f \$f ] || echo \$f; done")
if [ -z "$MISSING" ]; then ok "16 fichiers Python présents dans /app de l'image"; else ko "fichiers absents de l'image : $MISSING"; fi
IMPORT_OUT=$(docker run --rm -e MONGO_URL=mongodb://unused:27017 -e DB_NAME=validate -e JWT_SECRET=x "$TAG" \
  python -c "import fuel_cards, fuel_import, fuel_matching, fuel_anomalies, fuel_statements, legacy_identity, nofile, drivers, fines, auth, storage, reports, extraction, astra_data, technical_data; import server; print('IMPORTS_OK', fuel_matching.POINTS['card_assignment'], fuel_matching.POINTS['direct_vehicle_id'], len(fuel_statements.RECO_STATUSES), len(fuel_statements.BLOCKER_TYPES))" 2>&1)
if echo "$IMPORT_OUT" | grep -q "IMPORTS_OK 90 100 4 5"; then ok "imports Lot A-G + server OK (card_assignment=90, direct_vehicle_id=100, 4 statuts rapprochement, 5 blockers) — 0 ModuleNotFoundError"; else ko "imports KO : $(echo "$IMPORT_OUT" | tail -5)"; fi

echo "== 3. Mongo éphémère + démarrage backend"
docker network create "$NET" >/dev/null 2>&1 || true
docker rm -f "$MONGO" "$BACK" >/dev/null 2>&1 || true
docker run -d --name "$MONGO" --network "$NET" mongo:7 >/dev/null
for i in $(seq 1 30); do docker exec "$MONGO" mongosh --quiet --eval "db.adminCommand('ping').ok" 2>/dev/null | grep -q 1 && break; sleep 1; done
docker run -d --name "$BACK" --network "$NET" -p "127.0.0.1:${PORT}:8001" \
  -e MONGO_URL="mongodb://${MONGO}:27017" -e DB_NAME="logitrak_validate_$(date +%s)" -e JWT_SECRET="$JWT_SECRET" \
  -e ADMIN_EMAIL="$ADMIN_EMAIL" -e ADMIN_PASSWORD="$ADMIN_PASSWORD" -e STORAGE_BACKEND=local -e LOCAL_STORAGE_DIR=/data/storage \
  -e ASTRA_DATA_DIR=/data/astra -e SEED_DEMO_DATA=false -e CORS_ORIGINS="*" "$TAG" >/dev/null
STARTED=0
for i in $(seq 1 60); do
  if docker logs "$BACK" 2>&1 | grep -q "Application startup complete"; then STARTED=1; break; fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$BACK" 2>/dev/null)" != "true" ]; then break; fi
  sleep 1
done
if [ "$STARTED" = "1" ]; then ok "uvicorn : 'Application startup complete' en ${i}s"; else ko "backend non démarré — logs :"; docker logs "$BACK" 2>&1 | tail -40; fi
if docker logs "$BACK" 2>&1 | grep -qiE "ModuleNotFoundError|ImportError|Traceback"; then ko "erreur Python au démarrage (voir docker logs $BACK)"; docker logs "$BACK" 2>&1 | grep -iE -A3 "ModuleNotFoundError|ImportError|Traceback" | head -20; else ok "aucun ModuleNotFoundError / ImportError / Traceback dans les logs de démarrage"; fi
docker logs "$BACK" 2>&1 | grep -q "Scheduler started" && ok "scheduler démarré" || echo "  [INFO] scheduler non signalé (NAVIXY non configuré : attendu)"

echo "== 4. Smoke runtime (GET existants, non destructifs)"
B="http://127.0.0.1:${PORT}"
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
[ "$(code "$B/api/vehicles")" = "401" ] && ok "GET /api/vehicles sans jeton → 401 (auth active)" || ko "GET /api/vehicles sans jeton → $(code "$B/api/vehicles") (attendu 401)"
TOKEN=$(curl -s -X POST "$B/api/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
if [ -n "$TOKEN" ]; then ok "POST /api/auth/login (superadmin seedé) → jeton"; else ko "login superadmin KO"; fi
H="Authorization: Bearer $TOKEN"
for ep in /api/vehicles /api/fuel-cards /api/fuel/import-fields /api/fuel/imports /api/fuel/anomalies /api/tenant-settings/fuel /api/energy /api/fuel/statements /api/tenant-settings/fuel/reconciliation; do
  c=$(code -H "$H" "$B$ep"); [ "$c" = "200" ] && ok "GET $ep → 200" || ko "GET $ep → $c (attendu 200)"
done
[ "$(code -H "$H" "$B/api/fuel/imports/00000000-0000-0000-0000-000000000000")" = "404" ] && ok "GET /api/fuel/imports/{inconnu} → 404 (fail-closed)" || ko "GET /api/fuel/imports/{inconnu} ≠ 404"
[ "$(code -H "$H" "$B/api/fuel/statements/00000000-0000-0000-0000-000000000000")" = "404" ] && ok "GET /api/fuel/statements/{inconnu} → 404 (fail-closed, Lot G)" || ko "GET /api/fuel/statements/{inconnu} ≠ 404"
[ "$(code -H "$H" "$B/api/fuel/reconciliations")" = "422" ] && ok "GET /api/fuel/reconciliations sans period_month → 422 (Lot G)" || ko "GET /api/fuel/reconciliations sans period_month ≠ 422"
RECO=$(curl -s -H "$H" "$B/api/tenant-settings/fuel/reconciliation")
echo "$RECO" | grep -q '"threshold_pct":null' && echo "$RECO" | grep -q '"threshold_l":null' && ok "tenant-settings/fuel/reconciliation : seuils null par défaut (Lot G)" || ko "tenant-settings/fuel/reconciliation inattendu : $RECO"
FIELDS=$(curl -s -H "$H" "$B/api/fuel/import-fields" | grep -o '"key"' | wc -l | tr -d ' ')
[ "$FIELDS" -ge 15 ] && ok "import-fields : $FIELDS champs cibles" || ko "import-fields : $FIELDS champs (attendu ≥ 15)"
SETTINGS=$(curl -s -H "$H" "$B/api/tenant-settings/fuel")
echo "$SETTINGS" | grep -q '"score_auto":90' && echo "$SETTINGS" | grep -q '"score_review":70' && ok "tenant-settings/fuel : score_auto=90, score_review=70" || ko "tenant-settings/fuel inattendu : $SETTINGS"

echo "== 5. Résultat"
echo "  PASS=$PASS FAIL=$FAIL"
if [ "$FAIL" = "0" ]; then echo "DOCKER BACKEND VALIDATION = PASS (image $TAG, exécution réelle sur $(hostname) le $(date -u +%FT%TZ))"; exit 0; else echo "DOCKER BACKEND VALIDATION = FAIL"; exit 1; fi
