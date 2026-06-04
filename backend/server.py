from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import requests
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone, date, timedelta

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
# Object storage helpers (Emergent object storage)
# ---------------------------------------------------------------------------
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "logitrak-fleet"
storage_key = None

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


def init_storage():
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
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
        raise NavixyError("Clé API Navixy non configurée")
    body = {"hash": NAVIXY_HASH}
    if payload:
        body.update(payload)
    try:
        resp = requests.post(f"{NAVIXY_BASE_URL}{path}", json=body, timeout=30)
    except requests.RequestException as exc:
        raise NavixyError(f"Erreur réseau Navixy: {exc}")
    try:
        data = resp.json()
    except ValueError:
        raise NavixyError(f"Réponse Navixy invalide (HTTP {resp.status_code})")
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

        existing = await db.vehicles.find_one({"navixy_tracker_id": tid})
        if existing:
            await db.vehicles.update_one({"navixy_tracker_id": tid}, {"$set": navixy_fields})
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
    account = (info.get("paas_settings", {}) or {}).get("service_title") or "Navixy"
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


@api_router.get("/vehicles/{vehicle_id}/live")
async def vehicle_live(vehicle_id: str):
    v = await db.vehicles.find_one({"id": vehicle_id}, {"_id": 0})
    if not v:
        raise HTTPException(status_code=404, detail="Véhicule introuvable")
    tid = v.get("navixy_tracker_id")
    if not tid:
        raise HTTPException(status_code=400, detail="Véhicule non lié à un tracker Navixy")
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
# Seed demo fleet
# ---------------------------------------------------------------------------
def iso(offset_days: int) -> str:
    return (date.today() + timedelta(days=offset_days)).isoformat()


VAN_PHOTOS = [
    "https://images.unsplash.com/photo-1695222833131-54ee679ae8e5?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    "https://images.unsplash.com/photo-1606611013016-969c19ba27bb?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
    "https://images.unsplash.com/photo-1601584115197-04ecc0da31d7?crop=entropy&cs=srgb&fm=jpg&q=85&w=900",
]


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


app.include_router(api_router)

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
