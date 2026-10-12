"""Télématique de DÉMONSTRATION — strictement cosmétique, lecture seule, tenants marqués `demo_seed` uniquement.
Aucune écriture en base, aucun appel réseau Navixy. Fabrique un miroir télématique fictif DÉTERMINISTE à partir des
véhicules canoniques de la démo : peuple la page Intégrité (8 liés/identiques · 1 divergence · 1 non lié) et un encart
« Suivi télématique (démo) » par véhicule. N'affecte jamais `default` ni la vraie synchronisation."""
import hashlib
from datetime import datetime, timedelta, timezone

PROVIDER = "navixy-demo"

# Points fictifs (Suisse) — jamais de vraie position
_SPOTS = [
    ("Genève — Carouge", 46.1828, 6.1394), ("Lausanne — Sébeillon", 46.5269, 6.6090),
    ("Nyon — La Côte", 46.3833, 6.2390), ("Fribourg — Centre", 46.8065, 7.1615),
    ("Berne — Wankdorf", 46.9631, 7.4650), ("Zürich — Altstetten", 47.3912, 8.4877),
    ("Sion — Est", 46.2270, 7.3800), ("Morges — Port", 46.5100, 6.4980),
    ("Vevey — Gare", 46.4628, 6.8430), ("Yverdon — Sud", 46.7780, 6.6410),
]
_STATUSES = [("parked", "À l'arrêt"), ("moving", "En roulage"), ("idle", "Contact mis"),
             ("parked", "À l'arrêt"), ("moving", "En roulage")]


def _h(vehicle_id: str) -> int:
    return int(hashlib.sha256((vehicle_id or "").encode()).hexdigest(), 16)


def _rid(vehicle_id: str) -> str:
    return f"nvx-demo-{_h(vehicle_id) % 900000 + 100000}"


def _alter_plate(plate):
    """Décale le dernier chiffre de la plaque pour simuler une divergence plaque Documents ↔ télématique."""
    s = str(plate or "GE 000000")
    for i in range(len(s) - 1, -1, -1):
        if s[i].isdigit():
            return s[:i] + str((int(s[i]) + 1) % 10) + s[i + 1:]
    return s + "1"


def _ordered(vehicles: list) -> list:
    return sorted(vehicles, key=lambda v: (v.get("plaque") or "", v.get("id") or ""))


def simulate(vehicles: list) -> dict:
    """Miroir télématique fictif. Retourne `remote_by_id` (objets « vehicle » façon API) + `nvid`
    (vehicle_id → id télématique synthétique, ou None si volontairement « non lié ») + `diverg_id`."""
    vs = _ordered(vehicles)
    n = len(vs)
    not_linked = vs[-1]["id"] if n >= 1 else None
    diverg = vs[-2]["id"] if n >= 2 else None
    remote_by_id, nvid = {}, {}
    for v in vs:
        vid = v["id"]
        if vid == not_linked:
            nvid[vid] = None
            continue
        rid = _rid(vid)
        nvid[vid] = rid
        reg = _alter_plate(v.get("plaque")) if vid == diverg else v.get("plaque")
        remote_by_id[rid] = {
            "id": rid, "reg_number": reg, "vin": v.get("vin"),
            "label": f"LGK · {v.get('plaque') or vid[:6]}",
            "model": f"{v.get('marque') or ''} {v.get('modele') or ''}".strip() or None,
            "color": (v.get("carte_grise") or {}).get("couleur"),
            "manufacture_year": v.get("annee"), "type": "car", "garage_id": None,
        }
    return {"remote_by_id": remote_by_id, "nvid": nvid, "diverg_id": diverg, "not_linked_id": not_linked}


def tracking(vehicle: dict) -> dict:
    """Suivi fictif déterministe d'un véhicule (encart fiche véhicule). Toujours `demo: True`."""
    vid = vehicle["id"]
    h = _h(vid)
    spot = _SPOTS[h % len(_SPOTS)]
    status, status_label = _STATUSES[h % len(_STATUSES)]
    minutes_ago = 1 + (h // 7) % 240
    seen_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    speed = ((h // 13) % 85) + 8 if status == "moving" else 0
    odo = int(vehicle.get("kilometrage") or 0) + (h % 45)
    return {
        "demo": True, "provider": PROVIDER,
        "status": status, "status_label": status_label,
        "speed_kmh": speed,
        "last_seen_at": seen_at.isoformat(), "last_seen_minutes": minutes_ago,
        "position": {"lat": round(spot[1], 5), "lng": round(spot[2], 5), "label": spot[0]},
        "odometer_km": odo,
        "ignition": status in ("moving", "idle"),
        "tracker_id": _rid(vid),
    }
