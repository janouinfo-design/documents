"""Impersonation utilisateur précis (console Super Admin → « Se connecter comme cet utilisateur »).
Backend = source de vérité : droits EXACTS de la cible (rôle, vehicle_scope, driver_id, read_only, modules), audit start/end."""
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-imp-{_RUN}"
OTHER = f"pytest-imp-o-{_RUN}"
MANAGER = f"imp-mgr-{_RUN}@pytest.ch"
DRIVER = f"imp-drv-{_RUN}@pytest.ch"
RO = f"imp-ro-{_RUN}@pytest.ch"
INACTIVE = f"imp-off-{_RUN}@pytest.ch"
OTHER_ADMIN = f"imp-other-{_RUN}@pytest.ch"
PW = f"Pw-{_RUN}-xyz1"
ADMIN = (f"imp-adm-{_RUN}@pytest.ch", PW)
_S, _cache = {}, {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _login(creds):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _login((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_user(tenant, email, role, **extra):
    r = requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": email, "password": PW, "role": role, **extra},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _impersonate(user_id, tenant=None, expect=200):
    r = requests.post(f"{_BASE}/api/admin/tenants/{tenant or TENANT}/impersonate", json={"user_id": user_id}, headers=sa(), timeout=30)
    assert r.status_code == expect, r.text
    return r.json()


def _end(token):
    return requests.post(f"{_BASE}/api/auth/impersonation/end", headers=_h(token), timeout=30)


def setup_module():
    for t in (TENANT, OTHER):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Imp {t}", "id": t}, headers=sa(), timeout=30).status_code == 200
    _S["admin"] = _create_user(TENANT, ADMIN[0], "admin")
    _S["other_admin"] = _create_user(OTHER, OTHER_ADMIN, "admin")
    h = _login(ADMIN)
    for key, plate in (("v1", "V1"), ("v2", "V2")):
        r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"{plate} {_RUN[:5].upper()}", "marque": "VW", "modele": "ID.3"}, headers=h, timeout=30)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    r = requests.post(f"{_BASE}/api/drivers", json={"nom": "Rochat", "prenom": "Marc"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    _S["driver_id"] = r.json()["id"]
    _S["manager"] = _create_user(TENANT, MANAGER, "manager", vehicle_scope=[_S["v1"]])
    _S["driver"] = _create_user(TENANT, DRIVER, "driver", driver_id=_S["driver_id"])
    _S["ro"] = _create_user(TENANT, RO, "read_only")
    _S["inactive"] = _create_user(TENANT, INACTIVE, "admin")
    assert requests.put(f"{_BASE}/api/admin/users/{_S['inactive']['id']}", json={"disabled": True}, headers=sa(), timeout=30).status_code == 200


def teardown_module():
    db = _mongo()
    for t in (TENANT, OTHER):
        for coll in ("users", "vehicles", "documents", "drivers", "driver_assignments", "audit_logs", "alerts",
                     "vehicle_field_meta", "tenant_integrations", "tenant_settings", "impersonation_sessions"):
            db[coll].delete_many({"tenant_id": t})
        db.tenants.delete_many({"id": t})


class TestAdminTarget:
    def test_superadmin_to_client_admin(self):
        data = _impersonate(_S["admin"]["id"])
        assert data["user"]["role"] == "admin" and data["user"]["impersonation"]["by"] == _ENV["SUPERADMIN_EMAIL"]
        tok = data["token"]
        me = requests.get(f"{_BASE}/api/auth/me", headers=_h(tok), timeout=30).json()
        assert me["email"] == ADMIN[0] and me["role"] == "admin" and me["tenant_id"] == TENANT
        assert me["impersonation"]["session_id"] == data["session_id"]
        assert "_impersonator" not in me
        plates = {v["id"] for v in requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30).json()}
        assert plates == {_S["v1"], _S["v2"]}
        # Jamais les droits superadmin dans les endpoints : console interdite, mot de passe intouchable
        assert requests.get(f"{_BASE}/api/admin/overview", headers=_h(tok), timeout=30).status_code == 403
        r = requests.post(f"{_BASE}/api/auth/change-password", json={"current_password": "x", "new_password": "Nouveau-123456"}, headers=_h(tok), timeout=30)
        assert r.status_code == 403
        _S["admin_tok"] = tok

    def test_business_audit_carries_impersonated_by(self):
        tok = _S["admin_tok"]
        r = requests.patch(f"{_BASE}/api/drivers/{_S['driver_id']}", json={"notes": "Modifié en mode assistance"}, headers=_h(tok), timeout=30)
        assert r.status_code == 200, r.text
        row = _mongo().audit_logs.find_one({"tenant_id": TENANT, "entity": "driver", "entity_id": _S["driver_id"], "action": "modify"}, {"_id": 0})
        assert row and row["user"] == ADMIN[0] and row["impersonated_by"] == _ENV["SUPERADMIN_EMAIL"]
        assert row["impersonation_session_id"]

    def test_exit_restores_superadmin_and_revokes_token(self):
        tok = _S["admin_tok"]
        r = _end(tok)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30).status_code == 401
        assert requests.get(f"{_BASE}/api/admin/overview", headers=sa(), timeout=30).status_code == 200
        # Le vrai compte client n'a pas été révoqué (token_version inchangé) : il peut toujours se connecter
        assert requests.get(f"{_BASE}/api/vehicles", headers=_login(ADMIN), timeout=30).status_code == 200


class TestManagerTarget:
    def test_manager_sees_only_vehicle_scope(self):
        tok = _impersonate(_S["manager"]["id"])["token"]
        me = requests.get(f"{_BASE}/api/auth/me", headers=_h(tok), timeout=30).json()
        assert me["role"] == "manager" and me["vehicle_scope"] == [_S["v1"]]
        ids = {v["id"] for v in requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30).json()}
        assert ids == {_S["v1"]}
        assert requests.get(f"{_BASE}/api/vehicles/{_S['v1']}", headers=_h(tok), timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/vehicles/{_S['v2']}", headers=_h(tok), timeout=30).status_code == 404, "véhicule hors scope invisible (fail-closed)"
        assert requests.delete(f"{_BASE}/api/vehicles/{_S['v1']}", headers=_h(tok), timeout=30).status_code == 403
        assert _end(tok).status_code == 200


class TestDriverTarget:
    def test_driver_limited_to_self_scope(self):
        tok = _impersonate(_S["driver"]["id"])["token"]
        me = requests.get(f"{_BASE}/api/auth/me", headers=_h(tok), timeout=30).json()
        assert me["role"] == "driver" and me["driver_id"] == _S["driver_id"]
        assert requests.get(f"{_BASE}/api/me/profile", headers=_h(tok), timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/me/vehicles", headers=_h(tok), timeout=30).status_code == 200
        r = requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "DRIVER_FORBIDDEN"
        assert requests.get(f"{_BASE}/api/documents", headers=_h(tok), timeout=30).status_code == 403
        assert _end(tok).status_code == 200


class TestReadOnlyTarget:
    def test_read_only_mutations_403(self):
        tok = _impersonate(_S["ro"]["id"])["token"]
        assert requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30).status_code == 200
        r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": "RO 1"}, headers=_h(tok), timeout=30)
        assert r.status_code == 403
        r = requests.put(f"{_BASE}/api/vehicles/{_S['v1']}", json={"marque": "X"}, headers=_h(tok), timeout=30)
        assert r.status_code == 403
        assert _end(tok).status_code == 200


class TestModulesAndGuards:
    def test_module_off_stays_off_during_impersonation(self):
        assert requests.put(f"{_BASE}/api/admin/tenants/{TENANT}", json={"modules": {"fines": False}}, headers=sa(), timeout=30).status_code == 200
        tok = _impersonate(_S["admin"]["id"])["token"]
        r = requests.get(f"{_BASE}/api/fines", headers=_h(tok), timeout=30)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "MODULE_DISABLED"
        me = requests.get(f"{_BASE}/api/auth/me", headers=_h(tok), timeout=30).json()
        assert me["tenant_modules"]["fines"] is False
        assert _end(tok).status_code == 200
        assert requests.put(f"{_BASE}/api/admin/tenants/{TENANT}", json={"modules": {"fines": True}}, headers=sa(), timeout=30).status_code == 200

    def test_other_tenant_user_impossible(self):
        _impersonate(_S["other_admin"]["id"], tenant=TENANT, expect=404)

    def test_inactive_user_impossible(self):
        _impersonate(_S["inactive"]["id"], expect=409)

    def test_unknown_tenant_404(self):
        _impersonate(_S["admin"]["id"], tenant=f"nope-{_RUN}", expect=404)

    def test_client_admin_cannot_impersonate(self):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/impersonate", json={"user_id": _S["ro"]["id"]}, headers=_login(ADMIN), timeout=30)
        assert r.status_code == 403

    def test_logout_while_impersonating_does_not_revoke_client(self):
        before = _mongo().users.find_one({"id": _S["ro"]["id"]}, {"_id": 0, "token_version": 1}).get("token_version", 0)
        tok = _impersonate(_S["ro"]["id"])["token"]
        assert requests.post(f"{_BASE}/api/auth/logout", headers=_h(tok), timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/vehicles", headers=_h(tok), timeout=30).status_code == 401
        after = _mongo().users.find_one({"id": _S["ro"]["id"]}, {"_id": 0, "token_version": 1}).get("token_version", 0)
        assert before == after

    def test_end_without_session_400(self):
        assert _end(_login(ADMIN)["Authorization"][7:]).status_code == 400


class TestAudit:
    def test_start_and_end_audited(self):
        db = _mongo()
        data = _impersonate(_S["manager"]["id"])
        sid = data["session_id"]
        start = db.audit_logs.find_one({"action": "impersonation_start", "session_id": sid}, {"_id": 0})
        assert start and start["tenant_id"] == TENANT and start["target_user_id"] == _S["manager"]["id"]
        assert start["target_role"] == "manager" and start["superadmin_id"] and start["created_at"]
        assert start["user"] == _ENV["SUPERADMIN_EMAIL"]
        assert _end(data["token"]).status_code == 200
        end = db.audit_logs.find_one({"action": "impersonation_end", "session_id": sid}, {"_id": 0})
        assert end and end["tenant_id"] == TENANT and end["target_user_id"] == _S["manager"]["id"]
        assert end["superadmin_id"] == start["superadmin_id"] and end["target_role"] == "manager"
        assert isinstance(end["duration_s"], int) and end["duration_s"] >= 0
        sess = db.impersonation_sessions.find_one({"id": sid}, {"_id": 0})
        assert sess["ended_at"] and sess["duration_s"] == end["duration_s"]
        # Fin répétée : idempotente côté session (jeton déjà révoqué → 401)
        assert _end(data["token"]).status_code == 401
