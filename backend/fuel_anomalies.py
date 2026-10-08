"""Phase 4C — Lot F (6a) : anomalies carburant persistées, recalculées par Documents (D8), décision humaine motivée.

Types (spec §6a.6, exacts) : depassement_reservoir · carte_inactive (= CARD_INACTIVE) · double_plein · montant_inhabituel ·
incoherence_montant · odometre_incoherent · plaque_differente · carte_vehicule_different (= CARD_VEHICLE_MISMATCH).
Unique (tenant, transaction, type) ; jamais recréée après décision ; warning ≠ correction automatique (vehicle_id / card_id
ne sont jamais substitués). D8 : décision legacy `justified` reprise uniquement si anomalie redétectée, même transaction legacy,
même type, donnée réelle ; `issues[]` → commentaire métier au plus, jamais une anomalie.
"""
from datetime import datetime
from statistics import median
from typing import Optional

from pydantic import BaseModel

TYPES = ("depassement_reservoir", "carte_inactive", "double_plein", "montant_inhabituel", "incoherence_montant",
         "odometre_incoherent", "plaque_differente", "carte_vehicule_different")
SEVERITY = {"depassement_reservoir": "critical", "carte_inactive": "critical", "carte_vehicule_different": "critical",
            "double_plein": "warning", "montant_inhabituel": "warning", "incoherence_montant": "warning",
            "odometre_incoherent": "warning", "plaque_differente": "warning"}
LABELS = {"depassement_reservoir": "Dépassement de la capacité du réservoir", "carte_inactive": "Carte inactive à la date de transaction",
          "double_plein": "Double plein rapproché", "montant_inhabituel": "Montant inhabituel", "incoherence_montant": "Quantité × prix ≠ montant",
          "odometre_incoherent": "Kilométrage incohérent", "plaque_differente": "Plaque du fichier différente du véhicule",
          "carte_vehicule_different": "Carte affectée à un autre véhicule"}
WARNING_CODES = {"carte_inactive": "CARD_INACTIVE", "carte_vehicule_different": "CARD_VEHICLE_MISMATCH"}
STATUSES = ("ouverte", "justifiee", "corrigee", "rejetee")
STATUS_LABELS = {"ouverte": "Ouverte", "justifiee": "Justifiée", "corrigee": "Corrigée", "rejetee": "Rejetée"}
DECISIONS = {"justify": "justifiee", "correct": "corrigee", "reject": "rejetee"}
REASON_MIN_LEN = 3


class DecisionPayload(BaseModel):
    decision: str
    reason: str


def _minutes_between(a: Optional[str], b: Optional[str]) -> Optional[float]:
    try:
        da, db_ = datetime.fromisoformat(a), datetime.fromisoformat(b)
    except (TypeError, ValueError):
        return None
    return abs((da - db_).total_seconds()) / 60


