"""Lot Sécurité 2 — SEC-001 (file-token scopé + révocation logout) et SEC-002 (validation uploads).
Fichier disjoint des autres suites. Utilise l'API réelle du preview."""
import io
import os
import sys
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import dotenv_values

_fe = dotenv_values("/app/frontend/.env")
_be = dotenv_values("/app/backend/.env")
BASE = (_fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
NO_AUTH = {"Authorization": ""}

PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\nxref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\n%%EOF"
PNG_BYTES = bytes.fromhex("89504e470d0a1a0a0000000d494844520000000100000001080600000"
                          "01f15c4890000000a49444154789c6300010000050001") + b"\x00" * 10


def _session_token():
    r = requests.post(f"{API}/auth/login", json={
        "email": _be.get("ADMIN_EMAIL"), "password": _be.get("ADMIN_PASSWORD")}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _file_token():
    r = requests.get(f"{API}/auth/file-token", timeout=30)
    r.raise_for_status()
    data = r.json()
    assert data.get("expires_in") == 600
    return data["token"]


@pytest.fixture(scope="module")
def vehicle():
    r = requests.post(f"{API}/vehicles", json={
        "plaque": "ZZ SEC2 999", "marque": "TestSec", "modele": "Lot2"}, timeout=30)
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    yield vid
    requests.delete(f"{API}/vehicles/{vid}", timeout=30)


@pytest.fixture(scope="module")
def uploaded_pdf(vehicle):
    r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                      files={"file": ("preuve.pdf", PDF_BYTES, "application/pdf")},
                      data={"folder": "Divers"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# SEC-001 — file-token scopé et révocation
# ---------------------------------------------------------------------------
class TestSec001FileToken:
    def test_session_token_ok_on_business_api(self):
        r = requests.get(f"{API}/vehicles", timeout=30)
        assert r.status_code == 200

    def test_session_token_in_query_refused_on_files(self):
        tok = _session_token()
        r = requests.get(f"{API}/files/logitrak-fleet/uploads/x/y.pdf",
                         params={"token": tok}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 401

    def test_file_token_ok_on_files(self, uploaded_pdf):
        ft = _file_token()
        r = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": ft}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("Content-Type", "").startswith("application/pdf")

    def test_file_token_ok_on_reports(self):
        ft = _file_token()
        r = requests.get(f"{API}/reports/conformite.pdf",
                         params={"token": ft}, headers=NO_AUTH, timeout=60)
        assert r.status_code == 200
        assert "pdf" in r.headers.get("Content-Type", "")

    def test_file_token_refused_on_business_api_header(self):
        ft = _file_token()
        for path in ("/vehicles", "/alerts", "/timeline", "/dashboard"):
            r = requests.get(f"{API}{path}",
                             headers={"Authorization": f"Bearer {ft}"}, timeout=30)
            assert r.status_code == 401, f"{path} -> {r.status_code}"

    def test_file_token_refused_on_business_api_query(self):
        ft = _file_token()
        r = requests.get(f"{API}/vehicles", params={"token": ft}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 401

    def test_file_token_tampered_refused(self, uploaded_pdf):
        ft = _file_token()
        bad = ft[:-4] + ("aaaa" if not ft.endswith("aaaa") else "bbbb")
        r = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": bad}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 401

    def test_file_token_expired_refused(self, uploaded_pdf):
        me = requests.get(f"{API}/auth/me", timeout=30).json()
        expired = jwt.encode(
            {"sub": me["id"], "tenant_id": me.get("tenant_id") or "default",
             "type": "file", "tv": int(me.get("token_version", 0) or 0),
             "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            _be["JWT_SECRET"], algorithm="HS256")
        r = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": expired}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 401

    def test_file_token_wrong_tenant_claim_refused(self, uploaded_pdf):
        me = requests.get(f"{API}/auth/me", timeout=30).json()
        forged = jwt.encode(
            {"sub": me["id"], "tenant_id": "autre-tenant",
             "type": "file", "tv": int(me.get("token_version", 0) or 0),
             "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            _be["JWT_SECRET"], algorithm="HS256")
        r = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": forged}, headers=NO_AUTH, timeout=30)
        assert r.status_code == 401

    def test_logout_revokes_session_and_file_tokens(self):
        s2 = _session_token()
        h2 = {"Authorization": f"Bearer {s2}"}
        f2 = requests.get(f"{API}/auth/file-token", headers=h2, timeout=30).json()["token"]
        try:
            r = requests.post(f"{API}/auth/logout", headers=h2, timeout=30)
            assert r.status_code == 200
            r = requests.get(f"{API}/vehicles", headers=h2, timeout=30)
            assert r.status_code == 401, "session non révoquée après logout"
            r = requests.get(f"{API}/files/logitrak-fleet/uploads/x/y.pdf",
                             params={"token": f2}, headers=NO_AUTH, timeout=30)
            assert r.status_code == 401, "file-token non révoqué après logout"
            r = requests.post(f"{API}/auth/login", json={
                "email": _be.get("ADMIN_EMAIL"), "password": _be.get("ADMIN_PASSWORD")},
                timeout=30)
            assert r.status_code == 200, "re-login après logout impossible"
        finally:
            conftest = sys.modules.get("conftest")
            if conftest is not None:
                conftest._token = None


# ---------------------------------------------------------------------------
# SEC-002 — validation des uploads + restitution sûre
# ---------------------------------------------------------------------------
class TestSec002Uploads:
    def test_html_rejected(self, vehicle):
        r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                          files={"file": ("evil.html", b"<script>1</script>", "text/html")},
                          data={"folder": "Divers"}, timeout=30)
        assert r.status_code == 400

    def test_exe_rejected_on_generic_upload(self):
        r = requests.post(f"{API}/upload",
                          files={"file": ("mal.exe", b"MZ\x00\x00", "application/octet-stream")},
                          data={"vehicle_id": "misc"}, timeout=30)
        assert r.status_code == 400

    def test_oversize_rejected(self, vehicle):
        big = b"0" * (25 * 1024 * 1024 + 1)
        r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                          files={"file": ("gros.pdf", big, "application/pdf")},
                          data={"folder": "Divers"}, timeout=120)
        assert r.status_code == 413

    def test_allowed_formats_accepted(self, vehicle):
        created = []
        for name, payload, ctype in [
            ("ok.pdf", PDF_BYTES, "application/pdf"),
            ("ok.png", PNG_BYTES, "image/png"),
            ("ok.csv", b"a;b\n1;2\n", "text/csv"),
        ]:
            r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                              files={"file": (name, payload, ctype)},
                              data={"folder": "Divers"}, timeout=30)
            assert r.status_code == 200, f"{name} -> {r.status_code}: {r.text}"
            created.append(r.json()["id"])
        for doc_id in created:
            requests.delete(f"{API}/documents/{doc_id}", timeout=30)

    def test_lying_content_type_neutralized(self, vehicle):
        # HTML déguisé en .png : accepté (extension autorisée) mais servi image/png + nosniff → inerte
        r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                          files={"file": ("piege.png", b"<script>alert(1)</script>", "text/html")},
                          data={"folder": "Divers"}, timeout=30)
        assert r.status_code == 200
        doc = r.json()
        ft = _file_token()
        s = requests.get(f"{API}/files/{doc['storage_path']}",
                         params={"token": ft}, headers=NO_AUTH, timeout=30)
        assert s.headers.get("Content-Type", "").startswith("image/png")
        assert s.headers.get("X-Content-Type-Options") == "nosniff"
        requests.delete(f"{API}/documents/{doc['id']}", timeout=30)

    def test_non_inline_type_forced_attachment(self, vehicle):
        r = requests.post(f"{API}/vehicles/{vehicle}/documents",
                          files={"file": ("data.csv", b"a;b\n", "text/csv")},
                          data={"folder": "Divers"}, timeout=30)
        assert r.status_code == 200
        doc = r.json()
        ft = _file_token()
        s = requests.get(f"{API}/files/{doc['storage_path']}",
                         params={"token": ft}, headers=NO_AUTH, timeout=30)
        assert s.headers.get("Content-Disposition", "").startswith("attachment")
        requests.delete(f"{API}/documents/{doc['id']}", timeout=30)

    def test_pdf_inline_preserved(self, uploaded_pdf):
        ft = _file_token()
        s = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": ft}, headers=NO_AUTH, timeout=30)
        assert s.headers.get("Content-Disposition", "").startswith("inline")

    def test_malicious_filename_sanitized(self, uploaded_pdf):
        ft = _file_token()
        s = requests.get(f"{API}/files/{uploaded_pdf['storage_path']}",
                         params={"token": ft, "download": "true",
                                 "filename": 'a"b\r\nX-Inject: 1'}, headers=NO_AUTH, timeout=30)
        assert s.status_code == 200
        cd = s.headers.get("Content-Disposition", "")
        assert "\r" not in cd and "\n" not in cd and 'a_b' in cd
        assert "X-Inject" not in s.headers

    def test_upload_to_unknown_vehicle_refused(self):
        r = requests.post(f"{API}/upload",
                          files={"file": ("ok.png", PNG_BYTES, "image/png")},
                          data={"vehicle_id": "00000000-0000-0000-0000-000000000000"}, timeout=30)
        assert r.status_code == 404
