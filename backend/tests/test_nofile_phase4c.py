"""Phase 4C — Lot B : document métier SANS fichier (D1) + lecture de coût générique D7 + convention D5."""
import re
import uuid
from datetime import datetime, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-nf-a-{_RUN}"
TENANT_B = f"pytest-nf-b-{_RUN}"
ADMIN_A = (f"nf-adm-a-{_RUN}@pytest.ch", f"NfAdmA-{_RUN}-1")
RO_A = (f"nf-ro-a-{_RUN}@pytest.ch", f"NfRoA-{_RUN}-1")
ADMIN_B = (f"nf-adm-b-{_RUN}@pytest.ch", f"NfAdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 120
PLEIN = {"station": "Agrola Payerne", "date": "2026-06-20", "heure": "07:15", "montant": 88.4, "devise": "CHF",
         "litres": 48.0, "prix_litre": 1.842, "type_carburant": "Diesel", "kilometrage": 13500,
         "business_category": "CARBURANT", "motif": "Ticket perdu — plein du 20.06 (relevé carte)"}
AMENDE = {"autorite": "Police cantonale fribourgeoise", "numero_amende": f"FR-{_RUN}-01", "date_infraction": "2026-06-18",
          "montant": 40.0, "devise": "CHF", "delai_paiement": "2026-07-18", "motif": "Amende reçue par courrier, non scannée"}
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


def _post(path, body, creds=ADMIN_A):
    return requests.post(f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=30)


def _fuel(vehicle_id, body=None, creds=ADMIN_A, **over):
    return _post(f"/vehicles/{vehicle_id}/fuel-transactions", {**(body if body is not None else PLEIN), **over}, creds)


def _fine(vehicle_id, body=None, creds=ADMIN_A, **over):
    return _post(f"/vehicles/{vehicle_id}/fines", {**(body if body is not None else AMENDE), **over}, creds)


def _attach(doc_id, creds=ADMIN_A, name="justif.png", data=PNG):
    return requests.post(f"{_BASE}/api/documents/{doc_id}/attach-file", files={"file": (name, data, "image/png")},
                         headers=_h(creds), timeout=30)


def _costs(creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/costs", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _veh_total(vehicle_id, creds=ADMIN_A):
    return round(sum(i["cout_annuel"] for i in _costs(creds)["items"] if i["vehicle_id"] == vehicle_id), 2)


def _item(doc_id, creds=ADMIN_A):
    return next((i for i in _costs(creds)["items"] if i["document_id"] == doc_id), None)


def _pending(doc_id, creds=ADMIN_A):
    return next((i for i in _costs(creds)["pending_fx"] if i["document_id"] == doc_id), None)


def _doc(doc_id):
    return _mongo().documents.find_one({"id": doc_id}, {"_id": 0})


def _txs(doc_id):
    return list(_mongo().fuel_transactions.find({"source_document_id": doc_id, "is_deleted": False}, {"_id": 0}))


def _audits(doc_id, action=None, entity="document"):
    q = {"tenant_id": TENANT_A, "entity": entity, "entity_id": doc_id}
    if action:
        q["action"] = action
    return list(_mongo().audit_logs.find(q, {"_id": 0}))


def _vehicle(payload, creds=ADMIN_A):
    r = _post("/vehicles", payload, creds)
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
    _S["veh_fx"] = _vehicle({"plaque": f"GE {_RUN[:6].upper()}", "kilometrage": 1000, "type_carburant": "Essence"})
    _S["veh_b"] = _vehicle({"plaque": f"BE {_RUN[:6].upper()}"}, creds=ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings", "fuel_transactions"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestDocumentSansFichierManual:
    def test_01_plein_manual_cree_document_sans_fichier_et_une_transaction(self):
        before = _veh_total(_S["veh_a"])
        r = _fuel(_S["veh_a"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] and body["created"] is True
        _S["doc_plein"] = body["document_id"]
        d = _doc(_S["doc_plein"])
        assert d["storage_path"] is None and d["justificatif_absent"] is True and d["source"] == "manual"
        assert d["document_type"] == "ticket_carburant" and d["extraction_status"] == "validated"
        assert d["motif_saisie"] == PLEIN["motif"] and d["montant"] == 88.4 and d["devise"] == "CHF"
        assert d["business_category"] == "CARBURANT" and d["montant_chf"] is None
        assert body["document"]["statut"] == "VALIDE" and body["document"]["justificatif_absent"] is True
        assert _mongo().files.count_documents({"tenant_id": TENANT_A}) == 0  # aucun fichier requis
        txs = _txs(_S["doc_plein"])
        assert len(txs) == 1 and txs[0]["source_document_id"] == _S["doc_plein"]
        assert txs[0]["created_from"] == "manual" and txs[0]["motif_saisie"] == PLEIN["motif"]
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 88.4  # coût compté exactement une fois
        assert body["cost"]["montant_chf"] == 88.4 and body["cost"]["pending_fx"] is False

    def test_02_convention_d5_zurich_sur_la_transaction(self):
        tx = _txs(_S["doc_plein"])[0]
        assert tx["date_heure"] == "2026-06-20T07:15:00" and tx["date_heure_source"] == "2026-06-20T07:15"
        assert tx["date_heure_tz"] == "Europe/Zurich" and tx["date_heure_tz_assumed"] is False

    def test_03_motif_obligatoire_et_validations(self):
        assert _fuel(_S["veh_a"], motif="").status_code == 422
        assert _fuel(_S["veh_a"], business_category="ENTRETIEN", motif="x" * 5).status_code == 422
        assert _fuel(_S["veh_a"], date="pas-une-date").status_code == 422
        assert _fuel(_S["veh_a"], source="import").status_code == 422
        assert _fuel(_S["veh_a"], source="legacy_import", legacy_id=None).status_code == 422
        assert _fine(_S["veh_a"], autorite="  ").status_code == 422
        assert _fine(_S["veh_a"], motif="").status_code == 422
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A, "is_deleted": False}) == 1

    def test_04_doublon_transaction_409_puis_override(self):
        r = _fuel(_S["veh_a"], motif="Second essai identique")
        assert r.status_code == 409 and r.json()["detail"]["kind"] == "transaction"
        assert r.json()["detail"]["existing_document_id"] == _S["doc_plein"]
        before = _veh_total(_S["veh_a"])
        r = _fuel(_S["veh_a"], motif="Deux pleins identiques le même jour (2 véhicules partagés)", duplicate_override=True)
        assert r.status_code == 200 and any(w["code"] == "DUPLICATE_OVERRIDDEN" for w in r.json()["warnings"])
        _S["doc_plein2"] = r.json()["document_id"]
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 88.4

    def test_05_endpoints_fichier_sans_binaire_reponse_propre_jamais_500(self):
        doc_id = _S["doc_plein"]
        r = requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(), timeout=30)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "NO_FILE"
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents/scan", data={"document_id": doc_id},
                          headers=_h(), timeout=60)
        assert r.status_code in (409, 503), r.text  # 503 = scan non configuré, jamais 500
        if r.status_code == 409:
            assert r.json()["detail"]["code"] == "NO_FILE"
        r = _post(f"/vehicles/{_S['veh_a']}/photo/from-document", {"document_id": doc_id})
        assert r.status_code == 422
        r = requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(), timeout=30)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "SOURCE_OF_FUEL_TRANSACTION"
        listed = requests.get(f"{_BASE}/api/documents", params={"vehicle_id": _S["veh_a"]}, headers=_h(), timeout=30).json()
        me = next(d for d in listed if d["id"] == doc_id)
        assert me["justificatif_absent"] is True and me["storage_path"] is None and me["label"].startswith("Plein Agrola")
        energy = requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/energy", headers=_h(), timeout=30).json()
        assert sum(1 for t in energy["transactions"] if t["source_document_id"] == doc_id) == 1

    def test_06_attacher_fichier_plus_tard_meme_document_pas_de_deuxieme_cout(self):
        doc_id = _S["doc_plein"]
        before = _veh_total(_S["veh_a"])
        n_docs = _mongo().documents.count_documents({"tenant_id": TENANT_A, "is_deleted": False})
        r = _attach(doc_id)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["id"] == doc_id and out["storage_path"] and out["justificatif_absent"] is False
        assert out["original_filename"] == "justif.png" and out["duplicate_of"] is None
        d = _doc(doc_id)
        assert d["sha256"] and d["montant"] == 88.4 and d["file_attached_by"] == ADMIN_A[0]
        assert _veh_total(_S["veh_a"]) == before
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A, "is_deleted": False}) == n_docs
        assert len(_txs(doc_id)) == 1  # 1 document carburant = max 1 transaction, même après le justificatif
        r = requests.get(f"{_BASE}/api/files/{d['storage_path']}", headers=_h(), timeout=30)
        assert r.status_code == 200 and r.content == PNG
        assert _attach(doc_id).status_code == 409
        assert _attach(doc_id).json()["detail"]["code"] == "FILE_ALREADY_PRESENT"

    def test_07_attach_sha256_dedup_avertissement(self):
        r = _attach(_S["doc_plein2"])
        assert r.status_code == 200 and r.json()["duplicate_of"]["document_id"] == _S["doc_plein"]

    def test_08_amende_manuelle_cout_echeance_statut_a_payer(self):
        before = _veh_total(_S["veh_a"])
        r = _fine(_S["veh_a"])
        assert r.status_code == 200, r.text
        body = r.json()
        _S["doc_amende"] = body["document_id"]
        d = _doc(_S["doc_amende"])
        assert d["storage_path"] is None and d["justificatif_absent"] is True and d["document_type"] == "amende"
        assert d["montant"] == 40.0 and d["fournisseur"] == AMENDE["autorite"] and d["numero"] == AMENDE["numero_amende"]
        assert d["date_debut"] == "2026-06-18" and d["date_expiration"] == "2026-07-18" and d["payee"] is False
        assert body["document"]["statut"] in ("A_PAYER", "EN_RETARD")
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 40.0
        item = _item(_S["doc_amende"])
        assert item["category"] == "Amende" and item["justificatif_absent"] is True
        dl = requests.get(f"{_BASE}/api/deadlines", headers=_h(), timeout=30).json()
        mine = [i for i in dl["items"] if i["key"] == f"doc:{_S['doc_amende']}"]
        assert len(mine) == 1 and mine[0]["is_fine"] is True
        r = _fine(_S["veh_a"], motif="Même amende saisie deux fois")
        assert r.status_code == 409 and r.json()["detail"]["kind"] == "amende"
        r = requests.delete(f"{_BASE}/api/documents/{_S['doc_amende']}", headers=_h(), timeout=30)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "VALIDATED_FINE"
        assert _txs(_S["doc_amende"]) == []  # une amende ne crée jamais de transaction énergie


