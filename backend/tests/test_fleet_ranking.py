"""Tests du comparateur de consommation flotte."""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
backend_env = dotenv_values("/app/backend/.env")


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(backend_env.get("MONGO_URL"))
    yield client[backend_env.get("DB_NAME")]
    client.close()


class TestConsumptionRanking:
    def test_shape_and_sorting(self):
        r = requests.get(f"{BASE_URL}/api/fleet/consumption-ranking", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == len(d["classement"]) + len(d["sans_donnees"])
        refs = [x["ref"] for x in d["classement"]]
        assert refs == sorted(refs), "classement non trié du plus sobre au plus gourmand"
        for i, x in enumerate(d["classement"]):
            assert x["rang"] == i + 1
            assert x["basis"] in ("reelle", "officielle")

    def test_delta_computed(self, mongo):
        v = mongo.vehicles.find_one({}, {"id": 1, "conso_officielle_l_100km": 1,
                                         "conso_reelle_l_100km": 1})
        orig = {k: v.get(k) for k in ("conso_officielle_l_100km", "conso_reelle_l_100km")}
        mongo.vehicles.update_one({"id": v["id"]}, {"$set": {
            "conso_officielle_l_100km": 6.0, "conso_reelle_l_100km": 6.9}})
        try:
            d = requests.get(f"{BASE_URL}/api/fleet/consumption-ranking", timeout=30).json()
            row = next(x for x in d["classement"] if x["vehicle_id"] == v["id"])
            assert row["ecart_l"] == 0.9
            assert row["ecart_pct"] == 15
            assert row["basis"] == "reelle"
            assert row["ref"] == 6.9
        finally:
            mongo.vehicles.update_one({"id": v["id"]}, {"$set": orig})

    def test_missing_listed(self, mongo):
        v = mongo.vehicles.find_one({"conso_officielle_l_100km": {"$in": [None, ""]},
                                     "conso_reelle_l_100km": {"$in": [None, ""]}}, {"id": 1})
        if not v:
            pytest.skip("Tous les véhicules ont des données de consommation")
        d = requests.get(f"{BASE_URL}/api/fleet/consumption-ranking", timeout=30).json()
        assert any(x["vehicle_id"] == v["id"] for x in d["sans_donnees"])
