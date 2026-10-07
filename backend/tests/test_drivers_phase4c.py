"""Phase 4C — Lot C : référentiel conducteurs + affectations datées + driver_id (FK tenant) + legacy idempotence."""
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-drv-a-{_RUN}"
TENANT_B = f"pytest-drv-b-{_RUN}"
ADMIN_A = (f"drv-adm-a-{_RUN}@pytest.ch", f"DrvAdmA-{_RUN}-1")
RO_A = (f"drv-ro-a-{_RUN}@pytest.ch", f"DrvRoA-{_RUN}-1")
ADMIN_B = (f"drv-adm-b-{_RUN}@pytest.ch", f"DrvAdmB-{_RUN}-1")
DRIVER = {"nom": "Rochat", "prenom": "Léa", "email": f"lea.rochat+{_RUN}@pytest.ch", "matricule_interne": f"CH-{_RUN[:4]}",
          "telephone": "+41 79 000 00 00", "groupe": "Lausanne"}
PLEIN = {"station": "Agrola Payerne", "date": "2026-06-20", "montant": 88.4, "devise": "CHF", "litres": 48.0,
         "business_category": "CARBURANT", "motif": "Ticket perdu — relevé carte"}
_S, _cache = {}, {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds=ADMIN_A):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _req(method, path, body=None, creds=ADMIN_A, **kw):
    return requests.request(method, f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=30, **kw)


def _driver(body=None, creds=ADMIN_A, **over):
    return _req("POST", "/drivers", {**(body if body is not None else DRIVER), **over}, creds)


def _assign(vehicle_id, body, creds=ADMIN_A):
    return _req("POST", f"/vehicles/{vehicle_id}/driver-assignments", body, creds)


def _audits(entity, entity_id, action=None, tenant=TENANT_A):
    q = {"tenant_id": tenant, "entity": entity, "entity_id": entity_id}
    if action:
        q["action"] = action
    return list(_mongo().audit_logs.find(q, {"_id": 0}).sort("created_at", 1))


