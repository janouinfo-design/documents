"""Archive des véhicules supprimés : consultation tenant-scopée + transfert
superadmin des documents conservés vers le client repreneur."""
import uuid
from datetime import datetime, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
SRC = f"pytest-arcsrc-{_RUN}"
DST = f"pytest-arcdst-{_RUN}"
ADM_SRC = (f"arcsrc-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
ADM_DST = (f"arcdst-{_RUN}@pytest.ch", f"Adm-{_RUN}-2")
_S = {}
_cache = {}


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
    for t, adm in ((SRC, ADM_SRC), (DST, ADM_DST)):
        r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Arc {t}", "id": t},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
        r = requests.post(f"{_BASE}/api/admin/tenants/{t}/users",
                          json={"email": adm[0], "password": adm[1], "role": "admin"},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
    # Véhicule source (manuel → supprimable) + document conservé
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADM_SRC), timeout=30,
                      json={"plaque": f"SRC {_RUN[:6].upper()}", "marque": "Audi", "modele": "OBD"})
    _S["veh_src"] = r.json()["id"]
    _S["doc"] = str(uuid.uuid4())
    _S["path"] = f"pytest-arc/{_RUN}.pdf"
    _mongo().documents.insert_one({
        "id": _S["doc"], "vehicle_id": _S["veh_src"], "tenant_id": SRC,
        "folder": "Divers", "original_filename": "carnet.pdf", "storage_path": _S["path"],
        "content_type": "application/pdf", "size": 10, "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()})
    # Véhicule cible chez le repreneur
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADM_DST), timeout=30,
                      json={"plaque": f"DST {_RUN[:6].upper()}", "marque": "Audi", "modele": "OBD"})
    _S["veh_dst"] = r.json()["id"]
    # Suppression → archive
    r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_src']}", headers=_h(*ADM_SRC), timeout=30)
    assert r.status_code == 200 and r.json()["documents_archived"] == 1


def teardown_module():
    db = _mongo()
    for t in (SRC, DST):
        for coll in ("vehicles", "vehicles_archive", "documents", "audit_logs",
                     "vehicle_field_meta", "users"):
            db[coll].delete_many({"tenant_id": t})
        db.tenants.delete_many({"id": t})


class TestArchiveConsultation:
    def test_liste_archive_tenant_scope(self):
        r = requests.get(f"{_BASE}/api/vehicles-archive", headers=_h(*ADM_SRC), timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1 and rows[0]["id"] == _S["veh_src"]
        assert rows[0]["documents_count"] == 1 and rows[0]["deleted_by"] == ADM_SRC[0]
        # L'autre tenant ne voit RIEN
        r = requests.get(f"{_BASE}/api/vehicles-archive", headers=_h(*ADM_DST), timeout=30)
        assert r.status_code == 200 and r.json() == []

    def test_documents_archive(self):
        r = requests.get(f"{_BASE}/api/vehicles-archive/{_S['veh_src']}/documents",
                         headers=_h(*ADM_SRC), timeout=30)
        assert r.status_code == 200
        docs = r.json()
        assert len(docs) == 1 and docs[0]["id"] == _S["doc"] and docs[0]["storage_path"] == _S["path"]
        # Cross-tenant → 404
        r = requests.get(f"{_BASE}/api/vehicles-archive/{_S['veh_src']}/documents",
                         headers=_h(*ADM_DST), timeout=30)
        assert r.status_code == 404


class TestTransfert:
    def test_admin_normal_403(self):
        r = requests.post(f"{_BASE}/api/admin/vehicles-archive/transfer", headers=_h(*ADM_SRC),
                          timeout=30, json={"source_tenant_id": SRC, "archive_vehicle_id": _S["veh_src"],
                                            "target_tenant_id": DST, "target_vehicle_id": _S["veh_dst"]})
        assert r.status_code == 403

    def test_cible_inexistante_404(self):
        r = requests.post(f"{_BASE}/api/admin/vehicles-archive/transfer", headers=sa(),
                          timeout=30, json={"source_tenant_id": SRC, "archive_vehicle_id": _S["veh_src"],
                                            "target_tenant_id": DST, "target_vehicle_id": "inexistant"})
        assert r.status_code == 404

    def test_transfert_superadmin_ok(self):
        r = requests.post(f"{_BASE}/api/admin/vehicles-archive/transfer", headers=sa(),
                          timeout=30, json={"source_tenant_id": SRC, "archive_vehicle_id": _S["veh_src"],
                                            "target_tenant_id": DST, "target_vehicle_id": _S["veh_dst"]})
        assert r.status_code == 200, r.text
        assert r.json()["transferred"] == 1
        doc = _mongo().documents.find_one({"id": _S["doc"]}, {"_id": 0})
        assert doc["tenant_id"] == DST and doc["vehicle_id"] == _S["veh_dst"]
        assert doc["is_deleted"] is False and doc["a_verifier"] is True
        assert doc["transferred_from"]["tenant_id"] == SRC
        assert "deleted_reason" not in doc

    def test_document_visible_chez_repreneur(self):
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_dst']}/documents", headers=_h(*ADM_DST), timeout=30)
        assert r.status_code == 200
        assert any(d["id"] == _S["doc"] for d in r.json())
        # Archive source : 0 document restant + trace du transfert
        r = requests.get(f"{_BASE}/api/vehicles-archive", headers=_h(*ADM_SRC), timeout=30)
        row = r.json()[0]
        assert row["documents_count"] == 0
        assert row["transferred_to"]["tenant_id"] == DST and row["transferred_to"]["documents"] == 1

    def test_retransfert_zero(self):
        r = requests.post(f"{_BASE}/api/admin/vehicles-archive/transfer", headers=sa(),
                          timeout=30, json={"source_tenant_id": SRC, "archive_vehicle_id": _S["veh_src"],
                                            "target_tenant_id": DST, "target_vehicle_id": _S["veh_dst"]})
        assert r.status_code == 200 and r.json()["transferred"] == 0
