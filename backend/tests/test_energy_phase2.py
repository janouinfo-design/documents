"""Phase 2 — Énergie & carburant : ticket validé → fuel_transaction (document = coût, transaction = données énergie)."""
import re
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-en-a-{_RUN}"
TENANT_B = f"pytest-en-b-{_RUN}"
ADMIN_A = (f"en-adm-a-{_RUN}@pytest.ch", f"EnAdmA-{_RUN}-1")
RO_A = (f"en-ro-a-{_RUN}@pytest.ch", f"EnRoA-{_RUN}-1")
ADMIN_B = (f"en-adm-b-{_RUN}@pytest.ch", f"EnAdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
PLATE_A = f"VD {_RUN[:6].upper()}"

MIGROL = {"station": "Migrol Bern Wankdorf", "date": "2026-06-12", "heure": "08:42", "montant": 74.17,
          "devise": "CHF", "litres": 41.2, "prix_litre": 1.8, "type_carburant": "Diesel",
          "kilometrage": 12900, "carte_last4": "1234"}
RECHARGE = {"station": "Ionity Grauholz", "date": "2026-06-14", "heure": "19:05", "montant": 31.5,
            "devise": "CHF", "energie_kwh": 45.0, "prix_kwh": 0.7, "type_carburant": "Électricité",
            "kilometrage": 20500}

_S = {}
_cache = {}


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


def _seed_ticket(vehicle_id, tenant=TENANT_A, fields=None):
    """Ticket déjà analysé (OCR simulé) — aucun appel LLM."""
    fields = dict(fields if fields is not None else MIGROL)
    doc_id = str(uuid.uuid4())
    _mongo().documents.insert_one({
        "id": doc_id, "vehicle_id": vehicle_id, "tenant_id": tenant, "folder": "Factures",
        "original_filename": f"ticket_{doc_id[:8]}.jpg", "storage_path": f"pytest/{doc_id}.jpg",
        "content_type": "image/jpeg", "size": 1, "pages": [], "sha256": uuid.uuid4().hex,
        "document_type": "ticket_carburant", "extraction_status": "done", "a_verifier": True, "source": "scan",
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "extracted_fields": [{"field": k, "value": v, "confidence": 0.95, "status": "found",
                              "target": "document", "current_value": None, "conflict": False}
                             for k, v in fields.items()],
    })
    return doc_id


def _validate(doc_id, fields, category="CARBURANT", creds=ADMIN_A, **extra):
    body = {"document_type": "ticket_carburant", "fields": fields, **extra}
    if category is not None:
        body["business_category"] = category
    return requests.post(f"{_BASE}/api/documents/{doc_id}/validate", json=body, headers=_h(creds), timeout=30)


def _costs(creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/costs", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _veh_total(vehicle_id, creds=ADMIN_A):
    return round(sum(i["cout_annuel"] for i in _costs(creds)["items"] if i["vehicle_id"] == vehicle_id), 2)


def _doc(doc_id):
    return _mongo().documents.find_one({"id": doc_id}, {"_id": 0})


def _tx(doc_id=None, vehicle_id=None, active_only=True):
    q = {"tenant_id": TENANT_A}
    if doc_id:
        q["source_document_id"] = doc_id
    if vehicle_id:
        q["vehicle_id"] = vehicle_id
    if active_only:
        q["is_deleted"] = False
    return list(_mongo().fuel_transactions.find(q, {"_id": 0}))


def _vehicle(payload, creds=ADMIN_A):
    r = requests.post(f"{_BASE}/api/vehicles", json=payload, headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


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
    _S["veh_a"] = _vehicle({"plaque": PLATE_A, "kilometrage": 12345, "type_carburant": "Diesel"})
    _S["veh_ev"] = _vehicle({"plaque": f"ZH {_RUN[:6].upper()}", "type_carburant": "Électrique", "kilometrage": 20000})
    _S["veh_can"] = _vehicle({"plaque": f"GE {_RUN[:6].upper()}", "type_carburant": "Essence", "kilometrage": 50000})
    _S["veh_t"] = _vehicle({"plaque": f"FR {_RUN[:6].upper()}", "type_carburant": "Diesel", "kilometrage": 12345})
    _S["veh_b"] = _vehicle({"plaque": f"BE {_RUN[:6].upper()}"}, creds=ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings",
                     "fuel_transactions", "fuel_transaction_matches", "fuel_anomalies"):  # Lot F : hook validation
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestTicketComplet:
    def test_ticket_complet_cree_une_transaction_et_un_seul_cout(self):
        before = _veh_total(_S["veh_a"])
        doc_id = _seed_ticket(_S["veh_a"])
        r = _validate(doc_id, MIGROL)
        assert r.status_code == 200, r.text
        res = r.json()
        tx = res["fuel_transaction"]
        assert tx and tx["source_document_id"] == doc_id and tx["vehicle_id"] == _S["veh_a"]
        assert tx["tenant_id"] == TENANT_A and tx["created_from"] == "document"
        assert tx["montant"] == 74.17 and tx["litres"] == 41.2 and tx["prix_litre"] == 1.8
        assert tx["energie"] == "thermique" and tx["type_carburant"] == "Diesel"
        assert tx["date"] == "2026-06-12" and tx["heure"] == "08:42" and tx["date_heure"] == "2026-06-12T08:42:00"
        assert tx["kilometrage"] == 12900 and tx["carte_last4"] == "1234" and tx["validated_by"] == ADMIN_A[0]
        assert res["cost"] == {"document_id": doc_id, "montant": 74.17, "devise": "CHF", "frequence": "unique",
                               "business_category": "CARBURANT", "category_label": "Carburant"}
        # Document = coût (champs V2) + classification
        d = _doc(doc_id)
        assert d["document_type"] == "ticket_carburant" and d["business_category"] == "CARBURANT"
        assert d["montant"] == 74.17 and d["devise"] == "CHF" and d["frequence"] == "unique"
        assert d["date_debut"] == "2026-06-12" and d["fournisseur"] == "Migrol Bern Wankdorf"
        assert d["kilometrage_releve"] == 12900 and d["extraction_status"] == "validated"
        # 1 document = 1 transaction en base
        rows = _tx(doc_id)
        assert len(rows) == 1 and rows[0]["id"] == tx["id"]
        # Anti double comptage : delta coûts = +74.17, jamais +148.34
        items = [i for i in _costs()["items"] if i["vehicle_id"] == _S["veh_a"] and i["montant"] == 74.17]
        assert len(items) == 1 and items[0]["key"] == f"doc:{doc_id}" and items[0]["source"] == "document"
        assert items[0]["category"] == "Carburant" and items[0]["business_category"] == "CARBURANT"
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 74.17
        _S["doc_migrol"], _S["tx_migrol"] = doc_id, tx["id"]

    def test_collect_costs_ne_lit_jamais_fuel_transactions(self):
        src = open("/app/backend/server.py", encoding="utf-8").read()
        m = re.search(r"async def collect_costs\(.*?(?=\n(?:async def |def |@api_router|class ))", src, re.S)
        assert m, "collect_costs introuvable"
        assert "fuel_transactions" not in m.group(0)
        for name in ("list_costs", "vehicle_costs", "costs_csv"):
            fm = re.search(rf"async def {name}\(.*?(?=\n(?:async def |def |@api_router|class ))", src, re.S)
            if fm:
                assert "fuel_transactions" not in fm.group(0), name

    def test_kilometrage_ticket_jamais_ecrit_sur_le_vehicule(self):
        v = _mongo().vehicles.find_one({"id": _S["veh_a"]}, {"_id": 0, "kilometrage": 1})
        assert v["kilometrage"] == 12345

    def test_revalidation_idempotente(self):
        doc_id = _S["doc_migrol"]
        before = _veh_total(_S["veh_a"])
        r = _validate(doc_id, {**MIGROL, "station": "Migrol Bern Wankdorf (corrigé)"})
        assert r.status_code == 200, r.text
        assert r.json()["fuel_transaction"]["id"] == _S["tx_migrol"]
        rows = _tx(doc_id)
        assert len(rows) == 1 and rows[0]["station"] == "Migrol Bern Wankdorf (corrigé)"
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A, "source_document_id": doc_id}) == 1
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 0.0
        assert len([i for i in _costs()["items"] if i["key"] == f"doc:{doc_id}"]) == 1

    def test_index_unique_source_document(self):
        with pytest.raises(DuplicateKeyError):
            _mongo().fuel_transactions.insert_one({"id": str(uuid.uuid4()), "tenant_id": TENANT_A,
                                                   "vehicle_id": _S["veh_a"], "source_document_id": _S["doc_migrol"],
                                                   "is_deleted": False})

    def test_energie_endpoints(self):
        r = requests.get(f"{_BASE}/api/energy", headers=_h(), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        ids = {t["id"] for t in data["transactions"]}
        assert _S["tx_migrol"] in ids
        row = next(t for t in data["transactions"] if t["id"] == _S["tx_migrol"])
        assert row["plaque"] == PLATE_A and row["montant"] == 74.17
        bv = next(b for b in data["by_vehicle"] if b["vehicle_id"] == _S["veh_a"])
        assert bv["depenses"] == 74.17 and bv["litres"] == 41.2 and bv["prix_moyen_l"] == 1.8
        assert bv["conso_tickets"] is None  # 1 seul plein → données insuffisantes, jamais d'estimation
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/energy", headers=_h(), timeout=30)
        assert r.status_code == 200
        ve = r.json()
        assert ve["totals"]["transactions"] == 1 and ve["totals"]["depenses"] == 74.17
        assert ve["conso_tickets"] is None and ve["kilometrage_vehicule"] == 12345
        r = requests.get(f"{_BASE}/api/energy", params={"date_from": "2026-07-01"}, headers=_h(), timeout=30)
        assert r.status_code == 200 and _S["tx_migrol"] not in {t["id"] for t in r.json()["transactions"]}


class TestTicketIncompletEtCoherence:
    def test_ticket_incomplet_sans_litres(self):
        doc_id = _seed_ticket(_S["veh_a"], fields={"station": "Shell", "date": "2026-06-20", "montant": 55.0})
        r = _validate(doc_id, {"station": "Shell", "date": "2026-06-20", "montant": 55.0})
        assert r.status_code == 200, r.text
        tx = r.json()["fuel_transaction"]
        assert tx["montant"] == 55.0 and tx["litres"] is None and tx["prix_litre"] is None
        assert tx["heure"] is None and tx["date_heure"] == "2026-06-20" and tx["kilometrage"] is None
        assert tx["devise"] == "CHF" and tx["energie"] == "thermique"
        assert r.json()["conso_update"] == {"applied": False, "reason": "INSUFFICIENT_DATA"}
        assert r.json()["cost"]["montant"] == 55.0
        _S["doc_shell"] = doc_id

    def test_ticket_sans_montant_ni_quantite_aucune_transaction(self):
        doc_id = _seed_ticket(_S["veh_a"], fields={"station": "Coop", "date": "2026-06-21"})
        r = _validate(doc_id, {"station": "Coop", "date": "2026-06-21"})
        assert r.status_code == 200, r.text
        assert r.json()["fuel_transaction"] is None and r.json()["cost"] is None
        assert "TRANSACTION_SKIPPED" in {w["code"] for w in r.json()["warnings"]}
        assert _tx(doc_id) == []

    def test_incoherence_litres_prix_avertissement_non_bloquant(self):
        fields = {**MIGROL, "date": "2026-06-22", "litres": 30.0, "prix_litre": 1.8, "montant": 74.17}
        doc_id = _seed_ticket(_S["veh_a"], fields=fields)
        r = requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(), timeout=30)
        assert r.status_code == 200
        assert "AMOUNT_MISMATCH" in {w["code"] for w in r.json()["coherence_warnings"]}
        assert r.json()["suggested_business_category"] == "CARBURANT"
        r = _validate(doc_id, fields)
        assert r.status_code == 200, r.text
        assert "AMOUNT_MISMATCH" in {w["code"] for w in r.json()["warnings"]}
        tx = r.json()["fuel_transaction"]
        assert tx["litres"] == 30.0 and tx["montant"] == 74.17  # valeurs conservées telles quelles, jamais corrigées

    def test_kilometrage_ticket_superieur_odometre_avertissement(self):
        fields = {**MIGROL, "date": "2026-06-23", "kilometrage": 99999}
        doc_id = _seed_ticket(_S["veh_a"], fields=fields)
        r = _validate(doc_id, fields)
        assert r.status_code == 200, r.text
        assert "ODOMETER_INCONSISTENT" in {w["code"] for w in r.json()["warnings"]}
        assert _mongo().vehicles.find_one({"id": _S["veh_a"]}, {"_id": 0, "kilometrage": 1})["kilometrage"] == 12345


class TestElectrique:
    def test_recharge_ev_sans_litres(self):
        before = _veh_total(_S["veh_ev"])
        doc_id = _seed_ticket(_S["veh_ev"], fields=RECHARGE)
        r = requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(), timeout=30)
        assert r.json()["suggested_business_category"] == "ENERGIE_ELECTRIQUE"
        r = _validate(doc_id, RECHARGE, category="ENERGIE_ELECTRIQUE")
        assert r.status_code == 200, r.text
        tx = r.json()["fuel_transaction"]
        assert tx["energie"] == "electrique" and tx["energie_kwh"] == 45.0 and tx["prix_kwh"] == 0.7
        assert tx["litres"] is None and tx["prix_litre"] is None and tx["montant"] == 31.5
        assert r.json()["cost"]["category_label"] == "Énergie électrique"
        assert round(_veh_total(_S["veh_ev"]) - before, 2) == 31.5
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_ev']}/energy", headers=_h(), timeout=30)
        ve = r.json()
        assert ve["totals"]["energie_kwh"] == 45.0 and ve["totals"]["litres"] == 0
        assert ve["totals"]["prix_moyen_kwh"] == 0.7 and ve["totals"]["prix_moyen_l"] is None
        _S["doc_ev"] = doc_id

    def test_conso_kwh_par_recharges_et_jamais_en_litres(self):
        f2 = {**RECHARGE, "date": "2026-06-20", "kilometrage": 20800, "energie_kwh": 54.0, "montant": 37.8}
        r = _validate(_seed_ticket(_S["veh_ev"], fields=f2), f2, category="ENERGIE_ELECTRIQUE")
        assert r.status_code == 200, r.text
        assert r.json()["conso_update"]["applied"] is False
        assert r.json()["conso_update"]["reason"] in ("INSUFFICIENT_DATA", "ELECTRIC_VEHICLE")
        v = _mongo().vehicles.find_one({"id": _S["veh_ev"]}, {"_id": 0, "conso_reelle_l_100km": 1, "conso_reelle_source": 1})
        assert not v.get("conso_reelle_l_100km")  # jamais de L/100 sur un véhicule électrique
        ve = requests.get(f"{_BASE}/api/vehicles/{_S['veh_ev']}/energy", headers=_h(), timeout=30).json()
        assert ve["conso_tickets"] is None
        assert ve["conso_kwh_tickets"] == {"value": 18.0, "unit": "kWh/100km", "km": 300, "kwh": 54.0, "n": 2,
                                           "from": "2026-06-14", "to": "2026-06-20", "source": "fuel_transactions"}