class TestLegacyImport:
    def test_10_legacy_import_sans_fichier_idempotent(self):
        before = _veh_total(_S["veh_a"])
        body = {**PLEIN, "date": "2026-05-02", "heure": "18:40", "montant": 61.15, "litres": 33.1, "motif": None,
                "source": "legacy_import", "legacy_source": "journal", "legacy_id": f"fuel-{_RUN}-77",
                "created_at": "2025-11-03T10:00:00+00:00"}
        ids = set()
        for _ in range(3):
            r = _fuel(_S["veh_a"], body)
            assert r.status_code == 200, r.text
            ids.add(r.json()["document_id"])
        assert len(ids) == 1
        doc_id = ids.pop()
        d = _doc(doc_id)
        assert d["source"] == "legacy_import" and d["justificatif_absent"] is True and d["storage_path"] is None
        assert d["legacy_source"] == "journal" and d["legacy_id"] == f"fuel-{_RUN}-77" and d["migration_version"] == 1
        assert d["created_at"] == "2025-11-03T10:00:00+00:00" and d["validated_by"] == "import"
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A, "legacy_id": f"fuel-{_RUN}-77"}) == 1
        txs = _txs(doc_id)
        assert len(txs) == 1 and txs[0]["created_from"] == "legacy_import" and txs[0]["legacy_id"] == f"fuel-{_RUN}-77"
        assert txs[0]["date_heure_tz_assumed"] is True and txs[0]["date_heure_source"] == "2026-05-02T18:40"
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 61.15  # 3 rejeux = 1 coût
        _S["doc_legacy"] = doc_id

    def test_11_legacy_replay_est_une_mise_a_jour_pas_un_doublon(self):
        body = {**PLEIN, "date": "2026-05-02", "heure": "18:40", "montant": 62.0, "litres": 33.5, "motif": None,
                "source": "legacy_import", "legacy_id": f"fuel-{_RUN}-77", "duplicate_override": True}
        r = _fuel(_S["veh_a"], body)
        assert r.status_code == 200 and r.json()["created"] is False and r.json()["document_id"] == _S["doc_legacy"]
        assert _doc(_S["doc_legacy"])["montant"] == 62.0 and len(_txs(_S["doc_legacy"])) == 1
        assert _txs(_S["doc_legacy"])[0]["montant"] == 62.0
        assert _audits(_S["doc_legacy"], "legacy_replay")

    def test_12_isolation_meme_legacy_id_autre_tenant(self):
        body = {**PLEIN, "motif": None, "source": "legacy_import", "legacy_id": f"fuel-{_RUN}-77"}
        r = _fuel(_S["veh_b"], body, creds=ADMIN_B)
        assert r.status_code == 200 and r.json()["document_id"] != _S["doc_legacy"]
        assert _mongo().documents.count_documents({"legacy_id": f"fuel-{_RUN}-77", "tenant_id": {"$in": [TENANT_A, TENANT_B]}}) == 2

    def test_13_index_legacy_lot_a_toujours_present(self):
        idx = _mongo().documents.index_information()
        assert idx["uniq_legacy_key"]["unique"] is True


