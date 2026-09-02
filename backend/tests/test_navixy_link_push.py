"""Liaison / création fiche véhicule Navixy => push IMMÉDIAT des données déjà validées.
Chaîne complète testée contre un mock Navixy local (aucune écriture réelle)."""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-linkpush-{_RUN}"
ADMIN = (f"linkpush-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
_S = {}
_cache = {}

# --- Mock Navixy (fiche 501 existante non liée ; création renvoie 502) -----
MOCK = {"vehicles": {501: {"id": 501, "label": "Kangoo dépôt", "type": "car", "subtype": "universal",
                           "reg_number": f"VD {_RUN[:6].upper()}", "tracker_id": None}},
        "updates": [], "creates": []}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
        path = self.path.split("?")[0]
        if path == "/vehicle/list":
            out = {"success": True, "list": list(MOCK["vehicles"].values())}
        elif path == "/vehicle/read":
            out = {"success": True, "value": MOCK["vehicles"].get(body.get("vehicle_id")) or {}}
        elif path == "/vehicle/update":
            MOCK["updates"].append(body["vehicle"])
            MOCK["vehicles"][body["vehicle"]["id"]] = body["vehicle"]
            out = {"success": True}
        elif path == "/vehicle/create":
            new = dict(body["vehicle"], id=502)
            MOCK["creates"].append(new)
            MOCK["vehicles"][502] = new
            out = {"success": True, "id": 502}
        else:
            out = {"success": True, "list": []}
        payload = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(email, password):
    key = (email, password)
    if key not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        assert r.status_code == 200, f"login {email} -> {r.status_code}"
        _cache[key] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[key]


def sa():
    return _h(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])


def setup_module():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    _S["server"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"
    r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"LinkPush {_RUN}", "id": TENANT},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                      json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    _mongo().tenant_integrations.insert_one({
        "tenant_id": TENANT, "provider": "navixy", "enabled": True,
        "api_hash": f"mock-{_RUN}", "base_url": base_url, "write_enabled": True})
    # Véhicule canonique avec données validées (plaque = preuve de liaison avec la fiche 501)
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"VD {_RUN[:6].upper()}", "marque": "Renault", "modele": "Kangoo",
                            "annee": 2022, "type_carburant": "Diesel", "capacite_reservoir_l": 54,
                            "carte_grise": {"couleur": "blanc", "poids_total": 2210}})
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]


def teardown_module():
    _S["server"].shutdown()
    db = _mongo()
    for coll in ("vehicles", "documents", "audit_logs", "vehicle_field_meta",
                 "tenant_integrations", "users"):
        db[coll].delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


class TestLinkPush:
    def test_liaison_pousse_immediatement(self):
        r = requests.post(f"{_BASE}/api/integrations/navixy/link", headers=_h(*ADMIN), timeout=30,
                          json={"vehicle_id": _S["veh"], "external_vehicle_id": 501})
        assert r.status_code == 200, r.text
        res = r.json()
        assert "plaque" in res["matched_by"]
        assert res["navixy_push"]["status"] == "pushed"
        assert "fuel_tank_volume" in res["navixy_push"]["fields"]
        # Read-merge-write : la fiche mock a reçu les champs validés SANS perdre son label
        last = MOCK["updates"][-1]
        assert last["id"] == 501 and last["label"] == "Kangoo dépôt"
        assert last["fuel_tank_volume"] == 54 and last["gross_weight"] == 2210
        assert last["fuel_type"] == "diesel" and last["model"] == "Renault Kangoo"

    def test_statut_sync_persiste(self):
        v = _mongo().vehicles.find_one({"id": _S["veh"]}, {"_id": 0, "navixy_vehicle_id": 1,
                                                           "integrations.navixy.sync_status": 1})
        assert v["navixy_vehicle_id"] == 501
        assert v["integrations"]["navixy"]["sync_status"] == "ok"

    def test_relink_409(self):
        r = requests.post(f"{_BASE}/api/integrations/navixy/link", headers=_h(*ADMIN), timeout=30,
                          json={"vehicle_id": _S["veh"], "external_vehicle_id": 501})
        assert r.status_code == 409


class TestCreatePush:
    def test_creation_confirmee_pousse_le_reste(self):
        r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                          json={"plaque": f"GE {_RUN[:6].upper()}", "marque": "Citroën", "modele": "C3",
                                "type_carburant": "Essence", "capacite_reservoir_l": 44})
        vid = r.json()["id"]
        sim = requests.post(f"{_BASE}/api/integrations/navixy/create-vehicle", headers=_h(*ADMIN),
                            timeout=30, json={"vehicle_id": vid, "confirm": False})
        assert sim.status_code == 200 and sim.json()["confirmed"] is False
        assert MOCK["creates"] == []  # simulation = zéro écriture
        r = requests.post(f"{_BASE}/api/integrations/navixy/create-vehicle", headers=_h(*ADMIN),
                          timeout=30, json={"vehicle_id": vid, "confirm": True})
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["external_vehicle_id"] == 502
        # Le push complète la fiche créée avec les champs non envoyés à la création
        assert res["navixy_push"]["status"] == "pushed"
        assert "fuel_tank_volume" in res["navixy_push"]["fields"]
        assert MOCK["vehicles"][502]["fuel_tank_volume"] == 44
        assert MOCK["vehicles"][502]["fuel_type"] == "petrol"


class TestEditPush:
    """Toute modification d'un champ compatible dans Documents part immédiatement vers Navixy."""

    def test_put_champ_compatible_pousse(self):
        r = requests.put(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30,
                         json={"carte_grise": {"couleur": "rouge"}})
        assert r.status_code == 200, r.text
        assert r.json()["navixy_push"]["status"] == "pushed"
        assert MOCK["vehicles"][501]["color"] == "rouge"

    def test_conso_officielle_poussee_norm_avg(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/conso/apply", headers=_h(*ADMIN),
                          timeout=30, json={"value_l_100km": 5.6, "norme": "WLTP",
                                            "source": "ESTIMATION_IA"})
        assert r.status_code == 200, r.text
        assert r.json()["navixy_push"]["status"] == "pushed"
        assert MOCK["vehicles"][501]["norm_avg_fuel_consumption"] == 5.6

    def test_champ_non_compatible_aucun_push(self):
        n_before = len(MOCK["updates"])
        r = requests.put(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30,
                         json={"responsable": "Marc Test"})
        assert r.status_code == 200, r.text
        assert "navixy_push" not in r.json()
        assert len(MOCK["updates"]) == n_before  # aucune écriture Navixy inutile
