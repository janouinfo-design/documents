from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import base64
import json
import asyncio
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta

from extraction import (DOC_TYPES, FIELD_DEFS, check_image_quality, enhance_and_pdf, get_provider,
                        pdf_to_images_b64, prepare_image_b64, normalize_value)
from reports import build_conformity_pdf, build_costs_csv, build_vehicle_pdf
from technical_data import TECH_FIELD_DEFS
import astra_data
from astra_data import AstraLookupError
from auth import (authenticate_request, check_lockout, clear_failures, create_access_token,
                  hash_password, record_failure, seed_admin, verify_password)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="LogiTrak - Gestion Administrative de Flotte")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authentification — superadmin unique (JWT Bearer 24 h)
# ---------------------------------------------------------------------------
auth_router = APIRouter(prefix="/api/auth")


async def require_auth(request: Request) -> dict:
    return await authenticate_request(request, db)


class LoginPayload(BaseModel):
    email: str
    password: str


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str


@auth_router.post("/login")
async def auth_login(payload: LoginPayload, request: Request):
    email = payload.email.strip().lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}|{email}"
    await check_lockout(db, identifier)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        await record_failure(db, identifier)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    await clear_failures(db, identifier)
    safe = {k: v for k, v in user.items() if k not in ("_id", "password_hash")}
    return {"token": create_access_token(user["id"], user["email"]), "user": safe}


@auth_router.get("/me")
async def auth_me(user: dict = Depends(require_auth)):
    return user