class TestD7CollectCosts:
    def test_20_chf_lit_montant(self):
        item = _item(_S["doc_plein"])
        assert item["montant"] == 88.4 and item["devise"] == "CHF" and item["montant_origine"] is None

    def test_21_non_chf_avec_montant_chf(self):
        before = _veh_total(_S["veh_fx"])
        r = _fuel(_S["veh_fx"], station="Total Annemasse", date="2026-06-21", montant=70.0, devise="EUR", montant_chf=66.5,
                  litres=38.0, prix_litre=1.842, motif="Plein en France, carte carburant", kilometrage=None)
        assert r.status_code == 200, r.text
        _S["doc_eur_ok"] = r.json()["document_id"]
        d = _doc(_S["doc_eur_ok"])
        assert d["montant"] == 70.0 and d["devise"] == "EUR" and d["montant_chf"] == 66.5
        item = _item(_S["doc_eur_ok"])
        assert item["montant"] == 66.5 and item["devise"] == "CHF" and item["cout_annuel"] == 66.5
        assert item["montant_origine"] == 70.0 and item["devise_origine"] == "EUR"
        assert round(_veh_total(_S["veh_fx"]) - before, 2) == 66.5
        assert _txs(_S["doc_eur_ok"])[0]["montant"] == 70.0 and _txs(_S["doc_eur_ok"])[0]["devise"] == "EUR"

    def test_22_non_chf_sans_montant_chf_pending_fx_exclu_du_total(self):
        before = _costs()["totals"]["annuel"]
        before_v = _veh_total(_S["veh_fx"])
        r = _fine(_S["veh_fx"], autorite="Polizia Municipale Como", numero_amende=f"IT-{_RUN}", montant=95.0, devise="EUR",
                  delai_paiement="2026-08-01", motif="Amende italienne, taux non connu")
        assert r.status_code == 200, r.text
        _S["doc_eur_pending"] = r.json()["document_id"]
        assert r.json()["cost"]["pending_fx"] is True and r.json()["cost"]["montant_chf"] is None
        costs = _costs()
        assert costs["totals"]["annuel"] == before and _veh_total(_S["veh_fx"]) == before_v
        assert _item(_S["doc_eur_pending"]) is None
        p = _pending(_S["doc_eur_pending"])
        assert p and p["montant"] == 95.0 and p["devise"] == "EUR" and p["status"] == "pending_fx"
        assert costs["totals"]["pending_fx_count"] >= 1
        veh = requests.get(f"{_BASE}/api/vehicles/{_S['veh_fx']}/costs", headers=_h(), timeout=30).json()
        assert any(i["document_id"] == _S["doc_eur_pending"] for i in veh["pending_fx"]) and veh["totals"]["pending_fx_count"] == 1
        dl = requests.get(f"{_BASE}/api/deadlines", headers=_h(), timeout=30).json()
        assert any(i["key"] == f"doc:{_S['doc_eur_pending']}" for i in dl["items"])  # échéance suivie même en attente FX

    def test_23_patch_montant_chf_sort_de_pending_fx_et_audit_avant_apres(self):
        before = _costs()["totals"]["annuel"]
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc_eur_pending']}", json={"montant_chf": 90.25}, headers=_h(), timeout=30)
        assert r.status_code == 200, r.text
        assert _pending(_S["doc_eur_pending"]) is None
        item = _item(_S["doc_eur_pending"])
        assert item["montant"] == 90.25 and item["montant_origine"] == 95.0 and item["devise_origine"] == "EUR"
        assert round(_costs()["totals"]["annuel"] - before, 2) == 90.25
        last = _audits(_S["doc_eur_pending"], "modify")[-1]
        assert "montant_chf: — → 90.25" in last["detail"] and last["user"] == ADMIN_A[0]

    def test_24_montant_chf_ignore_si_devise_chf(self):
        r = _fuel(_S["veh_fx"], date="2026-06-22", montant=50.0, montant_chf=49.0, motif="Test CHF avec montant_chf parasite", litres=27.0)
        assert r.status_code == 200 and _doc(r.json()["document_id"])["montant_chf"] is None
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc_eur_pending']}", json={"devise": "CHF"}, headers=_h(), timeout=30)
        assert r.status_code == 200 and _doc(_S["doc_eur_pending"])["montant_chf"] is None
        assert _item(_S["doc_eur_pending"])["montant"] == 95.0
        requests.patch(f"{_BASE}/api/documents/{_S['doc_eur_pending']}", json={"devise": "EUR", "montant_chf": 90.25}, headers=_h(), timeout=30)

    def test_25_collect_costs_ne_lit_jamais_fuel_transactions(self):
        src = open("/app/backend/server.py", encoding="utf-8").read()
        m = re.search(r"async def collect_costs\(.*?(?=\n(?:async def |def |@api_router|class ))", src, re.S)
        assert m and "fuel_transactions" not in m.group(0)
        assert "cost_amount_chf" in m.group(0)  # D7 générique appliqué dans le moteur unique


