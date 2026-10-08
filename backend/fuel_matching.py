"""Phase 4C — Lot F (6a) : rattachement transaction ↔ véhicule, scoré et explicable (sans trajets ni géolocalisation).

Décision figée (réconciliation §6a.5 / §6a.15) :
- `vehicle_id` explicite valide → 100, méthode `direct_vehicle_id`, auto_matched ;
- carte résolue unique (`found`) + exactement 1 affectation `vehicule` couvrant la date + carte utilisable à cette date
  → score normatif 90, méthode `card_assignment`, auto_matched (règle déterministe, pas un total de barème) ;
- carte inactive/non utilisable → pénalité −50, jamais auto, `matched_review` + CARD_INACTIVE ;
- conducteur affecté à date +20 ; carburant compatible +10 / incompatible −40 ; plaque = 0 point, candidats de revue uniquement ;
- toute ambiguïté (plusieurs cartes, plusieurs affectations, conflit) → jamais auto → `matched_review` ;
- seuils tenant `score_auto=90`, `score_review=70` ; un candidat identifié sous le seuil auto n'est jamais abandonné
  silencieusement : `matched_review` (proposé si ≥ score_review, listé sinon) ; aucun candidat → `unmatched`.
"""
from typing import Optional

from pydantic import BaseModel

MATCH_STATUSES = ("auto_matched", "matched_review", "unmatched", "manual")
MATCH_LABELS = {"auto_matched": "Rattaché automatiquement", "matched_review": "À vérifier", "unmatched": "Non rattaché", "manual": "Rattaché manuellement"}
POINTS = {"direct_vehicle_id": 100, "card_assignment": 90, "card_candidate": 50, "driver_assignment": 20,
          "fuel_compatible": 10, "fuel_incompatible": -40, "card_inactive": -50, "plate_candidate": 0}
RULE_LABELS = {"direct_vehicle_id": "Identifiant véhicule explicite", "card_assignment": "Carte unique affectée au véhicule à la date (déterministe)",
               "card_candidate": "Affectation d'une carte candidate (carte ambiguë)", "driver_assignment": "Conducteur affecté à la date",
               "fuel_compatible": "Carburant compatible", "fuel_incompatible": "Carburant incompatible", "card_inactive": "Carte inactive / non utilisable",
               "plate_candidate": "Plaque du fichier (aide à la revue, 0 point)", "manual": "Décision humaine motivée", "document": "Véhicule du document validé"}
DEFAULT_FUEL_SETTINGS = {"score_auto": 90, "score_review": 70, "double_window_min": 60, "amount_multiplier": 3.0,
                         "amount_min_history": 5, "tank_tolerance_pct": 10.0}
_ELECTRIC = ("electr", "lectri", "kwh", "strom", "recharge")


class ManualMatchPayload(BaseModel):
    vehicle_id: str
    reason: str


class ManualCardPayload(BaseModel):
    card_id: Optional[str] = None
    reason: str


class FuelSettingsPayload(BaseModel):
    score_auto: Optional[int] = None
    score_review: Optional[int] = None
    double_window_min: Optional[int] = None
    amount_multiplier: Optional[float] = None
    amount_min_history: Optional[int] = None
    tank_tolerance_pct: Optional[float] = None


def settings_from(doc: Optional[dict]) -> dict:
    s = dict(DEFAULT_FUEL_SETTINGS)
    s.update({k: v for k, v in ((doc or {}).get("fuel") or {}).items() if k in s and v is not None})
    return s


def settings_errors(p: FuelSettingsPayload) -> list:
    e = []
    for k in ("score_auto", "score_review"):
        v = getattr(p, k)
        if v is not None and not 0 <= v <= 100:
            e.append(f"{k} : 0–100")
    if p.score_auto is not None and p.score_review is not None and p.score_review > p.score_auto:
        e.append("score_review ≤ score_auto")
    for k in ("double_window_min", "amount_min_history"):
        if getattr(p, k) is not None and getattr(p, k) < 0:
            e.append(f"{k} ≥ 0")
    for k in ("amount_multiplier", "tank_tolerance_pct"):
        if getattr(p, k) is not None and getattr(p, k) < 0:
            e.append(f"{k} ≥ 0")
    return e


def is_electric(label) -> Optional[bool]:
    s = (label or "").casefold()
    if not s:
        return None
    return any(h in s for h in _ELECTRIC)


def fuel_compatible(tx_energie: Optional[str], tx_type: Optional[str], vehicle_type: Optional[str]) -> Optional[bool]:
    """True/False si comparable (thermique vs électrique), None si inconnu — jamais bloquant."""
    v = is_electric(vehicle_type)
    if v is None:
        return None
    t = (tx_energie == "electrique") if tx_energie else is_electric(tx_type)
    if t is None:
        return None
    return t == v