class TestPlaqueDoublons:
    def test_plaque_differente_avertissement_sans_reaffectation(self):
        fields = {**MIGROL, "date": "2026-06-24", "plaque": "ZH 999 999"}
        doc_id = _seed_ticket(_S["veh_a"], fields=fields)
        r = _validate(doc_id, fields)
        assert r.status_code == 200, r.text
        w = next(w for w in r.json()["warnings"] if w["code"] == "PLATE_MISMATCH")
        assert w["document_plate"] == "ZH 999 999" and w["vehicle_plate"] == PLATE_A
        assert _doc(doc_id)["vehicle_id"] == _S["veh_a"] and _doc(doc_id)["plaque_mentionnee"] == "ZH 999 999"
        assert _tx(doc_id)[0]["vehicle_id"] == _S["veh_a"] and _tx(doc_id)[0]["plaque_mentionnee"] == "ZH 999 999"

    def test_doublon_fichier_sha256_signale(self):
        data = PNG + _RUN.encode()
        r1 = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents", headers=_h(),
                           files={"file": ("t1.png", data, "image/png")}, data={"folder": "Factures"}, timeout=30)
        r2 = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents", headers=_h(),
                           files={"file": ("t2.png", data, "image/png")}, data={"folder": "Factures"}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["duplicate_of"] is None
        assert r2.json()["duplicate_of"]["document_id"] == r1.json()["id"]  # avertissement, jamais de blocage/suppression
        assert _doc(r2.json()["id"])["is_deleted"] is False

    def test_doublon_transaction_409_puis_confirmation_explicite(self):
        fields = {**MIGROL, "station": "Migrol (second ticket)"}  # même véhicule + date + montant + litres
        doc_id = _seed_ticket(_S["veh_a"], fields=fields)
        before = _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A, "is_deleted": False})
        r = _validate(doc_id, fields)
        assert r.status_code == 409, r.text
        det = r.json()["detail"]
        assert det["code"] == "DUPLICATE_SUSPECTED" and det["kind"] == "transaction"
        assert det["existing_document_id"] == _S["doc_migrol"]
        # Aucune écriture tant que l'utilisateur n'a pas confirmé
        assert _tx(doc_id) == [] and _doc(doc_id)["extraction_status"] == "done"
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A, "is_deleted": False}) == before
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A, "source_document_id": _S["doc_migrol"]}) == 1
        r = _validate(doc_id, fields, duplicate_override=True)
        assert r.status_code == 200, r.text
        assert "DUPLICATE_OVERRIDDEN" in {w["code"] for w in r.json()["warnings"]}
        assert len(_tx(doc_id)) == 1
        _S["doc_dup"] = doc_id