@auth_router.post("/change-password")
async def auth_change_password(payload: ChangePasswordPayload, user: dict = Depends(require_auth)):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="Le nouveau mot de passe doit contenir au moins 8 caractères.")
    full = await db.users.find_one({"id": user["id"]})
    if not full or not verify_password(payload.current_password, full.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    await db.users.update_one({"id": user["id"]}, {"$set": {
        "password_hash": hash_password(payload.new_password),
        "password_changed_in_app": True,
        "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "ok"}


@auth_router.post("/logout")
async def auth_logout(user: dict = Depends(require_auth)):
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Object storage helpers (Emergent object storage)
# ---------------------------------------------------------------------------
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
APP_NAME = "logitrak-fleet"
extraction_provider = get_provider(EMERGENT_KEY, ANTHROPIC_KEY)
storage_key = None
STORAGE_BACKEND = (os.environ.get("STORAGE_BACKEND") or "emergent").lower()
LOCAL_STORAGE_DIR = os.environ.get("ADMIN_DOCS_STORAGE_PATH") or os.environ.get("LOCAL_STORAGE_DIR") or "/data/storage"
MAX_FILE_SIZE_MB = int(os.environ.get("ADMIN_DOCS_MAX_FILE_SIZE_MB", "25"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
_DEFAULT_DOC_TYPES = "pdf,jpg,jpeg,png,webp,docx,doc,xls,xlsx,zip,csv"
ALLOWED_DOC_EXTS = {e.strip().lower().lstrip(".") for e in (os.environ.get("ADMIN_DOCS_ALLOWED_TYPES") or _DEFAULT_DOC_TYPES).split(",") if e.strip()}
ALLOWED_MEDIA_EXTS = ALLOWED_DOC_EXTS | {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"}

EXT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip", "csv": "text/csv", "txt": "text/plain",
    "mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm",
}


def _local_path(path: str) -> str:
    base = os.path.abspath(LOCAL_STORAGE_DIR)
    full = os.path.abspath(os.path.join(base, path))
    if full != base and not full.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Chemin invalide")
    return full


def init_storage():
    global storage_key
    if STORAGE_BACKEND == "local":
        os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)
        return "local"
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    if STORAGE_BACKEND == "local":
        full = _local_path(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        with open(full + ".meta", "w") as f:
            f.write(content_type or "application/octet-stream")
        return {"path": path, "size": len(data)}
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    if STORAGE_BACKEND == "local":
        full = _local_path(path)
        if not os.path.exists(full):
            raise FileNotFoundError(path)
        with open(full, "rb") as f:
            data = f.read()
        ctype = guess_mime(path)
        if os.path.exists(full + ".meta"):
            with open(full + ".meta") as f:
                ctype = f.read().strip() or ctype
        return data, ctype
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60,
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def guess_mime(filename: str, fallback: str = "application/octet-stream") -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return EXT_MIME.get(ext, fallback)


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_upload(filename: str, size: int, allowed: set):
    ext = _ext_of(filename)
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Type de fichier non autorisé: .{ext or '?'}")
    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {MAX_FILE_SIZE_MB} Mo)")


# ---------------------------------------------------------------------------
# Navixy integration (GPS fleet tracking) — EU cluster, hash auth
# ---------------------------------------------------------------------------
import re

NAVIXY_BASE_URL = os.environ.get("NAVIXY_BASE_URL", "https://api.eu.navixy.com/v2")
NAVIXY_HASH = os.environ.get("NAVIXY_API_HASH")


class NavixyError(Exception):
    pass


def navixy_post(path: str, payload: dict = None) -> dict:
    if not NAVIXY_HASH:
        raise NavixyError("Clé API de synchronisation non configurée")
    body = {"hash": NAVIXY_HASH}
    if payload:
        body.update(payload)
    try:
        resp = requests.post(f"{NAVIXY_BASE_URL}{path}", json=body, timeout=30)
    except requests.RequestException as exc:
        raise NavixyError(f"Erreur réseau du service de synchronisation: {exc}")
    try:
        data = resp.json()
    except ValueError:
        raise NavixyError(f"Réponse du service de synchronisation invalide (HTTP {resp.status_code})")
    if isinstance(data, dict) and data.get("success") is False:
        status = data.get("status", {}) or {}
        raise NavixyError(status.get("description") or "Erreur Navixy")
    return data


_PLATE_RE = re.compile(r"\b([A-Z]{2})\s?(\d{1,3}(?:\s?\d{2,3}){1,2})\b")


def parse_navixy_label(label: str):
    """Extract a Swiss plate and a clean name from a tracker label."""
    if not label:
        return None, ""
    m = _PLATE_RE.search(label)
    if m:
        plate = f"{m.group(1)} {m.group(2)}".replace("  ", " ").strip()
        name = (label[: m.start()] + label[m.end():]).strip(" -·").strip()
        return plate, name
    return None, label.strip()


# ---------------------------------------------------------------------------
# Email / deadline alerts
# ---------------------------------------------------------------------------
EMAIL_PROVIDER = (os.environ.get("EMAIL_PROVIDER") or "").strip().lower()
EMAIL_API_KEY = (os.environ.get("EMAIL_API_KEY") or "").strip()
EMAIL_FROM = (os.environ.get("EMAIL_FROM") or "").strip()
ALERT_RECIPIENTS = [e.strip() for e in (os.environ.get("ALERT_RECIPIENTS") or "").split(",") if e.strip()]

ALERT_THRESHOLDS = {"leasing": [180, 90, 30], "assurance": [90, 60, 30], "controle": [90, 60, 30, 7]}
ALERT_FIELDS = {
    "leasing": ("leasing", "date_fin", "Fin de leasing"),
    "assurance": ("assurance", "date_echeance", "Renouvellement assurance"),
    "controle": ("controle_technique", "date_prochain", "Contrôle technique"),
}
ALERT_METRIC_KEY = {"leasing": "leasing", "assurance": "assurance", "controle": "controle"}


def email_enabled() -> bool:
    return bool(EMAIL_PROVIDER and EMAIL_API_KEY and EMAIL_FROM)


def send_email_sync(to_list, subject: str, html: str) -> str:
    """Send an email. MOCKED (logged only) until a provider + key + from are configured."""
    if not email_enabled() or not to_list:
        logger.info("EMAIL (MOCKED) -> %s | %s", to_list or "(aucun destinataire)", subject)
        return "mocked"
    try:
        if EMAIL_PROVIDER == "resend":
            r = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {EMAIL_API_KEY}", "Content-Type": "application/json"},
                json={"from": EMAIL_FROM, "to": to_list, "subject": subject, "html": html},
                timeout=20,
            )
            r.raise_for_status()
            return "sent"
        if EMAIL_PROVIDER == "sendgrid":
            r = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {EMAIL_API_KEY}", "Content-Type": "application/json"},
                json={
                    "personalizations": [{"to": [{"email": e} for e in to_list]}],
                    "from": {"email": EMAIL_FROM},
                    "subject": subject,
                    "content": [{"type": "text/html", "value": html}],
                },
                timeout=20,
            )
            r.raise_for_status()
            return "sent"
    except Exception as e:
        logger.error("Email send failed: %s", e)
        return "failed"
    logger.info("EMAIL (MOCKED, fournisseur inconnu) -> %s | %s", to_list, subject)
    return "mocked"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Leasing(BaseModel):
    societe: Optional[str] = ""
    numero_contrat: Optional[str] = ""
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    mensualite_chf: Optional[float] = 0
    duree_mois: Optional[int] = 0
    km_contractuel: Optional[int] = 0
    km_annuel: Optional[int] = 0
    option_achat: Optional[bool] = False
    valeur_residuelle: Optional[float] = 0
    cout_total: Optional[float] = 0
    cout_mensuel: Optional[float] = 0
    commentaires: Optional[str] = ""


class Assurance(BaseModel):
    compagnie: Optional[str] = ""
    numero_police: Optional[str] = ""
    type_couverture: Optional[str] = ""
    prime_annuelle: Optional[float] = 0
    franchise: Optional[float] = 0
    assistance: Optional[bool] = False
    contact_sinistre: Optional[str] = ""
    date_debut: Optional[str] = None
    date_echeance: Optional[str] = None


class CarteGrise(BaseModel):
    date_mise_circulation: Optional[str] = None
    poids_total: Optional[int] = 0
    nombre_places: Optional[int] = 0


class ControleTechnique(BaseModel):
    date_dernier: Optional[str] = None
    date_prochain: Optional[str] = None
    centre: Optional[str] = ""
    resultat: Optional[str] = ""


class VehicleBase(BaseModel):
    photo_url: Optional[str] = ""
    plaque: str = ""
    marque: Optional[str] = ""
    modele: Optional[str] = ""
    annee: Optional[int] = 0
    vin: Optional[str] = ""
    type_carburant: Optional[str] = ""
    cylindree_cm3: Optional[int] = 0
    puissance_kw: Optional[float] = 0
    variante: Optional[str] = ""
    numero_homologation: Optional[str] = ""
    categorie: Optional[str] = ""
    poids_vide: Optional[int] = 0
    co2_g_km: Optional[float] = 0
    conso_officielle_l_100km: Optional[float] = 0
    conso_officielle_norme: Optional[str] = ""
    co2_norme: Optional[str] = ""
    capacite_reservoir_l: Optional[float] = 0
    conso_reelle_l_100km: Optional[float] = 0
    conso_reelle_source: Optional[str] = "unavailable"
    carburant_niveau_pct: Optional[float] = None
    carburant_niveau_date: Optional[str] = ""
    kilometrage: Optional[int] = 0
    groupe: Optional[str] = ""
    base: Optional[str] = ""
    responsable: Optional[str] = ""
    tracker_gps: Optional[str] = ""
    prochaine_maintenance: Optional[str] = None
    prochaine_expertise: Optional[str] = None
    source: Optional[str] = "manual"
    navixy_tracker_id: Optional[int] = None
    navixy_vehicle_id: Optional[int] = None


class VehicleCreate(VehicleBase):
    leasing: Leasing = Field(default_factory=Leasing)
    assurance: Assurance = Field(default_factory=Assurance)
    carte_grise: CarteGrise = Field(default_factory=CarteGrise)
    controle_technique: ControleTechnique = Field(default_factory=ControleTechnique)


class VehicleUpdate(BaseModel):
    photo_url: Optional[str] = None
    plaque: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    annee: Optional[int] = None
    vin: Optional[str] = None
    type_carburant: Optional[str] = None
    cylindree_cm3: Optional[int] = None
    puissance_kw: Optional[float] = None
    variante: Optional[str] = None
    numero_homologation: Optional[str] = None
    categorie: Optional[str] = None
    poids_vide: Optional[int] = None
    co2_g_km: Optional[float] = None
    conso_officielle_l_100km: Optional[float] = None
    conso_officielle_norme: Optional[str] = None
    co2_norme: Optional[str] = None
    capacite_reservoir_l: Optional[float] = None
    conso_reelle_l_100km: Optional[float] = None
    conso_reelle_source: Optional[str] = None
    kilometrage: Optional[int] = None
    groupe: Optional[str] = None
    base: Optional[str] = None
    responsable: Optional[str] = None
    tracker_gps: Optional[str] = None
    prochaine_maintenance: Optional[str] = None
    prochaine_expertise: Optional[str] = None
    leasing: Optional[Leasing] = None
    assurance: Optional[Assurance] = None
    carte_grise: Optional[CarteGrise] = None
    controle_technique: Optional[ControleTechnique] = None


class InspectionPhoto(BaseModel):
    angle: str
    url: Optional[str] = None
    path: Optional[str] = None
    content_type: Optional[str] = None
    original_filename: Optional[str] = None
    kind: Optional[str] = "image"


class InspectionCreate(BaseModel):
    date: Optional[str] = None
    responsable: Optional[str] = ""
    kilometrage: Optional[int] = 0
    commentaire: Optional[str] = ""
    photos: List[InspectionPhoto] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Utility: status / metrics computation
# ---------------------------------------------------------------------------
def days_until(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        d = date.fromisoformat(date_str[:10])
    except (ValueError, TypeError):
        return None
    return (d - date.today()).days


def level_from_days(days: Optional[int]) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= 30:
        return "critical"
    if days <= 90:
        return "warning"
    return "ok"


def months_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    if not start or not end:
        return None
    try:
        s = date.fromisoformat(start[:10])
        e = date.fromisoformat(end[:10])
    except (ValueError, TypeError):
        return None
    return max(0, (e.year - s.year) * 12 + (e.month - s.month))


def compute_metrics(v: dict) -> dict:
    leasing = v.get("leasing") or {}
    assurance = v.get("assurance") or {}
    controle = v.get("controle_technique") or {}

    l_days = days_until(leasing.get("date_fin"))
    l_level = level_from_days(l_days)
    total_months = leasing.get("duree_mois") or months_between(
        leasing.get("date_debut"), leasing.get("date_fin")) or 0
    months_remaining = None
    percent_used = None
    cost_remaining = None
    mensualite = leasing.get("mensualite_chf") or leasing.get("cout_mensuel") or 0
    if leasing.get("date_fin"):
        if l_days is not None:
            months_remaining = max(0, round(l_days / 30.4))
            cost_remaining = round(months_remaining * (mensualite or 0))
        if total_months:
            used = total_months - (months_remaining or 0)
            percent_used = max(0, min(100, round(used / total_months * 100)))

    a_days = days_until(assurance.get("date_echeance"))
    c_days = days_until(controle.get("date_prochain"))

    a_level = level_from_days(a_days)
    c_level = level_from_days(c_days)

    overall = "ok"
    levels = [l_level, a_level, c_level]
    if "expired" in levels:
        overall = "expired"
    elif "critical" in levels:
        overall = "critical"
    elif "warning" in levels:
        overall = "warning"
    elif "unknown" in levels:
        overall = "unknown"

    return {
        "leasing": {
            "days_remaining": l_days,
            "level": l_level,
            "months_remaining": months_remaining,
            "total_months": total_months,
            "percent_used": percent_used,
            "cost_remaining": cost_remaining,
        },
        "assurance": {"days_remaining": a_days, "level": a_level},
        "controle": {"days_remaining": c_days, "level": c_level},
        "overall": overall,
        "compliant": overall == "ok",
    }


def clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


async def audit(action: str, entity: str, request: Request = None, entity_id: str = None,
                vehicle_id: str = None, detail: str = ""):
    """Append an audit-trail entry (create/modify/delete/download)."""
    rec = {
        "id": str(uuid.uuid4()),
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "vehicle_id": vehicle_id,
        "detail": detail,
        "user": "anonymous",  # no authentication in current version
        "ip": (request.client.host if request and request.client else None),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.audit_logs.insert_one(dict(rec))
    except Exception as e:
        logger.error("Audit log failed: %s", e)


# ---------------------------------------------------------------------------
# Vehicle endpoints
# ---------------------------------------------------------------------------
@api_router.get("/")
async def root():
    return {"message": "LogiTrak Fleet Admin API"}


@api_router.get("/vehicles")
async def list_vehicles():
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    for v in vehicles:
        v["metrics"] = compute_metrics(v)
    vehicles.sort(key=lambda x: x.get("plaque", ""))
    return vehicles


@api_router.post("/vehicles")
async def create_vehicle(payload: VehicleCreate):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc["created_at"] = now
    doc["updated_at"] = now
    await db.vehicles.insert_one(dict(doc))
    doc = clean(doc)
    doc["metrics"] = compute_metrics(doc)
    return doc


@api_router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str):
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    v["metrics"] = compute_metrics(v)
    return v


@api_router.put("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: str, payload: VehicleUpdate):
    update = payload.model_dump(exclude_unset=True)
    if not update:
        raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.vehicles.update_one({"id": vehicle_id}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    v["metrics"] = compute_metrics(v)
    return v


@api_router.delete("/vehicles/{vehicle_id}")
async def delete_vehicle(vehicle_id: str):
    await db.vehicles.delete_one({"id": vehicle_id})
    await db.documents.delete_many({"vehicle_id": vehicle_id})
    await db.inspections.delete_many({"vehicle_id": vehicle_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# File upload / serving
# ---------------------------------------------------------------------------
@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), vehicle_id: str = Form("misc")):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{vehicle_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    content_type = file.content_type or guess_mime(file.filename)
    if content_type in ("application/octet-stream", "", None):
        content_type = guess_mime(file.filename)
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=502, detail="Échec du téléversement")
    record = {
        "id": str(uuid.uuid4()),
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "vehicle_id": vehicle_id,
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.files.insert_one(dict(record))
    return {
        "id": record["id"],
        "path": result["path"],
        "original_filename": file.filename,
        "content_type": content_type,
        "size": record["size"],
    }


@api_router.get("/files/{path:path}")
async def serve_file(path: str, download: bool = False, filename: Optional[str] = None):
    try:
        data, content_type = get_object(path)
    except Exception:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    disposition = "attachment" if download else "inline"
    headers = {}
    if filename:
        headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    else:
        headers["Content-Disposition"] = disposition
    return Response(content=data, media_type=content_type, headers=headers)


# ---------------------------------------------------------------------------
# Documents (arborescence)
# ---------------------------------------------------------------------------
FOLDERS = ["Leasing", "Assurance", "Carte grise", "Contrôle technique",
           "Factures", "États des lieux", "Contrats", "Divers"]
REQUIRED_FOLDERS = ["Carte grise", "Leasing", "Assurance", "Contrôle technique"]


@api_router.get("/vehicles/{vehicle_id}/documents")
async def list_documents(vehicle_id: str):
    docs = await db.documents.find(
        {"vehicle_id": vehicle_id, "is_deleted": False}, {"_id": 0}
    ).to_list(1000)
    docs.sort(key=lambda d: d.get("created_at", ""), reverse=True)
    return docs


@api_router.post("/vehicles/{vehicle_id}/documents")
async def add_document(vehicle_id: str, file: UploadFile = File(...), folder: str = Form("Divers")):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/uploads/{vehicle_id}/{uuid.uuid4()}.{ext}"
    data = await file.read()
    content_type = file.content_type or guess_mime(file.filename)
    if content_type in ("application/octet-stream", "", None):
        content_type = guess_mime(file.filename)
    try:
        result = put_object(path, data, content_type)
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=502, detail="Échec du téléversement")
    record = {
        "id": str(uuid.uuid4()),
        "vehicle_id": vehicle_id,
        "folder": folder if folder in FOLDERS else "Divers",
        "original_filename": file.filename,
        "storage_path": result["path"],
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.documents.insert_one(dict(record))
    return clean(record)


@api_router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    await db.documents.update_one({"id": doc_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Inspections (état des lieux)
# ---------------------------------------------------------------------------
@api_router.get("/vehicles/{vehicle_id}/inspections")
async def list_inspections(vehicle_id: str):
    items = await db.inspections.find({"vehicle_id": vehicle_id}, {"_id": 0}).to_list(1000)
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    return items


@api_router.post("/vehicles/{vehicle_id}/inspections")
async def create_inspection(vehicle_id: str, payload: InspectionCreate):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["vehicle_id"] = vehicle_id
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    if not doc.get("date"):
        doc["date"] = date.today().isoformat()
    await db.inspections.insert_one(dict(doc))
    return clean(doc)


@api_router.delete("/inspections/{inspection_id}")
async def delete_inspection(inspection_id: str):
    await db.inspections.delete_one({"id": inspection_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard & Timeline
# ---------------------------------------------------------------------------
@api_router.get("/dashboard")
async def dashboard():
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    documents = await db.documents.find(
        {"is_deleted": False}, {"_id": 0, "vehicle_id": 1, "folder": 1}
    ).to_list(5000)

    folders_by_vehicle: dict = {}
    for d in documents:
        folders_by_vehicle.setdefault(d["vehicle_id"], set()).add(d["folder"])

    leasing_expired = leasing_soon = 0
    assurance_renew = controle_upcoming = 0
    vehicles_missing_docs = 0
    cout_leasing_mensuel = 0.0
    cout_assurance_annuel = 0.0
    vehicles_conformes = 0

    for v in vehicles:
        m = compute_metrics(v)
        if m["leasing"]["level"] == "expired":
            leasing_expired += 1
        elif m["leasing"]["level"] in ("critical", "warning"):
            leasing_soon += 1
        if m["assurance"]["level"] in ("expired", "critical", "warning"):
            assurance_renew += 1
        if m["controle"]["level"] in ("expired", "critical", "warning"):
            controle_upcoming += 1
        if m["compliant"]:
            vehicles_conformes += 1
        leasing = v.get("leasing") or {}
        assurance = v.get("assurance") or {}
        cout_leasing_mensuel += leasing.get("mensualite_chf") or leasing.get("cout_mensuel") or 0
        cout_assurance_annuel += assurance.get("prime_annuelle") or 0
        present = folders_by_vehicle.get(v["id"], set())
        if any(f not in present for f in REQUIRED_FOLDERS):
            vehicles_missing_docs += 1

    return {
        "total_vehicles": len(vehicles),
        "leasing_expired": leasing_expired,
        "leasing_soon": leasing_soon,
        "assurance_renew": assurance_renew,
        "controle_upcoming": controle_upcoming,
        "documents_missing": vehicles_missing_docs,
        "cout_leasing_mensuel": round(cout_leasing_mensuel),
        "cout_assurance_annuel": round(cout_assurance_annuel),
        "vehicles_conformes": vehicles_conformes,
    }


@api_router.get("/timeline")
async def timeline():
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    events = []

    def add(v, type_, label, date_str):
        if not date_str:
            return
        days = days_until(date_str)
        events.append({
            "vehicle_id": v["id"],
            "plaque": v.get("plaque"),
            "marque": v.get("marque"),
            "modele": v.get("modele"),
            "type": type_,
            "label": label,
            "date": date_str[:10],
            "days_remaining": days,
            "level": level_from_days(days),
        })

    for v in vehicles:
        leasing = v.get("leasing") or {}
        assurance = v.get("assurance") or {}
        controle = v.get("controle_technique") or {}
        add(v, "leasing", "Fin de leasing", leasing.get("date_fin"))
        add(v, "assurance", "Renouvellement assurance", assurance.get("date_echeance"))
        add(v, "controle", "Contrôle technique", controle.get("date_prochain"))
        add(v, "expertise", "Expertise", v.get("prochaine_expertise"))
        add(v, "maintenance", "Maintenance", v.get("prochaine_maintenance"))

    events.sort(key=lambda e: e["date"])
    return events


# ---------------------------------------------------------------------------
# Navixy endpoints (import fleet, sync odometer, live state)
# ---------------------------------------------------------------------------
def _empty_nested():
    return {
        "leasing": Leasing().model_dump(),
        "assurance": Assurance().model_dump(),
        "carte_grise": CarteGrise().model_dump(),
        "controle_technique": ControleTechnique().model_dump(),
    }


FUEL_FRESH_DAYS = 7


def _parse_navixy_time(s):
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _extract_fuel_readings(resp: dict) -> dict:
    """Niveau carburant (%) et litres cumulés CAN récents depuis /tracker/readings/list."""
    out = {}
    cutoff = datetime.now(timezone.utc) - timedelta(days=FUEL_FRESH_DAYS)
    for item in (resp.get("inputs") or []) + (resp.get("states") or []):
        name = str(item.get("name") or "")
        val = item.get("value")
        ts = _parse_navixy_time(item.get("update_time"))
        if not isinstance(val, (int, float)) or ts is None or ts < cutoff:
            continue
        if name in ("obd_fuel", "fuel_level", "can_fuel_level") and 0 <= val <= 100:
            out["niveau_pct"] = round(float(val), 1)
            out["niveau_date"] = ts.date().isoformat()
        elif name in ("can_consumption", "obd_total_fuel", "total_fuel_used") and val > 0:
            out["litres_cumules"] = round(float(val), 1)
    return out


async def _record_fuel_snapshot(vehicle_id: str, litres: float, km: int):
    """Snapshot quotidien (litres cumulés CAN + odomètre) puis calcul de la conso réelle MESURÉE.
    Jamais d'estimation : il faut deux snapshots espacés d'au moins 100 km."""
    now = datetime.now(timezone.utc)
    await db.fuel_snapshots.update_one(
        {"vehicle_id": vehicle_id, "day": now.date().isoformat()},
        {"$set": {"litres_cumules": litres, "km": km, "recorded_at": now.isoformat()}},
        upsert=True)
    snaps = await db.fuel_snapshots.find({"vehicle_id": vehicle_id}, {"_id": 0}).sort("day", 1).to_list(400)
    if len(snaps) < 2:
        return
    last = snaps[-1]
    base = next((s for s in snaps[:-1]
                 if last["km"] - s["km"] >= 100 and last["litres_cumules"] > s["litres_cumules"]), None)
    if not base:
        return
    conso = (last["litres_cumules"] - base["litres_cumules"]) / (last["km"] - base["km"]) * 100
    if not 2 <= conso <= 60:
        return
    iso = now.isoformat()
    await db.vehicles.update_one({"id": vehicle_id}, {"$set": {
        "conso_reelle_l_100km": round(conso, 1), "conso_reelle_source": "can", "updated_at": iso}})
    await db.vehicle_field_meta.update_one(
        {"vehicle_id": vehicle_id, "field": "conso_reelle_l_100km"},
        {"$set": {"label": "Consommation réelle (L/100 km)", "source": "can",
                  "provider": "navixy_can", "confidence": None,
                  "validated_by": "système", "validated_at": iso, "updated_at": iso}},
        upsert=True)


async def navixy_sync_internal() -> dict:
    trackers = navixy_post("/tracker/list").get("list", [])
    tracker_ids = [t["id"] for t in trackers]
    odometer = {}
    if tracker_ids:
        cres = navixy_post("/tracker/counter/value/list", {"type": "odometer", "trackers": tracker_ids})
        odometer = cres.get("value", {}) or {}
    vehicles_remote = navixy_post("/vehicle/list").get("list", [])
    veh_by_tracker = {v["tracker_id"]: v for v in vehicles_remote if v.get("tracker_id")}

    now = datetime.now(timezone.utc).isoformat()
    created = updated = 0

    for t in trackers:
        tid = t["id"]
        label = t.get("label") or ""
        linked = veh_by_tracker.get(tid, {})
        plate_from_label, name = parse_navixy_label(label)
        km_val = odometer.get(str(tid))
        km = round(km_val) if isinstance(km_val, (int, float)) else 0
        source_obj = t.get("source") or {}
        model = (linked.get("model") or "").strip()
        if len(model) <= 2 or model.isdigit():
            model = ""
        plaque = (linked.get("reg_number") or plate_from_label or label or "").strip()
        full = (model or name or label).strip()
        parts = full.split(" ", 1)
        marque = parts[0]
        modele = parts[1] if len(parts) > 1 else ""

        navixy_fields = {
            "plaque": plaque,
            "marque": marque,
            "modele": modele,
            "vin": linked.get("vin") or "",
            "annee": linked.get("manufacture_year") or 0,
            "kilometrage": km,
            "tracker_gps": source_obj.get("device_id") or label,
            "navixy_tracker_id": tid,
            "navixy_vehicle_id": linked.get("id"),
            "source": "navixy",
            "updated_at": now,
        }

        fuel = {}
        try:
            fuel = _extract_fuel_readings(navixy_post("/tracker/readings/list", {"tracker_id": tid}))
        except Exception:
            pass
        if fuel.get("niveau_pct") is not None:
            navixy_fields["carburant_niveau_pct"] = fuel["niveau_pct"]
            navixy_fields["carburant_niveau_date"] = fuel["niveau_date"]

        existing = await db.vehicles.find_one({"navixy_tracker_id": tid})
        if existing:
            # Les champs validés depuis un document scanné restent prioritaires sur Navixy
            metas = await db.vehicle_field_meta.find(
                {"vehicle_id": existing["id"], "source": "document_scan",
                 "field": {"$in": ["plaque", "marque", "modele", "vin", "annee"]}},
                {"_id": 0, "field": 1},
            ).to_list(10)
            protected = {m["field"] for m in metas}
            fields_to_set = {k: val for k, val in navixy_fields.items() if k not in protected}
            await db.vehicles.update_one({"navixy_tracker_id": tid}, {"$set": fields_to_set})
            updated += 1
        else:
            doc = {
                "id": str(uuid.uuid4()),
                "photo_url": "",
                "groupe": "",
                "base": "",
                "responsable": "",
                "prochaine_maintenance": None,
                "prochaine_expertise": None,
                "created_at": now,
                **_empty_nested(),
                **navixy_fields,
            }
            await db.vehicles.insert_one(dict(doc))
            created += 1

        vid = existing["id"] if existing else doc["id"]
        if fuel.get("litres_cumules") is not None and km > 0:
            await _record_fuel_snapshot(vid, fuel["litres_cumules"], km)

    removed = await db.vehicles.delete_many({"source": {"$in": ["demo", None]}})
    return {"synced": len(trackers), "created": created, "updated": updated, "removed_demo": removed.deleted_count}


@api_router.get("/navixy/status")
async def navixy_status():
    if not NAVIXY_HASH:
        return {"connected": False, "configured": False}
    try:
        trackers = navixy_post("/tracker/list").get("list", [])
        info = navixy_post("/user/get_info")
    except NavixyError as e:
        return {"connected": False, "configured": True, "error": str(e)}
    account = (info.get("paas_settings", {}) or {}).get("service_title") or "Télématique"
    imported = await db.vehicles.count_documents({"source": "navixy"})
    return {
        "connected": True,
        "configured": True,
        "trackers_count": len(trackers),
        "imported_count": imported,
        "account": account,
    }


@api_router.post("/navixy/sync")
async def navixy_sync():
    try:
        result = await navixy_sync_internal()
    except NavixyError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@api_router.post("/demo/fill-admin")
async def demo_fill_admin():
    """Remplit les véhicules sans données administratives avec un jeu de
    démonstration fictif (leasing, assurance, carte grise, contrôle technique)
    + quelques états des lieux. Non destructif : ne touche pas aux données déjà saisies."""
    result = await enrich_demo_admin()
    return result


@api_router.get("/vehicles/{vehicle_id}/live")
async def vehicle_live(vehicle_id: str):
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    tid = v.get("navixy_tracker_id")
    if not tid:
        raise HTTPException(status_code=400, detail="Véhicule non lié à un tracker GPS")
    try:
        states = navixy_post("/tracker/get_states", {"trackers": [tid]}).get("states", {}) or {}
        cres = navixy_post("/tracker/counter/value/list", {"type": "odometer", "trackers": [tid]}).get("value", {}) or {}
    except NavixyError as e:
        raise HTTPException(status_code=502, detail=str(e))
    st = states.get(str(tid)) or {}
    gps = st.get("gps") or {}
    loc = gps.get("location") or {}
    odo = cres.get(str(tid))
    return {
        "tracker_id": tid,
        "connection_status": st.get("connection_status"),
        "movement_status": st.get("movement_status"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "speed": gps.get("speed"),
        "heading": gps.get("heading"),
        "last_update": st.get("last_update"),
        "gsm_network": (st.get("gsm") or {}).get("network_name"),
        "battery_level": st.get("battery_level"),
        "odometer_km": round(odo) if isinstance(odo, (int, float)) else None,
    }


# ---------------------------------------------------------------------------
# Deadline alerts engine + OCR
# ---------------------------------------------------------------------------
async def run_alerts() -> dict:
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    now = datetime.now(timezone.utc).isoformat()
    created = 0
    emails_sent = 0
    upcoming = []

    for v in vehicles:
        for type_, (coll, datef, label) in ALERT_FIELDS.items():
            sub = v.get(coll) or {}
            due = sub.get(datef)
            if not due:
                continue
            days = days_until(due)
            if days is None:
                continue
            level = level_from_days(days)
            if days <= 180:
                upcoming.append({"plaque": v.get("plaque"), "type": type_, "label": label, "due": due[:10], "days": days, "level": level})

            thresholds = ALERT_THRESHOLDS[type_]
            crossed = [t for t in thresholds if 0 <= days <= t]
            if days < 0:
                crossed_threshold = 0
            elif crossed:
                crossed_threshold = min(crossed)
            else:
                continue

            key = {"vehicle_id": v["id"], "type": type_, "threshold": crossed_threshold, "due_date": due[:10]}
            if await db.alerts.find_one(key):
                continue

            msg = f"{v.get('plaque')} · {label} le {due[:10]} " + ("(ÉCHU)" if days < 0 else f"(dans {days} j)")
            subject = f"[LogiTrak] Échéance {label} — {v.get('plaque')}"
            status = await asyncio.to_thread(send_email_sync, ALERT_RECIPIENTS, subject, f"<p>{msg}</p>")
            if status == "sent":
                emails_sent += 1
            rec = {
                **key, "id": str(uuid.uuid4()), "plaque": v.get("plaque"), "label": label,
                "days_remaining": days, "level": level, "message": msg, "kind": "threshold",
                "channel": "email", "status": status, "recipients": ALERT_RECIPIENTS, "created_at": now,
            }
            await db.alerts.insert_one(dict(rec))
            created += 1

    upcoming.sort(key=lambda x: x["days"])
    today = date.today().isoformat()
    digest_status = "skipped"
    if upcoming and not await db.alerts.find_one({"kind": "digest", "digest_date": today}):
        rows = "".join(f"<li>{u['plaque']} — {u['label']} le {u['due']} (dans {u['days']} j)</li>" for u in upcoming)
        subject = f"[LogiTrak] Récapitulatif des échéances — {len(upcoming)} à suivre"
        digest_status = await asyncio.to_thread(send_email_sync, ALERT_RECIPIENTS, subject, f"<h3>Échéances à venir</h3><ul>{rows}</ul>")
        await db.alerts.insert_one({
            "id": str(uuid.uuid4()), "kind": "digest", "digest_date": today, "type": "digest",
            "label": "Récapitulatif quotidien", "message": f"{len(upcoming)} échéance(s) à venir",
            "level": "info", "channel": "email", "status": digest_status,
            "recipients": ALERT_RECIPIENTS, "items": upcoming, "created_at": now,
        })

    return {"created": created, "emails_sent": emails_sent, "digest_status": digest_status,
            "upcoming": len(upcoming), "email_enabled": email_enabled()}


@api_router.get("/alerts")
async def list_alerts():
    vehicles = await db.vehicles.find({}, {"_id": 0}).to_list(1000)
    items = []
    for v in vehicles:
        m = compute_metrics(v)
        for type_, (coll, datef, label) in ALERT_FIELDS.items():
            sub = v.get(coll) or {}
            due = sub.get(datef)
            mk = m.get(ALERT_METRIC_KEY[type_], {})
            level = mk.get("level")
            if due and level in ("expired", "critical", "warning"):
                items.append({
                    "vehicle_id": v["id"], "plaque": v.get("plaque"), "marque": v.get("marque"),
                    "modele": v.get("modele"), "type": type_, "label": label, "due_date": due[:10],
                    "days_remaining": mk.get("days_remaining"), "level": level,
                })
    items.sort(key=lambda x: x["days_remaining"] if x["days_remaining"] is not None else 9999)
    stats = {
        "total": len(items),
        "expired": sum(1 for i in items if i["level"] == "expired"),
        "critical": sum(1 for i in items if i["level"] == "critical"),
        "warning": sum(1 for i in items if i["level"] == "warning"),
    }
    return {"items": items, "stats": stats, "email_enabled": email_enabled(), "recipients": ALERT_RECIPIENTS}


@api_router.get("/alerts/log")
async def alerts_log():
    return await db.alerts.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)


@api_router.post("/alerts/run")
async def alerts_run():
    return await run_alerts()


# ---------------------------------------------------------------------------
# Scan intelligent de documents (upload -> extraction -> validation -> fiche véhicule)
# ---------------------------------------------------------------------------
SCAN_EXTS = {"pdf", "jpg", "jpeg", "png", "webp"}
MAX_SCAN_PAGES = 8


def _get_current(v: dict, target: str, field: str):
    if target == "root":
        return v.get(field)
    if target == "document":
        return None
    return (v.get(target) or {}).get(field)


def _is_empty(x) -> bool:
    return x is None or x == "" or x == 0


def _same_value(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (TypeError, ValueError):
        pass
    na = re.sub(r"\s+", " ", str(a or "").strip()).casefold()
    nb = re.sub(r"\s+", " ", str(b or "").strip()).casefold()
    return na == nb


def _build_review_fields(vehicle: dict, defs_list: list, raw_fields: dict) -> list:
    defs = {d["key"]: d for d in defs_list}
    out = []
    for key, info in (raw_fields or {}).items():
        fd = defs.get(key)
        if not fd or not isinstance(info, dict):
            continue
        value = normalize_value(info.get("value"), fd["kind"])
        if value is None:
            continue
        conf = info.get("confidence")
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            conf = None
        current = _get_current(vehicle, fd["target"], key)
        has_current = not _is_empty(current)
        conflict = has_current and not _same_value(current, value)
        status = info.get("status")
        if status not in ("found", "uncertain", "missing"):
            status = "uncertain" if (conf is not None and conf < 0.6) else "found"
        out.append({
            "field": key, "label": fd["label"], "target": fd["target"], "kind": fd["kind"],
            "value": value, "confidence": conf, "status": status,
            "current_value": current if has_current else None,
            "conflict": conflict,
        })
    order = [d["key"] for d in defs_list]
    out.sort(key=lambda f: order.index(f["field"]))
    return out


@api_router.get("/document-types")
async def list_document_types():
    return [{"key": k, **v} for k, v in DOC_TYPES.items()]


@api_router.post("/vehicles/{vehicle_id}/documents/scan")
async def scan_vehicle_document(vehicle_id: str, request: Request,
                                files: List[UploadFile] = File(None),
                                document_type: Optional[str] = Form(None),
                                document_id: Optional[str] = Form(None),
                                as_pdf: Optional[str] = Form(None)):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    if not (ANTHROPIC_KEY or EMERGENT_KEY):
        raise HTTPException(status_code=503,
                            detail="Scan non configuré sur ce serveur — renseignez ANTHROPIC_API_KEY (Claude) "
                                   "ou EMERGENT_LLM_KEY (deploy/.env sur le VPS) puis redémarrez le backend.")
    if document_type and document_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Type de document inconnu")

    images_b64 = []
    quality_warnings = []
    if document_id:
        # Ré-analyse d'un document déjà téléversé (changement de type, nouvel essai)
        record = await db.documents.find_one(
            {"id": document_id, "vehicle_id": vehicle_id, "is_deleted": False}, {"_id": 0})
        if not record:
            raise HTTPException(status_code=404, detail="Document introuvable")
        pages = record.get("pages") or [{"storage_path": record["storage_path"],
                                         "content_type": record.get("content_type", "")}]
        for page in pages:
            try:
                data, ctype = get_object(page["storage_path"])
            except Exception:
                raise HTTPException(status_code=404, detail="Fichier source introuvable")
            if "pdf" in (ctype or "").lower():
                images_b64.extend(pdf_to_images_b64(data))
            else:
                images_b64.append(prepare_image_b64(data))
    else:
        if not files:
            raise HTTPException(status_code=400, detail="Aucun fichier fourni")
        if len(files) > MAX_SCAN_PAGES:
            raise HTTPException(status_code=400, detail=f"Maximum {MAX_SCAN_PAGES} pages par scan")
        inputs = []
        for f in files:
            data = await f.read()
            ext = _ext_of(f.filename)
            if ext not in SCAN_EXTS:
                raise HTTPException(status_code=400,
                                    detail=f"Format non supporté pour le scan: .{ext or '?'} (PDF, JPG, PNG, WEBP)")
            if len(data) > MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"Fichier trop volumineux (max {MAX_FILE_SIZE_MB} Mo)")
            inputs.append((f, data, ext))
        for f, data, ext in inputs:
            if ext == "pdf":
                continue
            q = check_image_quality(data)
            if q["level"] == "blocked":
                raise HTTPException(status_code=422,
                                    detail="Certains éléments du document ne sont pas suffisamment lisibles ("
                                           + ", ".join(q["issues"]) +
                                           "). Veuillez reprendre la photo ou importer un document de meilleure qualité.")
            quality_warnings.extend(q["issues"])
        as_pdf_flag = (as_pdf or "").strip().lower() in ("1", "true", "yes")
        pages, total_size = [], 0
        if as_pdf_flag and all(ext != "pdf" for _, _, ext in inputs):
            # Photos du scanner : amélioration de lisibilité + assemblage en un PDF unique
            try:
                pdf_bytes, jpegs = enhance_and_pdf([data for _, data, _ in inputs])
            except Exception:
                raise HTTPException(status_code=422, detail="Image illisible")
            images_b64 = [prepare_image_b64(j) for j in jpegs]
            filename = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.pdf"
            path = f"{APP_NAME}/uploads/{vehicle_id}/{uuid.uuid4()}.pdf"
            try:
                stored = put_object(path, pdf_bytes, "application/pdf")
            except Exception as e:
                logger.error("Scan upload failed: %s", e)
                raise HTTPException(status_code=502, detail="Échec du téléversement")
            pages.append({"storage_path": stored["path"], "original_filename": filename,
                          "content_type": "application/pdf", "size": stored.get("size", len(pdf_bytes))})
            total_size = len(pdf_bytes)
        else:
            for f, data, ext in inputs:
                if ext == "pdf":
                    try:
                        imgs = pdf_to_images_b64(data)
                    except Exception:
                        raise HTTPException(status_code=422, detail="PDF illisible ou corrompu")
                    if not imgs:
                        raise HTTPException(status_code=422, detail="PDF sans page exploitable")
                    images_b64.extend(imgs)
                else:
                    try:
                        images_b64.append(prepare_image_b64(data))
                    except Exception:
                        raise HTTPException(status_code=422, detail=f"Image illisible: {f.filename}")
                content_type = f.content_type or guess_mime(f.filename)
                path = f"{APP_NAME}/uploads/{vehicle_id}/{uuid.uuid4()}.{ext}"
                try:
                    stored = put_object(path, data, content_type)
                except Exception as e:
                    logger.error("Scan upload failed: %s", e)
                    raise HTTPException(status_code=502, detail="Échec du téléversement")
                pages.append({"storage_path": stored["path"], "original_filename": f.filename,
                              "content_type": content_type, "size": stored.get("size", len(data))})
                total_size += len(data)
        record = {
            "id": str(uuid.uuid4()), "vehicle_id": vehicle_id,
            "folder": DOC_TYPES.get(document_type, {}).get("folder", "Divers"),
            "original_filename": pages[0]["original_filename"],
            "storage_path": pages[0]["storage_path"],
            "content_type": pages[0]["content_type"],
            "size": total_size, "pages": pages,
            "document_type": document_type, "extraction_status": "processing",
            "source": "scan", "imported_by": "utilisateur", "is_deleted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.documents.insert_one(dict(record))
        record.pop("_id", None)

    images_b64 = images_b64[:MAX_SCAN_PAGES]
    try:
        result = await extraction_provider.analyze(images_b64, document_type)
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        await db.documents.update_one({"id": record["id"]}, {"$set": {"extraction_status": "failed"}})
        if isinstance(e, (ImportError, ModuleNotFoundError)):
            err_msg = ("Module OCR absent du serveur (emergentintegrations) — "
                       "reconstruisez l'image backend (docker compose build backend).")
        elif isinstance(e, RuntimeError) and "clé d'extraction" in str(e):
            err_msg = ("Scan non configuré sur ce serveur — renseignez ANTHROPIC_API_KEY (Claude) "
                       "ou EMERGENT_LLM_KEY (deploy/.env sur le VPS) puis redémarrez le backend.")
        else:
            err_msg = "Analyse impossible. Réessayez ou saisissez les données manuellement."
        return {"document_id": record["id"], "extraction_status": "failed",
                "error": err_msg}

    detected = result.get("document_type")
    if detected not in DOC_TYPES:
        detected = None
    dtype = document_type or detected or "autre"
    if dtype not in DOC_TYPES:
        dtype = "autre"
    type_mismatch = None
    if document_type and detected and detected != document_type:
        type_mismatch = {"expected": document_type, "expected_label": DOC_TYPES[document_type]["label"],
                         "detected": detected, "detected_label": DOC_TYPES[detected]["label"],
                         "confidence": result.get("type_confidence")}
    fields = _build_review_fields(vehicle, FIELD_DEFS.get(dtype, []), result.get("fields"))
    defs_labels = {d["key"]: d["label"] for d in FIELD_DEFS.get(dtype, [])}
    missing_fields = [defs_labels[k] for k, v in (result.get("fields") or {}).items()
                      if k in defs_labels and isinstance(v, dict) and v.get("status") == "missing"]
    await db.documents.update_one({"id": record["id"]}, {"$set": {
        "extraction_status": "done", "document_type": dtype,
        "type_confidence": result.get("type_confidence"),
        "detected_type": detected,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "quality_warnings": quality_warnings,
        "folder": DOC_TYPES[dtype]["folder"],
        "extracted_fields": fields,
    }})
    await audit("scan", "document", request, record["id"], vehicle_id,
                f"Scan {DOC_TYPES[dtype]['label']} — {len(fields)} champ(s) détecté(s)")
    return {"document_id": record["id"], "extraction_status": "done",
            "document_type": dtype, "type_confidence": result.get("type_confidence"),
            "detected_type": detected, "type_mismatch": type_mismatch,
            "quality_warnings": quality_warnings, "missing_fields": missing_fields,
            "pages_count": len(images_b64), "fields": fields}


class DocumentValidate(BaseModel):
    document_type: str
    fields: dict = Field(default_factory=dict)


@api_router.post("/documents/{doc_id}/validate")
async def validate_scanned_document(doc_id: str, payload: DocumentValidate, request: Request):
    docrec = await db.documents.find_one({"id": doc_id, "is_deleted": False}, {"_id": 0})
    if not docrec:
        raise HTTPException(status_code=404, detail="Document introuvable")
    dtype = payload.document_type
    if dtype not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Type de document inconnu")
    vehicle = await db.vehicles.find_one({"id": docrec["vehicle_id"]}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")

    defs = {d["key"]: d for d in FIELD_DEFS.get(dtype, [])}
    conf_by_field = {f["field"]: f.get("confidence") for f in docrec.get("extracted_fields") or []}
    root_updates, sub_updates, doc_data, applied = {}, {}, {}, []

    for key, raw in (payload.fields or {}).items():
        fd = defs.get(key)
        if not fd:
            continue
        value = normalize_value(raw, fd["kind"])
        if value is None:
            continue
        if fd["target"] == "document":
            doc_data[key] = value
            continue
        current = _get_current(vehicle, fd["target"], key)
        if not _is_empty(current) and _same_value(current, value):
            continue
        if fd["target"] == "root":
            root_updates[key] = value
        else:
            sub_updates.setdefault(fd["target"], {})[key] = value
        applied.append((key, fd, current, value))

    now = datetime.now(timezone.utc).isoformat()
    update = dict(root_updates)
    for sub, vals in sub_updates.items():
        update[sub] = {**(vehicle.get(sub) or {}), **vals}
    if update:
        update["updated_at"] = now
        await db.vehicles.update_one({"id": vehicle["id"]}, {"$set": update})

    type_label = DOC_TYPES[dtype]["label"]
    for key, fd, old, new in applied:
        fpath = key if fd["target"] == "root" else f"{fd['target']}.{key}"
        await db.vehicle_field_meta.update_one(
            {"vehicle_id": vehicle["id"], "field": fpath},
            {"$set": {"label": fd["label"], "source": "document_scan",
                      "source_document_id": doc_id, "confidence": conf_by_field.get(key),
                      "validated_by": "utilisateur", "validated_at": now, "updated_at": now}},
            upsert=True)
        old_txt = old if not _is_empty(old) else "—"
        await audit("modify", "vehicle", request, vehicle["id"], vehicle["id"],
                    f"{fd['label']}: {old_txt} → {new} (source: {type_label})")

    await db.documents.update_one({"id": doc_id}, {"$set": {
        "document_type": dtype, "folder": DOC_TYPES[dtype]["folder"],
        "validated_at": now, "validated_by": "utilisateur", "validated_fields": payload.fields,
        "document_data": doc_data, "extraction_status": "validated",
    }})
    await audit("validate", "document", request, doc_id, vehicle["id"],
                f"Validation {type_label} — {len(applied) + len(doc_data)} champ(s) appliqué(s)")

    fresh = await db.vehicles.find_one({"id": vehicle["id"]}, {"_id": 0})
    fresh["metrics"] = compute_metrics(fresh)
    return {"ok": True, "applied": len(applied) + len(doc_data), "document_id": doc_id, "vehicle": fresh}


@api_router.get("/vehicles/{vehicle_id}/field-meta")
async def get_vehicle_field_meta(vehicle_id: str):
    return await db.vehicle_field_meta.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}).sort("updated_at", -1).to_list(200)


# ---------------------------------------------------------------------------
# Enrichissement technique externe (SwissCarInfo — données officielles OFROU)
# ---------------------------------------------------------------------------
async def _can_locked_keys(vehicle_id: str) -> set:
    """Champs mesurés via CAN/OBD — jamais remplacés par des données constructeur."""
    metas = await db.vehicle_field_meta.find(
        {"vehicle_id": vehicle_id, "provider": "navixy_can"}, {"_id": 0, "field": 1}).to_list(100)
    locked_paths = {m["field"] for m in metas}
    return {d["key"] for d in TECH_FIELD_DEFS
            if (d["key"] if d["target"] == "root" else f"{d['target']}.{d['key']}") in locked_paths}


@api_router.get("/technical-data/status")
async def technical_data_status():
    imported = await astra_data.is_imported(db)
    return {"configured": imported, "provider": "astra" if imported else None,
            "detail": "Base officielle ASTRA/OFROU (copie locale)" if imported
            else "Données ASTRA non importées — POST /api/astra/import"}


@api_router.get("/config/status")
async def config_status():
    return {"scan_configured": bool(ANTHROPIC_KEY or EMERGENT_KEY),
            "scan_provider": "claude" if ANTHROPIC_KEY else ("gpt" if EMERGENT_KEY else None),
            "technical_data_configured": await astra_data.is_imported(db)}


# ---------------------------------------------------------------------------
# Données officielles ASTRA/OFROU (locales) — import & recherche
# ---------------------------------------------------------------------------
@api_router.get("/astra/status")
async def astra_status_endpoint():
    return await astra_data.astra_status(db)


@api_router.post("/astra/import")
async def astra_import_endpoint(datasets: Optional[str] = None,
                                download: bool = True, force: bool = False):
    names = [d.strip() for d in datasets.split(",") if d.strip()] if datasets else None
    if names:
        unknown = [n for n in names if n not in astra_data.DATASETS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Datasets inconnus : {', '.join(unknown)}")
    if await astra_data.import_active(db):
        raise HTTPException(status_code=409, detail="Un import ASTRA est déjà en cours.")
    asyncio.create_task(astra_data.run_import(db, datasets=names, download=download, force_download=force))
    return {"started": True, "datasets": names or list(astra_data.DATASETS)}


@api_router.get("/astra/search")
async def astra_search(homologation: Optional[str] = None,
                       vin: Optional[str] = None, plate: Optional[str] = None):
    if homologation:
        key = astra_data.normalize_approval(homologation)
        result = await astra_data.lookup_homologation(db, key) if key else None
        if result:
            return {"found": True, **result}
        return {"found": False, "reason": "not_found",
                "message": f"Homologation « {homologation} » introuvable dans les données ASTRA locales (TAS + TG)."}
    if vin:
        if await db.astra_edatenblatt.estimated_document_count() == 0:
            return {"found": False, "reason": "edatenblatt_not_imported",
                    "message": "Recherche par VIN indisponible — dataset eDatenblatt non importé "
                               "(POST /api/astra/import?datasets=edatenblatt)."}
        try:
            result = await astra_data.lookup_vin(db, vin)
        except AstraLookupError as e:
            return {"found": False, "reason": e.code, "message": str(e)}
        if result:
            return {"found": True, **result}
        return {"found": False, "reason": "not_found",
                "message": f"VIN « {vin} » introuvable dans les fiches eDatenblatt (véhicules importés dès ~2023)."}
    if plate:
        return {"found": False, "reason": "plate_lookup_unavailable_without_external_provider",
                "message": "La recherche par plaque seule n'est pas disponible sans fournisseur externe. "
                           "Utilisez le n° d'homologation (case 24), le VIN ou scannez la carte grise."}
    raise HTTPException(status_code=400, detail="Paramètre requis : homologation, vin ou plate")


@api_router.get("/reports/conformite.pdf")
async def conformity_report():
    vehicles = await db.vehicles.find({}, {"_id": 0}).sort("plaque", 1).to_list(1000)
    for v in vehicles:
        v["metrics"] = compute_metrics(v)
    pdf_bytes = build_conformity_pdf(vehicles)
    await audit("download", "report", None, "conformite", None,
                f"Export PDF du rapport de conformité flotte ({len(vehicles)} véhicules)")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="rapport-conformite-logitrak.pdf"'})


@api_router.get("/reports/couts.csv")
async def costs_csv_report():
    vehicles = await db.vehicles.find({}, {"_id": 0}).sort("plaque", 1).to_list(1000)
    for v in vehicles:
        v["metrics"] = compute_metrics(v)
    csv_text = build_costs_csv(vehicles)
    await audit("download", "report", None, "couts_csv", None,
                f"Export CSV des coûts flotte ({len(vehicles)} véhicules)")
    return Response(content="\ufeff" + csv_text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="couts-flotte-logitrak.csv"'})


@api_router.get("/reports/vehicule/{vehicle_id}.pdf")
async def vehicle_report(vehicle_id: str):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    vehicle["metrics"] = compute_metrics(vehicle)
    history = await db.audit_logs.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}).sort("created_at", -1).to_list(30)
    documents = await db.documents.find(
        {"vehicle_id": vehicle_id, "is_deleted": False}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pdf_bytes = build_vehicle_pdf(vehicle, history, documents,
                                  {k: v["label"] for k, v in DOC_TYPES.items()})
    await audit("download", "report", None, f"vehicule_{vehicle_id}", vehicle_id,
                f"Export PDF de la fiche véhicule {vehicle.get('plaque')}")
    plaque_slug = re.sub(r"\W+", "-", vehicle.get("plaque") or vehicle_id).strip("-").lower()
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="fiche-{plaque_slug}.pdf"'})


class TechnicalApply(BaseModel):
    fields: dict = Field(default_factory=dict)
    matched_by: Optional[str] = None
    retrieved_at: Optional[str] = None
    provider: Optional[str] = None


@api_router.post("/vehicles/{vehicle_id}/enrich-technical")
async def enrich_technical(vehicle_id: str, request: Request):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    try:
        result = await astra_data.resolve_vehicle_data(db, vehicle)
    except AstraLookupError as e:
        raise HTTPException(status_code=e.http_status, detail=str(e))
    can_locked = await _can_locked_keys(vehicle_id)
    main = result.get("fields") or {}
    raw = {k: {"value": v, "confidence": None} for k, v in main.items() if k not in can_locked}
    fields = _build_review_fields(vehicle, TECH_FIELD_DEFS, raw)
    variantes = []
    for var in (result.get("variantes") or []):
        vraw = {k: {"value": v, "confidence": None} for k, v in (var.get("fields") or {}).items()
                if v not in (None, "") and k not in main and k not in can_locked}
        variantes.append({"label": var.get("label"),
                          "fields": _build_review_fields(vehicle, TECH_FIELD_DEFS, vraw)})
    await audit("enrich", "vehicle", request, vehicle_id, vehicle_id,
                f"Recherche base officielle ASTRA/OFROU ({result.get('provider')}) — {len(fields)} champ(s) trouvé(s)")
    return {"provider": result.get("provider"), "matched_by": result.get("matched_by"),
            "retrieved_at": result.get("retrieved_at"), "match": result.get("match"),
            "lookup_ms": result.get("lookup_ms"),
            "requires_variant_choice": len(variantes) > 0, "variantes": variantes,
            "fields": fields}


@api_router.post("/vehicles/{vehicle_id}/enrich-technical/apply")
async def apply_technical_enrichment(vehicle_id: str, payload: TechnicalApply, request: Request):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    defs = {d["key"]: d for d in TECH_FIELD_DEFS}
    can_locked = await _can_locked_keys(vehicle_id)
    root_updates, sub_updates, applied = {}, {}, []
    for key, raw in (payload.fields or {}).items():
        fd = defs.get(key)
        if not fd or key in can_locked:
            continue
        value = normalize_value(raw, fd["kind"])
        if value is None:
            continue
        current = _get_current(vehicle, fd["target"], key)
        if not _is_empty(current) and _same_value(current, value):
            continue
        if fd["target"] == "root":
            root_updates[key] = value
        else:
            sub_updates.setdefault(fd["target"], {})[key] = value
        applied.append((key, fd, current, value))

    now = datetime.now(timezone.utc).isoformat()
    update = dict(root_updates)
    for sub, vals in sub_updates.items():
        update[sub] = {**(vehicle.get(sub) or {}), **vals}
    if update:
        update["updated_at"] = now
        await db.vehicles.update_one({"id": vehicle["id"]}, {"$set": update})

    for key, fd, old, new in applied:
        fpath = key if fd["target"] == "root" else f"{fd['target']}.{key}"
        await db.vehicle_field_meta.update_one(
            {"vehicle_id": vehicle["id"], "field": fpath},
            {"$set": {"label": fd["label"], "source": "external_vehicle_database",
                      "provider": payload.provider or "astra_tas", "source_ref": payload.matched_by or "",
                      "retrieved_at": payload.retrieved_at or "", "confidence": None,
                      "previous_value": old if not _is_empty(old) else None,
                      "applied_value": new,
                      "validated_by": "utilisateur", "validated_at": now, "updated_at": now}},
            upsert=True)
        old_txt = old if not _is_empty(old) else "—"
        await audit("modify", "vehicle", request, vehicle["id"], vehicle["id"],
                    f"{fd['label']}: {old_txt} → {new} (source: Base officielle ASTRA/OFROU)")

    fresh = await db.vehicles.find_one({"id": vehicle["id"]}, {"_id": 0})
    fresh["metrics"] = compute_metrics(fresh)
    return {"ok": True, "applied": len(applied), "vehicle": fresh}


class TechnicalRevert(BaseModel):
    field: str


@api_router.post("/vehicles/{vehicle_id}/enrich-technical/revert")
async def revert_technical_field(vehicle_id: str, payload: TechnicalRevert, request: Request):
    vehicle = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not vehicle:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    defs = {d["key"]: d for d in TECH_FIELD_DEFS}
    key = payload.field.split(".")[-1]
    fd = defs.get(key)
    if not fd:
        raise HTTPException(status_code=422, detail="Champ inconnu")
    fpath = key if fd["target"] == "root" else f"{fd['target']}.{key}"
    meta = await db.vehicle_field_meta.find_one(
        {"vehicle_id": vehicle_id, "field": fpath, "source": "external_vehicle_database"}, {"_id": 0})
    if not meta or "previous_value" not in meta:
        raise HTTPException(status_code=404,
                            detail="Aucune valeur précédente enregistrée pour ce champ.")
    prev = meta.get("previous_value")
    current = _get_current(vehicle, fd["target"], key)
    now = datetime.now(timezone.utc).isoformat()
    if fd["target"] == "root":
        await db.vehicles.update_one({"id": vehicle_id}, {"$set": {key: prev, "updated_at": now}})
    else:
        sub = {**(vehicle.get(fd["target"]) or {}), key: prev}
        await db.vehicles.update_one({"id": vehicle_id}, {"$set": {fd["target"]: sub, "updated_at": now}})
    await db.vehicle_field_meta.delete_one({"vehicle_id": vehicle_id, "field": fpath})
    cur_txt = current if not _is_empty(current) else "—"
    prev_txt = prev if not _is_empty(prev) else "—"
    await audit("modify", "vehicle", request, vehicle_id, vehicle_id,
                f"{fd['label']}: {cur_txt} → {prev_txt} (retour à la valeur précédant l'enrichissement ASTRA)")
    fresh = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    fresh["metrics"] = compute_metrics(fresh)
    return {"ok": True, "vehicle": fresh}


@api_router.post("/vehicles/enrich-technical/batch")
async def enrich_technical_batch(request: Request):
    if not await astra_data.is_imported(db):
        raise HTTPException(status_code=503,
                            detail="Base technique ASTRA non importée — lancez POST /api/astra/import.")
    vehicles = await db.vehicles.find({}, {"_id": 0}).sort("plaque", 1).to_list(1000)
    out = []
    for v in vehicles:
        base = {"vehicle_id": v["id"], "plaque": v.get("plaque"),
                "marque": v.get("marque"), "modele": v.get("modele")}
        try:
            result = await astra_data.resolve_vehicle_data(db, v)
        except AstraLookupError as e:
            out.append({**base, "status": e.code, "message": str(e)})
            continue
        can_locked = await _can_locked_keys(v["id"])
        main = result.get("fields") or {}
        raw = {k: {"value": val, "confidence": None} for k, val in main.items() if k not in can_locked}
        fields = _build_review_fields(v, TECH_FIELD_DEFS, raw)
        out.append({**base, "status": "found", "provider": result.get("provider"),
                    "matched_by": result.get("matched_by"), "retrieved_at": result.get("retrieved_at"),
                    "match": result.get("match"),
                    "requires_variant_choice": bool(result.get("variantes")),
                    "fields": fields})
    found = sum(1 for r in out if r["status"] == "found")
    await audit("enrich", "vehicle", request, "fleet", None,
                f"Recherche flotte base officielle ASTRA/OFROU — {found}/{len(out)} véhicule(s) trouvé(s)")
    return {"total": len(out), "found": found, "results": out}


@api_router.get("/fleet/consumption-ranking")
async def fleet_consumption_ranking():
    vehicles = await db.vehicles.find({}, {"_id": 0}).sort("plaque", 1).to_list(1000)
    items, missing = [], []
    for v in vehicles:
        off = v.get("conso_officielle_l_100km")
        real = v.get("conso_reelle_l_100km")
        base = {"vehicle_id": v["id"], "plaque": v.get("plaque"),
                "marque": v.get("marque"), "modele": v.get("modele"),
                "type_carburant": v.get("type_carburant"),
                "conso_officielle": off if off not in (None, "") else None,
                "conso_officielle_norme": v.get("conso_officielle_norme"),
                "conso_reelle": real if real not in (None, "") else None,
                "conso_reelle_source": v.get("conso_reelle_source")}
        if base["conso_officielle"] is None and base["conso_reelle"] is None:
            missing.append(base)
            continue
        ref = base["conso_reelle"] if base["conso_reelle"] is not None else base["conso_officielle"]
        item = {**base, "ref": float(ref),
                "basis": "reelle" if base["conso_reelle"] is not None else "officielle"}
        if base["conso_officielle"] is not None and base["conso_reelle"] is not None:
            delta = round(float(base["conso_reelle"]) - float(base["conso_officielle"]), 1)
            item["ecart_l"] = delta
            item["ecart_pct"] = round(delta / float(base["conso_officielle"]) * 100) if float(base["conso_officielle"]) else None
        items.append(item)
    items.sort(key=lambda x: x["ref"])
    for i, it in enumerate(items):
        it["rang"] = i + 1
    return {"classement": items, "sans_donnees": missing, "total": len(vehicles)}


@api_router.get("/vehicles/{vehicle_id}/history")
async def get_vehicle_history(vehicle_id: str):
    return await db.audit_logs.find(
        {"vehicle_id": vehicle_id}, {"_id": 0}).sort("created_at", -1).to_list(50)


# ---------------------------------------------------------------------------
# Seed demo fleet
# ---------------------------------------------------------------------------
def iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


VAN_PHOTOS = [
    "https://images.unsplash.com/photo-1695222833131-54ee679ae8e5?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    "https://images.unsplash.com/photo-1606611013016-969c19ba27bb?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
]

# ---------------------------------------------------------------------------
# Demo administrative data (fictional) — fills empty vehicles for showcasing.
# ---------------------------------------------------------------------------
DEMO_LEASING_COS = ["Arval Suisse", "ALD Automotive", "LeasePlan", "PostFinance Leasing", "Mobility Fleet", "AMAG Leasing"]
DEMO_INSURERS = ["AXA", "Zurich Assurances", "La Mobilière", "Allianz Suisse", "Helvetia", "Vaudoise"]
DEMO_CENTRES = ["Service auto OCAN Genève", "SAN Vaud Lausanne", "StVA Zürich", "OCN Fribourg", "Service auto VS Sion", "SAN Vaud Nyon"]
DEMO_COUVERTURE = ["Casco complète", "Casco partielle", "RC + Casco complète", "Casco complète", "RC", "Casco partielle"]
# Échéances variées (jours) -> mix expiré / critique / attention / ok
DEMO_LEASING_FIN = [-18, 62, 520, 84, 690, 880, 150, 25, 400, -5, 300, 730]
DEMO_ASS_ECH = [24, 210, 430, 47, -6, 600, 90, 300, 55, 700, 18, 250]
DEMO_CTRL = [19, 410, 540, 73, 300, 6, 200, 500, 30, 120, 800, 60]
DEMO_MENSUALITE = [890, 1040, 760, 1180, 950, 820, 910, 1090, 780, 1150, 860, 990]
DEMO_PRIME = [1980, 1450, 2340, 1720, 980, 1290, 2100, 1600, 1180, 2450, 1350, 1890]
DEMO_FRANCHISE = [1000, 500, 2000, 1000, 0, 500]
DEMO_DMG_PHOTOS = [
    "https://images.unsplash.com/photo-1654027197679-84c14708d5de?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    "https://images.unsplash.com/photo-1673187139211-1e7ec3dd60ec?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
]


def _demo_admin_data(i: int, annee: int = 0) -> dict:
    n = len(DEMO_LEASING_FIN)
    lfin, aech, ctrl = DEMO_LEASING_FIN[i % n], DEMO_ASS_ECH[i % n], DEMO_CTRL[i % n]
    duree = 48
    mensualite = DEMO_MENSUALITE[i % len(DEMO_MENSUALITE)]
    debut = (date.today() + timedelta(days=lfin) - timedelta(days=duree * 30)).isoformat()
    yr = annee if annee and annee > 1990 else 2021
    return {
        "leasing": {
            "societe": DEMO_LEASING_COS[i % len(DEMO_LEASING_COS)],
            "numero_contrat": f"LSG-2022-{4500 + i}",
            "date_debut": debut,
            "date_fin": iso(lfin),
            "mensualite_chf": mensualite,
            "duree_mois": duree,
            "km_contractuel": 120000,
            "option_achat": i % 2 == 0,
            "valeur_residuelle": 9800 + (i % 6) * 1400,
            "cout_total": mensualite * duree,
            "cout_mensuel": mensualite,
            "commentaires": "Données de démonstration · entretien inclus, pneus hiver fournis.",
        },
        "assurance": {
            "compagnie": DEMO_INSURERS[i % len(DEMO_INSURERS)],
            "numero_police": f"POL-{780000 + i * 11}",
            "type_couverture": DEMO_COUVERTURE[i % len(DEMO_COUVERTURE)],
            "prime_annuelle": DEMO_PRIME[i % len(DEMO_PRIME)],
            "franchise": DEMO_FRANCHISE[i % len(DEMO_FRANCHISE)],
            "assistance": True,
            "contact_sinistre": "+41 800 80 80 80",
            "date_debut": iso(aech - 365),
            "date_echeance": iso(aech),
        },
        "carte_grise": {
            "date_mise_circulation": iso(-((2026 - yr) * 365)),
            "poids_total": 3500,
            "nombre_places": 3,
        },
        "controle_technique": {
            "date_dernier": iso(ctrl - 730),
            "date_prochain": iso(ctrl),
            "centre": DEMO_CENTRES[i % len(DEMO_CENTRES)],
            "resultat": "Conforme" if i % 3 else "Conforme avec remarques",
        },
    }


def _has_admin_data(v: dict) -> bool:
    leasing = (v.get("leasing") or {}).get("date_fin")
    assurance = (v.get("assurance") or {}).get("date_echeance")
    controle = (v.get("controle_technique") or {}).get("date_prochain")
    return bool(leasing or assurance or controle)


async def enrich_demo_admin() -> dict:
    """Fill fictional admin data on vehicles that have none (non-destructive)."""
    vehicles = await db.vehicles.find({}, {"_id": 0}).sort("plaque", 1).to_list(1000)
    now = datetime.now(timezone.utc).isoformat()
    enriched = 0
    for i, v in enumerate(vehicles):
        if _has_admin_data(v):
            continue
        fields = {**_demo_admin_data(i, v.get("annee") or 0), "updated_at": now}
        if not v.get("photo_url"):
            fields["photo_url"] = VAN_PHOTOS[i % len(VAN_PHOTOS)]
        await db.vehicles.update_one({"id": v["id"]}, {"$set": fields})
        enriched += 1

    inspections_added = 0
    if vehicles and await db.inspections.count_documents({}) == 0:
        vid = vehicles[0]["id"]
        km = vehicles[0].get("kilometrage") or 80000
        samples = [
            {
                "id": str(uuid.uuid4()), "vehicle_id": vid, "date": iso(-200),
                "responsable": vehicles[0].get("responsable") or "Marc Favre",
                "kilometrage": max(0, km - 13000),
                "commentaire": "Données de démo · état général bon. Rayure portière avant droite signalée.",
                "photos": [
                    {"angle": "avant_gauche", "url": VAN_PHOTOS[0], "kind": "image"},
                    {"angle": "dommages", "url": DEMO_DMG_PHOTOS[0], "kind": "image"},
                ],
                "created_at": now,
            },
            {
                "id": str(uuid.uuid4()), "vehicle_id": vid, "date": iso(-12),
                "responsable": "Sophie Dubois", "kilometrage": km,
                "commentaire": "Données de démo · nouveau choc pare-chocs arrière. Devis carrosserie demandé.",
                "photos": [
                    {"angle": "arriere_droite", "url": DEMO_DMG_PHOTOS[1], "kind": "image"},
                    {"angle": "dommages", "url": DEMO_DMG_PHOTOS[0], "kind": "image"},
                ],
                "created_at": now,
            },
        ]
        await db.inspections.insert_many([dict(x) for x in samples])
        inspections_added = len(samples)

    return {"enriched": enriched, "total": len(vehicles), "inspections_added": inspections_added}


async def seed_data():
    count = await db.vehicles.count_documents({})
    if count > 0:
        return

    specs = [
        # plaque, marque, modele, annee, base, groupe, responsable, km, leasing_fin, ass_ech, ctrl_prochain, maint, exp, photo
        ("GE 123 456", "Mercedes-Benz", "Sprinter 316", 2021, "Genève", "Livraison", "Marc Favre", 84200, -18, 24, 19, 12, 380, 0),
        ("VD 456 789", "Volkswagen", "Crafter 35", 2022, "Lausanne", "Technique", "Léa Rochat", 51300, 62, 210, 410, 40, 300, 1),
        ("ZH 789 012", "Ford", "Transit Custom", 2023, "Zürich", "Direction", "Daniel Meier", 28900, 520, 430, 540, 200, 600, 2),
        ("GE 246 810", "Renault", "Master 150", 2020, "Genève", "Livraison", "Sophie Dubois", 132400, 84, 47, 73, 25, 120, 1),
        ("FR 135 791", "Iveco", "Daily 35S", 2021, "Fribourg", "Technique", "Antoine Berset", 97600, 690, -6, 300, 60, 250, 2),
        ("VS 975 310", "Peugeot", "Boxer 335", 2022, "Sion", "Livraison", "Camille Roux", 43800, 880, 600, 6, 15, 410, 0),
    ]
    leasing_cos = ["Arval Suisse", "ALD Automotive", "LeasePlan", "PostFinance Leasing", "Mobility Fleet", "AMAG Leasing"]
    insurers = ["AXA", "Zurich Assurances", "La Mobilière", "Allianz Suisse", "Helvetia", "Vaudoise"]
    centres = ["Service auto OCAN Genève", "SAN Vaud Lausanne", "StVA Zürich", "OCN Fribourg", "Service auto VS Sion", "SAN Vaud Nyon"]

    vehicles = []
    for i, (plaque, marque, modele, annee, base, groupe, resp, km, lfin, aech, cprochain, maint, exp, photo) in enumerate(specs):
        duree = 48
        mensualite = [890, 1040, 760, 1180, 950, 820][i]
        debut = (date.fromisoformat(iso(lfin)) - timedelta(days=duree * 30)).isoformat()
        vehicles.append({
            "id": str(uuid.uuid4()),
            "source": "demo",
            "photo_url": VAN_PHOTOS[photo],
            "plaque": plaque,
            "marque": marque,
            "modele": modele,
            "annee": annee,
            "vin": f"WDB{906633 + i}A{100000 + i * 137}",
            "kilometrage": km,
            "groupe": groupe,
            "base": base,
            "responsable": resp,
            "tracker_gps": f"LT-GPS-{1000 + i}",
            "prochaine_maintenance": iso(maint),
            "prochaine_expertise": iso(exp),
            "leasing": {
                "societe": leasing_cos[i],
                "numero_contrat": f"LSG-2022-{4500 + i}",
                "date_debut": debut,
                "date_fin": iso(lfin),
                "mensualite_chf": mensualite,
                "duree_mois": duree,
                "km_contractuel": 120000,
                "option_achat": i % 2 == 0,
                "valeur_residuelle": [12500, 15800, 18200, 9800, 13400, 11200][i],
                "cout_total": mensualite * duree,
                "cout_mensuel": mensualite,
                "commentaires": "Entretien inclus, pneus hiver fournis.",
            },
            "assurance": {
                "compagnie": insurers[i],
                "numero_police": f"POL-{780000 + i * 11}",
                "type_couverture": ["Casco complète", "Casco partielle", "RC + Casco complète", "Casco complète", "RC", "Casco partielle"][i],
                "prime_annuelle": [1980, 1450, 2340, 1720, 980, 1290][i],
                "franchise": [1000, 500, 2000, 1000, 0, 500][i],
                "assistance": True,
                "contact_sinistre": "+41 800 80 80 80",
                "date_debut": iso(aech - 365),
                "date_echeance": iso(aech),
            },
            "carte_grise": {
                "date_mise_circulation": iso(-((2026 - annee) * 365)),
                "poids_total": [3500, 3500, 3200, 3500, 3500, 3500][i],
                "nombre_places": 3,
            },
            "controle_technique": {
                "date_dernier": iso(cprochain - 730),
                "date_prochain": iso(cprochain),
                "centre": centres[i],
                "resultat": "Conforme" if i % 3 else "Conforme avec remarques",
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    await db.vehicles.insert_many([dict(v) for v in vehicles])

    # Seed a couple of inspections (état des lieux) with demo photos
    dmg1 = "https://images.unsplash.com/photo-1654027197679-84c14708d5de?crop=entropy&cs=srgb&fm=jpg&q=85&w=900"
    dmg2 = "https://images.unsplash.com/photo-1673187139211-1e7ec3dd60ec?crop=entropy&cs=srgb&fm=jpg&q=85&w=900"
    inspections = [
        {
            "id": str(uuid.uuid4()),
            "vehicle_id": vehicles[0]["id"],
            "date": iso(-200),
            "responsable": "Marc Favre",
            "kilometrage": 71200,
            "commentaire": "État général bon. Rayure portière avant droite signalée.",
            "photos": [
                {"angle": "avant_gauche", "url": VAN_PHOTOS[0], "kind": "image"},
                {"angle": "dommages", "url": dmg1, "kind": "image"},
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "id": str(uuid.uuid4()),
            "vehicle_id": vehicles[0]["id"],
            "date": iso(-12),
            "responsable": "Sophie Dubois",
            "kilometrage": 84200,
            "commentaire": "Nouveau choc pare-chocs arrière. Devis carrosserie demandé.",
            "photos": [
                {"angle": "arriere_droite", "url": dmg2, "kind": "image"},
                {"angle": "dommages", "url": dmg1, "kind": "image"},
            ],
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    await db.inspections.insert_many([dict(x) for x in inspections])
    logger.info("Seeded demo fleet: %d vehicles", len(vehicles))


@app.on_event("startup")
async def startup():
    try:
        await db.alerts.create_index([("vehicle_id", 1), ("type", 1), ("threshold", 1), ("due_date", 1)])
        await db.alerts.create_index([("kind", 1), ("digest_date", 1)])
        await db.vehicles.create_index("navixy_tracker_id")
        await db.vehicle_field_meta.create_index([("vehicle_id", 1), ("field", 1)], unique=True)
        await db.audit_logs.create_index([("vehicle_id", 1), ("created_at", -1)])
        await db.fuel_snapshots.create_index([("vehicle_id", 1), ("day", 1)], unique=True)
        await db.astra_tas.create_index("_key", unique=True)
        await db.astra_tg.create_index("_key", unique=True)
        await db.astra_tas_emissions.create_index([("_key", 1), ("seq", 1)], unique=True)
        await db.astra_tg_verbrauch.create_index([("_key", 1), ("seq", 1)], unique=True)
        await db.astra_edatenblatt.create_index("_key")
        await db.astra_edatenblatt.create_index([("_key", 1), ("sig", 1)])
        await db.astra_import_runs.create_index([("dataset", 1), ("started_at", -1)])
    except Exception as e:
        logger.error(f"Index creation failed: {e}")
    try:
        await db.users.create_index("email", unique=True)
        await db.login_attempts.create_index("identifier", unique=True)
        await seed_admin(db)
    except Exception as e:
        logger.error(f"Auth seed failed: {e}")
    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    try:
        await seed_data()
    except Exception as e:
        logger.error(f"Seed failed: {e}")
    try:
        if NAVIXY_HASH and await db.vehicles.count_documents({"source": "navixy"}) == 0:
            result = await navixy_sync_internal()
            logger.info("Navixy auto-sync: %s", result)
    except Exception as e:
        logger.error(f"Navixy sync failed: {e}")
    try:
        result = await run_alerts()
        logger.info("Initial alerts run: %s", result)
    except Exception as e:
        logger.error(f"Initial alerts run failed: {e}")
    try:
        scheduler = AsyncIOScheduler(timezone="UTC")

        async def daily_job():
            try:
                if NAVIXY_HASH:
                    await navixy_sync_internal()
            except Exception as e:
                logger.error(f"Scheduled Navixy sync failed: {e}")
            try:
                await run_alerts()
            except Exception as e:
                logger.error(f"Scheduled alerts failed: {e}")

        scheduler.add_job(daily_job, IntervalTrigger(hours=24), id="daily-sync-alerts", replace_existing=True)
        if astra_data.sync_enabled():
            async def astra_sync_job():
                try:
                    await astra_data.run_import(db, download=True, force_download=True)
                except Exception as e:
                    logger.error(f"Scheduled ASTRA sync failed: {e}")

            scheduler.add_job(astra_sync_job, IntervalTrigger(days=30),
                              id="astra-monthly-sync", replace_existing=True)
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Scheduler started: daily Navixy sync + deadline alerts")
    except Exception as e:
        logger.error(f"Scheduler start failed: {e}")
    try:
        if astra_data.sync_enabled() and not await astra_data.import_active(db):
            pending = await astra_data.pending_datasets(db)
            if pending:
                logger.info("ASTRA auto-import au démarrage: %s", pending)
                asyncio.create_task(astra_data.run_import(db, datasets=pending, download=True))
    except Exception as e:
        logger.error(f"ASTRA auto-import start failed: {e}")


app.include_router(auth_router)
app.include_router(api_router, dependencies=[Depends(require_auth)])

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