def score_vehicle(ctx: dict, settings: dict) -> dict:
    """Pur. ctx = {direct_vehicle_id, card: {status, card_id, usable, assigned_vehicle_ids[], candidate_vehicle_ids[]},
    driver_vehicle_id, plate_candidate_ids[], fuel_compat: {vehicle_id: bool|None}}.
    → {vehicle_id, score, status, method, breakdown[], candidates[], deterministic, review_reasons[]}."""
    auto_th, review_th = int(settings.get("score_auto", 90)), int(settings.get("score_review", 70))
    if ctx.get("direct_vehicle_id"):
        vid = ctx["direct_vehicle_id"]
        return {"vehicle_id": vid, "score": 100, "status": "auto_matched", "method": "direct_vehicle_id", "deterministic": True,
                "breakdown": [{"rule": "direct_vehicle_id", "label": RULE_LABELS["direct_vehicle_id"], "points": 100, "vehicle_id": vid}],
                "candidates": [{"vehicle_id": vid, "partial_score": 100, "sources": ["direct_vehicle_id"], "proposed": True}], "review_reasons": []}
    card = ctx.get("card") or {}
    cands: dict = {}
    review_reasons, deterministic_vid = [], None

    def add(vid, rule, points, **extra):
        c = cands.setdefault(vid, {"vehicle_id": vid, "partial_score": 0, "sources": [], "breakdown": []})
        c["partial_score"] += points
        if rule not in c["sources"]:
            c["sources"].append(rule)
        c["breakdown"].append({"rule": rule, "label": RULE_LABELS[rule], "points": points, **extra})

    assigned = list(card.get("assigned_vehicle_ids") or [])
    if card.get("status") == "found":
        if len(assigned) == 1:
            vid = assigned[0]
            if card.get("usable"):
                deterministic_vid = vid
                add(vid, "card_assignment", POINTS["card_assignment"], card_unique=True, assignment_at_date=True, assigned_vehicle_id=vid, card_usable=True)
            else:
                add(vid, "card_assignment", POINTS["card_assignment"], card_unique=True, assignment_at_date=True, assigned_vehicle_id=vid, card_usable=False)
                add(vid, "card_inactive", POINTS["card_inactive"], reasons=card.get("inactive_reasons") or [])
                review_reasons.append("CARD_INACTIVE")
        elif len(assigned) > 1:
            review_reasons.append("MULTIPLE_CARD_ASSIGNMENTS")
            for vid in assigned:
                add(vid, "card_candidate", POINTS["card_candidate"], card_unique=True, assignment_at_date=True, assigned_vehicle_id=vid)
                if not card.get("usable"):
                    add(vid, "card_inactive", POINTS["card_inactive"])
    elif card.get("status") == "ambiguous":
        review_reasons.append("CARD_AMBIGUOUS")
        for vid in card.get("candidate_vehicle_ids") or []:
            add(vid, "card_candidate", POINTS["card_candidate"], card_unique=False)
    if ctx.get("driver_vehicle_id"):
        add(ctx["driver_vehicle_id"], "driver_assignment", POINTS["driver_assignment"])
    for vid in ctx.get("plate_candidate_ids") or []:
        add(vid, "plate_candidate", POINTS["plate_candidate"], plate=ctx.get("plate_hint"))
    if len(ctx.get("plate_candidate_ids") or []) > 1:
        review_reasons.append("PLATE_AMBIGUOUS")
    compat = ctx.get("fuel_compat") or {}
    for vid in list(cands):
        c = compat.get(vid)
        if c is True and vid != deterministic_vid:  # le lien déterministe reste au score normatif 90 (bonus informatif non ajouté)
            add(vid, "fuel_compatible", POINTS["fuel_compatible"])
        elif c is False:
            add(vid, "fuel_incompatible", POINTS["fuel_incompatible"])
    for c in cands.values():
        c["proposed"] = c["partial_score"] >= review_th
    ordered = sorted(cands.values(), key=lambda c: -c["partial_score"])
    if not ordered:
        return {"vehicle_id": None, "score": 0, "status": "unmatched", "method": None, "deterministic": False, "breakdown": [],
                "candidates": [], "review_reasons": review_reasons}
    best = ordered[0]
    tie = len(ordered) > 1 and ordered[1]["partial_score"] == best["partial_score"]
    if tie:
        review_reasons.append("TIE")
    # Auto uniquement : lien déterministe carte (ou direct), score ≥ seuil, aucune raison de revue, pas d'égalité, carburant non incompatible
    if (deterministic_vid == best["vehicle_id"] and best["partial_score"] >= auto_th and not review_reasons
            and compat.get(best["vehicle_id"]) is not False):
        return {"vehicle_id": best["vehicle_id"], "score": best["partial_score"], "status": "auto_matched", "method": "card_assignment",
                "deterministic": True, "breakdown": best["breakdown"], "candidates": ordered, "review_reasons": []}
    if compat.get(best.get("vehicle_id")) is False and deterministic_vid == best["vehicle_id"]:
        review_reasons.append("FUEL_INCOMPATIBLE")
    if best["partial_score"] < review_th and not review_reasons:
        review_reasons.append("BELOW_REVIEW_THRESHOLD")
    return {"vehicle_id": None, "score": best["partial_score"], "status": "matched_review", "method": None, "deterministic": False,
            "breakdown": best["breakdown"], "candidates": ordered, "review_reasons": sorted(set(review_reasons))}


def card_inactive_eval(card: Optional[dict], tx_date: Optional[str]) -> dict:
    """Règle figée Lot F : CARD_INACTIVE = (statut courant ≠ active) OU (expire_le renseigné ET expire_le < date tx).
    Aucune reconstruction historique du statut via audit_logs (limitation documentée)."""
    if not card:
        return {"inactive": False, "evaluation_model": "current_status_tx_date_expiration", "card_status_current": None}
    status = card.get("statut")
    exp = card.get("expire_le")
    by_status = status != "active"
    by_exp = bool(exp and tx_date and str(exp)[:10] < str(tx_date)[:10])
    return {"inactive": by_status or by_exp, "inactive_by_status": by_status, "inactive_by_expiration": by_exp,
            "card_status_current": status, "expire_le": exp, "transaction_date": tx_date,
            "evaluation_model": "current_status_tx_date_expiration"}
