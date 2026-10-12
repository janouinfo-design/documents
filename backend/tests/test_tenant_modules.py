"""Modules par client (console Super Admin) — ON → OFF → ON sans perte de données, 403 MODULE_DISABLED,
échéances/alertes filtrées, mode assistance superadmin, audit structuré."""
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-mod-{_RUN}"
ADMIN = (f"mod-adm-{_RUN}@pytest.ch", f"ModAdm-{_RUN}-1")
AMENDE = {"autorite": "Police cantonale vaudoise", "numero_amende": f"VD-{_RUN}-01", "date_infraction": "2026-06-01",
          "montant": 120.0, "devise": "CHF", "delai_paiement": "2026-06-10", "motif": "Amende test modules"}
ALL = ("vehicles", "documents", "deadlines", "costs", "energy", "drivers", "fines", "ai", "alerts", "integrity")
_S, _cache = {}, {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds=ADMIN):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _get(path, creds=ADMIN, headers=None):
    return requests.get(f"{_BASE}/api{path}", headers={**_h(creds), **(headers or {})}, timeout=30)


def _set(modules):
    r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT}", json={"modules": modules}, headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def setup_module():
    assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Modules {_RUN}", "id": TENANT}, headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users", json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                         headers=sa(), timeout=30).status_code == 200
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD {_RUN[:6].upper()}", "marque": "VW", "modele": "Caddy"},
                      headers=_h(), timeout=30)
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]
    r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/fines", json=AMENDE, headers=_h(), timeout=30)
    assert r.status_code == 200, r.text
    _S["fine_doc"] = r.json().get("id") or r.json().get("document_id")


def teardown_module():
    db = _mongo()
    for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta",
                 "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings", "fuel_transactions"):
        db[coll].delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


def _fingerprint():
    db = _mongo()
    return {c: db[c].count_documents({"tenant_id": TENANT}) for c in ("vehicles", "documents", "users")}


class TestDefaults:
    def test_new_tenant_all_modules_on(self):
        ov = _get("/admin/overview", creds=(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])).json()
        t = next(x for x in ov["tenants"] if x["id"] == TENANT)
        assert t["modules"] == {k: True for k in ALL}
        assert [m["key"] for m in ov["module_catalog"]] == list(ALL)

    def test_legacy_tenant_without_modules_key_is_fully_enabled(self):
        """Compatibilité : un tenant sans configuration `modules` = tout activé (zéro régression)."""
        _mongo().tenants.update_one({"id": TENANT}, {"$unset": {"modules": ""}})
        me = _get("/auth/me").json()
        assert me["tenant_modules"] == {k: True for k in ALL}
        assert _get("/fines").status_code == 200

    def test_me_exposes_tenant_modules(self):
        me = _get("/auth/me").json()
        assert set(me["tenant_modules"]) == set(ALL)


