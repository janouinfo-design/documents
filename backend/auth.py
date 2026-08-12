"""Authentification JWT — compte superadmin unique (email + mot de passe bcrypt)."""
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def _extract_token(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    token = request.cookies.get("access_token")
    if token:
        return token
    return request.query_params.get("token")


async def authenticate_request(request: Request, db) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expirée — reconnectez-vous")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Jeton invalide")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Jeton invalide")
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


# ---------------------------------------------------------------------------
# Protection force brute — 5 échecs = verrouillage 15 min (par IP + email)
# ---------------------------------------------------------------------------
async def check_lockout(db, identifier: str):
    doc = await db.login_attempts.find_one({"identifier": identifier})
    if not doc or doc.get("count", 0) < MAX_ATTEMPTS:
        return
    last = datetime.fromisoformat(doc["last_at"])
    if datetime.now(timezone.utc) - last < timedelta(minutes=LOCKOUT_MINUTES):
        raise HTTPException(status_code=429,
                            detail=f"Trop de tentatives — réessayez dans {LOCKOUT_MINUTES} minutes.")
    await db.login_attempts.delete_one({"identifier": identifier})


async def record_failure(db, identifier: str):
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1}, "$set": {"last_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True)


async def clear_failures(db, identifier: str):
    await db.login_attempts.delete_one({"identifier": identifier})


async def seed_admin(db):
    """Crée le superadmin depuis .env ; ne touche jamais un mot de passe changé dans l'app
    (sauf ADMIN_FORCE_RESET=true pour récupération)."""
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not password:
        logger.warning("ADMIN_EMAIL/ADMIN_PASSWORD absents — aucun compte superadmin seedé")
        return
    force = (os.environ.get("ADMIN_FORCE_RESET") or "").strip().lower() == "true"
    existing = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc).isoformat()
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email, "name": "Super Admin",
            "role": "superadmin", "password_hash": hash_password(password),
            "password_changed_in_app": False, "created_at": now, "updated_at": now})
        logger.info("Compte superadmin créé: %s", email)
    elif force or (not existing.get("password_changed_in_app")
                   and not verify_password(password, existing.get("password_hash", ""))):
        await db.users.update_one({"email": email}, {"$set": {
            "password_hash": hash_password(password),
            "password_changed_in_app": False, "updated_at": now}})
        logger.info("Mot de passe superadmin resynchronisé depuis .env (%s)", email)
