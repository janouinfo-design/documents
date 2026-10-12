"""
E2E tests for Super Admin tenant_modules feature.
- Validates: /api/admin/overview module_catalog + modules; module toggle persistence; 
  per-tenant disabled module 403 MODULE_DISABLED; auth/me tenant_modules field;
  422 on unknown module key; non-superadmin 403 on admin PUT;
  ensure demo-logitrak modules are all restored to ON at end.
"""
import os
import time
import requests
import pytest

from dotenv import dotenv_values
_FE = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _FE.get("REACT_APP_BACKEND_URL") or "").rstrip("/")

# Read .env for creds (preview has no python-dotenv in test ctx -> read file)
def _env(path="/app/backend/.env"):
    out = {}
    with open(path) as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.strip().partition("=")
                out[k] = v.strip().strip('"').strip("'")
    return out

ENV = _env()
SUPERADMIN_EMAIL = ENV.get("SUPERADMIN_EMAIL")
SUPERADMIN_PASSWORD = ENV.get("SUPERADMIN_PASSWORD")
ADMIN_EMAIL = ENV.get("ADMIN_EMAIL")
ADMIN_PASSWORD = ENV.get("ADMIN_PASSWORD")
DEMO_ADMIN_EMAIL = "admin@demo-logitrak.ch"
DEMO_ADMIN_PASSWORD = "DemoPreview2026!"
DEMO_TID = "demo-logitrak"

EXPECTED_MODULES = {"vehicles","documents","deadlines","costs","energy",
                    "drivers","fines","ai","alerts","integrity"}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def sa_token():
    return _login(SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


@pytest.fixture(scope="module")
def demo_admin_token():
    return _login(DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)


@pytest.fixture(scope="module", autouse=True)
def restore_demo_modules_at_end(sa_token):
    yield
    # Ensure all modules ON at the end
    all_on = {k: True for k in EXPECTED_MODULES}
    r = requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     json={"modules": all_on}, timeout=20)
    assert r.status_code == 200, f"restore failed: {r.status_code} {r.text}"


def test_admin_overview_module_catalog(sa_token):
    r = requests.get(f"{BASE_URL}/api/admin/overview",
                     headers={"Authorization": f"Bearer {sa_token}"}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "module_catalog" in data, data.keys()
    cat = data["module_catalog"]
    keys = {m["key"] for m in cat}
    assert keys == EXPECTED_MODULES, f"got {keys}"
    # per-tenant modules dict
    tenants = data.get("tenants", [])
    demo = next((t for t in tenants if t.get("id") == DEMO_TID or t.get("tenant_id") == DEMO_TID), None)
    assert demo is not None, f"demo-logitrak not found; tenants={[t.get('id') for t in tenants]}"
    mods = demo.get("modules") or {}
    assert set(mods.keys()) >= EXPECTED_MODULES, f"missing module keys: {EXPECTED_MODULES - set(mods.keys())}"
    assert all(isinstance(v, bool) for v in mods.values())


def test_unknown_module_key_returns_422(sa_token):
    r = requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     json={"modules": {"inconnu": False}}, timeout=20)
    assert r.status_code == 422, f"expected 422, got {r.status_code} {r.text}"


def test_non_superadmin_forbidden_on_admin_put(demo_admin_token):
    r = requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {demo_admin_token}"},
                     json={"modules": {"fines": False}}, timeout=20)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


def test_module_toggle_fines_off_then_on(sa_token):
    # Snapshot fines count before
    demo_admin_tok = _login(DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)
    r0 = requests.get(f"{BASE_URL}/api/fines",
                      headers={"Authorization": f"Bearer {demo_admin_tok}"}, timeout=20)
    assert r0.status_code == 200
    before = r0.json() if isinstance(r0.json(), list) else r0.json().get("items", [])
    before_count = len(before)

    # Turn fines OFF
    r = requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     json={"modules": {"fines": False}}, timeout=20)
    assert r.status_code == 200, r.text

    # Fresh login (tenant modules read from DB)
    demo_admin_tok = _login(DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)

    # /api/auth/me shows tenant_modules.fines=false
    me = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {demo_admin_tok}"}, timeout=20).json()
    tm = me.get("tenant_modules") or me.get("user", {}).get("tenant_modules") or {}
    assert tm.get("fines") is False, f"tenant_modules.fines expected False, got {tm}"

    # /api/fines → 403 MODULE_DISABLED
    rf = requests.get(f"{BASE_URL}/api/fines",
                      headers={"Authorization": f"Bearer {demo_admin_tok}"}, timeout=20)
    assert rf.status_code == 403, f"expected 403, got {rf.status_code} {rf.text}"
    body = rf.json()
    code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
    assert code == "MODULE_DISABLED", f"expected MODULE_DISABLED, got {body}"

    # Turn back ON
    r = requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     json={"modules": {"fines": True}}, timeout=20)
    assert r.status_code == 200

    demo_admin_tok = _login(DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD)
    rf2 = requests.get(f"{BASE_URL}/api/fines",
                       headers={"Authorization": f"Bearer {demo_admin_tok}"}, timeout=20)
    assert rf2.status_code == 200
    after = rf2.json() if isinstance(rf2.json(), list) else rf2.json().get("items", [])
    assert len(after) == before_count, f"fines count changed {before_count} -> {len(after)}"


def test_default_tenant_admin_sees_full_modules(sa_token):
    tok = _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    me = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20).json()
    tm = me.get("tenant_modules") or me.get("user", {}).get("tenant_modules") or {}
    # All modules should be enabled (default)
    for k in EXPECTED_MODULES:
        assert tm.get(k, True) is True, f"default tenant module {k} unexpectedly off: {tm}"


def test_superadmin_acting_tenant_header_fines_off(sa_token):
    # Disable fines on demo
    requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                 headers={"Authorization": f"Bearer {sa_token}"},
                 json={"modules": {"fines": False}}, timeout=20)
    try:
        r = requests.get(f"{BASE_URL}/api/fines",
                         headers={"Authorization": f"Bearer {sa_token}",
                                  "X-Acting-Tenant": DEMO_TID}, timeout=20)
        assert r.status_code == 403, f"expected 403 via acting-tenant, got {r.status_code}"
        body = r.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        assert code == "MODULE_DISABLED"
    finally:
        requests.put(f"{BASE_URL}/api/admin/tenants/{DEMO_TID}",
                     headers={"Authorization": f"Bearer {sa_token}"},
                     json={"modules": {"fines": True}}, timeout=20)
