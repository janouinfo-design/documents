"""Sécurisation Documents — audit trail (upload/download/delete), RBAC read_only,
isolation tenant sur fichiers, en-têtes cache, cas limites fichiers, stockage local."""
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-docsec-a-{_RUN}"
TENANT_B = f"pytest-docsec-b-{_RUN}"
ADMIN_A = (f"docsec-adm-a-{_RUN}@pytest.ch", f"AdmA-{_RUN}-1")
ADMIN_B = (f"docsec-adm-b-{_RUN}@pytest.ch", f"AdmB-{_RUN}-1")
RO_A = (f"docsec-ro-a-{_RUN}@pytest.ch", f"RoA-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120
# conftest.py injecte un Bearer admin par défaut : ce header non-Bearer le neutralise
NO_BEARER = {"Authorization": "None"}

_S = {}
_cache = {}
_mongo_db = None


def _get_file(path, **params):
    return requests.get(f"{_BASE}/api/files/{path}", params=params or None,
                        headers=NO_BEARER, timeout=30)


def _mongo():
    global _mongo_db
    if _mongo_db is None:
        _mongo_db = MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]
    return _mongo_db


def _h(creds):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login",
                          json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, f"login {creds[0]} -> {r.status_code}"
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _file_token(creds):
    r = requests.get(f"{_BASE}/api/auth/file-token", headers=_h(creds), timeout=30)
    assert r.status_code == 200
    return r.json()["token"]


def _upload_doc(creds, vehicle_id, name="test-doc.png"):
    return requests.post(f"{_BASE}/api/vehicles/{vehicle_id}/documents",
                         headers=_h(creds), files={"file": (name, PNG, "image/png")},
                         data={"folder": "Divers"}, timeout=30)


def setup_module():
    for tid_, name, admin in ((TENANT_A, "A", ADMIN_A), (TENANT_B, "B", ADMIN_B)):
        r = requests.post(f"{_BASE}/api/admin/tenants",
                          json={"name": f"DocSec {name} {_RUN}", "id": tid_},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
        r = requests.post(f"{_BASE}/api/admin/tenants/{tid_}/users",
                          json={"email": admin[0], "password": admin[1], "role": "admin"},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users",
                      json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"ZH {_RUN[:6].upper()}"},
                      headers=_h(ADMIN_A), timeout=30)
    assert r.status_code == 200, r.text
    _S["veh_a"] = r.json()["id"]
    r = _upload_doc(ADMIN_A, _S["veh_a"])
    assert r.status_code == 200, r.text
    _S["doc"] = r.json()
    _S["path"] = _S["doc"]["storage_path"]


def teardown_module():
    db = _mongo()
    tids = [TENANT_A, TENANT_B]
    for coll in ("users", "vehicles", "documents", "files", "audit_logs", "tenant_integrations"):
        db[coll].delete_many({"tenant_id": {"$in": tids}})
    db.tenants.delete_many({"id": {"$in": tids}})


class TestAuditTrail:
    def test_upload_creates_audit_event(self):
        ev = _mongo().audit_logs.find_one(
            {"action": "create", "entity": "document", "entity_id": _S["doc"]["id"]})
        assert ev, "aucun audit event pour l'upload"
        assert ev["tenant_id"] == TENANT_A
        assert ev["user"] == ADMIN_A[0]
        assert ev["vehicle_id"] == _S["veh_a"]

    def test_download_creates_audit_event_and_secure_headers(self):
        r = _get_file(_S["path"], token=_file_token(ADMIN_A), download="true")
        assert r.status_code == 200
        # Backend : "private, no-store" ; le proxy preview peut réécrire — no-store doit rester
        assert "no-store" in (r.headers.get("Cache-Control") or "")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert "attachment" in (r.headers.get("Content-Disposition") or "")
        ev = _mongo().audit_logs.find_one(
            {"action": "download", "entity": "document", "entity_id": _S["path"]})
        assert ev and ev["tenant_id"] == TENANT_A

    def test_delete_soft_deletes_and_creates_audit_event(self):
        r = _upload_doc(ADMIN_A, _S["veh_a"], name="to-delete.png")
        assert r.status_code == 200
        doc_id = r.json()["id"]
        r = requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200
        rec = _mongo().documents.find_one({"id": doc_id})
        assert rec and rec["is_deleted"] is True, "le soft-delete doit être conservé"
        ev = _mongo().audit_logs.find_one(
            {"action": "delete", "entity": "document", "entity_id": doc_id})
        assert ev and ev["tenant_id"] == TENANT_A and ev["user"] == ADMIN_A[0]


