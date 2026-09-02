"""Échéance contrôle DÉRIVÉE de la carte grise : date_dernier + intervalle tenant (défaut 24 mois).
À la volée uniquement (aucune écriture DB), supprimée dès qu'une vraie échéance existe."""
import uuid
from datetime import date, datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-derived-{_RUN}"
ADMIN = (f"derived-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
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


def sa():
    return _h(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])


def ro():
    return _h("ro-e2e@client-test.ch", "RoTest-2026y")


def _deadlines(vehicle_id=None):
    params = {"vehicle_id": vehicle_id} if vehicle_id else {}
    r = requests.get(f"{_BASE}/api/deadlines", params=params, headers=_h(*ADMIN), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _derived(items, vid):
    return [i for i in items if i["key"] == f"derived:{vid}:controle"]


def setup_module():
    r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Derived {_RUN}", "id": TENANT},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                      json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"DE {_RUN[:6].upper()}", "marque": "VW", "modele": "Polo"})
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]


def teardown_module():
    db = _mongo()
    db.vehicles.delete_many({"tenant_id": TENANT})
    db.documents.delete_many({"tenant_id": TENANT})
    db.audit_logs.delete_many({"tenant_id": TENANT})
    db.tenant_settings.delete_many({"tenant_id": TENANT})
    db.users.delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


def _set_ct(date_dernier=None, date_prochain=None):
    r = requests.put(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30,
                     json={"controle_technique": {"date_dernier": date_dernier,
                                                  "date_prochain": date_prochain}})
    assert r.status_code == 200, r.text


class TestDerivation:
    def test_sans_date_dernier_aucune_derivee(self):
        assert _derived(_deadlines(_S["veh"]), _S["veh"]) == []

    def test_derivee_24_mois_par_defaut(self):
        _set_ct(date_dernier="2025-03-15")
        items = _derived(_deadlines(_S["veh"]), _S["veh"])
        assert len(items) == 1
        d = items[0]
        assert d["source"] == "derived"
        assert d["provenance"] == "CARTE_GRISE"
        assert d["date"] == "2027-03-15"  # + 24 mois
        assert d["is_document_deadline"] is False  # jamais d'alerte e-mail sur une estimation
        assert d["category"] == "Contrôle technique"
        assert "estimé" in d["label"] and "24 mois" in d["label"]

    def test_aucune_ecriture_db(self):
        v = _mongo().vehicles.find_one({"id": _S["veh"]}, {"_id": 0, "controle_technique": 1})
        assert not v["controle_technique"].get("date_prochain")  # rien d'écrit par la dérivation

    def test_statut_expire_si_expertise_ancienne(self):
        _set_ct(date_dernier="2020-01-10")
        d = _derived(_deadlines(_S["veh"]), _S["veh"])[0]
        assert d["date"] == "2022-01-10" and d["statut"] == "EXPIRE"

    def test_fin_de_mois_31_janvier(self):
        _set_ct(date_dernier="2025-12-31")
        d = _derived(_deadlines(_S["veh"]), _S["veh"])[0]
        assert d["date"] == "2027-12-31"
        _set_ct(date_dernier="2026-01-31")  # +24 => 2028-01-31 ; contrôle +1 mois via réglage plus bas


class TestSuppression:
    def test_vraie_date_prochain_supprime_la_derivee(self):
        _set_ct(date_dernier="2025-03-15", date_prochain="2027-06-01")
        items = _deadlines(_S["veh"])
        assert _derived(items, _S["veh"]) == []
        legacy = [i for i in items if i["key"] == f"legacy:{_S['veh']}:controle"]
        assert len(legacy) == 1 and legacy[0]["date"] == "2027-06-01"  # pas de double comptage

    def test_document_controle_date_supprime_la_derivee(self):
        _set_ct(date_dernier="2025-03-15")
        assert len(_derived(_deadlines(_S["veh"]), _S["veh"])) == 1
        now = datetime.now(timezone.utc).isoformat()
        doc_id = str(uuid.uuid4())
        _mongo().documents.insert_one({
            "id": doc_id, "vehicle_id": _S["veh"], "tenant_id": TENANT,
            "folder": "Contrôle technique", "original_filename": f"ct-{_RUN}.pdf",
            "storage_path": f"logitrak-fleet/media/{_S['veh']}/ct.pdf",
            "content_type": "application/pdf", "size": 10, "is_deleted": False,
            "date_expiration": "2027-09-01", "created_at": now})
        try:
            items = _deadlines(_S["veh"])
            assert _derived(items, _S["veh"]) == []
            assert any(i["key"] == f"doc:{doc_id}" for i in items)  # le vrai document prime
        finally:
            _mongo().documents.delete_many({"id": doc_id})


class TestIntervalleConfigurable:
    def test_put_intervalle_12_mois(self):
        r = requests.put(f"{_BASE}/api/settings/deadlines", headers=_h(*ADMIN), timeout=30,
                         json={"urgent_days": 30, "warning_days": 90, "controle_interval_months": 12})
        assert r.status_code == 200, r.text
        assert r.json()["controle_interval_months"] == 12
        _set_ct(date_dernier="2025-03-15")
        d = _derived(_deadlines(_S["veh"]), _S["veh"])[0]
        assert d["date"] == "2026-03-15" and "12 mois" in d["label"]

    def test_get_settings_expose_intervalle(self):
        r = requests.get(f"{_BASE}/api/settings/deadlines", headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200
        assert r.json()["controle_interval_months"] == 12
        assert r.json()["defaults"]["controle_interval_months"] == 24

    def test_intervalle_invalide_422(self):
        for bad in (0, 121, -3):
            r = requests.put(f"{_BASE}/api/settings/deadlines", headers=_h(*ADMIN), timeout=30,
                             json={"urgent_days": 30, "warning_days": 90, "controle_interval_months": bad})
            assert r.status_code == 422, f"{bad} -> {r.status_code}"

    def test_put_sans_intervalle_le_conserve(self):
        r = requests.put(f"{_BASE}/api/settings/deadlines", headers=_h(*ADMIN), timeout=30,
                         json={"urgent_days": 25, "warning_days": 80})
        assert r.status_code == 200 and r.json()["controle_interval_months"] == 12

    def test_read_only_put_403(self):
        r = requests.put(f"{_BASE}/api/settings/deadlines", headers=ro(), timeout=30,
                         json={"urgent_days": 30, "warning_days": 90, "controle_interval_months": 6})
        assert r.status_code == 403

    def test_tenant_scope_intervalle(self):
        """L'intervalle 12 mois du tenant test ne fuit pas vers les autres tenants."""
        r = requests.get(f"{_BASE}/api/settings/deadlines",
                         headers=_h(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"]), timeout=30)
        assert r.status_code == 200
        assert r.json()["controle_interval_months"] == 24  # défaut, jamais modifié ici
