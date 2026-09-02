"""CO₂ officiel — base ASTRA/OFROU d'abord, estimation IA en dernier recours.
Aucune écriture sans validation, provenance tracée, norme (est.) pour l'IA, RBAC, tenant scope."""
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
    # Sans homologation ni VIN => ASTRA introuvable garanti => fallback IA déterministe
    r = requests.post(f"{_BASE}/api/vehicles", headers=adm(), timeout=30,
                      json={"plaque": f"CB {_RUN[:6].upper()}", "marque": "VW", "modele": "Polo 1.2",
                            "cylindree_cm3": 1198, "puissance_kw": 51, "type_carburant": "Essence"})
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]
    vb = _mongo().vehicles.find_one({"tenant_id": "client-test-e2e"}, {"_id": 0, "id": 1})
    _S["veh_ro"] = vb["id"] if vb else None


def teardown_module():
    db = _mongo()
    db.vehicles.delete_many({"id": _S.get("veh", "n/a")})
    db.vehicle_field_meta.delete_many({"vehicle_id": _S.get("veh", "n/a")})
    db.audit_logs.delete_many({"vehicle_id": _S.get("veh", "n/a")})


class TestRbacEtTenant:
    def test_read_only_403(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        for path in ("co2/suggest", "co2/apply"):
            r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/{path}",
                              json={"value_g_km": 120}, headers=ro(), timeout=30)
            assert r.status_code == 403, f"{path} -> {r.status_code}"

    def test_cross_tenant_404(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_ro']}/co2/apply",
                          json={"value_g_km": 120}, headers=adm(), timeout=30)
        assert r.status_code == 404


class TestApply:
    def test_bornes_invalides_422(self):
        for bad in (-5, 900):
            r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/co2/apply",
                              json={"value_g_km": bad}, headers=adm(), timeout=30)
            assert r.status_code == 422, f"{bad} -> {r.status_code}"

    def test_apply_ia_ecrit_norme_est_et_trace(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/co2/apply",
                          json={"value_g_km": 128, "norme": "NEDC", "source": "ESTIMATION_IA"},
                          headers=adm(), timeout=30)
        assert r.status_code == 200, r.text
        v = r.json()["vehicle"]
        assert v["co2_g_km"] == 128
        assert v["co2_norme"] == "NEDC (est.)"  # estimation clairement marquée
        meta = _mongo().vehicle_field_meta.find_one(
            {"vehicle_id": _S["veh"], "field": "co2_g_km"}, {"_id": 0})
        assert meta and meta["source"] == "estimation_ia" and meta["validated_by"] == "utilisateur"
        log = _mongo().audit_logs.find_one(
            {"vehicle_id": _S["veh"], "detail": {"$regex": "CO₂ officiel"}}, {"_id": 0})
        assert log is not None and "estimation IA" in log["detail"]

    def test_apply_astra_norme_sans_est(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/co2/apply",
                          json={"value_g_km": 125, "norme": "WLTP", "source": "ASTRA_OFROU",
                                "matched_by": "homologation", "retrieved_at": "2026-09-02"},
                          headers=adm(), timeout=30)
        assert r.status_code == 200, r.text
        v = r.json()["vehicle"]
        assert v["co2_norme"] == "WLTP"  # donnée officielle, pas de (est.)
        meta = _mongo().vehicle_field_meta.find_one(
            {"vehicle_id": _S["veh"], "field": "co2_g_km"}, {"_id": 0})
        assert meta["source"] == "external_vehicle_database" and meta["provider"] == "astra_tas"

    def test_zero_valide_electrique(self):
        """0 g/km est une valeur officielle légitime (véhicule électrique)."""
        r = requests.post(f"{_BASE}/api/vehicles", headers=adm(), timeout=30,
                          json={"plaque": f"CZ {_RUN[:6].upper()}", "marque": "Renault",
                                "modele": "Zoe", "type_carburant": "Électrique"})
        vid = r.json()["id"]
        try:
            r = requests.post(f"{_BASE}/api/vehicles/{vid}/co2/apply",
                              json={"value_g_km": 0, "norme": "WLTP", "source": "ESTIMATION_IA"},
                              headers=adm(), timeout=30)
            assert r.status_code == 200, r.text
            assert r.json()["vehicle"]["co2_g_km"] == 0
        finally:
            _mongo().vehicles.delete_many({"id": vid})
            _mongo().vehicle_field_meta.delete_many({"vehicle_id": vid})
            _mongo().audit_logs.delete_many({"vehicle_id": vid})


class TestSuggestionReelle:
    def test_fallback_ia_vw_polo_plausible(self):
        """Véhicule sans homologation/VIN => ASTRA introuvable => IA. VW Polo 1.2 essence ≈ 105–135 g/km."""
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/co2/suggest",
                          headers=adm(), timeout=120)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["source"] == "ESTIMATION_IA"
        assert 80 <= s["value_g_km"] <= 200, f"valeur implausible: {s['value_g_km']}"
        assert s.get("norme") in ("WLTP", "NEDC", None)
        assert s.get("rationale")
        # Aucune écriture sans validation : valeur inchangée (125 appliquée précédemment)
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=adm(), timeout=30).json()
        assert v["co2_g_km"] == 125

    def test_vehicule_sans_marque_422(self):
        r = requests.post(f"{_BASE}/api/vehicles", headers=adm(), timeout=30,
                          json={"plaque": f"CY {_RUN[:6].upper()}"})
        vid = r.json()["id"]
        try:
            r = requests.post(f"{_BASE}/api/vehicles/{vid}/co2/suggest", headers=adm(), timeout=30)
            assert r.status_code == 422
        finally:
            _mongo().vehicles.delete_many({"id": vid})
