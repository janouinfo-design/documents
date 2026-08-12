"""Tests Vehicle Data API — données officielles ASTRA/OFROU locales (phases 1-2)."""
import os
import sys
import time

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
import astra_data  # noqa: E402

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = backend_env.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME") or os.environ.get("DB_NAME")

KNOWN_APPROVAL = "1AA101"  # ALFA ROMEO 145 1.9 TD — présent dans TAS et TG


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


# --------------------------- unités : normalisation & labels ---------------------------
class TestNormalizeAndLabels:
    def test_normalize_approval(self):
        assert astra_data.normalize_approval(" 1ab 123 ") == "1AB123"
        assert astra_data.normalize_approval("1AA-101") == "1AA101"
        assert astra_data.normalize_approval("") is None
        assert astra_data.normalize_approval(None) is None

    def test_fuel_labels(self):
        assert astra_data.FUEL_LABELS["B"] == "Essence"
        assert astra_data.FUEL_LABELS["D"] == "Diesel"
        assert astra_data.FUEL_LABELS["E"] == "Électrique"

    def test_gearbox_label(self):
        assert "manuelle" in astra_data.gearbox_label("m5")
        assert "5" in astra_data.gearbox_label("m5")
        assert "automatique" in astra_data.gearbox_label("a8")


# --------------------------- unités : parsers streaming ---------------------------
class TestParsers:
    def test_parse_tas(self, tmp_path):
        p = tmp_path / "tas.csv"
        p.write_text(
            '\ufeff"chTypeApprovalNumber";"versionNo";"makeName";"commercialName";"chFuelType";'
            '"engineCapacity";"maximumNetPower";"chNrOfSeatingPositionsMinimum";'
            '"chMassOfTheVehicleInRunningOrderMinimum";"technicallyPermissibleMaximumLadenMassMinimum";'
            '"gearboxEmissions1.chGearboxType"\n'
            '"1XY123";"2";"TESTMAKE";"Model X";"D";"1968";"110";"5";"1650";"2200";"a7"\n',
            encoding="utf-8")
        docs = list(astra_data.parse_tas(str(p)))
        assert len(docs) == 1
        d = docs[0]
        assert d["_key"] == "1XY123"
        assert d["make"] == "TESTMAKE"
        assert d["fuel_code"] == "D"
        assert d["engine_capacity"] == 1968
        assert d["power_kw"] == 110.0
        assert d["curb_weight"] == 1650
        assert d["gearboxes"] == ["a7"]

    def test_parse_tg(self, tmp_path):
        header = ("Typengenehmigungsnummer\tTypengenehmigung erteilt\t01 Fahrzeugart\t03 Fahrzeugklasse"
                  "\t04 Marke\t04 Typ\t26 Bauart Treibstoff\t27 Hubraum\t28 Leistung kW"
                  "\t37 Anzahl Plätze Total von\t52 Leergewicht von\t53 Garantiegewicht von\t18 Getriebe 1")
        row = "1ZZ999\t19970101\tPERSONENWAGEN\tM1\tTESTTG\tModel Y\tB\t1600\t74\t5\t1200\t1700\tm5"
        p = tmp_path / "tg.txt"
        p.write_text(header + "\n" + row + "\n", encoding="latin-1")
        docs = list(astra_data.parse_tg(str(p)))
        assert len(docs) == 1
        d = docs[0]
        assert d["_key"] == "1ZZ999"
        assert d["fuel_code"] == "B"
        assert d["engine_capacity"] == 1600
        assert d["curb_weight"] == 1200
        assert d["gross_weight"] == 1700
        assert d["gearboxes"] == ["m5"]

    def test_conso_wltp_priority_and_electric_co2(self):
        row = {"conso_wltp": 5.1, "conso_nedc": 4.4, "co2_wltp": 118.0, "co2_nedc": 105.0}
        f = astra_data._tas_emission_fields(row, "D")
        assert f["conso_officielle_l_100km"] == 5.1
        assert f["conso_officielle_norme"] == "WLTP"
        assert f["co2_g_km"] == 118.0
        assert f["co2_norme"] == "WLTP"
        # BEV : CO₂ 0 légitime
        f0 = astra_data._tas_emission_fields({"co2_wltp": 0.0}, "E")
        assert f0["co2_g_km"] == 0.0
        # Thermique : CO₂ 0 = donnée manquante
        f1 = astra_data._tas_emission_fields({"co2_wltp": 0.0}, "B")
        assert f1["co2_g_km"] is None

    def test_variant_divergence(self):
        doc = {"_key": "1XY123", "approval_no": "1XY123", "make": "M", "fuel_code": "B", "gearboxes": []}
        rows = [{"gearbox": "m6", "conso_wltp": 6.1, "co2_wltp": 140.0},
                {"gearbox": "a8", "conso_wltp": 6.8, "co2_wltp": 155.0}]
        res = astra_data._build_result("astra_tas", doc, rows)
        assert len(res["variantes"]) == 2
        assert "conso_officielle_l_100km" not in res["fields"]
        # boîte unique connue → résolution automatique
        doc2 = dict(doc, gearboxes=["a8"])
        res2 = astra_data._build_result("astra_tas", doc2, rows)
        assert res2["variantes"] == []
        assert res2["fields"]["conso_officielle_l_100km"] == 6.8


