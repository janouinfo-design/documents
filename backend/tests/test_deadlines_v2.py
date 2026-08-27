"""Documents V2 — Étape 4 : moteur central d'échéances, dual-read, seuils tenant, alertes."""
import uuid
from datetime import date, timedelta

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-dl4a-{_RUN}"
TENANT_B = f"pytest-dl4b-{_RUN}"
ADMIN_A = (f"dl4-adm-a-{_RUN}@pytest.ch", f"AdmA-{_RUN}-1")
RO_A = (f"dl4-ro-a-{_RUN}@pytest.ch", f"RoA-{_RUN}-1")
ADMIN_B = (f"dl4-adm-b-{_RUN}@pytest.ch", f"AdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80

_S = {}
_cache = {}
_mongo_db = None


def _iso(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _mongo():
    global _mongo_db
    if _mongo_db is None:
        _mongo_db = MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]
    return _mongo_db


def _h(creds=ADMIN_A):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login",
                          json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _upload(vehicle_id, folder="Divers", name="d.png", creds=ADMIN_A):
    r = requests.post(f"{_BASE}/api/vehicles/{vehicle_id}/documents", headers=_h(creds),
                      files={"file": (name, PNG, "image/png")}, data={"folder": folder}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _patch(doc_id, payload, creds=ADMIN_A):
    r = requests.patch(f"{_BASE}/api/documents/{doc_id}", json=payload, headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _deadlines(params=None, creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/deadlines", params=params or {}, headers=_h(creds), timeout=30)
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

    # Tenant A — véhicule "bornes" (documents V2 uniquement)
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD D{_RUN[:4]}"}, headers=_h(), timeout=30)
    _S["veh_docs"] = r.json()["id"]
    for name, offset in (("m1", -1), ("p1", 1), ("p30", 30), ("p31", 31),
                         ("p90", 90), ("p91", 91)):
        d = _upload(_S["veh_docs"], "Divers", f"{name}.png")
        _S[f"doc_{name}"] = _patch(d["id"], {"date_expiration": _iso(offset),
                                             "responsable": "J. Testeur" if name == "m1" else None})
    _S["doc_nodate"] = _upload(_S["veh_docs"], "Divers", "nodate.png")
    # Date invalide : insérée directement (l'API refuse à raison les dates non parsables)
    bad_id = str(uuid.uuid4())
    _mongo().documents.insert_one({
        "id": bad_id, "vehicle_id": _S["veh_docs"], "tenant_id": TENANT_A,
        "folder": "Divers", "original_filename": "invalide.png",
        "date_expiration": "9999-99-99", "is_deleted": False, "created_at": _iso(0)})
    _S["doc_invalid"] = bad_id

    # Tenant A — véhicule "legacy" (sous-objets hérités)
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD L{_RUN[:4]}"}, headers=_h(), timeout=30)
    _S["veh_legacy"] = r.json()["id"]
    requests.put(f"{_BASE}/api/vehicles/{_S['veh_legacy']}",
                 json={"assurance": {"compagnie": "TestAssur", "date_echeance": _iso(40)},
                       "leasing": {"societe": "TestLease", "date_fin": _iso(200)}},
                 headers=_h(), timeout=30)

    # Tenant B — véhicule avec assurance legacy expirée (isolation)
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"GE B{_RUN[:4]}"},
                      headers=_h(ADMIN_B), timeout=30)
    _S["veh_b"] = r.json()["id"]
    requests.put(f"{_BASE}/api/vehicles/{_S['veh_b']}",
                 json={"assurance": {"compagnie": "BAssur", "date_echeance": _iso(-10)}},
                 headers=_h(ADMIN_B), timeout=30)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestMoteurBornes:
    def test_statuts_bornes_defaut_30_90(self):
        by = _by_key(_deadlines())
        expected = {"m1": "EXPIRE", "p1": "URGENT", "p30": "URGENT",
                    "p31": "A_PLANIFIER", "p90": "A_PLANIFIER", "p91": "OK"}
        for name, statut in expected.items():
            item = by[f"doc:{_S[f'doc_{name}']['id']}"]
            assert item["statut"] == statut, f"{name}: {item['statut']} != {statut}"
            assert item["source"] == "document" and item["is_document_deadline"] is True

    def test_sans_echeance_jamais_zero(self):
        by = _by_key(_deadlines())
        item = by[f"doc:{_S['doc_nodate']['id']}"]
        assert item["statut"] == "SANS_ECHEANCE"
        assert item["days_remaining"] is None
        assert item["level"] == "unknown"

    def test_date_invalide(self):
        by = _by_key(_deadlines())
        item = by[f"doc:{_S['doc_invalid']}"]
        assert item["statut"] == "DATE_INVALIDE"
        assert item["days_remaining"] is None

    def test_responsable_ou_non_attribue(self):
        by = _by_key(_deadlines())
        assert by[f"doc:{_S['doc_m1']['id']}"]["responsable"] == "J. Testeur"
        assert by[f"doc:{_S['doc_p1']['id']}"]["responsable"] is None

    def test_summary_coherent(self):
        data = _deadlines()
        s = data["summary"]
        counted = {k: 0 for k in ("EXPIRE", "URGENT", "A_PLANIFIER", "OK", "SANS_ECHEANCE", "DATE_INVALIDE")}
        for i in data["items"]:
            counted[i["statut"]] += 1
        assert s["expired"] == counted["EXPIRE"] and s["urgent"] == counted["URGENT"]
        assert s["warning"] == counted["A_PLANIFIER"] and s["no_date"] == counted["SANS_ECHEANCE"]
        assert s["invalid_date"] == counted["DATE_INVALIDE"]
        assert s["total"] == len(data["items"])

    def test_tri_urgent_puis_chronologique(self):
        data = _deadlines()
        rank = {"EXPIRE": 0, "URGENT": 1, "A_PLANIFIER": 2, "OK": 3, "DATE_INVALIDE": 4, "SANS_ECHEANCE": 5}
        ranks = [rank[i["statut"]] for i in data["items"]]
        assert ranks == sorted(ranks), "urgence d'abord non respectée"


class TestDualRead:
    def test_legacy_seul_visible(self):
        by = _by_key(_deadlines())
        item = by[f"legacy:{_S['veh_legacy']}:assurance"]
        assert item["source"] == "legacy" and item["category"] == "Assurance"
        assert item["statut"] == "A_PLANIFIER" and item["document_id"] is None
        leas = by[f"legacy:{_S['veh_legacy']}:leasing"]
        assert leas["statut"] == "OK"

    def test_doc_v2_sans_date_ne_masque_pas_legacy(self):
        _S["doc_assur"] = _upload(_S["veh_legacy"], "Assurance", "police.png")
        by = _by_key(_deadlines())
        assert f"legacy:{_S['veh_legacy']}:assurance" in by, \
            "un document V2 SANS date ne doit pas masquer l'échéance legacy"

    def test_doc_v2_date_masque_legacy_zero_doublon(self):
        _patch(_S["doc_assur"]["id"], {"date_expiration": _iso(50), "label": "Police RC 2026"})
        data = _deadlines()
        by = _by_key(data)
        assert f"legacy:{_S['veh_legacy']}:assurance" not in by, "double comptage legacy/V2"
        assert by[f"doc:{_S['doc_assur']['id']}"]["statut"] == "A_PLANIFIER"
        assurance_items = [i for i in data["items"]
                           if i["vehicle_id"] == _S["veh_legacy"] and i["category"] == "Assurance"]
        assert len(assurance_items) == 1, f"attendu 1 échéance Assurance, obtenu {len(assurance_items)}"

    def test_leasing_legacy_reste_visible(self):
        by = _by_key(_deadlines())
        assert f"legacy:{_S['veh_legacy']}:leasing" in by


class TestConsommateurs:
    def test_dashboard_kpis_docs_egaux_moteur(self):
        k = requests.get(f"{_BASE}/api/dashboard", headers=_h(), timeout=30).json()
        s = _deadlines()["summary"]["documents"]
        assert k["docs_expires"] == s["expired"]
        assert k["docs_expire_30"] == s["urgent"]
        assert k["docs_expire_31_90"] == s["warning"]
        assert k["deadline_thresholds"] == {"urgent_days": 30, "warning_days": 90}

    def test_manquant_jamais_melange_avec_expire(self):
        r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD C{_RUN[:4]}"},
                          headers=_h(), timeout=30)
        vid = r.json()["id"]
        d = _upload(vid, "Assurance", "expiree.png")
        _patch(d["id"], {"date_expiration": _iso(-5)})
        c = requests.get(f"{_BASE}/api/vehicles/{vid}/conformite-documents",
                         headers=_h(), timeout=30).json()
        assert "Assurance" in c["expires"] and "Assurance" not in c["manquants"]
        assert "Carte grise" in c["manquants"] and "Carte grise" not in c["expires"]

    def test_timeline_adaptateur_moteur(self):
        r = requests.get(f"{_BASE}/api/timeline", headers=_h(), timeout=30)
        assert r.status_code == 200
        events = r.json()
        keys = {e["key"] for e in events}
        assert f"doc:{_S['doc_m1']['id']}" in keys and f"legacy:{_S['veh_legacy']}:leasing" in keys
        for e in events:
            for f in ("vehicle_id", "plaque", "type", "label", "date", "days_remaining", "level"):
                assert f in e
            assert e["days_remaining"] is not None, "timeline ne doit contenir que des items datés"
        dates = [e["date"] for e in events]
        assert dates == sorted(dates)

    def test_alerts_depuis_moteur(self):
        data = requests.get(f"{_BASE}/api/alerts", headers=_h(), timeout=30).json()
        assert data["thresholds"] == {"urgent_days": 30, "warning_days": 90}
        assert all(i["statut"] in ("EXPIRE", "URGENT", "A_PLANIFIER") for i in data["items"])
        doc_items = [i for i in data["items"] if i["document_id"] == _S["doc_m1"]["id"]]
        assert doc_items and doc_items[0]["level"] == "expired" and doc_items[0]["category"] == "Divers"
        assert not any(i["key"] if False else (i["source"] == "legacy" and i["category"] == "Assurance"
                                               and i["vehicle_id"] == _S["veh_legacy"])
                       for i in data["items"]), "legacy masqué par V2 doit rester absent des alertes"

    def test_filtre_documents_echeance_seuils(self):
        r = requests.get(f"{_BASE}/api/documents", params={"echeance": "30"},
                         headers=_h(), timeout=30).json()
        ids = {d["id"] for d in r}
        assert _S["doc_p1"]["id"] in ids and _S["doc_p30"]["id"] in ids
        assert _S["doc_p31"]["id"] not in ids and _S["doc_m1"]["id"] not in ids

    def test_filtres_endpoint_deadlines(self):
        data = _deadlines({"vehicle_id": _S["veh_docs"], "statut": "EXPIRE"})
        assert all(i["vehicle_id"] == _S["veh_docs"] and i["statut"] == "EXPIRE" for i in data["items"])
        assert data["count"] == len(data["items"]) >= 1
        data = _deadlines({"category": "Assurance"})
        assert all(i["category"] == "Assurance" for i in data["items"])
        data = _deadlines({"days": 30})
        assert all(i["days_remaining"] is not None and i["days_remaining"] <= 30 for i in data["items"])


class TestAlertesIdempotence:
    def test_run_puis_rerun_zero(self):
        r1 = requests.post(f"{_BASE}/api/alerts/run", headers=_h(), timeout=60).json()
        assert r1["created"] >= 1
        r2 = requests.post(f"{_BASE}/api/alerts/run", headers=_h(), timeout=60).json()
        assert r2["created"] == 0, "les alertes doivent être idempotentes"

    def test_cle_canonique_document(self):
        rec = _mongo().alerts.find_one({"tenant_id": TENANT_A, "type": "document",
                                        "document_id": _S["doc_m1"]["id"]})
        assert rec, "alerte document manquante"
        assert rec["category"] == "Divers" and rec["threshold"] == 0 and rec["source"] == "document"
        assert rec["vehicle_id"] == _S["veh_docs"]

    def test_cle_legacy_inchangee(self):
        requests.put(f"{_BASE}/api/vehicles/{_S['veh_legacy']}",
                     json={"controle_technique": {"date_prochain": _iso(5)}},
                     headers=_h(), timeout=30)
        r = requests.post(f"{_BASE}/api/alerts/run", headers=_h(), timeout=60).json()
        assert r["created"] >= 1
        rec = _mongo().alerts.find_one({"tenant_id": TENANT_A, "type": "controle",
                                        "vehicle_id": _S["veh_legacy"]})
        assert rec and rec["threshold"] == 7 and "document_id" not in rec

    def test_isolation_run_tenant(self):
        assert _mongo().alerts.count_documents({"tenant_id": TENANT_B}) == 0, \
            "le run du tenant A ne doit jamais créer d'alertes pour B"


class TestSeuilsTenant:
    def test_defauts(self):
        r = requests.get(f"{_BASE}/api/settings/deadlines", headers=_h(), timeout=30).json()
        assert r["urgent_days"] == 30 and r["warning_days"] == 90
        assert r["defaults"] == {"urgent_days": 30, "warning_days": 90}

    def test_read_only_lecture_ok_ecriture_403(self):
        assert requests.get(f"{_BASE}/api/settings/deadlines", headers=_h(RO_A), timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/deadlines", headers=_h(RO_A), timeout=30).status_code == 200
        r = requests.put(f"{_BASE}/api/settings/deadlines",
                         json={"urgent_days": 5, "warning_days": 50}, headers=_h(RO_A), timeout=30)
        assert r.status_code == 403

    def test_validation_422(self):
        for bad in ({"urgent_days": 90, "warning_days": 30}, {"urgent_days": 0, "warning_days": 90},
                    {"urgent_days": 30, "warning_days": 800}):
            assert requests.put(f"{_BASE}/api/settings/deadlines", json=bad,
                                headers=_h(), timeout=30).status_code == 422

    def test_seuils_personnalises_appliques(self):
        r = requests.put(f"{_BASE}/api/settings/deadlines",
                         json={"urgent_days": 10, "warning_days": 40}, headers=_h(), timeout=30)
        assert r.status_code == 200 and r.json() == {"urgent_days": 10, "warning_days": 40}
        by = _by_key(_deadlines())
        assert by[f"doc:{_S['doc_p1']['id']}"]["statut"] == "URGENT"
        assert by[f"doc:{_S['doc_p30']['id']}"]["statut"] == "A_PLANIFIER"
        assert by[f"doc:{_S['doc_p90']['id']}"]["statut"] == "OK"
        k = requests.get(f"{_BASE}/api/dashboard", headers=_h(), timeout=30).json()
        assert k["deadline_thresholds"] == {"urgent_days": 10, "warning_days": 40}
        # le filtre échéances de la page Documents suit les seuils du tenant
        ids = {d["id"] for d in requests.get(f"{_BASE}/api/documents", params={"echeance": "30"},
                                             headers=_h(), timeout=30).json()}
        assert _S["doc_p1"]["id"] in ids and _S["doc_p30"]["id"] not in ids

    def test_isolation_seuils_tenant_b(self):
        r = requests.get(f"{_BASE}/api/settings/deadlines", headers=_h(ADMIN_B), timeout=30).json()
        assert r["urgent_days"] == 30 and r["warning_days"] == 90
        by = _by_key(_deadlines(creds=ADMIN_B))
        assert by[f"legacy:{_S['veh_b']}:assurance"]["statut"] == "EXPIRE"

    def test_restauration_defauts(self):
        r = requests.put(f"{_BASE}/api/settings/deadlines",
                         json={"urgent_days": 30, "warning_days": 90}, headers=_h(), timeout=30)
        assert r.status_code == 200
        by = _by_key(_deadlines())
        assert by[f"doc:{_S['doc_p30']['id']}"]["statut"] == "URGENT"


class TestCrossTenant:
    def test_aucune_fuite_entre_tenants(self):
        a_vehicles = {i["vehicle_id"] for i in _deadlines()["items"]}
        b_vehicles = {i["vehicle_id"] for i in _deadlines(creds=ADMIN_B)["items"]}
        assert _S["veh_b"] not in a_vehicles
        assert not (b_vehicles & {_S["veh_docs"], _S["veh_legacy"]})
        assert b_vehicles == {_S["veh_b"]}

    def test_alertes_filtrees_tenant(self):
        b = requests.get(f"{_BASE}/api/alerts", headers=_h(ADMIN_B), timeout=30).json()
        assert all(i["vehicle_id"] == _S["veh_b"] for i in b["items"])
