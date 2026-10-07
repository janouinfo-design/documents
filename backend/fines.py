"""Phase 4C — Lot D : amendes — 10 statuts métier (parité Journal, sans perte), paiement
(`paid_on` = date métier ≠ `paid_at` = horodatage technique), pièces liées typées, règles D9.

Le caractère « payé » est DÉRIVÉ du statut par une fonction unique (`is_paid`) ; le champ `payee`
stocké n'est qu'un miroir écrit par cette même dérivation (compatibilité Phase 3), jamais une
seconde vérité métier. `fine_status` absent = `a_payer` (ou `payee` si l'ancien drapeau l'indique) :
compatibilité de LECTURE uniquement, aucune écriture ni migration.
"""
import re
from datetime import date
from typing import Optional

from pydantic import BaseModel

FINE_STATUSES = ("recue", "a_analyser", "conducteur_a_identifier", "en_attente_conducteur", "contestee",
                 "a_payer", "payee", "refacturee", "cloturee", "annulee")
JOURNAL_STATUS_MAP = {"received": "recue", "to_analyze": "a_analyser", "driver_to_identify": "conducteur_a_identifier",
                      "awaiting_driver": "en_attente_conducteur", "disputed": "contestee", "to_pay": "a_payer",
                      "paid": "payee", "recharged": "refacturee", "closed": "cloturee", "cancelled": "annulee"}
FINE_STATUS_LABELS = {"recue": "Reçue", "a_analyser": "À analyser", "conducteur_a_identifier": "Conducteur à identifier",
                      "en_attente_conducteur": "En attente conducteur", "contestee": "Contestée", "a_payer": "À payer",
                      "payee": "Payée", "refacturee": "Refacturée", "cloturee": "Clôturée", "annulee": "Annulée"}
DEFAULT_FINE_STATUS = "a_payer"
PAID_STATUSES = ("payee", "refacturee")
DEADLINE_INACTIVE = ("payee", "refacturee", "cloturee", "annulee")  # D9 + table §5.5
COST_EXCLUDED = ("annulee",)  # D9 : montant conservé, document conservé, exclue des totaux
CREATION_FORBIDDEN = DEADLINE_INACTIVE  # états terminaux : jamais à la création, uniquement via action métier auditée
STATUS_AUDIT_ACTION = {"annulee": "fine_cancel", "refacturee": "fine_recharge", "cloturee": "fine_close",
                       "contestee": "fine_dispute", "payee": "fine_paid"}
PAYMENT_REVERT_ACTION = "fine_payment_reverted"  # dé-paiement = correction métier motivée, auditée avant/après

PIECE_TYPES = ("pdf", "photo", "courrier", "contestation", "preuve_paiement", "libre")
PIECE_LABELS = {"pdf": "PDF", "photo": "Photo", "courrier": "Courrier", "contestation": "Contestation",
                "preuve_paiement": "Preuve de paiement", "libre": "Libre"}
PRIORITIES = ("low", "normal", "high", "urgent")
# Codes Journal PROUVÉS dans les entrées 4B (speeding / parking / other, défaut `other`). L'enum complet
# (8 valeurs) sera figé après lecture seule du code source Journal : aucun code supplémentaire n'est inventé ici,
# la valeur est conservée telle quelle (chaîne) pour rester migrable sans perte.
KNOWN_INFRACTION_TYPES = ("speeding", "parking", "other")
INFRACTION_LABELS = {"speeding": "Excès de vitesse", "parking": "Stationnement", "other": "Autre"}
DEFAULT_INFRACTION_TYPE = "other"
LIEU_KEYS = ("pays", "canton", "ville", "lieu")
INTERNAL_FIELDS = ("notes_internes",)  # D6.3 : masqué côté serveur pour read_only
MOTIF_MIN_LEN = 3
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FineStatusChange(BaseModel):
    fine_status: str
    motif: Optional[str] = None
    paid_on: Optional[str] = None
    payment_ref: Optional[str] = None


class FinePaid(BaseModel):
    payee: bool = True
    paid_on: Optional[str] = None
    payment_ref: Optional[str] = None
    motif: Optional[str] = None  # obligatoire pour un dé-paiement (payee=false)


def leaving_paid(before: str, after: str) -> bool:
    """Dé-paiement : quitter payee/refacturee vers un statut non payé (hors clôture, qui conserve les faits)."""
    return before in PAID_STATUSES and after not in PAID_STATUSES and after != "cloturee"


def payment_revert_detail(doc: dict, before: str, after: str, motif: str, user: str, now: str) -> str:
    return (f"Dé-paiement (correction métier) — statut {before} → {after} · motif : {motif} · par {user} le {now} · "
            f"avant : paid_on={doc.get('paid_on') or '—'}, paid_at={doc.get('paid_at') or '—'}, "
            f"payment_ref={doc.get('payment_ref') or '—'}, paid_by={doc.get('paid_by') or '—'} → après : paid_on=—, paid_at=—, payment_ref=—")


