"""Phase 4C — Lot E : référentiel cartes carburant (`fuel_cards`) + affectations datées (`fuel_card_assignments`).
Identité = UUID tenant-scopé ; `(fournisseur, last4)` NON unique (D2) → collision = avertissement + confirmation humaine,
jamais d'auto-fusion ; AUCUN fingerprint HMAC Journal (secret non portable) ; statut déclaré jamais modifié
automatiquement ; `expiration_state` dérivé en lecture seule des seuils Échéances du tenant."""
import re
from typing import Optional

from pydantic import BaseModel, ConfigDict

STATUSES = ("active", "suspendue", "expiree", "bloquee", "remplacee")  # Journal 1:1
JOURNAL_STATUS_MAP = {"active": "active", "suspended": "suspendue", "expired": "expiree", "blocked": "bloquee",
                      "replaced": "remplacee"}
STATUS_LABELS = {"active": "Active", "suspendue": "Suspendue", "expiree": "Expirée", "bloquee": "Bloquée",
                 "remplacee": "Remplacée"}
ASSIGNMENT_TYPES = ("vehicule", "conducteur", "pool", "autre")  # Journal vehicle|driver|pool|other
JOURNAL_ASSIGNMENT_TYPE_MAP = {"vehicle": "vehicule", "driver": "conducteur", "pool": "pool", "other": "autre"}
ASSIGNMENT_TYPE_LABELS = {"vehicule": "Véhicule", "conducteur": "Conducteur", "pool": "Pool", "autre": "Autre"}
EXPIRATION_STATES = ("valide", "bientot", "expiree", "sans_date")
EXPIRATION_LABELS = {"valide": "Valide", "bientot": "Expire bientôt", "expiree": "Expirée", "sans_date": "Sans date"}
WARNING_LABELS = {"CARD_EXPIRED": "Carte expirée (date dépassée)", "CARD_EXPIRING_SOON": "Expiration prochaine",
                  "CARD_UNASSIGNED": "Carte active sans affectation en cours",
                  "ASSIGNMENT_INCONSISTENT": "Affectation en cours incohérente (véhicule ou conducteur indisponible)",
                  "CARD_NOT_ACTIVE": "Statut non actif"}
SOURCES = ("manual", "legacy_import")
MOTIF_MIN_LEN = 3
CARD_FIELDS = ("fournisseur", "compte_fournisseur", "last4", "numero_masque", "external_card_id", "type_affectation",
               "produits_autorises", "plafond_tx", "plafond_jour", "plafond_mois", "pays_autorises", "activee_le",
               "expire_le", "notes")