def detect(tx: dict, ctx: dict, settings: dict) -> list:
    """Pur. ctx = {vehicle, card, card_inactive (card_inactive_eval), card_assigned_vehicle_ids[], neighbors[] (tx même véhicule/carte),
    history_amounts[] (montant_chf des tx précédentes du véhicule), prev_km (km de la tx précédente du véhicule)}."""
    out = []
    v = ctx.get("vehicle") or {}
    qty = tx.get("energie_kwh") if tx.get("energie") == "electrique" else tx.get("litres")
    cap = v.get("capacite_reservoir_l") if tx.get("energie") != "electrique" else None  # pas de capacité batterie dans le modèle → muette
    tol = float(settings.get("tank_tolerance_pct", 10)) / 100
    if cap and qty and qty > cap * (1 + tol):
        out.append({"type": "depassement_reservoir", "explanation": f"{qty} L > capacité {cap} L (+{int(tol * 100)} %)",
                    "context": {"quantity": qty, "capacity_l": cap, "tolerance_pct": tol * 100}})
    ci = ctx.get("card_inactive") or {}
    if tx.get("card_id") and ci.get("inactive"):
        out.append({"type": "carte_inactive", "card_id": tx["card_id"],
                    "explanation": "Carte " + " et ".join(x for x in (("statut " + str(ci.get("card_status_current"))) if ci.get("inactive_by_status") else None,
                                                                     f"expirée le {ci.get('expire_le')}" if ci.get("inactive_by_expiration") else None) if x)
                                   + f" à la date {tx.get('date')}", "context": dict(ci)})
    assigned = ctx.get("card_assigned_vehicle_ids") or []
    if tx.get("card_id") and assigned and tx.get("vehicle_id") not in assigned:
        out.append({"type": "carte_vehicule_different", "card_id": tx["card_id"],
                    "explanation": "La carte est affectée à un autre véhicule à la date de la transaction — aucune réaffectation automatique",
                    "context": {"card_assigned_vehicle_ids": assigned, "transaction_vehicle_id": tx.get("vehicle_id"), "auto_correction": False}})
    window = float(settings.get("double_window_min", 60))
    for n in ctx.get("neighbors") or []:
        if n.get("id") == tx.get("id"):
            continue
        mins = _minutes_between(tx.get("date_heure"), n.get("date_heure"))
        if mins is not None and mins <= window and (tx.get("heure") and n.get("heure")):
            out.append({"type": "double_plein", "related_transaction_id": n["id"],
                        "explanation": f"Autre transaction ({'même carte' if n.get('card_id') and n.get('card_id') == tx.get('card_id') else 'même véhicule'}) à {mins:.0f} min",
                        "context": {"minutes": round(mins, 1), "window_min": window, "related_transaction_id": n["id"]}})
            break
    hist = [h for h in (ctx.get("history_amounts") or []) if h is not None]
    amt = tx.get("montant_chf") if tx.get("montant_chf") is not None else (tx.get("montant") if (tx.get("devise") or "CHF") == "CHF" else None)
    if amt is not None and len(hist) >= int(settings.get("amount_min_history", 5)):
        med = median(hist)
        mult = float(settings.get("amount_multiplier", 3))
        if med > 0 and amt > mult * med:
            out.append({"type": "montant_inhabituel", "explanation": f"{amt:.2f} CHF > {mult:g} × médiane {med:.2f} CHF ({len(hist)} tx)",
                        "context": {"amount_chf": amt, "median_chf": round(med, 2), "multiplier": mult, "history_n": len(hist)}})
    price = tx.get("prix_kwh") if tx.get("energie") == "electrique" else tx.get("prix_litre")
    m = tx.get("montant")
    if qty and price and m:
        calc = qty * price
        if abs(calc - m) > max(0.10, 0.05 * m):
            out.append({"type": "incoherence_montant", "explanation": f"{qty} × {price} = {calc:.2f} ≠ {m:.2f} {tx.get('devise')}",
                        "context": {"quantity": qty, "unit_price": price, "computed": round(calc, 2), "amount": m}})
    km, prev_km, vkm = tx.get("kilometrage"), ctx.get("prev_km"), v.get("kilometrage") or 0
    if km:
        if prev_km and km < prev_km:
            out.append({"type": "odometre_incoherent", "explanation": f"{km} km < transaction précédente {prev_km} km",
                        "context": {"km": km, "previous_km": prev_km}})
        elif vkm and km > vkm * 1.05 + 500:
            out.append({"type": "odometre_incoherent", "explanation": f"{km} km > odomètre véhicule {vkm} km — odomètre non modifié",
                        "context": {"km": km, "vehicle_km": vkm}})
    plate_hint, vplate = ctx.get("plate_hint_norm"), ctx.get("vehicle_plate_norm")
    if plate_hint and vplate and plate_hint != vplate:
        out.append({"type": "plaque_differente", "explanation": f"Plaque du fichier « {tx.get('plaque_mentionnee') or tx.get('vehicle_hint')} » ≠ véhicule « {v.get('plaque')} » — aucune réaffectation",
                    "context": {"file_plate": tx.get("plaque_mentionnee") or tx.get("vehicle_hint"), "vehicle_plate": v.get("plaque"), "auto_correction": False}})
    for a in out:
        a.setdefault("severity", SEVERITY[a["type"]])
        a.setdefault("vehicle_id", tx.get("vehicle_id"))
        a.setdefault("card_id", tx.get("card_id"))
        a.setdefault("related_transaction_id", None)
    return out


def decision_errors(p: DecisionPayload) -> list:
    e = []
    if p.decision not in DECISIONS:
        e.append("decision : justify | correct | reject")
    if len((p.reason or "").strip()) < REASON_MIN_LEN:
        e.append("motif obligatoire (≥ 3 caractères)")
    return e


def reimport_legacy_decision(tx: dict, open_anomalies: list, legacy: dict) -> dict:
    """D8.b pur — décision legacy `justified` reprise UNIQUEMENT si : (1) anomalie redétectée par Documents (ouverte, même type),
    (2) même transaction legacy (legacy_source + legacy_id), (3) même type, (4) donnée réelle (non test). Aucune création d'anomalie."""
    checks = {
        "same_legacy_transaction": bool(tx.get("legacy_source")) and tx.get("legacy_source") == legacy.get("legacy_source")
        and bool(tx.get("legacy_id")) and tx.get("legacy_id") == legacy.get("legacy_transaction_id"),
        "known_type": legacy.get("type") in TYPES,
        "redetected": any(a.get("type") == legacy.get("type") and a.get("status") == "ouverte" and a.get("transaction_id") == tx.get("id")
                          for a in open_anomalies),
        "legacy_status_justified": legacy.get("status") == "justified",
        "real_data": not bool(legacy.get("is_test")) and not bool(tx.get("is_test")),
    }
    ok = all(checks.values())
    target = next((a for a in open_anomalies if ok and a.get("type") == legacy.get("type")), None)
    return {"accepted": ok, "checks": checks, "anomaly_id": target.get("id") if target else None,
            "decision": {"status": "justifiee", "decision_reason": legacy.get("reason") or "Décision legacy justifiée (D8)",
                         "decided_by": legacy.get("decided_by") or "legacy", "decided_at": legacy.get("decided_at"),
                         "legacy_decision": True} if ok else None}


def legacy_issue_to_comment(issue: dict, is_real: bool) -> Optional[str]:
    """D8.c pur — un `issue` Journal n'est jamais une anomalie : au plus un commentaire métier (si réel et utile)."""
    msg = (issue or {}).get("message")
    if not is_real or not msg or not str(msg).strip():
        return None
    who, when = issue.get("reported_by"), issue.get("reported_at")
    return f"Signalement legacy{f' ({who})' if who else ''}{f' {str(when)[:10]}' if when else ''} : {str(msg).strip()}"
