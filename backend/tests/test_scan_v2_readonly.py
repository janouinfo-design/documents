"""Quick re-confirmation of RBAC/tenant isolation for POST scan (V2 request)."""
import io
import os
import pytest
import requests
from PIL import Image, ImageDraw

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

BASE_URL = _load_frontend_env().rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

ADMIN_EMAIL = "admin@logitrak.ch"
ADMIN_PASSWORD = "3a9218d1606b52e003383e52d7aea3d6"
RO_EMAIL = "ro-e2e@client-test.ch"
RO_PASSWORD = "RoTest-2026y"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_jpeg(text="Police d'assurance N° 12345"):
    img = Image.new("RGB", (1000, 700), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 30), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


def _first_vehicle_id(token):
    r = requests.get(f"{BASE_URL}/api/vehicles", headers=_headers(token), timeout=20)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    assert items, "no vehicle"
    return items[0]["id"], items[0].get("plaque")


def test_readonly_scan_forbidden():
    """Read-only user must NOT be able to POST /documents/scan."""
    token_ro = _login(RO_EMAIL, RO_PASSWORD)
    vid, plaque = _first_vehicle_id(token_ro)
    files = {"files": ("test.jpg", _make_jpeg(), "image/jpeg")}
    r = requests.post(
        f"{BASE_URL}/api/vehicles/{vid}/documents/scan",
        headers=_headers(token_ro),
        files=files,
        data={"document_type": "assurance"},
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


def test_cross_tenant_scan_returns_404():
    """Admin of tenant default POSTing scan on a vehicle of tenant client-test-e2e must get 404."""
    token_admin = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    token_ro = _login(RO_EMAIL, RO_PASSWORD)
    other_vid, _ = _first_vehicle_id(token_ro)  # vehicle of client-test-e2e
    files = {"files": ("test.jpg", _make_jpeg(), "image/jpeg")}
    r = requests.post(
        f"{BASE_URL}/api/vehicles/{other_vid}/documents/scan",
        headers=_headers(token_admin),
        files=files,
        data={"document_type": "assurance"},
        timeout=30,
    )
    assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text}"


def test_scan_invalid_extension_rejected():
    token = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    vid, _ = _first_vehicle_id(token)
    files = {"files": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    r = requests.post(
        f"{BASE_URL}/api/vehicles/{vid}/documents/scan",
        headers=_headers(token),
        files=files,
        data={"document_type": "autre"},
        timeout=30,
    )
    assert r.status_code in (400, 415, 422), f"expected client error, got {r.status_code}: {r.text[:200]}"


def test_scan_max_pages_exceeded():
    token = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    vid, _ = _first_vehicle_id(token)
    files = [("files", (f"p{i}.jpg", _make_jpeg(f"page {i}"), "image/jpeg")) for i in range(9)]
    r = requests.post(
        f"{BASE_URL}/api/vehicles/{vid}/documents/scan",
        headers=_headers(token),
        files=files,
        data={"document_type": "autre"},
        timeout=60,
    )
    assert r.status_code in (400, 413, 422), f"expected reject, got {r.status_code}: {r.text[:200]}"
