"""Phase 4C — Lot C : référentiel conducteurs (`drivers`) + affectations datées véhicule↔conducteur
(`driver_assignments`). Identité = UUID tenant-scopé ; nom/prénom = affichage uniquement, jamais une clé
de résolution ; `driver_id` optionnel sur documents / fuel_transactions (FK validée dans le tenant)."""
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

TENANT_TZ = "Europe/Zurich"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DRIVER_FIELDS = ("nom", "prenom", "email", "telephone", "matricule_interne", "navixy_employee_id",
                 "actif", "date_debut", "date_fin", "groupe", "notes")
SOURCES = ("manual", "legacy_import")


class DriverCreate(BaseModel):
    nom: str
    prenom: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    matricule_interne: Optional[str] = None
    navixy_employee_id: Optional[int] = None
    actif: bool = True
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    groupe: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None


class DriverUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    email: Optional[str] = None
    telephone: Optional[str] = None
    matricule_interne: Optional[str] = None
    navixy_employee_id: Optional[int] = None
    actif: Optional[bool] = None
    date_debut: Optional[str] = None
    date_fin: Optional[str] = None
    groupe: Optional[str] = None
    notes: Optional[str] = None


class AssignmentCreate(BaseModel):
    driver_id: str
    valid_from: str
    valid_to: Optional[str] = None
    principal: bool = True
    motif: Optional[str] = None
    replace: bool = False
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None


class AssignmentClose(BaseModel):
    valid_to: Optional[str] = None
    motif: Optional[str] = None


def clean_str(v) -> Optional[str]:
    s = (v or "").strip() if isinstance(v, str) else v
    return s or None


def norm_email(v) -> Optional[str]:
    s = clean_str(v)
    return s.lower() if s else None


def today_zurich() -> str:
    return datetime.now(ZoneInfo(TENANT_TZ)).date().isoformat()


def is_date(v) -> bool:
    if not (isinstance(v, str) and DATE_RE.match(v)):
        return False
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_driver(data: dict) -> dict:
    """Nettoie les champs métier d'un conducteur (sans créer de clé d'identité sur le nom)."""
    out = {}
    for k in DRIVER_FIELDS:
        if k not in data:
            continue
        v = data[k]
        if k == "email":
            out[k] = norm_email(v)
        elif k in ("nom", "prenom", "telephone", "matricule_interne", "groupe", "notes", "date_debut", "date_fin"):
            out[k] = clean_str(v)
        else:
            out[k] = v
    return out


def driver_errors(d: dict, partial: bool = False) -> list:
    errors = []
    if not partial or "nom" in d:
        if not d.get("nom"):
            errors.append("nom obligatoire (donnée d'affichage)")
    if d.get("email") and not EMAIL_RE.match(d["email"]):
        errors.append("email invalide")
    for k in ("date_debut", "date_fin"):
        if d.get(k) and not is_date(d[k]):
            errors.append(f"{k} invalide (AAAA-MM-JJ)")
    if d.get("date_debut") and d.get("date_fin") and is_date(d["date_debut"]) and is_date(d["date_fin"]) \
            and d["date_fin"] < d["date_debut"]:
        errors.append("date_fin antérieure à date_debut")
    if d.get("navixy_employee_id") is not None and d["navixy_employee_id"] < 0:
        errors.append("navixy_employee_id invalide")
    return errors


def source_errors(payload) -> list:
    errors = []
    if payload.source not in SOURCES:
        errors.append("source : manual ou legacy_import")
    if payload.source == "legacy_import" and not clean_str(payload.legacy_id):
        errors.append("legacy_id obligatoire pour un import legacy")
    return errors


def assignment_errors(payload: AssignmentCreate) -> list:
    errors = source_errors(payload)
    if not is_date(payload.valid_from):
        errors.append("valid_from invalide (AAAA-MM-JJ)")
    if payload.valid_to and not is_date(payload.valid_to):
        errors.append("valid_to invalide (AAAA-MM-JJ)")
    if is_date(payload.valid_from) and payload.valid_to and is_date(payload.valid_to) and payload.valid_to < payload.valid_from:
        errors.append("valid_to antérieure à valid_from")
    if payload.replace and len(clean_str(payload.motif) or "") < 3:
        errors.append("motif obligatoire pour remplacer une affectation en cours")
    return errors


def overlaps(a_from: str, a_to: Optional[str], b_from: str, b_to: Optional[str]) -> bool:
    """Intervalles de dates inclusifs ; `None` = ouvert (affectation active)."""
    return (a_to is None or a_to >= b_from) and (b_to is None or b_to >= a_from)


def covers(a_from: str, a_to: Optional[str], day: str) -> bool:
    return a_from <= day and (a_to is None or a_to >= day)


def display_name(d: Optional[dict]) -> Optional[str]:
    if not d:
        return None
    name = " ".join(x for x in (d.get("prenom"), d.get("nom")) if x) or d.get("nom") or "Conducteur"
    return f"{name} · {d['matricule_interne']}" if d.get("matricule_interne") else name


def diff_fields(before: dict, after: dict) -> list:
    return [f"{k}: {before.get(k) if before.get(k) is not None else '—'} → {after[k] if after[k] is not None else '—'}"
            for k in after if k in DRIVER_FIELDS and after[k] != before.get(k)]
