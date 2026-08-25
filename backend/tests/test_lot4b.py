"""Lot 4b — vue client superadmin (X-Acting-Tenant) + rôle read_only."""
import uuid

import requests
from dotenv import dotenv_values

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_ID = f"pytest-4b-{_RUN}"
RO_EMAIL = f"ro-{_RUN}@pytest-4b.ch"
RO_PASSWORD = f"RoPass-{_RUN}-1"


def _login(email, password):
    return requests.post(f"{_BASE}/api/auth/login",
                         json={"email": email, "password": password}, timeout=30)


def _headers(email, password):
    r = _login(email, password)
    assert r.status_code == 200, f"login {email} -> {r.status_code}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


_cache = {}


def sa():
    if "sa" not in _cache:
        _cache["sa"] = _headers(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])
    return _cache["sa"]


def adm():
    if "adm" not in _cache:
        _cache["adm"] = _headers(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"])
    return _cache["adm"]


def setup_module():
    r = requests.post(f"{_BASE}/api/admin/tenants",
                      json={"name": f"Client 4b {_RUN}", "id": TENANT_ID},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                      json={"email": RO_EMAIL, "password": RO_PASSWORD, "role": "read_only"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text


class TestActingTenant:
    def test_superadmin_without_header_sees_platform_empty(self):
        r = requests.get(f"{_BASE}/api/vehicles", headers=sa(), timeout=30)
        assert r.status_code == 200 and r.json() == []

    def test_superadmin_with_header_sees_client_data(self):
        default_list = requests.get(f"{_BASE}/api/vehicles", headers=adm(), timeout=30).json()
        h = {**sa(), "X-Acting-Tenant": "default"}
        r = requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30)
        assert r.status_code == 200
        assert len(r.json()) == len(default_list)

    def test_unknown_acting_tenant_404(self):
        h = {**sa(), "X-Acting-Tenant": f"nope-{_RUN}"}
        r = requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30)
        assert r.status_code == 404

    def test_header_ignored_for_non_superadmin(self):
        h = {**adm(), "X-Acting-Tenant": TENANT_ID}
        r = requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30)
        assert r.status_code == 200
        assert len(r.json()) > 0  # voit toujours SON tenant default, pas le tenant vide

    def test_superadmin_can_write_in_acting_tenant(self):
        h = {**sa(), "X-Acting-Tenant": TENANT_ID}
        r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"SA {_RUN[:4].upper()}"},
                          headers=h, timeout=30)
        assert r.status_code == 200, r.text
        vid = r.json()["id"]
        ro = _headers(RO_EMAIL, RO_PASSWORD)
        seen = requests.get(f"{_BASE}/api/vehicles", headers=ro, timeout=30).json()
        assert any(v["id"] == vid for v in seen)
        not_seen = requests.get(f"{_BASE}/api/vehicles/{vid}", headers=adm(), timeout=30)
        assert not_seen.status_code == 404  # isolation : invisible depuis default
        d = requests.delete(f"{_BASE}/api/vehicles/{vid}", headers=h, timeout=30)
        assert d.status_code == 200

    def test_file_token_acting_superadmin_only(self):
        r = requests.get(f"{_BASE}/api/auth/file-token",
                         params={"acting_tenant": "default"}, headers=sa(), timeout=30)
        assert r.status_code == 200 and r.json().get("token")
        r = requests.get(f"{_BASE}/api/auth/file-token",
                         params={"acting_tenant": TENANT_ID}, headers=adm(), timeout=30)
        assert r.status_code == 403


class TestReadOnlyRole:
    def _ro(self):
        if "ro" not in _cache:
            _cache["ro"] = _headers(RO_EMAIL, RO_PASSWORD)
        return _cache["ro"]

    def test_read_allowed(self):
        for path in ("vehicles", "dashboard", "timeline", "alerts"):
            r = requests.get(f"{_BASE}/api/{path}", headers=self._ro(), timeout=30)
            assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_writes_forbidden_403(self):
        h = self._ro()
        checks = [
            ("POST", "vehicles", {"plaque": "RO 1"}),
            ("POST", "alerts/run", {}),
            ("PUT", "vehicles/fake-id", {"plaque": "RO 2"}),
            ("DELETE", "documents/fake-id", None),
        ]
        for method, path, body in checks:
            r = requests.request(method, f"{_BASE}/api/{path}", json=body, headers=h, timeout=30)
            assert r.status_code == 403, f"{method} {path} -> {r.status_code}"
            assert "lecture seule" in (r.json().get("detail") or "").lower()

    def test_can_change_own_password_and_logout(self):
        new_pw = f"RoPass-{_RUN}-2"
        r = requests.post(f"{_BASE}/api/auth/change-password",
                          json={"current_password": RO_PASSWORD, "new_password": new_pw},
                          headers=self._ro(), timeout=30)
        assert r.status_code == 200
        assert _login(RO_EMAIL, new_pw).status_code == 200
        h2 = _headers(RO_EMAIL, new_pw)
        assert requests.post(f"{_BASE}/api/auth/logout", headers=h2, timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/auth/me", headers=h2, timeout=30).status_code == 401

    def test_role_user_no_longer_accepted(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                          json={"email": f"u-{_RUN}@pytest-4b.ch", "password": "Whatever123", "role": "user"},
                          headers=sa(), timeout=30)
        assert r.status_code == 422