class TestOnOffOn:
    def test_fines_off_blocks_api_with_code_and_keeps_data(self):
        before = _fingerprint()
        _set({"fines": False})
        r = _get("/fines")
        assert r.status_code == 403
        d = r.json()["detail"]
        assert d["code"] == "MODULE_DISABLED" and d["module"] == "fines"
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/fines", json={**AMENDE, "numero_amende": f"VD-{_RUN}-02"}, headers=_h(), timeout=30)
        assert r.status_code == 403, "création d'amende bloquée par le module"
        # Les autres modules restent accessibles
        assert _get("/vehicles").status_code == 200
        assert _get("/dashboard").status_code == 200
        assert _get("/auth/me").json()["tenant_modules"]["fines"] is False
        # Échéances : l'amende disparaît des échéances / alertes, sans suppression en base
        items = _get("/deadlines").json()["items"]
        assert not any(i.get("is_fine") for i in items)
        assert _fingerprint() == before

    def test_fines_on_again_restores_everything(self):
        before = _fingerprint()
        _set({"fines": True})
        assert _get("/fines").status_code == 200
        assert _get("/auth/me").json()["tenant_modules"]["fines"] is True
        items = _get("/deadlines").json()["items"]
        assert any(i.get("is_fine") and i["vehicle_id"] == _S["veh"] for i in items), "l'amende réapparaît dans les échéances"
        assert _fingerprint() == before

    def test_documents_off_filters_document_deadlines_only(self):
        _set({"documents": False})
        assert _get("/documents").status_code == 403
        assert _get(f"/vehicles/{_S['veh']}/documents").status_code == 403
        assert _get("/vehicles").status_code == 200
        items = _get("/deadlines").json()["items"]
        assert not any(i.get("source") == "document" and not i.get("is_fine") for i in items)
        _set({"documents": True})
        assert _get("/documents").status_code == 200

    def test_vehicles_core_off_blocks_vehicle_subresources(self):
        _set({"vehicles": False})
        assert _get("/vehicles").status_code == 403
        assert _get(f"/vehicles/{_S['veh']}").status_code == 403
        assert _get(f"/vehicles/{_S['veh']}/documents").status_code == 403
        assert _get("/auth/me").status_code == 200
        _set({"vehicles": True})
        assert _get("/vehicles").status_code == 200

    def test_alerts_off_blocks_alerts_api(self):
        _set({"alerts": False})
        assert _get("/alerts").status_code == 403
        assert _get("/alerts/log").status_code == 403
        _set({"alerts": True})
        assert _get("/alerts").status_code == 200

    def test_energy_ai_integrity_off(self):
        _set({"energy": False, "ai": False, "integrity": False, "drivers": False, "costs": False, "deadlines": False})
        for path in ("/fuel-cards", "/fuel/anomalies", "/ai/status", "/fleet/integrity", "/drivers", "/costs", "/deadlines", "/timeline"):
            r = _get(path)
            assert r.status_code == 403, f"{path} -> {r.status_code}"
            assert r.json()["detail"]["code"] == "MODULE_DISABLED"
        assert _get("/dashboard").status_code == 200
        _set({k: True for k in ALL})
        for path in ("/fuel-cards", "/drivers", "/costs", "/deadlines"):
            assert _get(path).status_code == 200, path


class TestSuperadminAssistMode:
    def test_acting_superadmin_respects_disabled_modules(self):
        sa_creds = (_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])
        hdr = {"X-Acting-Tenant": TENANT}
        _set({"fines": False})
        r = _get("/fines", creds=sa_creds, headers=hdr)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "MODULE_DISABLED"
        assert _get("/vehicles", creds=sa_creds, headers=hdr).status_code == 200
        me = _get("/auth/me", creds=sa_creds, headers=hdr).json()
        assert me["acting_tenant"]["id"] == TENANT
        assert me["tenant_modules"]["fines"] is False and me["tenant_modules"]["vehicles"] is True
        _set({"fines": True})
        assert _get("/fines", creds=sa_creds, headers=hdr).status_code == 200

    def test_console_superadmin_me_has_no_tenant_modules(self):
        me = _get("/auth/me", creds=(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])).json()
        assert "tenant_modules" not in me and "acting_tenant" not in me

    def test_client_admin_cannot_toggle_modules(self):
        r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT}", json={"modules": {"fines": False}}, headers=_h(), timeout=30)
        assert r.status_code == 403


class TestAudit:
    def test_each_toggle_is_audited_with_old_new_and_actor(self):
        db = _mongo()
        db.audit_logs.delete_many({"tenant_id": TENANT, "action": "admin_module_toggle"})
        _set({"energy": False})
        _set({"energy": False})  # sans changement → pas d'audit supplémentaire
        _set({"energy": True})
        rows = list(db.audit_logs.find({"tenant_id": TENANT, "action": "admin_module_toggle"}, {"_id": 0}).sort("created_at", 1))
        assert len(rows) == 2
        assert rows[0]["module"] == "energy" and rows[0]["old_value"] is True and rows[0]["new_value"] is False
        assert rows[1]["module"] == "energy" and rows[1]["old_value"] is False and rows[1]["new_value"] is True
        for r in rows:
            assert r["superadmin_id"] and r["user"] == _ENV["SUPERADMIN_EMAIL"] and r["created_at"]
            assert r["entity"] == "tenant_module" and r["entity_id"] == f"{TENANT}:energy"

    def test_invalid_payloads_422(self):
        for body in ({"modules": {}}, {"modules": {"fines": "non"}}, {"modules": {"inconnu": True}}):
            r = requests.put(f"{_BASE}/api/admin/tenants/{TENANT}", json=body, headers=sa(), timeout=30)
            assert r.status_code == 422, body
