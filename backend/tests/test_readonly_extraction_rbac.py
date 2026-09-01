"""RBAC checks for read_only account on document extraction endpoints (iteration 32)."""
import os

import requests
from dotenv import dotenv_values

BASE_URL = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
RO = {"email": "ro-e2e@client-test.ch", "password": "RoTest-2026y"}
ADMIN = {"email": "admin@logitrak.ch", "password": "3a9218d1606b52e003383e52d7aea3d6"}
DOC_ID = "7557f924-1d4a-4ac4-ac8f-da1349d93718"  # admin-tenant analysed doc


def token(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text[:300]
    return r.json()["token"]


def test_admin_can_read_extraction():
    h = {"Authorization": f"Bearer {token(ADMIN)}"}
    r = requests.get(f"{BASE_URL}/api/documents/{DOC_ID}/extraction", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "_id" not in body
    assert len(body["fields"]) == 24
    assert body["extraction_status"] == "validated"


def test_readonly_cannot_read_other_tenant_extraction():
    h = {"Authorization": f"Bearer {token(RO)}"}
    r = requests.get(f"{BASE_URL}/api/documents/{DOC_ID}/extraction", headers=h, timeout=30)
    assert r.status_code in (403, 404), f"cross-tenant leak: {r.status_code} {r.text[:200]}"


def test_readonly_cannot_validate():
    h = {"Authorization": f"Bearer {token(RO)}"}
    r = requests.post(
        f"{BASE_URL}/api/documents/{DOC_ID}/validate",
        headers=h,
        json={"document_type": "permis_circulation", "fields": {"carrosserie": "X"}},
        timeout=30,
    )
    assert r.status_code in (403, 404), f"unexpected {r.status_code}: {r.text[:200]}"


def test_readonly_cannot_create_vehicle():
    h = {"Authorization": f"Bearer {token(RO)}"}
    r = requests.post(f"{BASE_URL}/api/vehicles", headers=h, json={"plaque": "TEST_RO 000"}, timeout=30)
    assert r.status_code == 403, f"unexpected {r.status_code}: {r.text[:200]}"
