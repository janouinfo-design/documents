"""Véhicules retirés de Navixy : marquage à la sync (jamais de suppression auto)
+ suppression manuelle sécurisée (documents conservés/récupérables)."""
import json
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-absent-{_RUN}"
ADMIN = (f"absent-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
RO = (f"absent-ro-{_RUN}@pytest.ch", f"Ro-{_RUN}-1")
_S = {}
_cache = {}

MOCK = {"trackers": []}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        path = self.path.split("?")[0]
        if path == "/tracker/list":
            out = {"success": True, "list": MOCK["trackers"]}
        elif path == "/tracker/counter/value/list":
            out = {"success": True, "value": {}}
        elif path == "/vehicle/list":
            out = {"success": True, "list": []}
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
    r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Absent {_RUN}", "id": TENANT},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    for creds, role in ((ADMIN, "admin"), (RO, "read_only")):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                          json={"email": creds[0], "password": creds[1], "role": role},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
    _mongo().tenant_integrations.insert_one({
        "tenant_id": TENANT, "provider": "navixy", "enabled": True,
        "api_hash": f"mock-{_RUN}", "base_url": base_url, "write_enabled": True})
    # Véhicule « importé de Navixy » (créé par API puis requalifié source navixy + tracker)
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"ZH {_RUN[:6].upper()}", "marque": "Audi", "modele": "OBD"})
    assert r.status_code == 200, r.text
    _S["veh_nav"] = r.json()["id"]
    _mongo().vehicles.update_one({"id": _S["veh_nav"]},
                                 {"$set": {"source": "navixy", "navixy_tracker_id": 999}})
    # Document lié (doit être conservé/soft-deleted, jamais détruit)
    _S["doc"] = str(uuid.uuid4())
    _mongo().documents.insert_one({
        "id": _S["doc"], "vehicle_id": _S["veh_nav"], "tenant_id": TENANT,
        "folder": "Divers", "original_filename": "test.pdf", "storage_path": f"pytest/{_RUN}.pdf",
        "content_type": "application/pdf", "size": 10, "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()})
    # Véhicule créé manuellement
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"GE {_RUN[:6].upper()}", "marque": "Fiat", "modele": "Panda"})
    assert r.status_code == 200, r.text
    _S["veh_man"] = r.json()["id"]


def teardown_module():
    _S["server"].shutdown()
    db = _mongo()
    for coll in ("vehicles", "vehicles_archive", "documents", "audit_logs",
                 "vehicle_field_meta", "tenant_integrations", "users"):
        db[coll].delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


class TestAbsentFlow:
    def test_delete_navixy_actif_409(self):
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_nav']}", headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 409, r.text
        assert "Retiré de Navixy" in r.json()["detail"]

    def test_sync_marque_absent(self):
        MOCK["trackers"] = []
        r = requests.post(f"{_BASE}/api/navixy/sync", headers=_h(*ADMIN), timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["marked_absent"] == 1
        v = _mongo().vehicles.find_one({"id": _S["veh_nav"]}, {"_id": 0})
        assert v["navixy_absent"] is True
        assert v["integrations"]["navixy"]["sync_status"] == "absent"
        assert v.get("navixy_absent_since")

    def test_retour_tracker_reset_puis_reabsent(self):
        MOCK["trackers"] = [{"id": 999, "label": f"ZH {_RUN[:6].upper()}"}]
        r = requests.post(f"{_BASE}/api/navixy/sync", headers=_h(*ADMIN), timeout=60)
        assert r.status_code == 200 and r.json()["marked_absent"] == 0
        v = _mongo().vehicles.find_one({"id": _S["veh_nav"]}, {"_id": 0, "navixy_absent": 1})
        assert v["navixy_absent"] is False
        MOCK["trackers"] = []
        r = requests.post(f"{_BASE}/api/navixy/sync", headers=_h(*ADMIN), timeout=60)
        assert r.json()["marked_absent"] == 1

    def test_read_only_delete_403(self):
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_nav']}", headers=_h(*RO), timeout=30)
        assert r.status_code == 403

    def test_cross_tenant_delete_404(self):
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_nav']}",
                            headers=_h(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"]), timeout=30)
        assert r.status_code == 404

    def test_delete_absent_ok_documents_conserves(self):
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_nav']}", headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["documents_archived"] == 1
        db = _mongo()
        assert db.vehicles.find_one({"id": _S["veh_nav"]}) is None
        arc = db.vehicles_archive.find_one({"id": _S["veh_nav"]}, {"_id": 0})
        assert arc and arc["deleted_by"] == ADMIN[0] and arc["plaque"].startswith("ZH")
        doc = db.documents.find_one({"id": _S["doc"]}, {"_id": 0})
        assert doc["is_deleted"] is True and doc["deleted_reason"] == "vehicle_removed"
        assert doc["storage_path"] == f"pytest/{_RUN}.pdf"  # fichier jamais détruit

    def test_delete_manuel_ok(self):
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_man']}", headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