class TestSecurite:
    def test_read_only_validate_403_et_base_inchangee(self):
        doc_id = _seed_ticket(_S["veh_a"], fields={**MIGROL, "date": "2026-06-25"})
        snapshot = _doc(doc_id)
        n_tx = _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A})
        r = _validate(doc_id, {**MIGROL, "date": "2026-06-25"}, creds=RO_A)
        assert r.status_code == 403, r.text
        after = _doc(doc_id)
        assert after == snapshot
        assert after["extraction_status"] == "done" and "validated_at" not in after
        assert "business_category" not in after and "montant" not in after
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A}) == n_tx
        assert _tx(doc_id) == []
        _S["doc_ro"] = doc_id

    def test_read_only_lecture_ok_ecritures_403(self):
        assert requests.get(f"{_BASE}/api/energy", headers=_h(RO_A), timeout=30).status_code == 200
        assert requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/energy", headers=_h(RO_A), timeout=30).status_code == 200
        assert requests.patch(f"{_BASE}/api/documents/{_S['doc_migrol']}", json={"montant": 1},
                              headers=_h(RO_A), timeout=30).status_code == 403
        assert requests.delete(f"{_BASE}/api/documents/{_S['doc_shell']}", headers=_h(RO_A), timeout=30).status_code == 403
        assert _doc(_S["doc_migrol"])["montant"] == 74.17 and _doc(_S["doc_shell"])["is_deleted"] is False

    def test_cross_tenant_404_et_isolation(self):
        assert _validate(_S["doc_ro"], MIGROL, creds=ADMIN_B).status_code == 404
        assert _tx(_S["doc_ro"]) == []
        assert requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/energy", headers=_h(ADMIN_B), timeout=30).status_code == 404
        assert requests.delete(f"{_BASE}/api/documents/{_S['doc_migrol']}", headers=_h(ADMIN_B), timeout=30).status_code == 404
        r = requests.get(f"{_BASE}/api/energy", headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 200 and r.json()["transactions"] == [] and r.json()["totals"]["depenses"] == 0
        r = requests.get(f"{_BASE}/api/energy", params={"vehicle_id": _S["veh_a"]}, headers=_h(ADMIN_B), timeout=30)
        assert r.json()["transactions"] == []
        assert _S["tx_migrol"] not in {i.get("document_id") for i in _costs(ADMIN_B)["items"]}

    def test_admin_temoin_meme_document_valide(self):
        r = _validate(_S["doc_ro"], {**MIGROL, "date": "2026-06-25"})
        assert r.status_code == 200, r.text
        assert len(_tx(_S["doc_ro"])) == 1 and _doc(_S["doc_ro"])["extraction_status"] == "validated"
        assert len([i for i in _costs()["items"] if i["key"] == f"doc:{_S['doc_ro']}"]) == 1

    def test_suppression_document_source_bloquee_409(self):
        r = requests.delete(f"{_BASE}/api/documents/{_S['doc_migrol']}", headers=_h(), timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "SOURCE_OF_FUEL_TRANSACTION"
        assert _doc(_S["doc_migrol"])["is_deleted"] is False
        assert len(_tx(_S["doc_migrol"])) == 1
        assert f"doc:{_S['doc_migrol']}" in {i["key"] for i in _costs()["items"]}

    def test_suppression_document_sans_transaction_ok(self):
        doc_id = _seed_ticket(_S["veh_a"], fields={"station": "X"})
        assert requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(), timeout=30).status_code == 200
        assert _doc(doc_id)["is_deleted"] is True


class TestConsoPriorite:
    def _two_fills(self, vid, km0):
        f1 = {**MIGROL, "date": "2026-05-01", "kilometrage": km0, "litres": 40.0, "prix_litre": 1.8, "montant": 72.0}
        f2 = {**MIGROL, "date": "2026-05-20", "kilometrage": km0 + 500, "litres": 35.0, "prix_litre": 1.8, "montant": 63.0}
        for f in (f1, f2):
            r = _validate(_seed_ticket(vid, fields=f), f)
            assert r.status_code == 200, r.text
        return r.json()["conso_update"]

    def test_can_prioritaire_jamais_remplace_par_tickets(self):
        _mongo().vehicles.update_one({"id": _S["veh_can"]}, {"$set": {"conso_reelle_l_100km": 6.3, "conso_reelle_source": "can"}})
        upd = self._two_fills(_S["veh_can"], 50000)
        assert upd["applied"] is False and upd["reason"] == "CAN_PRIORITY"
        assert upd["conso_tickets"]["value"] == 7.0 and upd["conso_tickets"]["source"] == "fuel_transactions"
        v = _mongo().vehicles.find_one({"id": _S["veh_can"]}, {"_id": 0, "conso_reelle_l_100km": 1, "conso_reelle_source": 1})
        assert v == {"conso_reelle_l_100km": 6.3, "conso_reelle_source": "can"}
        ve = requests.get(f"{_BASE}/api/vehicles/{_S['veh_can']}/energy", headers=_h(), timeout=30).json()
        assert ve["conso_reelle_source"] == "can" and ve["conso_reelle_l_100km"] == 6.3 and ve["conso_tickets"]["value"] == 7.0

    def test_sans_can_tickets_alimentent_la_conso_reelle(self):
        upd = self._two_fills(_S["veh_t"], 12900)  # 2026-05-01 → 12900 km ; 2026-05-20 → 13400 km (+500) ; 35 L
        assert upd["applied"] is True
        assert upd["conso"]["value"] == 7.0 and upd["conso"]["unit"] == "L/100km" and upd["conso"]["km"] == 500
        v = _mongo().vehicles.find_one({"id": _S["veh_t"]}, {"_id": 0, "conso_reelle_l_100km": 1, "conso_reelle_source": 1})
        assert v == {"conso_reelle_l_100km": 7.0, "conso_reelle_source": "fuel_transactions"}
        meta = _mongo().vehicle_field_meta.find_one({"vehicle_id": _S["veh_t"], "field": "conso_reelle_l_100km"}, {"_id": 0})
        assert meta["source"] == "fuel_transactions" and meta["measurement_type"] == "measured"
        # Le véhicule reste source canonique de l'odomètre : inchangé malgré les km des tickets
        assert _mongo().vehicles.find_one({"id": _S["veh_t"]}, {"_id": 0, "kilometrage": 1})["kilometrage"] == 12345
        ve = requests.get(f"{_BASE}/api/vehicles/{_S['veh_t']}/energy", headers=_h(), timeout=30).json()
        assert ve["conso_reelle_source"] == "fuel_transactions" and ve["conso_tickets"]["value"] == 7.0
