"""P0 — Vehicle Core : resolver, DTO /core, garde EV kWh/L, couleur, aucune écriture Navixy."""
import re
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _mk(payload):
    r = requests.post(f"{API}/vehicles", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _rm(vid):
    requests.delete(f"{API}/vehicles/{vid}")


def _fleet():
    r = requests.get(f"{API}/vehicles")
    assert r.status_code == 200
    return r.json()


class TestResolver:
    def test_requires_criterion(self):
        r = requests.get(f"{API}/vehicles/resolve")
        assert r.status_code == 422

    def test_by_vehicle_id(self):
        v = _fleet()[0]
        r = requests.get(f"{API}/vehicles/resolve", params={"vehicle_id": v["id"]}).json()
        assert r["status"] == "found" and r["matched_by"] == "vehicle_id"
        assert r["vehicle"]["vehicle_id"] == v["id"]

    def test_by_tracker_id(self):
        v = next(x for x in _fleet() if x.get("navixy_tracker_id"))
        r = requests.get(f"{API}/vehicles/resolve",
                         params={"navixy_tracker_id": v["navixy_tracker_id"]}).json()
        assert r["status"] == "found" and r["matched_by"] == "navixy_tracker_id"
        assert r["vehicle"]["vehicle_id"] == v["id"]

    def test_by_vin_normalized(self):
        v = next(x for x in _fleet() if (x.get("vin") or "").strip())
        messy = f"  {v['vin'].lower()} "
        r = requests.get(f"{API}/vehicles/resolve", params={"vin": messy}).json()
        assert r["status"] in ("found", "ambiguous")
        if r["status"] == "found":
            assert r["matched_by"] == "vin" and r["vehicle"]["vehicle_id"] == v["id"]

    def test_by_plate_normalized(self):
        v = next(x for x in _fleet() if (x.get("plaque") or "").strip())
        messy = v["plaque"].lower().replace(" ", "")
        r = requests.get(f"{API}/vehicles/resolve", params={"plate": messy}).json()
        assert r["status"] == "found" and r["matched_by"] == "plate"
        assert r["vehicle"]["vehicle_id"] == v["id"]

    def test_not_found_and_no_empty_vin_match(self):
        # VIN inconnu : ne doit matcher AUCUN véhicule (y compris ceux au VIN vide)
        r = requests.get(f"{API}/vehicles/resolve", params={"vin": "ZZZ99UNKNOWN000AA"}).json()
        assert r["status"] == "not_found" and r["searched_by"] == ["vin"]

    def test_ambiguous_explicit(self):
        a = _mk({"plaque": "ZZ 99999", "marque": "TestA"})
        b = _mk({"plaque": "ZZ 99999", "marque": "TestB"})
        try:
            r = requests.get(f"{API}/vehicles/resolve", params={"plate": "zz99999"}).json()
            assert r["status"] == "ambiguous" and r["count"] == 2
            assert {m["vehicle_id"] for m in r["matches"]} == {a, b}
        finally:
            _rm(a)
            _rm(b)

    def test_priority_vehicle_id_over_plate(self):
        real = _fleet()[0]
        tmp = _mk({"plaque": "ZZ 88888"})
        try:
            r = requests.get(f"{API}/vehicles/resolve",
                             params={"vehicle_id": real["id"], "plate": "ZZ 88888"}).json()
            assert r["status"] == "found" and r["matched_by"] == "vehicle_id"
            assert r["vehicle"]["vehicle_id"] == real["id"]
        finally:
            _rm(tmp)

    def test_vehicle_without_vin(self):
        tmp = _mk({"plaque": "ZZ 77771"})
        try:
            r = requests.get(f"{API}/vehicles/resolve", params={"plate": "ZZ 77771"}).json()
            assert r["status"] == "found" and r["vehicle"]["vin"] is None
        finally:
            _rm(tmp)


class TestEvGuard:
    def test_ev_rejects_l_100km(self):
        vid = _mk({"plaque": "ZZ 66666", "type_carburant": "Électrique"})
        try:
            r = requests.put(f"{API}/vehicles/{vid}", json={"conso_officielle_l_100km": 5.5})
            assert r.status_code == 422, r.text
            assert "kWh" in r.json()["detail"]
            r2 = requests.put(f"{API}/vehicles/{vid}", json={"conso_officielle_kwh_100km": 16.5})
            assert r2.status_code == 200
            v = requests.get(f"{API}/vehicles/{vid}").json()
            assert v["conso_officielle_kwh_100km"] == 16.5
            assert not v.get("conso_officielle_l_100km")
        finally:
            _rm(vid)

    def test_ev_create_rejects_l_100km(self):
        r = requests.post(f"{API}/vehicles", json={
            "plaque": "ZZ 66667", "type_carburant": "Électrique", "conso_officielle_l_100km": 4.2})
        assert r.status_code == 422

    def test_thermal_and_hybrid_keep_l_100km(self):
        d = _mk({"plaque": "ZZ 66668", "type_carburant": "Diesel"})
        h = _mk({"plaque": "ZZ 66669", "type_carburant": "Essence / Électrique (hybride)"})
        try:
            assert requests.put(f"{API}/vehicles/{d}", json={"conso_officielle_l_100km": 6.4}).status_code == 200
            assert requests.put(f"{API}/vehicles/{h}", json={"conso_officielle_l_100km": 1.8}).status_code == 200
        finally:
            _rm(d)
            _rm(h)


class TestCouleur:
    def test_couleur_survives_carte_grise_edit(self):
        vid = _mk({"plaque": "ZZ 55555"})
        try:
            r = requests.put(f"{API}/vehicles/{vid}", json={"carte_grise": {"couleur": "Rouge"}})
            assert r.status_code == 200
            # Édition classique carte grise SANS couleur (comportement du formulaire UI)
            r2 = requests.put(f"{API}/vehicles/{vid}", json={
                "carte_grise": {"date_mise_circulation": "2020-01-15", "poids_total": 2000,
                                "nombre_places": 5}})
            assert r2.status_code == 200
            cg = requests.get(f"{API}/vehicles/{vid}").json()["carte_grise"]
            assert cg["couleur"] == "Rouge"
            assert cg["poids_total"] == 2000 and cg["nombre_places"] == 5
        finally:
            _rm(vid)


class TestCoreDto:
    CONTRACT_KEYS = {"fuel_tank_capacity_l", "battery_capacity_gross_kwh",
                     "battery_capacity_usable_kwh", "reference_consumption_l_100km",
                     "reference_consumption_kwh_100km", "reference_range_km"}

    def test_core_shape_and_privacy(self):
        v = _fleet()[0]
        r = requests.get(f"{API}/vehicles/{v['id']}/core")
        assert r.status_code == 200
        body = r.json()
        assert set(body.keys()) == {"contract_version", "identity", "reference"}
        assert set(body["reference"].keys()) == self.CONTRACT_KEYS
        ident = body["identity"]
        for k in ("vehicle_id", "vin", "plate", "make", "model", "year", "category",
                  "energy", "navixy_tracker_id", "navixy_vehicle_id"):
            assert k in ident
        raw = r.text
        for forbidden in ("storage_path", "numero_police", "mensualite", "prime_annuelle",
                          "leasing", "assurance", "photo_url"):
            assert forbidden not in raw, f"champ privé exposé: {forbidden}"
        for entry in body["reference"].values():
            for k in ("value", "unit", "source", "provider", "measurement_type",
                      "confidence", "retrieved_at", "validated_by", "validated_at"):
                assert k in entry

    def test_old_document_battery_null(self):
        # Ancien véhicule sans les nouveaux champs → null, jamais de valeur inventée
        v = _fleet()[0]
        ref = requests.get(f"{API}/vehicles/{v['id']}/core").json()["reference"]
        assert ref["battery_capacity_gross_kwh"]["value"] is None
        assert ref["battery_capacity_usable_kwh"]["value"] is None
        assert ref["reference_range_km"]["value"] is None

    def test_zero_is_null_and_value_passthrough(self):
        vid = _mk({"plaque": "ZZ 44444", "capacite_reservoir_l": 0})
        try:
            ref = requests.get(f"{API}/vehicles/{vid}/core").json()["reference"]
            assert ref["fuel_tank_capacity_l"]["value"] is None
            requests.put(f"{API}/vehicles/{vid}", json={"capacite_reservoir_l": 60})
            ref2 = requests.get(f"{API}/vehicles/{vid}/core").json()["reference"]
            assert ref2["fuel_tank_capacity_l"]["value"] == 60
        finally:
            _rm(vid)

    def test_core_404(self):
        assert requests.get(f"{API}/vehicles/inexistant-xyz/core").status_code == 404


class TestAstraUnits:
    def test_tas_electric_goes_to_kwh(self):
        from astra_data import _tas_emission_fields
        out = _tas_emission_fields({"conso_wltp": 16.2, "co2_wltp": 0}, "E")
        assert out["conso_officielle_kwh_100km"] == 16.2
        assert out["conso_officielle_l_100km"] is None
        assert out["co2_g_km"] == 0 and out["conso_officielle_norme"] == "WLTP"

    def test_tas_thermal_goes_to_l(self):
        from astra_data import _tas_emission_fields
        out = _tas_emission_fields({"conso_wltp": 6.1, "co2_wltp": 139}, "B")
        assert out["conso_officielle_l_100km"] == 6.1
        assert out["conso_officielle_kwh_100km"] is None

    def test_tas_hydrogen_unit_not_assumed(self):
        from astra_data import _tas_emission_fields
        out = _tas_emission_fields({"conso_wltp": 1.0, "co2_wltp": 0}, "W")
        assert out["conso_officielle_l_100km"] is None
        assert out["conso_officielle_kwh_100km"] is None

    def test_edb_electric_goes_to_kwh(self):
        from astra_data import _edb_fields
        out = _edb_fields({"is_electric": True, "conso_wltp": 15.8})
        assert out["conso_officielle_kwh_100km"] == 15.8
        assert out["conso_officielle_l_100km"] is None

    def test_edb_thermal_goes_to_l(self):
        from astra_data import _edb_fields
        out = _edb_fields({"is_electric": False, "fuel_code": "10", "conso_wltp": 5.9})
        assert out["conso_officielle_l_100km"] == 5.9
        assert out["conso_officielle_kwh_100km"] is None


class TestNoNavixyWrite:
    def test_only_readonly_navixy_calls(self):
        src = Path(BACKEND_DIR, "server.py").read_text()
        targets = set(re.findall(r"navixy_post\(\s*[\"']([^\"']+)[\"']", src))
        allowed = {"/tracker/list", "/vehicle/list", "/tracker/counter/value/list",
                   "/tracker/readings/list", "/tracker/get_states", "/user/get_info"}
        assert targets <= allowed, f"appels Navixy non autorisés: {targets - allowed}"
        assert "vehicle/update" not in src and "vehicle/create" not in src


class TestRegressionFleet:
    def test_fleet_intact(self):
        fleet = _fleet()
        real = [v for v in fleet if v.get("source") == "navixy"]
        assert len(real) >= 12
        for v in real:
            assert v["id"] and v.get("plaque")
