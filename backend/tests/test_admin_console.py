"""Console Super Admin — rôles, clients, utilisateurs, intégrations, modules (Lot 4)."""
import uuid

import requests
from dotenv import dotenv_values

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_ID = f"pytest-client-{_RUN}"


def _login(email, password):
    return requests.post(f"{_BASE}/api/auth/login",
                         json={"email": email, "password": password}, timeout=30)


def _headers(email, password):
    r = _login(email, password)
    assert r.status_code == 200, f"login {email} -> {r.status_code}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


_sa_cache = {}


def sa_headers():
    if "h" not in _sa_cache:
        _sa_cache["h"] = _headers(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])
    return _sa_cache["h"]


def admin_headers():
    return _headers(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"])


class TestRoles:
    def test_superadmin_login_role_and_tenant(self):
        r = requests.get(f"{_BASE}/api/auth/me", headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "superadmin"
        assert me["tenant_id"] == "platform"

    def test_legacy_admin_demoted_to_client_admin(self):
        r = requests.get(f"{_BASE}/api/auth/me", headers=admin_headers(), timeout=30)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "admin"
        assert me["tenant_id"] == "default"

    def test_client_admin_forbidden_on_console(self):
        r = requests.get(f"{_BASE}/api/admin/overview", headers=admin_headers(), timeout=30)
        assert r.status_code == 403

    def test_invalid_token_rejected_on_console(self):
        r = requests.get(f"{_BASE}/api/admin/overview",
                         headers={"Authorization": "Bearer invalid.token.here"}, timeout=30)
        assert r.status_code == 401

    def test_business_api_still_works_for_client_admin(self):
        r = requests.get(f"{_BASE}/api/vehicles", headers=admin_headers(), timeout=30)
        assert r.status_code == 200


class TestTenants:
    def test_create_tenant(self):
        r = requests.post(f"{_BASE}/api/admin/tenants",
                          json={"name": f"Client Pytest {_RUN}", "id": TENANT_ID},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == TENANT_ID
        assert body["modules"] == {"documents": True}

    def test_duplicate_tenant_409(self):
        r = requests.post(f"{_BASE}/api/admin/tenants",
                          json={"name": "Dup", "id": TENANT_ID},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 409

    def test_platform_id_reserved(self):
        r = requests.post(f"{_BASE}/api/admin/tenants",
                          json={"name": "X", "id": "platform"}, headers=sa_headers(), timeout=30)
        assert r.status_code == 409

    def test_empty_name_422(self):
        r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": "  "},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 422

    def test_overview_lists_default_and_new(self):
        r = requests.get(f"{_BASE}/api/admin/overview", headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        ids = {t["id"]: t for t in r.json()["tenants"]}
        assert "default" in ids and TENANT_ID in ids
        assert "api_hash" not in str(r.json())
        assert ids["default"]["users"] >= 1


class TestUsers:
    EMAIL = f"admin-{_RUN}@pytest-client.ch"
    PASSWORD = f"Pw-{_RUN}-initial"

    def test_create_user(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                          json={"email": self.EMAIL, "password": self.PASSWORD, "name": "Admin Client"},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "admin"
        assert "password_hash" not in r.json()

    def test_duplicate_email_409(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                          json={"email": self.EMAIL, "password": "Whatever123"},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 409

    def test_short_password_422(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                          json={"email": f"x-{_RUN}@c.ch", "password": "short"},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 422

    def test_superadmin_role_refused(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users",
                          json={"email": f"y-{_RUN}@c.ch", "password": "Whatever123", "role": "superadmin"},
                          headers=sa_headers(), timeout=30)
        assert r.status_code == 422

    def test_new_user_sees_only_its_empty_tenant(self):
        h = _headers(self.EMAIL, self.PASSWORD)
        r = requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30)
        assert r.status_code == 200
        assert r.json() == []
        rd = requests.get(f"{_BASE}/api/vehicles", headers=admin_headers(), timeout=30)
        default_vehicles = rd.json()
        if default_vehicles:
            rx = requests.get(f"{_BASE}/api/vehicles/{default_vehicles[0]['id']}", headers=h, timeout=30)
            assert rx.status_code == 404

    def test_client_user_cannot_access_console(self):
        h = _headers(self.EMAIL, self.PASSWORD)
        r = requests.get(f"{_BASE}/api/admin/overview", headers=h, timeout=30)
        assert r.status_code == 403

    def _user_id(self):
        r = requests.get(f"{_BASE}/api/admin/tenants/{TENANT_ID}/users", headers=sa_headers(), timeout=30)
        return next(u for u in r.json() if u["email"] == self.EMAIL)["id"]

    def test_password_reset_revokes_sessions(self):
        h_old = _headers(self.EMAIL, self.PASSWORD)
        new_pw = f"Pw-{_RUN}-rotated"
        r = requests.put(f"{_BASE}/api/admin/users/{self._user_id()}",
                         json={"password": new_pw}, headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert requests.get(f"{_BASE}/api/auth/me", headers=h_old, timeout=30).status_code == 401
        assert _login(self.EMAIL, self.PASSWORD).status_code == 401
        assert _login(self.EMAIL, new_pw).status_code == 200
        type(self).PASSWORD = new_pw

    def test_disable_user_blocks_login_and_tokens(self):
        uid = self._user_id()
        h_live = _headers(self.EMAIL, self.PASSWORD)
        r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"disabled": True},
                         headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert _login(self.EMAIL, self.PASSWORD).status_code == 401
        assert requests.get(f"{_BASE}/api/auth/me", headers=h_live, timeout=30).status_code == 401
        r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"disabled": False},
                         headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert _login(self.EMAIL, self.PASSWORD).status_code == 200

    def test_superadmin_account_not_modifiable(self):
        me = requests.get(f"{_BASE}/api/auth/me", headers=sa_headers(), timeout=30).json()
        r = requests.put(f"{_BASE}/api/admin/users/{me['id']}", json={"disabled": True},
                         headers=sa_headers(), timeout=30)
        assert r.status_code == 403


class TestIntegration:
    def test_set_api_hash_never_returned(self):
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}/integration",
                         json={"api_hash": f"pytest-hash-{_RUN}", "enabled": True},
                         headers=sa_headers(), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["configured"] is True
        assert body["enabled"] is True
        assert "api_hash" not in body
        g = requests.get(f"{_BASE}/api/admin/tenants/{TENANT_ID}/integration",
                         headers=sa_headers(), timeout=30)
        assert g.status_code == 200 and "api_hash" not in g.json()

    def test_empty_update_422(self):
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}/integration",
                         json={}, headers=sa_headers(), timeout=30)
        assert r.status_code == 422

    def test_unknown_tenant_404(self):
        r = requests.get(f"{_BASE}/api/admin/tenants/nope-{_RUN}/integration",
                         headers=sa_headers(), timeout=30)
        assert r.status_code == 404


class TestModulesAndDisable:
    def test_module_documents_disable_blocks_business_api(self):
        h = _headers(TestUsers.EMAIL, TestUsers.PASSWORD)
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}",
                         json={"modules": {"documents": False}}, headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30).status_code == 403
        assert requests.get(f"{_BASE}/api/auth/me", headers=h, timeout=30).status_code == 200
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}",
                         json={"modules": {"documents": True}}, headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30).status_code == 200

    def test_tenant_disable_blocks_everything(self):
        h = _headers(TestUsers.EMAIL, TestUsers.PASSWORD)
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}",
                         json={"disabled": True}, headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert _login(TestUsers.EMAIL, TestUsers.PASSWORD).status_code == 401
        assert requests.get(f"{_BASE}/api/vehicles", headers=h, timeout=30).status_code == 401
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT_ID}",
                         json={"disabled": False}, headers=sa_headers(), timeout=30)
        assert r.status_code == 200
        assert _login(TestUsers.EMAIL, TestUsers.PASSWORD).status_code == 200

    def test_default_tenant_unaffected(self):
        assert requests.get(f"{_BASE}/api/vehicles", headers=admin_headers(), timeout=30).status_code == 200


def teardown_module():
    from pymongo import MongoClient
    c = MongoClient(_ENV["MONGO_URL"])
    db = c[_ENV["DB_NAME"]]
    db.users.delete_many({"tenant_id": TENANT_ID})
    db.vehicles.delete_many({"tenant_id": TENANT_ID})
    db.tenant_integrations.delete_many({"tenant_id": TENANT_ID})
    db.tenants.delete_many({"id": TENANT_ID})
    c.close()
