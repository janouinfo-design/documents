"""SSO Navixy (session_key) — échange fail-closed, mapping master→tenant, provisioning read_only.
In-process (ASGITransport) avec navixy_get_user_info/navixy_master_of monkeypatchés :
AUCUNE session_key réelle, aucun appel réseau Navixy."""
import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import server as server_mod  # noqa: E402

_RUN = uuid.uuid4().hex[:8]
TENANT_ID = f"pytest-sso-{_RUN}"
MASTER_ID = 800000 + int(_RUN[:4], 16) % 90000
NAV_USER_ID = 900000 + int(_RUN[4:], 16) % 90000
SSO_EMAIL = f"sso-{_RUN}@hubclient.ch"
FAKE_KEY = f"fake-session-{_RUN}-abcdef123456"


def _nav_ok(user_id=None, master_id=None, email=None):
    def fake(_key):
        return {"success": True,
                "user_info": {"id": user_id or NAV_USER_ID, "login": email or SSO_EMAIL,
                              "first_name": "Hub", "last_name": "User"},
                "master": {"id": master_id or MASTER_ID}}
    return fake


@pytest_asyncio.fixture
async def aclient():
    from motor.motor_asyncio import AsyncIOMotorClient
    server_mod.client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    server_mod.db = server_mod.client[os.environ["DB_NAME"]]
    await server_mod.db.tenants.update_one(
        {"id": TENANT_ID},
        {"$setOnInsert": {"id": TENANT_ID, "name": f"SSO Test {_RUN}", "disabled": False,
                          "modules": {"documents": True}, "created_at": "2026-01-01T00:00:00+00:00"}},
        upsert=True)
    await server_mod.db.tenant_integrations.update_one(
        {"tenant_id": TENANT_ID, "provider": "navixy"},
        {"$set": {"api_hash": f"pytest-hash-{_RUN}", "enabled": False,
                  "master_user_id": MASTER_ID}},
        upsert=True)
    transport = ASGITransport(app=server_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    await server_mod.db.users.delete_many({"tenant_id": TENANT_ID})
    await server_mod.db.tenant_integrations.delete_many({"tenant_id": TENANT_ID})
    await server_mod.db.tenants.delete_many({"id": TENANT_ID})


async def _exchange(ac, key=FAKE_KEY):
    return await ac.post("/api/auth/navixy/exchange", json={"session_key": key})


@pytest.mark.asyncio
class TestFailClosed:
    async def test_missing_field_422(self, aclient):
        r = await aclient.post("/api/auth/navixy/exchange", json={})
        assert r.status_code == 422

    async def test_empty_or_short_key_401(self, aclient):
        for bad in ("", "   ", "short"):
            r = await _exchange(aclient, bad)
            assert r.status_code == 401

    async def test_invalid_session_401(self, aclient, monkeypatch):
        def boom(_k):
            raise server_mod.NavixyError("invalid_session")
        monkeypatch.setattr(server_mod, "navixy_get_user_info", boom)
        r = await _exchange(aclient)
        assert r.status_code == 401
        assert "expirée ou invalide" in r.json()["detail"]

    async def test_navixy_network_error_503_no_login(self, aclient, monkeypatch):
        def boom(_k):
            raise server_mod.NavixyError("network")
        monkeypatch.setattr(server_mod, "navixy_get_user_info", boom)
        r = await _exchange(aclient)
        assert r.status_code == 503
        assert "token" not in r.json()

    async def test_unmapped_master_403_no_default_fallback(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info",
                            _nav_ok(master_id=1, user_id=2, email=f"x-{_RUN}@nowhere.ch"))
        monkeypatch.setattr(server_mod, "navixy_master_of", lambda *a, **k: None)
        r = await _exchange(aclient)
        assert r.status_code == 403
        assert await server_mod.db.users.find_one({"email": f"x-{_RUN}@nowhere.ch"}) is None

    async def test_tenant_disabled_401(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        await server_mod.db.tenants.update_one({"id": TENANT_ID}, {"$set": {"disabled": True}})
        r = await _exchange(aclient)
        await server_mod.db.tenants.update_one({"id": TENANT_ID}, {"$set": {"disabled": False}})
        assert r.status_code == 401

    async def test_module_documents_disabled_403(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        await server_mod.db.tenants.update_one(
            {"id": TENANT_ID}, {"$set": {"modules": {"documents": False}}})
        r = await _exchange(aclient)
        await server_mod.db.tenants.update_one(
            {"id": TENANT_ID}, {"$set": {"modules": {"documents": True}}})
        assert r.status_code == 403


@pytest.mark.asyncio
class TestProvisioningAndRbac:
    async def test_valid_session_provisions_read_only_once(self, aclient, monkeypatch, caplog):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        r1 = await _exchange(aclient)
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["user"]["role"] == "read_only"
        assert body["user"]["tenant_id"] == TENANT_ID
        assert body["expires_in"] <= 3600
        r2 = await _exchange(aclient)
        assert r2.status_code == 200
        assert r2.json()["user"]["id"] == body["user"]["id"]
        assert await server_mod.db.users.count_documents({"email": SSO_EMAIL}) == 1
        assert FAKE_KEY not in caplog.text

    async def test_sso_token_reads_ok_writes_403_cross_tenant_404(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        token = (await _exchange(aclient)).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        me = await aclient.get("/api/auth/me", headers=h)
        assert me.status_code == 200 and me.json()["role"] == "read_only"
        lst = await aclient.get("/api/vehicles", headers=h)
        assert lst.status_code == 200 and lst.json() == []
        w = await aclient.post("/api/vehicles", json={"plaque": "SSO 1"}, headers=h)
        assert w.status_code == 403
        other = await server_mod.db.vehicles.find_one({"tenant_id": "default"}, {"id": 1})
        if other:
            x = await aclient.get(f"/api/vehicles/{other['id']}", headers=h)
            assert x.status_code == 404

    async def test_sso_user_has_no_password_login(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        await _exchange(aclient)
        r = await aclient.post("/api/auth/login",
                               json={"email": SSO_EMAIL, "password": "anything123"})
        assert r.status_code in (401, 429)

    async def test_disabled_sso_user_refused(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "navixy_get_user_info", _nav_ok())
        await _exchange(aclient)
        await server_mod.db.users.update_one({"email": SSO_EMAIL}, {"$set": {"disabled": True}})
        r = await _exchange(aclient)
        await server_mod.db.users.update_one({"email": SSO_EMAIL}, {"$set": {"disabled": False}})
        assert r.status_code == 401

    async def test_email_collision_other_tenant_403(self, aclient, monkeypatch):
        from dotenv import dotenv_values
        admin_email = (dotenv_values(os.path.join(BACKEND_DIR, ".env")).get("ADMIN_EMAIL")
                       or "admin@logitrak.ch").strip().lower()
        monkeypatch.setattr(server_mod, "navixy_get_user_info",
                            _nav_ok(user_id=NAV_USER_ID + 1, email=admin_email))
        r = await _exchange(aclient)
        assert r.status_code == 403
        u = await server_mod.db.users.find_one({"email": admin_email.lower()})
        assert u and u.get("tenant_id") == "default" and "navixy_user_id" not in u