class TestReadOnlyRbac:
    def test_read_only_can_download(self):
        r = _get_file(_S["path"], token=_file_token(RO_A))
        assert r.status_code == 200

    def test_read_only_cannot_upload(self):
        r = _upload_doc(RO_A, _S["veh_a"])
        assert r.status_code == 403

    def test_read_only_cannot_delete(self):
        r = requests.delete(f"{_BASE}/api/documents/{_S['doc']['id']}",
                            headers=_h(RO_A), timeout=30)
        assert r.status_code == 403
        assert _mongo().documents.find_one({"id": _S["doc"]["id"]})["is_deleted"] is False


class TestTenantIsolationFiles:
    def test_b_cannot_list_documents_of_a(self):
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents",
                         headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404

    def test_b_cannot_download_file_of_a(self):
        r = _get_file(_S["path"], token=_file_token(ADMIN_B))
        assert r.status_code == 404

    def test_b_cannot_delete_doc_of_a(self):
        r = requests.delete(f"{_BASE}/api/documents/{_S['doc']['id']}",
                            headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404
        assert _mongo().documents.find_one({"id": _S["doc"]["id"]})["is_deleted"] is False

    def test_file_without_any_token_refused(self):
        r = _get_file(_S["path"])
        assert r.status_code == 401

    def test_access_token_in_query_refused_on_files(self):
        access = _h(ADMIN_A)["Authorization"][7:]
        r = _get_file(_S["path"], token=access)
        assert r.status_code == 401


class TestFileEdgeCases:
    def test_db_record_without_physical_file_returns_clean_404(self):
        ghost_path = _S["path"].replace(".png", f"-ghost-{_RUN}.pdf")
        _mongo().documents.insert_one({
            "id": str(uuid.uuid4()), "vehicle_id": _S["veh_a"], "tenant_id": TENANT_A,
            "folder": "Divers", "original_filename": "ghost.pdf", "storage_path": ghost_path,
            "content_type": "application/pdf", "size": 1, "is_deleted": False,
            "created_at": "2026-01-01T00:00:00+00:00"})
        tok = _file_token(ADMIN_A)
        r = _get_file(ghost_path, token=tok)
        assert r.status_code == 404

    def test_path_traversal_rejected(self):
        tok = _file_token(ADMIN_A)
        r = _get_file("..%2F..%2Fetc%2Fpasswd", token=tok)
        assert r.status_code in (400, 404)

    def test_upload_disallowed_extension_rejected(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents",
                          headers=_h(ADMIN_A),
                          files={"file": ("evil.exe", b"MZ\x00", "application/octet-stream")},
                          data={"folder": "Divers"}, timeout=30)
        assert r.status_code == 400


class TestLocalStorageUnit:
    def test_local_path_traversal_guard(self, tmp_path, monkeypatch):
        import server as server_mod
        from fastapi import HTTPException
        monkeypatch.setattr(server_mod, "LOCAL_STORAGE_DIR", str(tmp_path))
        with pytest.raises(HTTPException) as exc:
            server_mod._local_path("../../etc/passwd")
        assert exc.value.status_code == 400

    def test_local_put_get_roundtrip_persists_on_disk(self, tmp_path, monkeypatch):
        import server as server_mod
        monkeypatch.setattr(server_mod, "STORAGE_BACKEND", "local")
        monkeypatch.setattr(server_mod, "LOCAL_STORAGE_DIR", str(tmp_path))
        rel = f"t/{_RUN}/sample.pdf"
        server_mod.put_object(rel, b"%PDF-1.4 test", "application/pdf")
        assert (tmp_path / "t" / _RUN / "sample.pdf").exists()
        data, ctype = server_mod.get_object(rel)
        assert data == b"%PDF-1.4 test" and ctype == "application/pdf"
