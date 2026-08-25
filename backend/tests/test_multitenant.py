"""Tests d'isolation multi-tenant et de généricité du socle véhicule canonique.

Les tenants de test (test-b, test-c, test-vol) sont créés/supprimés par la suite.
Aucune assertion sur un nombre de véhicules du compte pilote (jamais `== 12`).
"""
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_be = dotenv_values(Path(BACKEND_DIR, ".env"))
_db = MongoClient(_be["MONGO_URL"])[_be["DB_NAME"]]

TEST_TENANTS = ["test-b", "test-c", "test-vol"]
TEST_PASSWORD = "TenantTest-2026!"


def _seed_user(tenant_id: str) -> str:
    import auth as auth_mod
    email = f"user-{tenant_id}@test.logitrak.ch"
    _db.users.update_one({"email": email}, {"$set": {
        "id": str(uuid.uuid4()), "email": email, "name": f"User {tenant_id}",
        "role": "superadmin", "tenant_id": tenant_id,
        "password_hash": auth_mod.hash_password(TEST_PASSWORD),
        "password_changed_in_app": False}}, upsert=True)
    return email


def _login(email: str) -> dict:
    import requests as real_requests
    r = real_requests.post(f"{API}/auth/login",
                           json={"email": email, "password": TEST_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def tenants():
    headers = {t: _login(_seed_user(t)) for t in TEST_TENANTS}
    yield headers
    _db.users.delete_many({"email": {"$regex": "@test.logitrak.ch$"}})
    for coll in ("vehicles", "documents", "alerts", "vehicle_field_meta",
                 "audit_logs", "fuel_snapshots", "tenant_integrations", "login_attempts"):
        _db[coll].delete_many({"tenant_id": {"$in": TEST_TENANTS}})
    _db.login_attempts.delete_many({})


import requests as plain_requests  # non patché par conftest (headers explicites)


def _mk(headers, payload):
    r = plain_requests.post(f"{API}/vehicles", json=payload, headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["id"]


class TestTenantIsolation:
    def test_tenant_b_starts_empty_then_isolated(self, tenants):
        hb, ha_list = tenants["test-b"], None
        r = plain_requests.get(f"{API}/vehicles", headers=hb, timeout=20)
        assert r.status_code == 200 and r.json() == []
        vid_b = _mk(hb, {"plaque": "TB 11111", "marque": "TenantB"})
        # Tenant A (pilote, via conftest token) ne voit PAS le véhicule de B
        ra = requests.get(f"{API}/vehicles")
        assert all(v["id"] != vid_b for v in ra.json())
        # accès direct cross-tenant → 404 (lecture, écriture, suppression, core, docs, meta, history)
        for method, url in [("get", f"{API}/vehicles/{vid_b}"),
                            ("get", f"{API}/vehicles/{vid_b}/core"),
                            ("get", f"{API}/vehicles/{vid_b}/documents"),
                            ("get", f"{API}/vehicles/{vid_b}/field-meta"),
                            ("get", f"{API}/vehicles/{vid_b}/history")]:
            assert getattr(requests, method)(url).status_code == 404, url
        assert requests.put(f"{API}/vehicles/{vid_b}", json={"marque": "Hack"}).status_code == 404
        assert requests.delete(f"{API}/vehicles/{vid_b}").status_code == 404
        # et B voit toujours son véhicule intact
        rb = plain_requests.get(f"{API}/vehicles/{vid_b}", headers=hb, timeout=20)
        assert rb.status_code == 200 and rb.json()["marque"] == "TenantB"

    def test_resolver_never_crosses_tenants(self, tenants):
        hb = tenants["test-b"]
        _mk(hb, {"plaque": "TB 22222"})
        # Le pilote (tenant default) ne résout PAS la plaque du tenant B
        r = requests.get(f"{API}/vehicles/resolve", params={"plate": "TB 22222"}).json()
        assert r["status"] == "not_found"
        # B la résout chez lui
        rb = plain_requests.get(f"{API}/vehicles/resolve", params={"plate": "tb22222"},
                                headers=hb, timeout=20).json()
        assert rb["status"] == "found"

    def test_pilot_vehicles_not_visible_from_tenant_b(self, tenants):
        hb = tenants["test-b"]
        pilot = requests.get(f"{API}/vehicles").json()
        if not pilot:
            pytest.skip("aucun véhicule pilote")
        r = plain_requests.get(f"{API}/vehicles/{pilot[0]['id']}", headers=hb, timeout=20)
        assert r.status_code == 404


class TestTenantWithoutTelematics:
    def test_tenant_c_documents_and_dashboard_work_without_navixy(self, tenants):
        hc = tenants["test-c"]
        vid = _mk(hc, {"plaque": "TC 11111", "marque": "TenantC", "modele": "SansNavixy"})
        assert plain_requests.get(f"{API}/dashboard", headers=hc, timeout=20).status_code == 200
        assert plain_requests.get(f"{API}/timeline", headers=hc, timeout=20).status_code == 200
        assert plain_requests.get(f"{API}/vehicles/{vid}/core", headers=hc, timeout=20).status_code == 200
        st = plain_requests.get(f"{API}/navixy/status", headers=hc, timeout=20).json()
        assert st == {"connected": False, "configured": False}
        sync = plain_requests.post(f"{API}/navixy/sync", headers=hc, timeout=20)
        assert sync.status_code == 503
        integ = plain_requests.get(f"{API}/fleet/integrity", headers=hc, timeout=30).json()
        assert integ["navixy_status"] == "not_configured"
        entry = next(e for e in integ["vehicles"] if e["vehicle_id"] == vid)
        assert entry["link_status"] == "INTEGRATION_ABSENTE"
        sugg = plain_requests.get(f"{API}/integrations/navixy/link-suggestions", headers=hc, timeout=20)
        assert sugg.status_code == 503

    def test_link_and_create_are_tenant_guarded(self, tenants):
        hc = tenants["test-c"]
        pilot = requests.get(f"{API}/vehicles").json()
        linked = [v for v in pilot if v.get("navixy_vehicle_id")]
        if not linked:
            pytest.skip("aucun véhicule pilote lié")
        # Injection d'un vehicle_id d'un AUTRE tenant → 404, jamais d'action
        r = plain_requests.post(f"{API}/integrations/navixy/link", headers=hc, timeout=20,
                                json={"vehicle_id": linked[0]["id"],
                                      "external_vehicle_id": linked[0]["navixy_vehicle_id"]})
        assert r.status_code == 404
        r2 = plain_requests.post(f"{API}/integrations/navixy/create-vehicle", headers=hc, timeout=20,
                                 json={"vehicle_id": linked[0]["id"], "confirm": False})
        assert r2.status_code == 404


class TestGenericStatuses:
    def test_integrity_statuses_on_pilot(self):
        body = requests.get(f"{API}/fleet/integrity").json()
        assert body["navixy_status"] in ("ok",) or body["navixy_status"].startswith("error")
        assert body["total"] >= 1
        for e in body["vehicles"]:
            assert e["link_status"] in ("LIE", "NON_LIE", "ERREUR_INTEGRATION", "INTEGRATION_ABSENTE")
            if e["link_status"] == "LIE":
                assert e["fields"]["departement"]["status"] == "NON_SUPPORTE"

    def test_integrity_filters(self):
        only_vin = requests.get(f"{API}/fleet/integrity", params={"field": "vin"}).json()
        for e in only_vin["vehicles"]:
            if e.get("fields"):
                assert set(e["fields"].keys()) <= {"vin"}
        non_lies = requests.get(f"{API}/fleet/integrity", params={"status": "NON_LIE"}).json()
        assert all(e["link_status"] == "NON_LIE" for e in non_lies["vehicles"])
        bad = requests.get(f"{API}/fleet/integrity", params={"provider": "autre"})
        assert bad.status_code == 422

    def test_vin_check_generic_no_autocorrection(self, tenants):
        hb = tenants["test-b"]
        vid = _mk(hb, {"plaque": "TB 33333", "vin": "ABC123"})
        v = plain_requests.get(f"{API}/vehicles/{vid}", headers=hb, timeout=20).json()
        assert v["vin_check"]["status"] == "a_verifier"
        assert any("longueur" in m for m in v["vin_check"]["motifs"])
        assert v["vin"] == "ABC123"  # jamais corrigé automatiquement
        vid2 = _mk(hb, {"plaque": "TB 44444", "vin": "WVWZZZ1KZAW000001"})
        v2 = plain_requests.get(f"{API}/vehicles/{vid2}", headers=hb, timeout=20).json()
        assert v2["vin_check"]["status"] == "ok"

    def test_demo_data_forbidden_in_production(self):
        r = requests.post(f"{API}/demo/fill-admin")
        assert r.status_code == 403


class TestVolume:
    def test_no_assumption_on_fleet_size(self, tenants):
        hv = tenants["test-vol"]
        docs = [{"id": str(uuid.uuid4()), "tenant_id": "test-vol", "plaque": f"TV {i:05d}",
                 "marque": "Volume", "modele": str(i), "vin": "", "source": "manual",
                 "carte_grise": {}, "leasing": {}, "assurance": {}, "controle_technique": {}}
                for i in range(300)]
        _db.vehicles.insert_many(docs)
        r = plain_requests.get(f"{API}/vehicles", headers=hv, timeout=60)
        assert r.status_code == 200 and len(r.json()) == 300
        res = plain_requests.get(f"{API}/vehicles/resolve", params={"plate": "TV 00042"},
                                 headers=hv, timeout=20).json()
        assert res["status"] == "found"
        integ = plain_requests.get(f"{API}/fleet/integrity", headers=hv, timeout=60).json()
        assert integ["total"] == 300
        dash = plain_requests.get(f"{API}/dashboard", headers=hv, timeout=60)
        assert dash.status_code == 200
