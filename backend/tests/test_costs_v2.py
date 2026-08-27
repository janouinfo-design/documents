"""Coûts : moteur central dérivé des documents V2 + legacy dual-read, séries annuelles."""
import uuid
from datetime import date

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-cost-a-{_RUN}"
TENANT_B = f"pytest-cost-b-{_RUN}"
ADMIN_A = (f"cost-adm-a-{_RUN}@pytest.ch", f"CAdmA-{_RUN}-1")
RO_A = (f"cost-ro-a-{_RUN}@pytest.ch", f"CRoA-{_RUN}-1")
ADMIN_B = (f"cost-adm-b-{_RUN}@pytest.ch", f"CAdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
YEAR = date.today().year

_S = {}
_cache = {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds=ADMIN_A):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login",
                          json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _upload(vehicle_id, folder="Divers", name="c.png", creds=ADMIN_A):
    r = requests.post(f"{_BASE}/api/vehicles/{vehicle_id}/documents", headers=_h(creds),
                      files={"file": (name, PNG, "image/png")}, data={"folder": folder}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _patch(doc_id, payload, creds=ADMIN_A):
    r = requests.patch(f"{_BASE}/api/documents/{doc_id}", json=payload, headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _costs(creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/costs", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _by_key(data):
    return {i["key"]: i for i in data["items"]}


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant},
                             headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users",
                             json={"email": admin[0], "password": admin[1], "role": "admin"},
                             headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users",
                         json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"},
                         headers=sa(), timeout=30).status_code == 200

    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"CO A{_RUN[:4]}"}, headers=_h(), timeout=30)
    _S["veh_a"] = r.json()["id"]
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"CO L{_RUN[:4]}"}, headers=_h(), timeout=30)
    _S["veh_legacy"] = r.json()["id"]
    requests.put(f"{_BASE}/api/vehicles/{_S['veh_legacy']}",
                 json={"leasing": {"societe": "LeaseCo", "mensualite_chf": 400,
                                   "date_debut": f"{YEAR - 1}-01-01", "date_fin": f"{YEAR + 1}-12-31"},
                       "assurance": {"compagnie": "AssurCo", "prime_annuelle": 900,
                                     "date_echeance": f"{YEAR}-11-30"}},
                 headers=_h(), timeout=30)

    # Documents V2 avec montants (veh_a)
    d = _upload(_S["veh_a"], "Divers", "mensuel.png")
    _S["doc_mensuel"] = _patch(d["id"], {"montant": 100, "frequence": "mensuel",
                                         "date_debut": f"{YEAR}-01-01",
                                         "date_expiration": f"{YEAR + 2}-12-31"})
    d = _upload(_S["veh_a"], "Divers", "annuel.png")
    _S["doc_annuel"] = _patch(d["id"], {"montant": 500, "frequence": "annuel"})
    d = _upload(_S["veh_a"], "Divers", "unique.png")
    _S["doc_unique"] = _patch(d["id"], {"montant": 300, "frequence": "unique",
                                        "date_debut": f"{YEAR - 1}-06-01"})
    d = _upload(_S["veh_a"], "Divers", "sans-montant.png")
    _S["doc_sans_montant"] = d

    # Tenant B : un coût pour tester l'isolation
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"CO B{_RUN[:4]}"},
                      headers=_h(ADMIN_B), timeout=30)
    _S["veh_b"] = r.json()["id"]
    d = _upload(_S["veh_b"], "Divers", "b.png", creds=ADMIN_B)
    _patch(d["id"], {"montant": 777, "frequence": "annuel"}, creds=ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestNormalisation:
    def test_recurrent_annuel_echeance_future_couvre_annee_courante(self):
        r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"CO F{_RUN[:4]}"},
                          headers=_h(), timeout=30)
        vid = r.json()["id"]
        requests.put(f"{_BASE}/api/vehicles/{vid}",
                     json={"assurance": {"compagnie": "FutureAssur", "prime_annuelle": 1450,
                                         "date_echeance": f"{YEAR + 1}-06-01"}},
                     headers=_h(), timeout=30)
        data = _costs()
        item = _by_key(data)[f"legacy:{vid}:assurance"]
        assert YEAR in item["years"] and item["actif"] is True, \
            "un poste annuel récurrent échéant l'an prochain doit couvrir l'année courante"
        assert vid in {b["vehicle_id"] for b in data["by_vehicle"]}

    def test_totaux_egaux_somme_items_actifs(self):
        data = _costs()
        assert data["totals"]["annuel"] == round(
            sum(i["cout_annuel"] for i in data["items"] if i["actif"]), 2)
        assert data["totals"]["postes_actifs"] == sum(1 for i in data["items"] if i["actif"])

    def test_annualisation_par_frequence(self):
        by = _by_key(_costs())
        m = by[f"doc:{_S['doc_mensuel']['id']}"]
        assert m["cout_annuel"] == 1200 and m["recurrent"] is True
        a = by[f"doc:{_S['doc_annuel']['id']}"]
        assert a["cout_annuel"] == 500 and a["recurrent"] is True
        u = by[f"doc:{_S['doc_unique']['id']}"]
        assert u["cout_annuel"] == 300 and u["recurrent"] is False

    def test_doc_sans_montant_absent(self):
        by = _by_key(_costs())
        assert f"doc:{_S['doc_sans_montant']['id']}" not in by

    def test_series_annuelles(self):
        data = _costs()
        smap = {s["year"]: s["total"] for s in data["series"]}
        # doc mensuel couvre YEAR..YEAR+2 ; unique compté sur YEAR-1 uniquement
        assert smap.get(YEAR + 2, 0) >= 1200
        assert smap.get(YEAR - 1, 0) >= 300 + 4800  # unique + leasing legacy (YEAR-1..YEAR+1)
        # l'unique ne compte PAS l'année courante
        cur_keys = [i for i in data["items"] if i["key"] == f"doc:{_S['doc_unique']['id']}"]
        assert YEAR not in cur_keys[0]["years"]

    def test_totaux_annee_courante(self):
        data = _costs()
        t = data["totals"]
        assert data["year"] == YEAR
        # actifs YEAR : 1200 + 500 + leasing 4800 + assurance 900 + assurance future 1450 (unique exclu)
        assert t["annuel"] == 1200 + 500 + 4800 + 900 + 1450
        assert t["mensuel"] == round(t["annuel"] / 12, 2)