# --------------------------- API : statut & limitations ---------------------------
class TestAstraApi:
    def test_status_shape(self):
        r = requests.get(f"{BASE_URL}/api/astra/status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "datasets" in d and "imported" in d
        for name in ("tas", "tas_emission", "tg", "tg_verbrauch"):
            assert name in d["datasets"]

    def test_plate_lookup_unavailable(self):
        r = requests.get(f"{BASE_URL}/api/astra/search", params={"plate": "VD 12345"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["found"] is False
        assert d["reason"] == "plate_lookup_unavailable_without_external_provider"

    def test_vin_lookup_phase3(self):
        r = requests.get(f"{BASE_URL}/api/astra/search", params={"vin": "ZAR93000012345678"}, timeout=30)
        d = r.json()
        assert d["found"] is False
        assert "edatenblatt" in d["reason"]


# --------------------------- API : recherche & resolver (après import) ---------------------------
@pytest.fixture(scope="module")
def imported():
    r = requests.get(f"{BASE_URL}/api/astra/status", timeout=30)
    d = r.json()
    if not d.get("imported"):
        pytest.skip("Données ASTRA non importées dans cet environnement")
    return d


class TestLookupAfterImport:
    def test_search_known_homologation_perf(self, imported):
        t0 = time.perf_counter()
        r = requests.get(f"{BASE_URL}/api/astra/search",
                         params={"homologation": KNOWN_APPROVAL}, timeout=30)
        wall_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        d = r.json()
        assert d["found"] is True, d
        assert d["provider"] in ("astra_tas", "astra_tg")
        assert d["fields"], d
        assert d["match"]["make"] == "ALFA ROMEO"
        assert wall_ms < 2000, f"réponse E2E trop lente: {wall_ms:.0f} ms"

    def test_search_not_found(self, imported):
        r = requests.get(f"{BASE_URL}/api/astra/search", params={"homologation": "0QQ000"}, timeout=30)
        d = r.json()
        assert d["found"] is False
        assert d["reason"] == "not_found"

    def test_enrich_technical_e2e(self, imported, mongo):
        v = mongo.vehicles.find_one({}, {"id": 1, "numero_homologation": 1})
        assert v, "aucun véhicule en base"
        orig = v.get("numero_homologation")
        mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": KNOWN_APPROVAL}})
        try:
            r = requests.post(f"{BASE_URL}/api/vehicles/{v['id']}/enrich-technical", timeout=60)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["provider"] in ("astra_tas", "astra_tg")
            assert d["matched_by"] == "homologation"
            assert d.get("lookup_ms") is not None and d["lookup_ms"] < 500, d.get("lookup_ms")
            keys = {f["field"] for f in d["fields"]}
            keys |= {f["field"] for var in d.get("variantes", []) for f in var["fields"]}
            assert "type_carburant" in keys or "cylindree_cm3" in keys, d
        finally:
            mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": orig or ""}})

    def test_enrich_missing_homologation_422(self, imported, mongo):
        v = mongo.vehicles.find_one({}, {"id": 1, "numero_homologation": 1})
        orig = v.get("numero_homologation")
        mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": ""}})
        try:
            r = requests.post(f"{BASE_URL}/api/vehicles/{v['id']}/enrich-technical", timeout=30)
            assert r.status_code == 422, r.text
            assert "plaque" in r.json()["detail"].lower()
        finally:
            mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": orig or ""}})

    def test_enrich_unknown_homologation_404(self, imported, mongo):
        v = mongo.vehicles.find_one({}, {"id": 1, "numero_homologation": 1})
        orig = v.get("numero_homologation")
        mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": "0QQ000"}})
        try:
            r = requests.post(f"{BASE_URL}/api/vehicles/{v['id']}/enrich-technical", timeout=30)
            assert r.status_code == 404, r.text
            assert "introuvable" in r.json()["detail"].lower()
        finally:
            mongo.vehicles.update_one({"id": v["id"]}, {"$set": {"numero_homologation": orig or ""}})