LIFECYCLE_FIELDS = ("statut", "remplacee_par", "is_deleted", "archive_motif", "archived_at", "archived_by")  # jamais écrasés par un rejeu
FORBIDDEN_KEYS = ("fingerprint", "hmac", "numero", "numero_complet", "card_number", "pan")  # D2 : jamais stockés
LAST4_RE = re.compile(r"^\d{4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FLOOR = "0000-00-00"  # valid_from null (legacy) = depuis toujours


class FuelCardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")  # tout champ inconnu (ex. `fingerprint`) → 422
    fournisseur: str
    last4: str
    compte_fournisseur: Optional[str] = None
    numero_masque: Optional[str] = None
    external_card_id: Optional[str] = None
    type_affectation: str = "vehicule"
    produits_autorises: list = []
    plafond_tx: Optional[float] = None
    plafond_jour: Optional[float] = None
    plafond_mois: Optional[float] = None
    pays_autorises: list = []
    activee_le: Optional[str] = None
    expire_le: Optional[str] = None
    statut: str = "active"
    notes: Optional[str] = None
    collision_confirmed: bool = False
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None


class FuelCardUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fournisseur: Optional[str] = None
    last4: Optional[str] = None
    compte_fournisseur: Optional[str] = None
    numero_masque: Optional[str] = None
    external_card_id: Optional[str] = None
    type_affectation: Optional[str] = None
    produits_autorises: Optional[list] = None
    plafond_tx: Optional[float] = None
    plafond_jour: Optional[float] = None
    plafond_mois: Optional[float] = None
    pays_autorises: Optional[list] = None
    activee_le: Optional[str] = None
    expire_le: Optional[str] = None
    notes: Optional[str] = None
    collision_confirmed: bool = False


class FuelCardStatus(BaseModel):
    statut: str
    motif: Optional[str] = None
    remplacee_par: Optional[str] = None


class FuelCardArchive(BaseModel):
    motif: Optional[str] = None


class CardAssignmentCreate(BaseModel):
    type: str = "vehicule"
    vehicle_id: Optional[str] = None
    driver_id: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    motif: Optional[str] = None
    replace: bool = False
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None


class CardAssignmentClose(BaseModel):
    valid_to: Optional[str] = None
    motif: Optional[str] = None


def clean_str(v) -> Optional[str]:
    s = (v or "").strip() if isinstance(v, str) else v
    return s or None


def is_date(v) -> bool:
    if not (isinstance(v, str) and DATE_RE.match(v)):
        return False
    from datetime import datetime
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def normalize_status(value: str) -> str:
    v = (value or "").strip().lower()
    v = JOURNAL_STATUS_MAP.get(v, v)
    if v not in STATUSES:
        raise ValueError(f"statut inconnu « {value} » — valeurs : {', '.join(STATUSES)}")
    return v


def normalize_assignment_type(value: str) -> str:
    v = (value or "").strip().lower()
    v = JOURNAL_ASSIGNMENT_TYPE_MAP.get(v, v)
    if v not in ASSIGNMENT_TYPES:
        raise ValueError(f"type d'affectation inconnu « {value} » — valeurs : {', '.join(ASSIGNMENT_TYPES)}")
    return v


def normalize_card(data: dict) -> dict:
    out = {}
    for k in CARD_FIELDS:
        if k not in data:
            continue
        v = data[k]
        if k in ("fournisseur", "compte_fournisseur", "numero_masque", "external_card_id", "activee_le", "expire_le", "notes"):
            out[k] = clean_str(v)
        elif k == "last4":
            out[k] = (v or "").strip() if isinstance(v, str) else v
        elif k in ("produits_autorises", "pays_autorises"):
            out[k] = [str(x).strip() for x in (v or []) if str(x).strip()] if v is not None else None
        elif k == "type_affectation":
            out[k] = (v or "").strip().lower() if isinstance(v, str) else v
        else:
            out[k] = v
    return out


def card_errors(d: dict, partial: bool = False) -> list:
    errors = []
    if not partial or "fournisseur" in d:
        if not d.get("fournisseur"):
            errors.append("fournisseur obligatoire")
    if not partial or "last4" in d:
        if not (isinstance(d.get("last4"), str) and LAST4_RE.match(d["last4"])):
            errors.append("last4 : exactement 4 chiffres")
    if d.get("numero_masque") and len(re.findall(r"\d", d["numero_masque"])) > 4:
        errors.append("numero_masque : au plus 4 chiffres visibles (aucun numéro complet)")
    if d.get("type_affectation") is not None:
        try:
            d["type_affectation"] = normalize_assignment_type(d["type_affectation"])
        except ValueError as e:
            errors.append(str(e).replace("type d'affectation", "type_affectation"))
    for k in ("activee_le", "expire_le"):
        if d.get(k) and not is_date(d[k]):
            errors.append(f"{k} invalide (AAAA-MM-JJ)")
    if d.get("activee_le") and d.get("expire_le") and is_date(d["activee_le"]) and is_date(d["expire_le"]) \
            and d["expire_le"] < d["activee_le"]:
        errors.append("expire_le antérieure à activee_le")
    for k in ("plafond_tx", "plafond_jour", "plafond_mois"):
        if d.get(k) is not None and d[k] < 0:
            errors.append(f"{k} invalide")
    return errors


def source_errors(payload) -> list:
    errors = []
    if payload.source not in SOURCES:
        errors.append("source : manual ou legacy_import")
    if payload.source == "legacy_import" and not clean_str(payload.legacy_id):
        errors.append("legacy_id obligatoire pour un import legacy")
    return errors


def assignment_errors(payload: CardAssignmentCreate) -> list:
    errors = source_errors(payload)
    try:
        payload.type = normalize_assignment_type(payload.type)
    except ValueError as e:
        errors.append(str(e))
    if payload.type == "vehicule" and not clean_str(payload.vehicle_id):
        errors.append("vehicle_id obligatoire pour une affectation véhicule")
    if payload.type == "conducteur" and not clean_str(payload.driver_id):
        errors.append("driver_id obligatoire pour une affectation conducteur")
    if payload.type != "vehicule" and clean_str(payload.vehicle_id):
        errors.append("vehicle_id réservé au type véhicule")
    if payload.type != "conducteur" and clean_str(payload.driver_id):
        errors.append("driver_id réservé au type conducteur")
    if payload.valid_from is None:
        if payload.source != "legacy_import":
            errors.append("valid_from obligatoire (AAAA-MM-JJ) — null réservé aux imports legacy (§2.14)")
    elif not is_date(payload.valid_from):
        errors.append("valid_from invalide (AAAA-MM-JJ)")
    if payload.valid_to and not is_date(payload.valid_to):
        errors.append("valid_to invalide (AAAA-MM-JJ)")
    if payload.valid_from and payload.valid_to and is_date(payload.valid_from) and is_date(payload.valid_to) \
            and payload.valid_to < payload.valid_from:
        errors.append("valid_to antérieure à valid_from")
    if payload.replace and len(clean_str(payload.motif) or "") < MOTIF_MIN_LEN:
        errors.append("motif obligatoire pour remplacer une affectation en cours")
    return errors


def overlaps(a_from, a_to, b_from, b_to) -> bool:
    """Intervalles inclusifs ; `None` début = depuis toujours, `None` fin = en cours (même sémantique que Lot C)."""
    a_from, b_from = a_from or FLOOR, b_from or FLOOR
    return (a_to is None or a_to >= b_from) and (b_to is None or b_to >= a_from)


def covers(a_from, a_to, day: str) -> bool:
    return (a_from or FLOOR) <= day and (a_to is None or a_to >= day)


def current_by_type(assignments: list, day: str) -> dict:
    """Affectation courante par type à une date — règle du jour de passation Lot C : l'affectation remplacée qui se
    termine ce jour-là s'efface devant la nouvelle. Jamais deux affectations courantes pour un même type."""
    out = {}
    for t in ASSIGNMENT_TYPES:
        cands = [a for a in assignments if a.get("type") == t and covers(a.get("valid_from"), a.get("valid_to"), day)]
        if len(cands) > 1:
            cands = [a for a in cands if not (a.get("replaced") and a.get("valid_to") == day)] or cands
        cands.sort(key=lambda a: a.get("valid_from") or FLOOR, reverse=True)
        if cands:
            out[t] = {**cands[0], "ambiguous": len(cands) > 1}
    return out


def expiration(expire_le: Optional[str], days: Optional[int], statut_echeance: str) -> dict:
    """Dérivé lecture seule depuis `expire_le` + moteur Échéances du tenant (aucune écriture de statut)."""
    if not expire_le:
        state = "sans_date"
    elif statut_echeance == "EXPIRE":
        state = "expiree"
    elif statut_echeance in ("URGENT", "A_PLANIFIER"):
        state = "bientot"
    elif statut_echeance == "DATE_INVALIDE":
        state = "sans_date"
    else:
        state = "valide"
    return {"expiration_state": state, "expiration_label": EXPIRATION_LABELS[state], "expiration_statut": statut_echeance,
            "expiration_days": days}


def usable(statut: str, expiration_state: str) -> bool:
    return statut == "active" and expiration_state != "expiree"


def display_label(card: dict) -> str:
    return f"{card.get('fournisseur') or 'Carte'} ••••{card.get('last4') or '????'}"


def warnings_for(card: dict, exp: dict, current: dict, refs_ok: dict) -> list:
    out = []
    if exp["expiration_state"] == "expiree":
        out.append("CARD_EXPIRED")
    elif exp["expiration_state"] == "bientot":
        out.append("CARD_EXPIRING_SOON")
    if card.get("statut") != "active":
        out.append("CARD_NOT_ACTIVE")
    elif not current:
        out.append("CARD_UNASSIGNED")
    if any(not ok for ok in refs_ok.values()):
        out.append("ASSIGNMENT_INCONSISTENT")
    return [{"code": c, "label": WARNING_LABELS[c]} for c in out]


def diff_fields(before: dict, after: dict) -> list:
    return [f"{k}: {before.get(k) if before.get(k) not in (None, []) else '—'} → {after[k] if after[k] not in (None, []) else '—'}"
            for k in after if k in CARD_FIELDS and after[k] != before.get(k)]


def fmt(v) -> str:
    return "—" if v in (None, "", []) else str(v)