class TestDualRead:
    def test_legacy_visible_sans_doc(self):
        by = _by_key(_costs())
        l = by[f"legacy:{_S['veh_legacy']}:leasing"]
        assert l["cout_annuel"] == 4800 and l["category"] == "Leasing"
        a = by[f"legacy:{_S['veh_legacy']}:assurance"]
        assert a["cout_annuel"] == 900

    def test_doc_v2_masque_legacy_zero_doublon(self):
        d = _upload(_S["veh_legacy"], "Leasing", "contrat.png")
        _S["doc_leasing"] = _patch(d["id"], {"montant": 550, "frequence": "mensuel"})
        data = _costs()
        by = _by_key(data)
        assert f"legacy:{_S['veh_legacy']}:leasing" not in by, "double comptage coût legacy/V2"
        assert by[f"doc:{_S['doc_leasing']['id']}"]["cout_annuel"] == 6600
        leasing_items = [i for i in data["items"]
                         if i["vehicle_id"] == _S["veh_legacy"] and i["category"] == "Leasing"]
        assert len(leasing_items) == 1
        # l'assurance legacy reste visible (pas de doc Assurance avec montant)
        assert f"legacy:{_S['veh_legacy']}:assurance" in by

    def test_by_vehicle_et_csv(self):
        data = _costs()
        bv = {b["vehicle_id"]: b for b in data["by_vehicle"]}
        assert bv[_S["veh_legacy"]]["total_annuel"] == 6600 + 900
        r = requests.get(f"{_BASE}/api/reports/couts.csv", headers=_h(), timeout=30)
        assert r.status_code == 200
        assert "Coût annuel tous postes CHF" in r.text


class TestSecurite:
    def test_read_only_lecture_ok(self):
        assert requests.get(f"{_BASE}/api/costs", headers=_h(RO_A), timeout=30).status_code == 200

    def test_cross_tenant(self):
        a_ids = {i["vehicle_id"] for i in _costs()["items"]}
        b = _costs(creds=ADMIN_B)
        b_ids = {i["vehicle_id"] for i in b["items"]}
        assert _S["veh_b"] not in a_ids and not (b_ids & {_S["veh_a"], _S["veh_legacy"]})
        assert b["totals"]["annuel"] == 777

    def test_vehicle_costs_endpoint(self):
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/costs", headers=_h(), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert all(i["vehicle_id"] == _S["veh_a"] for i in d["items"])
        assert d["totals"]["annuel"] == 1700  # 1200 + 500, unique YEAR-1 exclu
        rb = requests.get(f"{_BASE}/api/vehicles/{_S['veh_b']}/costs", headers=_h(), timeout=30)
        assert rb.status_code == 404