def _vehicle(payload, creds=ADMIN_A):
    r = _req("POST", "/vehicles", payload, creds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"},
                             headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"},
                         headers=sa(), timeout=30).status_code == 200
    _S["veh_a"] = _vehicle({"plaque": f"VD {_RUN[:6].upper()}", "kilometrage": 13000, "type_carburant": "Diesel"})
    _S["veh_a2"] = _vehicle({"plaque": f"FR {_RUN[:6].upper()}", "kilometrage": 2000})
    _S["veh_b"] = _vehicle({"plaque": f"BE {_RUN[:6].upper()}"}, creds=ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations",
                     "doc_categories", "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestReferentielConducteurs:
    def test_01_creation_conducteur_tenant_a(self):
        r = _driver()
        assert r.status_code == 200, r.text
        d = r.json()
        _S["drv"] = d["id"]
        assert d["created"] is True and d["tenant_id"] == TENANT_A and d["actif"] is True and d["is_deleted"] is False
        assert d["display"] == f"Léa Rochat · CH-{_RUN[:4]}" and d["email"] == DRIVER["email"].lower() and d["source"] == "manual"
        assert len(d["id"]) == 36  # UUID stable
        db = _mongo().drivers.find_one({"id": d["id"]}, {"_id": 0})
        assert db["created_by"] == ADMIN_A[0] and "legacy_id" not in db

    def test_02_lecture_conducteur_tenant_a(self):
        r = _req("GET", f"/drivers/{_S['drv']}")
        assert r.status_code == 200 and r.json()["id"] == _S["drv"] and r.json()["assignments"] == []
        lst = _req("GET", "/drivers").json()
        assert [x["id"] for x in lst] == [_S["drv"]] and lst[0]["affectations"] == []
        assert _req("GET", "/drivers", params={"q": "rochat"}).json()[0]["id"] == _S["drv"]
        assert _req("GET", "/drivers", params={"q": "introuvable-zzz"}).json() == []

    def test_03_modification_conducteur_audit_avant_apres(self):
        r = _req("PATCH", f"/drivers/{_S['drv']}", {"telephone": "+41 79 111 11 11", "groupe": "Fribourg"})
        assert r.status_code == 200 and r.json()["groupe"] == "Fribourg"
        a = _audits("driver", _S["drv"], "modify")
        assert len(a) == 1 and "groupe: Lausanne → Fribourg" in a[0]["detail"] and "telephone: +41 79 000 00 00 → +41 79 111 11 11" in a[0]["detail"]
        assert a[0]["user"] == ADMIN_A[0] and a[0]["created_at"]
        r = _req("PATCH", f"/drivers/{_S['drv']}", {"nom": ""})
        assert r.status_code == 422
        r = _req("PATCH", f"/drivers/{_S['drv']}", {"email": "pas-un-email"})
        assert r.status_code == 422

    def test_04_aucune_unicite_sur_le_nom_mais_email_unique(self):
        r = _driver(email=None, matricule_interne=None)  # même nom/prénom = autorisé (doublon de nom J §11)
        assert r.status_code == 200, r.text
        _S["drv_homonyme"] = r.json()["id"]
        assert _S["drv_homonyme"] != _S["drv"]
        r = _driver(email=DRIVER["email"].upper(), matricule_interne="X")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "EMAIL_TAKEN"
        assert _req("PATCH", f"/drivers/{_S['drv_homonyme']}", {"email": DRIVER["email"]}).status_code == 409
        assert _driver(nom="   ").status_code == 422

    def test_05_desactivation_puis_reactivation(self):
        r = _req("PATCH", f"/drivers/{_S['drv_homonyme']}", {"actif": False})
        assert r.status_code == 200 and r.json()["actif"] is False
        assert "DÉSACTIVATION" in _audits("driver", _S["drv_homonyme"], "modify")[-1]["detail"]
        assert all(x["id"] != _S["drv_homonyme"] for x in _req("GET", "/drivers", params={"actif": "true"}).json())
        r = _assign(_S["veh_a2"], {"driver_id": _S["drv_homonyme"], "valid_from": "2026-01-01"})
        assert r.status_code == 422  # désactivé = non affectable
        assert _req("PATCH", f"/drivers/{_S['drv_homonyme']}", {"actif": True}).status_code == 200

    def test_06_archive_non_destructif_et_restore(self):
        r = _req("POST", f"/drivers/{_S['drv_homonyme']}/archive")
        assert r.status_code == 200 and r.json()["is_deleted"] is True
        assert _mongo().drivers.count_documents({"id": _S["drv_homonyme"]}) == 1  # jamais supprimé physiquement
        assert all(x["id"] != _S["drv_homonyme"] for x in _req("GET", "/drivers").json())
        assert any(x["id"] == _S["drv_homonyme"] for x in _req("GET", "/drivers", params={"include_archived": "1"}).json())
        assert _req("GET", f"/drivers/{_S['drv_homonyme']}").status_code == 200  # fiche consultable
        assert _assign(_S["veh_a2"], {"driver_id": _S["drv_homonyme"], "valid_from": "2026-01-01"}).status_code == 404
        assert _audits("driver", _S["drv_homonyme"], "archive")
        assert _req("POST", f"/drivers/{_S['drv_homonyme']}/restore").status_code == 200
        assert _audits("driver", _S["drv_homonyme"], "restore")


class TestAffectations:
    def test_10_affectation_driver_a_vers_vehicle_a(self):
        r = _assign(_S["veh_a"], {"driver_id": _S["drv"], "valid_from": "2026-01-01", "motif": "Chauffeur titulaire"})
        assert r.status_code == 200, r.text
        a = r.json()
        _S["assign1"] = a["id"]
        assert a["created"] is True and a["valid_to"] is None and a["principal"] is True and a["active"] is True
        assert a["driver_nom"].startswith("Léa Rochat") and a["tenant_id"] == TENANT_A and a["replaced"] == []
        at = _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2026-03-15"}).json()
        assert at["driver"]["id"] == _S["assign1"] and at["ambiguous"] is False and at["written"] == 0
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2025-12-31"}).json()["driver"] is None
        lst = _req("GET", "/drivers").json()
        me = next(x for x in lst if x["id"] == _S["drv"])
        assert [x["vehicle_id"] for x in me["affectations"]] == [_S["veh_a"]]
        assert _audits("driver_assignment", _S["assign1"], "create")[0]["detail"].startswith("Affectation créée (manual) : Léa Rochat")

    def test_11_affectation_vers_vehicule_autre_tenant_refusee(self):
        assert _assign(_S["veh_b"], {"driver_id": _S["drv"], "valid_from": "2026-01-01"}).status_code == 404  # véhicule B, admin A
        assert _assign(_S["veh_b"], {"driver_id": _S["drv"], "valid_from": "2026-01-01"}, creds=ADMIN_B).status_code == 404  # driver A, admin B
        assert _mongo().driver_assignments.count_documents({"vehicle_id": _S["veh_b"]}) == 0
        assert _mongo().driver_assignments.count_documents({"driver_id": _S["drv"], "tenant_id": {"$ne": TENANT_A}}) == 0

    def test_12_chevauchement_409_puis_remplacement_explicite_audite(self):
        r = _driver(nom="Bernasconi", prenom="Marco", email=None, matricule_interne=f"CH-{_RUN[4:8]}")
        assert r.status_code == 200
        _S["drv2"] = r.json()["id"]
        r = _assign(_S["veh_a"], {"driver_id": _S["drv2"], "valid_from": "2026-04-01"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "ASSIGNMENT_OVERLAP"
        assert r.json()["detail"]["conflicts"][0]["id"] == _S["assign1"]
        assert _assign(_S["veh_a"], {"driver_id": _S["drv2"], "valid_from": "2026-04-01", "replace": True}).status_code == 422  # motif requis
        r = _assign(_S["veh_a"], {"driver_id": _S["drv2"], "valid_from": "2026-04-01", "replace": True, "motif": "Changement de chauffeur"})
        assert r.status_code == 200, r.text
        _S["assign2"] = r.json()["id"]
        assert [c["id"] for c in r.json()["replaced"]] == [_S["assign1"]]
        old = _mongo().driver_assignments.find_one({"id": _S["assign1"]}, {"_id": 0})
        assert old["valid_to"] == "2026-03-31" and old["replaced"] is True and old["closed_by"] == ADMIN_A[0] and old["close_motif"] == "Changement de chauffeur"
        rep = _audits("driver_assignment", _S["assign1"], "replace")
        assert len(rep) == 1 and "valid_to — → 2026-03-31" in rep[0]["detail"] and "Changement de chauffeur" in rep[0]["detail"]
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2026-03-15"}).json()["driver"]["driver_id"] == _S["drv"]
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2026-05-01"}).json()["driver"]["driver_id"] == _S["drv2"]

    def test_13_historique_valid_from_valid_to_conserve(self):
        hist = _req("GET", f"/vehicles/{_S['veh_a']}/driver-assignments").json()
        assert [(h["id"], h["valid_from"], h["valid_to"]) for h in hist] == [
            (_S["assign2"], "2026-04-01", None), (_S["assign1"], "2026-01-01", "2026-03-31")]
        mine = _req("GET", f"/drivers/{_S['drv']}").json()["assignments"]
        assert mine[0]["id"] == _S["assign1"] and mine[0]["plaque"] == f"VD {_RUN[:6].upper()}" and mine[0]["active"] is False

    def test_14_fermeture_explicite_auditee(self):
        r = _req("POST", f"/driver-assignments/{_S['assign2']}/close", {"valid_to": "2026-06-30", "motif": "Départ"})
        assert r.status_code == 200 and r.json()["valid_to"] == "2026-06-30"
        assert _req("POST", f"/driver-assignments/{_S['assign2']}/close", {"valid_to": "2026-07-01"}).status_code == 409
        assert _req("POST", f"/driver-assignments/{_S['assign1']}/close", {}).status_code == 409  # déjà clôturée
        c = _audits("driver_assignment", _S["assign2"], "close")
        assert len(c) == 1 and "valid_to — → 2026-06-30" in c[0]["detail"] and "Départ" in c[0]["detail"]
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2026-07-15"}).json()["driver"] is None
        # remplacement refusé si le conflit n'est pas une affectation EN COURS (clôture explicite requise)
        r = _assign(_S["veh_a"], {"driver_id": _S["drv"], "valid_from": "2026-06-15", "replace": True, "motif": "Essai"})
        assert r.status_code == 409
        # affectation secondaire : cohabite sans conflit
        r = _assign(_S["veh_a"], {"driver_id": _S["drv"], "valid_from": "2026-06-15", "principal": False})
        assert r.status_code == 200 and r.json()["principal"] is False
        _S["assign_sec"] = r.json()["id"]

    def test_15_aucun_mapping_automatique_par_nom(self):
        r = _driver(nom="Rochat", prenom="Léa", email=None, matricule_interne=None)  # homonyme exact
        assert r.status_code == 200 and r.json()["id"] not in (_S["drv"], _S["drv_homonyme"])
        _S["drv_homonyme2"] = r.json()["id"]
        hist = _req("GET", f"/vehicles/{_S['veh_a']}/driver-assignments").json()
        assert all(h["driver_id"] != _S["drv_homonyme2"] for h in hist)  # aucune affectation déduite d'un nom
        at = _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", params={"date": "2026-02-01"}).json()
        assert at["driver"]["driver_id"] == _S["drv"]
        assert _mongo().audit_logs.count_documents({"tenant_id": TENANT_A, "entity": "driver_assignment",
                                                    "entity_id": {"$nin": [_S["assign1"], _S["assign2"], _S["assign_sec"]]}}) == 0
        assert _mongo().drivers.index_information().get("uniq_driver_tenant_id")
        assert not any(k for k, v in _mongo().drivers.index_information().items() if any(f[0] in ("nom", "prenom") for f in v["key"]))


class TestDriverIdEntites:
    def test_20_driver_id_accepte_sur_plein_amende_et_fiche(self):
        r = _req("POST", f"/vehicles/{_S['veh_a']}/fuel-transactions", {**PLEIN, "driver_id": _S["drv"]})
        assert r.status_code == 200, r.text
        _S["doc_plein"] = r.json()["document_id"]
        d = _mongo().documents.find_one({"id": _S["doc_plein"]}, {"_id": 0})
        assert d["driver_id"] == _S["drv"] and d["driver_validated_manually"] is True
        tx = _mongo().fuel_transactions.find_one({"source_document_id": _S["doc_plein"]}, {"_id": 0})
        assert tx["driver_id"] == _S["drv"]
        r = _req("POST", f"/vehicles/{_S['veh_a']}/fines", {"autorite": "Police", "numero_amende": f"N-{_RUN}", "montant": 40.0,
                                                           "delai_paiement": "2026-07-18", "motif": "Courrier", "driver_id": _S["drv2"]})
        assert r.status_code == 200 and _mongo().documents.find_one({"id": r.json()["document_id"]})["driver_id"] == _S["drv2"]
        _S["doc_amende"] = r.json()["document_id"]
        # sans driver_id : rien ne change
        r = _req("POST", f"/vehicles/{_S['veh_a2']}/fuel-transactions", {**PLEIN, "date": "2026-06-21"})
        assert r.status_code == 200 and _mongo().documents.find_one({"id": r.json()["document_id"]})["driver_id"] is None
        _S["doc_sans"] = r.json()["document_id"]
        # PATCH fiche : affecter puis retirer ("") — propagé à la transaction, audit avant/après
        r = _req("PATCH", f"/documents/{_S['doc_sans']}", {"driver_id": _S["drv"]})
        assert r.status_code == 200 and r.json()["driver_id"] == _S["drv"]
        assert _mongo().fuel_transactions.find_one({"source_document_id": _S["doc_sans"]})["driver_id"] == _S["drv"]
        assert f"driver_id: — → {_S['drv']}" in _audits("document", _S["doc_sans"], "modify")[-1]["detail"]
        r = _req("PATCH", f"/documents/{_S['doc_sans']}", {"driver_id": ""})
        assert r.status_code == 200 and r.json()["driver_id"] is None
        assert _mongo().fuel_transactions.find_one({"source_document_id": _S["doc_sans"]})["driver_id"] is None

    def test_21_filtres_et_enrichissement_energy_documents(self):
        e = _req("GET", "/energy", params={"driver_id": _S["drv"]}).json()
        assert [t["source_document_id"] for t in e["transactions"]] == [_S["doc_plein"]]
        assert e["transactions"][0]["driver_nom"].startswith("Léa Rochat")
        assert _req("GET", "/energy", params={"driver_id": _S["drv2"]}).json()["transactions"] == []
        docs = _req("GET", "/documents", params={"driver_id": _S["drv2"]}).json()
        assert [d["id"] for d in docs] == [_S["doc_amende"]] and docs[0]["driver_nom"].startswith("Marco Bernasconi")
        assert _req("GET", "/documents", params={"q": "bernasconi"}).json()[0]["id"] == _S["doc_amende"]
        ve = _req("GET", f"/vehicles/{_S['veh_a']}/energy").json()
        assert next(t for t in ve["transactions"] if t["source_document_id"] == _S["doc_plein"])["driver_nom"].startswith("Léa")
        vd = _req("GET", f"/vehicles/{_S['veh_a']}/documents").json()
        assert next(d for d in vd if d["id"] == _S["doc_amende"])["driver_nom"].startswith("Marco")

    def test_22_driver_id_autre_tenant_refuse(self):
        r = _driver(nom="Keller", email=None, matricule_interne=None, creds=ADMIN_B)
        assert r.status_code == 200
        _S["drv_b"] = r.json()["id"]
        before = _mongo().documents.count_documents({"tenant_id": TENANT_A})
        assert _req("POST", f"/vehicles/{_S['veh_a']}/fuel-transactions", {**PLEIN, "date": "2026-06-22", "driver_id": _S["drv_b"]}).status_code == 404
        assert _req("POST", f"/vehicles/{_S['veh_a']}/fines", {"autorite": "P", "montant": 1, "motif": "xxx", "driver_id": _S["drv_b"]}).status_code == 404
        assert _req("PATCH", f"/documents/{_S['doc_sans']}", {"driver_id": _S["drv_b"]}).status_code == 404
        assert _req("POST", f"/vehicles/{_S['veh_a']}/fuel-transactions", {**PLEIN, "date": "2026-06-23", "driver_id": "inexistant"}).status_code == 404
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A}) == before
        assert _mongo().documents.find_one({"id": _S["doc_sans"]})["driver_id"] is None
        # lecture croisée fail-closed
        assert _req("GET", f"/drivers/{_S['drv']}", creds=ADMIN_B).status_code == 404
        assert _req("PATCH", f"/drivers/{_S['drv']}", {"groupe": "X"}, creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/drivers/{_S['drv']}/archive", creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/driver-assignments/{_S['assign_sec']}/close", {}, creds=ADMIN_B).status_code == 404
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-assignments", creds=ADMIN_B).status_code == 404
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", creds=ADMIN_B).status_code == 404
        assert all(x["tenant_id"] == TENANT_B for x in _req("GET", "/drivers", creds=ADMIN_B).json())
        assert _req("GET", "/energy", params={"driver_id": _S["drv"]}, creds=ADMIN_B).json()["transactions"] == []


class TestLegacyEtSecurite:
    def test_30_legacy_idempotence_conducteur_et_affectation(self):
        body = {"nom": "Journal Driver", "email": None, "matricule_interne": None, "source": "legacy_import",
                "legacy_source": "journal", "legacy_id": f"drv-{_RUN}-9", "created_at": "2024-02-01T08:00:00+00:00",
                "navixy_employee_id": 12}
        ids = {_driver(body).json()["id"] for _ in range(3)}
        assert len(ids) == 1
        drv_id = ids.pop()
        d = _mongo().drivers.find_one({"id": drv_id}, {"_id": 0})
        assert d["legacy_source"] == "journal" and d["legacy_id"] == f"drv-{_RUN}-9" and d["migration_version"] == 1
        assert d["created_at"] == "2024-02-01T08:00:00+00:00" and d["created_by"] == "import" and d["navixy_employee_id"] == 12
        assert _mongo().drivers.count_documents({"tenant_id": TENANT_A, "legacy_id": f"drv-{_RUN}-9"}) == 1
        assert _audits("driver", drv_id, "legacy_replay")
        r = _driver(body, creds=ADMIN_B)  # même legacy_id, autre tenant = autre conducteur
        assert r.status_code == 200 and r.json()["id"] != drv_id
        abody = {"driver_id": drv_id, "valid_from": "2025-01-01", "valid_to": "2025-06-30", "source": "legacy_import",
                 "legacy_id": f"asg-{_RUN}-1", "created_at": "2025-01-01T00:00:00+00:00"}
        aids = {_assign(_S["veh_a2"], abody).json()["id"] for _ in range(3)}
        assert len(aids) == 1
        a = _mongo().driver_assignments.find_one({"id": aids.pop()}, {"_id": 0})
        assert a["legacy_id"] == f"asg-{_RUN}-1" and a["created_by"] == "import" and a["migration_version"] == 1
        assert _mongo().driver_assignments.count_documents({"tenant_id": TENANT_A, "legacy_id": f"asg-{_RUN}-1"}) == 1
        assert _driver({"nom": "X", "source": "legacy_import"}).status_code == 422  # legacy_id requis
        for coll in ("drivers", "driver_assignments"):
            assert _mongo()[coll].index_information()["uniq_legacy_key"]["unique"] is True

    def test_31_read_only_toutes_ecritures_403_base_inchangee(self):
        db = _mongo()
        n_d, n_a = db.drivers.count_documents({"tenant_id": TENANT_A}), db.driver_assignments.count_documents({"tenant_id": TENANT_A})
        assert _driver(email=None, matricule_interne=None, creds=RO_A).status_code == 403
        assert _req("PATCH", f"/drivers/{_S['drv']}", {"groupe": "RO"}, creds=RO_A).status_code == 403
        assert _req("POST", f"/drivers/{_S['drv']}/archive", creds=RO_A).status_code == 403
        assert _assign(_S["veh_a2"], {"driver_id": _S["drv"], "valid_from": "2026-07-01"}, creds=RO_A).status_code == 403
        assert _req("POST", f"/driver-assignments/{_S['assign_sec']}/close", {}, creds=RO_A).status_code == 403
        assert _req("PATCH", f"/documents/{_S['doc_sans']}", {"driver_id": _S["drv"]}, creds=RO_A).status_code == 403
        assert db.drivers.count_documents({"tenant_id": TENANT_A}) == n_d and db.driver_assignments.count_documents({"tenant_id": TENANT_A}) == n_a
        assert db.drivers.find_one({"id": _S["drv"]})["groupe"] == "Fribourg"
        # lecture autorisée
        assert _req("GET", "/drivers", creds=RO_A).status_code == 200
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-assignments", creds=RO_A).status_code == 200
        assert _req("GET", f"/vehicles/{_S['veh_a']}/driver-at", creds=RO_A).status_code == 200

    def test_32_audit_conducteur_et_affectations_complet(self):
        acts = {a["action"] for a in _audits("driver", _S["drv"])}
        assert {"create", "modify"} <= acts
        acts2 = {a["action"] for a in _audits("driver", _S["drv_homonyme"])}
        assert {"create", "modify", "archive", "restore"} <= acts2
        assert {a["action"] for a in _audits("driver_assignment", _S["assign1"])} == {"create", "replace"}
        assert {a["action"] for a in _audits("driver_assignment", _S["assign2"])} == {"create", "close"}
        for a in _audits("driver", _S["drv"]) + _audits("driver_assignment", _S["assign1"]):
            assert a["user"] == ADMIN_A[0] and a["ip"] and a["created_at"] and a["tenant_id"] == TENANT_A
        c = _audits("document", _S["doc_plein"], "create")[0]["detail"]
        assert "conducteur Léa Rochat" in c

    def test_33_aucune_donnee_journal_reelle(self):
        db = _mongo()
        q = {"tenant_id": {"$nin": [TENANT_A, TENANT_B]}, "legacy_id": {"$exists": True}}
        assert db.drivers.count_documents(q) == 0 and db.driver_assignments.count_documents(q) == 0
        assert db.drivers.count_documents({"tenant_id": "default"}) == 0 and db.driver_assignments.count_documents({"tenant_id": "default"}) == 0
        assert db.users.count_documents({"role": {"$in": ["driver", "manager"]}}) == 0  # rôles lot H non créés
