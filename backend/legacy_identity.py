"""Phase 4C — Lot A : identité legacy (Journal → Documents), idempotence et résolution lecture seule.

Aucune migration ici : seules des correspondances confirmées par un humain sont écrites.
Règles figées (D3/D4) : tenant par clé technique uniquement ; plaque = revue manuelle ;
tracker = affectation évolutive (avertissement, jamais identité historique).
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

LEGACY_SOURCE_DEFAULT = "journal"
LEGACY_SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
LEGACY_COLLECTIONS = ("documents", "fuel_transactions")  # lots C/E : drivers, fuel_cards, ...
TENANT_MATCH_KEY = "navixy_master_user_id"
MIGRATION_VERSION = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_vin(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())


def norm_plate(p) -> str:
    return re.sub(r"[^A-Z0-9]", "", (p or "").upper())


def normalize_source(value) -> str:
    src = (value or LEGACY_SOURCE_DEFAULT).strip().lower()
    if not LEGACY_SOURCE_RE.match(src):
        raise ValueError("legacy_source invalide")
    return src


def identity(v: dict) -> dict:
    return {"vehicle_id": v.get("id"), "vin": v.get("vin") or None,
            "plate": v.get("plaque") or None, "make": v.get("marque") or None,
            "model": v.get("modele") or None, "year": v.get("annee") or None,
            "navixy_tracker_id": v.get("navixy_tracker_id"),
            "navixy_vehicle_id": v.get("navixy_vehicle_id")}


def payload_sha256(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _criteria(vehicle_id=None, vin=None, navixy_vehicle_id=None, navixy_tracker_id=None, plate=None):
    vin_n, plate_n = norm_vin(vin), norm_plate(plate)
    criteria = []
    if vehicle_id:
        criteria.append(("vehicle_id", lambda v: v.get("id") == vehicle_id))
    if vin_n:
        criteria.append(("vin", lambda v: norm_vin(v.get("vin")) == vin_n))
    if navixy_vehicle_id is not None:
        criteria.append(("navixy_vehicle_id", lambda v: v.get("navixy_vehicle_id") == navixy_vehicle_id))
    if navixy_tracker_id is not None:
        criteria.append(("navixy_tracker_id", lambda v: v.get("navixy_tracker_id") == navixy_tracker_id))
    if plate_n:
        criteria.append(("plate", lambda v: norm_plate(v.get("plaque")) == plate_n))
    return criteria


def resolve_identity(vehicles, vehicle_id=None, vin=None, navixy_vehicle_id=None,
                     navixy_tracker_id=None, plate=None) -> dict:
    """Résolution LECTURE SEULE (contrat P0). Ordre : vehicle_id > vin > navixy_vehicle_id > tracker > plate.
    plate : jamais de match automatique (manual_review). Plusieurs résultats sur un critère fort = ambiguous."""
    criteria = _criteria(vehicle_id, vin, navixy_vehicle_id, navixy_tracker_id, plate)
    if not criteria:
        raise ValueError("Fournissez au moins un critère : vehicle_id, vin, navixy_vehicle_id, "
                         "navixy_tracker_id ou plate.")
    searched = [name for name, _ in criteria]
    for name, pred in criteria:
        matches = [v for v in vehicles if pred(v)]
        if name == "plate":
            if matches:
                return {"status": "manual_review", "matched_by": "plate", "count": len(matches),
                        "matches": [identity(m) for m in matches],
                        "note": "Rapprochement par plaque réservé à une confirmation manuelle"}
            continue
        if len(matches) == 1:
            out = {"status": "found", "matched_by": name, "vehicle": identity(matches[0])}
            if name == "navixy_tracker_id":
                out["warning"] = "tracker_join_no_assignment_history"
            return out
        if len(matches) > 1:
            return {"status": "ambiguous", "matched_by": name, "count": len(matches),
                    "matches": [identity(m) for m in matches]}
    return {"status": "not_found", "searched_by": searched}


_METHOD_BY_CRITERION = {"vin": "vin", "navixy_vehicle_id": "navixy_vehicle_id",
                        "navixy_tracker_id": "tracker_history_confirmed", "plate": "manual"}


def vehicle_candidates(vehicles, item: dict) -> dict:
    """Candidats Documents pour UN véhicule Journal — lecture seule, jamais de confirmation implicite.
    strong_candidate (vin / navixy_vehicle_id unique) · candidate_warning (tracker, évolutif)
    · manual_review (plaque) · ambiguous · not_found."""
    res = resolve_identity(vehicles, vin=item.get("vin"),
                           navixy_vehicle_id=item.get("navixy_vehicle_id"),
                           navixy_tracker_id=item.get("navixy_tracker_id"),
                           plate=item.get("plate")) if any(
        item.get(k) not in (None, "") for k in ("vin", "navixy_vehicle_id", "navixy_tracker_id", "plate")
    ) else {"status": "not_found", "searched_by": []}
    out = {"legacy_vehicle_id": item["legacy_vehicle_id"],
           "legacy": {k: item.get(k) for k in ("plate", "vin", "navixy_tracker_id", "navixy_vehicle_id", "model")},
           "candidates": [], "warnings": [], "method_suggested": None}
    matched_by = res.get("matched_by")
    if res["status"] == "found":
        out["status"] = "candidate_warning" if matched_by == "navixy_tracker_id" else "strong_candidate"
        out["candidates"] = [{**res["vehicle"], "matched_by": matched_by}]
        out["method_suggested"] = _METHOD_BY_CRITERION[matched_by]
        if res.get("warning"):
            out["warnings"].append(res["warning"])
    elif res["status"] in ("manual_review", "ambiguous"):
        out["status"] = res["status"]
        out["candidates"] = [{**m, "matched_by": matched_by} for m in res["matches"]]
        out["method_suggested"] = "manual"
        if res["status"] == "manual_review":
            out["warnings"].append("plate_requires_manual_confirmation")
    else:
        out["status"] = "not_found"
    return out


def tenant_candidates(integrations, tenants_by_id: dict, item: dict) -> dict:
    """Candidats tenant Documents par clé technique UNIQUEMENT (D3). `name` est ignoré."""
    raw = item.get(TENANT_MATCH_KEY)
    out = {"legacy_tenant_id": item["legacy_tenant_id"], "match_key": TENANT_MATCH_KEY,
           "match_value": None, "candidates": [], "note": "le nom n'est jamais utilisé pour la correspondance"}
    try:
        value = int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    if value is None:
        out["status"] = "no_technical_key"
        return out
    out["match_value"] = value
    matches = [i for i in integrations if i.get("master_user_id") == value]
    out["candidates"] = [{"tenant_id": i["tenant_id"],
                          "name": (tenants_by_id.get(i["tenant_id"]) or {}).get("name") or i["tenant_id"]}
                         for i in matches]
    out["status"] = "found" if len(matches) == 1 else ("ambiguous" if matches else "not_found")
    return out


async def ensure_legacy_indexes(db):
    for name in LEGACY_COLLECTIONS:
        await db[name].create_index(
            [("tenant_id", 1), ("legacy_source", 1), ("legacy_id", 1)], unique=True,
            partialFilterExpression={"legacy_id": {"$type": "string"}}, name="uniq_legacy_key")
    await db.legacy_tenant_map.create_index([("legacy_source", 1), ("legacy_tenant_id", 1)], unique=True)
    await db.legacy_vehicle_map.create_index(
        [("tenant_id", 1), ("legacy_source", 1), ("legacy_vehicle_id", 1)], unique=True)
    await db.legacy_vehicle_map.create_index([("tenant_id", 1), ("status", 1)])


async def upsert_legacy_record(db, collection: str, tenant_id: str, legacy_source: str,
                               legacy_id: str, payload: dict, migration_version: int = MIGRATION_VERSION) -> dict:
    """1 enregistrement Journal → max 1 enregistrement Documents. Rejouer = mise à jour, jamais un doublon."""
    if not (tenant_id and legacy_source and legacy_id):
        raise ValueError("tenant_id, legacy_source et legacy_id sont obligatoires")
    if payload.get("tenant_id") not in (None, tenant_id):
        raise ValueError("tenant_id du payload différent du tenant cible")
    key = {"tenant_id": tenant_id, "legacy_source": normalize_source(legacy_source), "legacy_id": str(legacy_id)}
    now = now_iso()
    body = {k: v for k, v in payload.items() if k not in ("_id", "id", "created_at")}
    body.update(key)
    body["migration_version"] = migration_version
    body["legacy_payload_sha256"] = payload_sha256(payload)
    body["updated_at"] = now
    coll = db[collection]
    existing = await coll.find_one(key, {"_id": 0, "id": 1, "legacy_payload_sha256": 1})
    if existing:
        await coll.update_one(key, {"$set": body})
        return {"id": existing["id"], "created": False,
                "changed": existing.get("legacy_payload_sha256") != body["legacy_payload_sha256"]}
    new_id = str(uuid.uuid4())
    await coll.insert_one({**body, "id": new_id, "created_at": payload.get("created_at") or now})
    return {"id": new_id, "created": True, "changed": True}
