"""Phase 4C — Lot B : documents métier SANS fichier (D1) + lecture de coût générique D7 + convention D5.

Un enregistrement sans justificatif (saisie manuelle motivée ou import legacy) est un *document*
(`storage_path=None`, `justificatif_absent=True`) : il reste la source unique du coût ; pour le
carburant il est le `source_document_id` de l'unique `fuel_transaction`. `collect_costs` ne lit jamais
`fuel_transactions`.
"""
import re
from typing import Optional

from pydantic import BaseModel

TENANT_TZ = "Europe/Zurich"  # D5 : fuseau métier ; saisie manuelle = heure locale Zurich
NOFILE_SOURCES = ("manual", "legacy_import")
FUEL_CATEGORIES = ("CARBURANT", "ENERGIE_ELECTRIQUE")
MOTIF_MIN_LEN = 3


class ManualFuelCreate(BaseModel):
    date: str
    heure: Optional[str] = None
    station: Optional[str] = None
    montant: float
    devise: Optional[str] = "CHF"
    montant_chf: Optional[float] = None
    litres: Optional[float] = None
    prix_litre: Optional[float] = None
    energie_kwh: Optional[float] = None
    prix_kwh: Optional[float] = None
    type_carburant: Optional[str] = None
    kilometrage: Optional[int] = None
    carte_last4: Optional[str] = None
    plaque: Optional[str] = None
    business_category: str
    motif: Optional[str] = None
    duplicate_override: bool = False
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None
    date_heure_tz_assumed: Optional[bool] = None


class ManualFineCreate(BaseModel):
    autorite: str
    numero_amende: Optional[str] = None
    date_infraction: Optional[str] = None
    montant: float
    devise: Optional[str] = "CHF"
    montant_chf: Optional[float] = None
    delai_paiement: Optional[str] = None
    plaque: Optional[str] = None
    motif: Optional[str] = None
    duplicate_override: bool = False
    source: str = "manual"
    legacy_source: Optional[str] = None
    legacy_id: Optional[str] = None
    created_at: Optional[str] = None


def norm_currency(dev) -> str:
    d = (dev or "").strip().upper()
    return d if re.fullmatch(r"[A-Z]{3}", d) else "CHF"


def norm_heure(heure) -> Optional[str]:
    m = re.fullmatch(r"(\d{1,2})[:h.](\d{2})", (heure or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 else None


def check_source(payload) -> list:
    """Erreurs de validation communes (source, motif, clé legacy, devise/montant_chf). [] = OK."""
    errors = []
    if payload.source not in NOFILE_SOURCES:
        errors.append("source : manual ou legacy_import")
    motif = (payload.motif or "").strip()
    if payload.source == "manual" and len(motif) < MOTIF_MIN_LEN:
        errors.append("motif obligatoire pour une saisie manuelle sans justificatif")
    if payload.source == "legacy_import" and not (payload.legacy_id or "").strip():
        errors.append("legacy_id obligatoire pour un import legacy")
    if payload.montant is None or payload.montant < 0:
        errors.append("montant invalide")
    if payload.montant_chf is not None and payload.montant_chf < 0:
        errors.append("montant_chf invalide")
    return errors


def montant_chf_for(devise: str, montant_chf) -> Optional[float]:
    """D7 : `montant_chf` n'a de sens que pour une devise ≠ CHF (ignoré sinon)."""
    if norm_currency(devise) == "CHF" or montant_chf is None:
        return None
    return round(float(montant_chf), 2)


def cost_amount_chf(doc: dict):
    """D7 — (montant CHF à sommer, converti) ou (None, False) = « conversion en attente » (exclu du total).
    CHF → montant ; non-CHF + montant_chf → montant_chf ; non-CHF sans montant_chf → None."""
    devise = norm_currency(doc.get("devise"))
    if devise == "CHF":
        return round(float(doc["montant"]), 2), False
    if doc.get("montant_chf") is not None:
        return round(float(doc["montant_chf"]), 2), True
    return None, False


def fuel_label(station, date_, electric: bool) -> str:
    return f"{'Recharge' if electric else 'Plein'} {station or 'sans station'} — {date_} (sans justificatif)"


def fine_label(autorite, numero) -> str:
    return f"Amende {autorite}" + (f" n° {numero}" if numero else "") + " (sans justificatif)"


def date_heure_fields(date_, heure, source: str, tz_assumed) -> dict:
    """D5 : date/heure manuelle = locale Europe/Zurich ; valeur brute toujours conservée."""
    raw = f"{date_}T{heure}" if heure else date_
    assumed = bool(tz_assumed) if tz_assumed is not None else (source == "legacy_import" and bool(heure))
    return {"date_heure_source": raw, "date_heure_tz": TENANT_TZ, "date_heure_tz_assumed": assumed}