class TestSecurite:
    def test_30_read_only_toutes_ecritures_403_base_inchangee(self):
        n_docs = _mongo().documents.count_documents({"tenant_id": TENANT_A})
        n_tx = _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A})
        assert _fuel(_S["veh_a"], creds=RO_A, date="2026-06-25").status_code == 403
        assert _fine(_S["veh_a"], creds=RO_A, numero_amende="RO-1").status_code == 403
        assert _attach(_S["doc_amende"], creds=RO_A).status_code == 403
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc_eur_ok']}", json={"montant_chf": 1.0}, headers=_h(RO_A), timeout=30)
        assert r.status_code == 403
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A}) == n_docs
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A}) == n_tx
        assert _doc(_S["doc_eur_ok"])["montant_chf"] == 66.5
        r = requests.get(f"{_BASE}/api/costs", headers=_h(RO_A), timeout=30)  # lecture OK
        assert r.status_code == 200 and any(i["document_id"] == _S["doc_plein"] for i in r.json()["items"])

    def test_31_cross_tenant_fail_closed(self):
        assert _fuel(_S["veh_a"], creds=ADMIN_B, date="2026-06-26").status_code == 404
        assert _fine(_S["veh_a"], creds=ADMIN_B, numero_amende="B-1").status_code == 404
        assert _attach(_S["doc_amende"], creds=ADMIN_B).status_code == 404
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc_eur_ok']}", json={"montant_chf": 1.0}, headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404
        assert requests.get(f"{_BASE}/api/documents/{_S['doc_plein']}/extraction", headers=_h(ADMIN_B), timeout=30).status_code == 404
        costs_b = _costs(ADMIN_B)
        assert not any(i["document_id"] in (_S["doc_plein"], _S["doc_amende"]) for i in costs_b["items"] + costs_b["pending_fx"])
        assert _mongo().documents.count_documents({"tenant_id": TENANT_B, "is_deleted": False}) == 1  # seul l'import B (test_12)

    def test_32_audit_creation_modification_attach(self):
        created = _audits(_S["doc_plein"], "create")
        assert created and "sans justificatif (manual, motif : Ticket perdu" in created[0]["detail"]
        assert created[0]["user"] == ADMIN_A[0] and created[0]["ip"] and created[0]["created_at"]
        tx_audit = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_transaction",
                                                 "entity_id": _txs(_S["doc_plein"])[0]["id"], "action": "create"})
        assert tx_audit and "manual" in tx_audit["detail"]
        attach = _audits(_S["doc_plein"], "attach_file")
        assert len(attach) == 1 and "justif.png" in attach[0]["detail"] and "aucun nouveau coût" in attach[0]["detail"]
        fine = _audits(_S["doc_amende"], "create")
        assert fine and "Amende sans justificatif" in fine[0]["detail"]
        eur = _audits(_S["doc_eur_ok"], "create")
        assert eur and "contre-valeur 66.5 CHF" in eur[0]["detail"]

    def test_33_aucune_donnee_journal_reelle_migree(self):
        db = _mongo()
        q = {"tenant_id": {"$nin": [TENANT_A, TENANT_B]}, "legacy_id": {"$exists": True}}
        assert db.documents.count_documents(q) == 0 and db.fuel_transactions.count_documents(q) == 0
        assert db.documents.count_documents({"tenant_id": "default", "source": "legacy_import"}) == 0
