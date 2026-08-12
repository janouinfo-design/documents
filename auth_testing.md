# Auth Testing Playbook — LogiTrak Documents

## Step 1: MongoDB Verification
```
mongosh
use <DB_NAME de backend/.env>
db.users.find({role: "superadmin"}).pretty()
db.users.findOne({role: "superadmin"}, {password_hash: 1})
```
Verify: bcrypt hash starts with `$2b$`, unique index on users.email, index on login_attempts.identifier.

## Step 2: API Testing (Bearer token, PAS de cookies)
```
# Login
curl -X POST {BASE_URL}/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"admin@logitrak.ch","password":"<voir memory/test_credentials.md>"}'
# → {"token": "...", "user": {...}}

# Me
curl {BASE_URL}/api/auth/me -H "Authorization: Bearer <token>"

# Route protégée sans token → 401
curl -i {BASE_URL}/api/vehicles

# Route protégée avec token → 200
curl {BASE_URL}/api/vehicles -H "Authorization: Bearer <token>"

# Téléchargement direct avec token en query param → 200
curl -o /dev/null -w "%{http_code}" "{BASE_URL}/api/reports/conformite.pdf?token=<token>"

# Mauvais mot de passe → 401 ; 5 échecs consécutifs → 429 (verrou 15 min).
# ATTENTION: nettoyer db.login_attempts après le test de brute force pour ne pas verrouiller le compte des tests suivants.

# Changement de mot de passe
curl -X POST {BASE_URL}/api/auth/change-password -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" -d '{"current_password":"...","new_password":"..."}'
# IMPORTANT: remettre le mot de passe d'origine après le test (nouveau login puis change-password inverse),
# sinon le conftest des tests pytest ne pourra plus se connecter.
```

## Step 3: Frontend
- Sans token: toute page → redirection /login (spinner puis redirect).
- Login mauvais mot de passe → login-error visible.
- Login OK → dashboard, user-menu-btn dans le header (email), items « Changer le mot de passe » et « Se déconnecter ».
- Déconnexion → retour /login, localStorage lt_token vidé.
- Session: token stocké dans localStorage `lt_token`; axios interceptor ajoute Authorization; 401 → purge + redirect /login.
