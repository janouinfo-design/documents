"""Capacité réservoir — suggestion IA (donnée constructeur) + validation humaine.
Aucune écriture sans validation, provenance tracée, RBAC read_only, tenant scope."""
import uuid

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
_S = {}
_cache = {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(email, password):
    key = (email, password)
    if key not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        assert r.status_code == 200, f"login {email} -> {r.status_code}"
        _cache[key] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[key]


def adm():
    return _h(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"])


def ro():
    return _h("ro-e2e@client-test.ch", "RoTest-2026y")


def setup_module():
    r = requests.post(f"{_BASE}/api/vehicles", headers=adm(), timeout=30,
                      json={"plaque": f"XX {_RUN[:6].upper()}", "marque": "VW", "modele": "Polo 1.2",
                            "vin": "", "cylindree_cm3": 1198, "puissance_kw": 51,
                            "type_carburant": "Essence"})
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]
    # Véhicule du tenant read_only (client-test-e2e) pour cross-tenant + RBAC
    vb = _mongo().vehicles.find_one({"tenant_id": "client-test-e2e"}, {"_id": 0, "id": 1})
    _S["veh_ro"] = vb["id"] if vb else None


def teardown_module():
    db = _mongo()
    db.vehicles.delete_many({"id": _S.get("veh", "n/a")})
    db.vehicle_field_meta.delete_many({"vehicle_id": _S.get("veh", "n/a")})
    db.audit_logs.delete_many({"vehicle_id": _S.get("veh", "n/a")})


class TestRbacEtTenant:
    def test_read_only_suggest_403(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/reservoir/suggest", headers=ro(), timeout=30)
        assert r.status_code == 403

    def test_read_only_apply_403(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/reservoir/apply",
                          json={"value_l": 45}, headers=ro(), timeout=30)
        assert r.status_code == 403

    def test_cross_tenant_404(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/reservoir/suggest", headers=adm(), timeout=30)
        assert r.status_code == 404
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/reservoir/apply",
                          json={"value_l": 45}, headers=adm(), timeout=30)
        assert r.status_code == 404


class TestApply:
    def test_bornes_invalides_422(self):
        for bad in (5, 900, 0):
            r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/reservoir/apply",
                              json={"value_l": bad}, headers=adm(), timeout=30)
            assert r.status_code == 422, f"{bad} -> {r.status_code}"

    def test_apply_ecrit_et_trace(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/reservoir/apply",
                          json={"value_l": 45}, headers=adm(), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["vehicle"]["capacite_reservoir_l"] == 45
        # La validation déclenche la sync Navixy (best effort) : véhicule de test non lié
        # => statut honnête « not_linked », AUCUNE écriture Navixy, sauvegarde locale intacte
        push = r.json().get("navixy_push")
        assert push is not None, "apply doit renvoyer le résultat de la sync Navixy"
        assert push["status"] in ("not_linked", "integration_absente")
        # Persistence DB
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=adm(), timeout=30).json()
        assert v["capacite_reservoir_l"] == 45
        # Provenance tracée
        meta = _mongo().vehicle_field_meta.find_one(
            {"vehicle_id": _S["veh"], "field": "capacite_reservoir_l"}, {"_id": 0})
        assert meta and meta["source"] == "estimation_ia" and meta["validated_by"] == "utilisateur"
        log = _mongo().audit_logs.find_one(
            {"vehicle_id": _S["veh"], "detail": {"$regex": "Capacité réservoir"}}, {"_id": 0})
        assert log is not None and log["user"]


class TestSuggestionReelle:
    def test_suggestion_vw_polo_plausible(self):
        """Appel LLM réel — la VW Polo 1.2 (6R) a un réservoir constructeur de 45 L."""
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/reservoir/suggest",
                          headers=adm(), timeout=120)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["source"] == "ESTIMATION_IA"
        assert 35 <= s["value_l"] <= 60, f"valeur implausible: {s['value_l']}"
        assert s.get("rationale")
        # Aucune écriture sans validation : la valeur véhicule reste celle appliquée avant (45)
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=adm(), timeout=30).json()
        assert v["capacite_reservoir_l"] == 45

    def test_vehicule_sans_marque_422(self):
        r = requests.post(f"{_BASE}/api/vehicles", headers=adm(), timeout=30,
                          json={"plaque": f"XY {_RUN[:6].upper()}"})
        vid = r.json()["id"]
        try:
            r = requests.post(f"{_BASE}/api/vehicles/{vid}/reservoir/suggest", headers=adm(), timeout=30)
            assert r.status_code == 422
        finally:
            _mongo().vehicles.delete_many({"id": vid})