def is_date(v) -> bool:
    if not (isinstance(v, str) and DATE_RE.match(v)):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def normalize_status(value) -> str:
    """Code Documents ou code Journal → code Documents. ValueError si inconnu (jamais de valeur inventée)."""
    s = (value or "").strip().lower()
    if s in FINE_STATUSES:
        return s
    if s in JOURNAL_STATUS_MAP:
        return JOURNAL_STATUS_MAP[s]
    raise ValueError(f"fine_status inconnu : {value!r} (attendu : {', '.join(FINE_STATUSES)})")


def fine_status_of(doc: dict) -> str:
    """Lecture seule : statut effectif. Absent (amende Phase 3) → `payee` si l'ancien drapeau l'indique, sinon `a_payer`."""
    s = doc.get("fine_status")
    if s in FINE_STATUSES:
        return s
    return "payee" if doc.get("payee") else DEFAULT_FINE_STATUS


def is_paid(status: str, doc: dict = None) -> bool:
    """Fonction UNIQUE de dérivation « payé » : payee/refacturee = oui ; cloturee = selon les faits de paiement conservés."""
    if status in PAID_STATUSES:
        return True
    if status == "cloturee" and doc:
        return bool(doc.get("paid_on") or doc.get("paid_at"))
    return False


def deadline_active(status: str) -> bool:
    return status not in DEADLINE_INACTIVE


def cost_counted(status: str) -> bool:
    return status not in COST_EXCLUDED


def badge(status: str, days) -> str:
    if status == "annulee":
        return "ANNULEE"
    if status == "cloturee":
        return "CLOTUREE"
    if status == "contestee":
        return "CONTESTEE"
    if status in PAID_STATUSES:
        return "PAYEE"
    return "EN_RETARD" if days is not None and days < 0 else "A_PAYER"


def cleared_payment() -> dict:
    return {"paid_on": None, "paid_at": None, "paid_by": None, "payment_ref": None}


def status_update(doc: dict, new_status: str, now: str, user: str, paid_on=None, payment_ref=None) -> dict:
    """Champs à écrire pour une transition. `paid_at` = horodatage technique serveur ; `paid_on` = date métier
    fournie, JAMAIS dérivée de `paid_at`. Quitter un statut payé (hors cloturee) efface les faits de paiement."""
    upd = {"fine_status": new_status}
    if new_status in PAID_STATUSES:
        upd["paid_at"] = doc.get("paid_at") or now
        upd["paid_by"] = doc.get("paid_by") or user
        upd["paid_on"] = paid_on if paid_on is not None else doc.get("paid_on")
        upd["payment_ref"] = payment_ref if payment_ref is not None else doc.get("payment_ref")
    elif new_status != "cloturee":
        upd.update(cleared_payment())
    upd["payee"] = is_paid(new_status, {**doc, **upd})
    return upd


def payment_errors(paid_on, payment_ref) -> list:
    errors = []
    if paid_on not in (None, "") and not is_date(paid_on):
        errors.append("paid_on invalide (AAAA-MM-JJ, date métier du paiement)")
    if payment_ref is not None and len(payment_ref.strip()) > 120:
        errors.append("payment_ref trop longue (120 caractères max)")
    return errors


def norm_ref(v) -> Optional[str]:
    s = (v or "").strip() if isinstance(v, str) else None
    return s or None


def norm_lieu(v) -> Optional[dict]:
    if not isinstance(v, dict):
        return None
    out = {k: (str(v.get(k)).strip() or None) if v.get(k) is not None else None for k in LIEU_KEYS}
    return out if any(out.values()) else None


def lieu_label(lieu) -> Optional[str]:
    if not isinstance(lieu, dict):
        return None
    return ", ".join(str(lieu[k]) for k in ("lieu", "ville", "canton", "pays") if lieu.get(k)) or None


def strip_internal(doc: dict, role: str) -> dict:
    """D6.3 — filtrage SERVEUR avant sérialisation : read_only ne reçoit jamais `notes_internes`."""
    if role == "read_only":
        for k in INTERNAL_FIELDS:
            doc.pop(k, None)
    return doc


def search_blob(d: dict) -> str:
    return " ".join(str(x or "") for x in (
        d.get("numero"), d.get("dossier_interne"), d.get("fournisseur"), d.get("plaque"), d.get("driver_nom"),
        d.get("label"), lieu_label(d.get("lieu_infraction")), d.get("type_infraction"))).lower()


def fmt_diff(before, after) -> str:
    return f"{before if before not in (None, '') else '—'} → {after if after not in (None, '') else '—'}"
