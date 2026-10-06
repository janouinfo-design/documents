"""Phase 1 — Pont Facture → Coûts : le document validé EST l'enregistrement de coût (Option 1)."""
import uuid
from datetime import datetime, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-bd-a-{_RUN}"
TENANT_B = f"pytest-bd-b-{_RUN}"
ADMIN_A = (f"bd-adm-a-{_RUN}@pytest.ch", f"BdAdmA-{_RUN}-1")
RO_A = (f"bd-ro-a-{_RUN}@pytest.ch", f"BdRoA-{_RUN}-1")
ADMIN_B = (f"bd-adm-b-{_RUN}@pytest.ch", f"BdAdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
PLATE_A = f"VD {_RUN[:6].upper()}"

GARAGE = {"fournisseur": "Garage du Léman SA", "numero_facture": "2026-1842", "date_facture": "2026-05-15",
          "montant_chf": 510.77, "montant_ht": 472.5, "tva_chf": 38.27, "devise": "CHF",
          "kilometrage_releve": 48210, "categorie_suggeree": "ENTRETIEN"}

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


def _seed_scanned(vehicle_id, tenant=TENANT_A, dtype="facture", fields=None, plaque=None):
    """Document déjà analysé (OCR simulé) — aucun appel LLM, aucun fichier réel nécessaire."""
    fields = dict(fields if fields is not None else GARAGE)
    if plaque:
        fields["plaque"] = plaque
    doc_id = str(uuid.uuid4())
    _mongo().documents.insert_one({
        "id": doc_id, "vehicle_id": vehicle_id, "tenant_id": tenant, "folder": "Factures",
        "original_filename": f"{doc_id[:8]}.jpg", "storage_path": f"pytest/{doc_id}.jpg",
        "content_type": "image/jpeg", "size": 1, "pages": [], "sha256": uuid.uuid4().hex,
        "document_type": dtype, "extraction_status": "done", "a_verifier": True, "source": "scan",
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "extracted_fields": [{"field": k, "value": v, "confidence": 0.99, "status": "found",
                              "target": "document", "current_value": None, "conflict": False}
                             for k, v in fields.items()],
    })
    return doc_id


def _validate(doc_id, fields, category="ENTRETIEN", creds=ADMIN_A, dtype="facture", **extra):
    body = {"document_type": dtype, "fields": fields, **extra}
    if category is not None:
        body["business_category"] = category
    return requests.post(f"{_BASE}/api/documents/{doc_id}/validate", json=body, headers=_h(creds), timeout=30)


def _costs(creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/costs", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return {i["key"]: i for i in r.json()["items"]}


def _doc(doc_id):
    return _mongo().documents.find_one({"id": doc_id}, {"_id": 0})


def _upload(vehicle_id, name, data=PNG, folder="Divers", creds=ADMIN_A):
    r = requests.post(f"{_BASE}/api/vehicles/{vehicle_id}/documents", headers=_h(creds),
                      files={"file": (name, data, "image/png")}, data={"folder": folder}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


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
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": PLATE_A, "kilometrage": 12345}, headers=_h(), timeout=30)
    assert r.status_code == 200, r.text
    _S["veh_a"] = r.json()["id"]
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"BE {_RUN[:6].upper()}"}, headers=_h(ADMIN_B), timeout=30)
    _S["veh_b"] = r.json()["id"]


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestFactureToCosts:
    def test_facture_validee_alimente_le_moteur_couts(self):
        doc_id = _seed_scanned(_S["veh_a"])
        r = _validate(doc_id, GARAGE, "ENTRETIEN")
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["cost"] == {"document_id": doc_id, "montant": 510.77, "devise": "CHF", "frequence": "unique",
                               "business_category": "ENTRETIEN", "category_label": "Entretien"}
        d = _doc(doc_id)
        # Champs V2 lus par collect_costs — le document EST le coût
        assert d["montant"] == 510.77 and d["devise"] == "CHF" and d["frequence"] == "unique"
        assert d["date_debut"] == "2026-05-15" and d["fournisseur"] == "Garage du Léman SA"
        assert d["numero"] == "2026-1842" and d["business_category"] == "ENTRETIEN"
        assert d["montant_ht"] == 472.5 and d["tva_chf"] == 38.27 and d["kilometrage_releve"] == 48210
        # document_data (détail OCR) conservé pour audit/review
        assert d["document_data"]["montant_chf"] == 510.77 and d["extraction_status"] == "validated"
        item = _costs()[f"doc:{doc_id}"]
        assert item["montant"] == 510.77 and item["cout_annuel"] == 510.77 and item["devise"] == "CHF"
        assert item["category"] == "Entretien" and item["business_category"] == "ENTRETIEN"
        assert item["category_source"] == "business" and item["frequence"] == "unique"
        assert item["source"] == "document" and item["document_id"] == doc_id
        assert item["vehicle_id"] == _S["veh_a"] and item["plaque"] == PLATE_A and 2026 in item["years"]
        assert item["fournisseur"] == "Garage du Léman SA" and item["numero"] == "2026-1842"
        _S["doc_garage"] = doc_id

    def test_couts_vehicule_et_csv(self):
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/costs", headers=_h(), timeout=30)
        assert r.status_code == 200
        assert f"doc:{_S['doc_garage']}" in {i["key"] for i in r.json()["items"]}
        r = requests.get(f"{_BASE}/api/reports/couts.csv", headers=_h(), timeout=30)
        assert r.status_code == 200 and PLATE_A in r.text

    def test_kilometrage_releve_jamais_ecrit_sur_le_vehicule(self):
        v = _mongo().vehicles.find_one({"id": _S["veh_a"]}, {"_id": 0, "kilometrage": 1})
        assert v["kilometrage"] == 12345

    def test_sans_categorie_confirmee_le_cout_apparait_non_classe(self):
        doc_id = _seed_scanned(_S["veh_a"])
        fields = {**GARAGE, "numero_facture": "NC-1", "montant_chf": 99.5}
        r = _validate(doc_id, fields, category=None)
        assert r.status_code == 200, r.text
        assert r.json()["cost"]["category_label"] == "Non classé"
        d = _doc(doc_id)
        assert "business_category" in d and d["business_category"] is None
        item = _costs()[f"doc:{doc_id}"]
        assert item["category"] == "Non classé" and item["category_source"] == "unclassified"
        assert item["business_category"] is None and item["montant"] == 99.5

    def test_ancien_document_sans_cle_retombe_sur_le_dossier(self):
        d = _upload(_S["veh_a"], "legacy.png", data=PNG + b"L")
        r = requests.patch(f"{_BASE}/api/documents/{d['id']}", json={"montant": 300, "frequence": "unique"},
                           headers=_h(), timeout=30)
        assert r.status_code == 200
        item = _costs()[f"doc:{d['id']}"]
        assert item["category"] == "Divers" and item["category_source"] == "folder"
        _S["doc_legacy"] = d["id"]

    def test_patch_categorie_metier(self):
        did = _S["doc_legacy"]
        r = requests.patch(f"{_BASE}/api/documents/{did}", json={"business_category": "PNEUS"}, headers=_h(), timeout=30)
        assert r.status_code == 200
        assert _costs()[f"doc:{did}"]["category"] == "Pneus"
        r = requests.patch(f"{_BASE}/api/documents/{did}", json={"business_category": "FOO"}, headers=_h(), timeout=30)
        assert r.status_code == 422
        r = requests.patch(f"{_BASE}/api/documents/{did}", json={"business_category": None}, headers=_h(), timeout=30)
        assert r.status_code == 200
        assert _costs()[f"doc:{did}"]["category"] == "Non classé"
        r = requests.patch(f"{_BASE}/api/documents/{did}", json={"montant_ht": -1}, headers=_h(), timeout=30)
        assert r.status_code == 422

    def test_devise_eur_conservee_et_chf_par_defaut(self):
        doc_eur = _seed_scanned(_S["veh_a"])
        r = _validate(doc_eur, {**GARAGE, "numero_facture": "EUR-1", "devise": "eur"}, "REPARATION")
        assert r.status_code == 200 and _doc(doc_eur)["devise"] == "EUR"
        doc_nodev = _seed_scanned(_S["veh_a"])
        fields = {k: v for k, v in GARAGE.items() if k != "devise"}
        r = _validate(doc_nodev, {**fields, "numero_facture": "NODEV-1"}, "LAVAGE")
        assert r.status_code == 200 and _doc(doc_nodev)["devise"] == "CHF"

    def test_categorie_inconnue_422(self):
        doc_id = _seed_scanned(_S["veh_a"])
        assert _validate(doc_id, GARAGE, "N_EXISTE_PAS").status_code == 422

    def test_type_autre_inchange(self):
        doc_id = _seed_scanned(_S["veh_a"], dtype="autre", fields={"titre": "Note", "date_document": "2026-06-01"})
        r = _validate(doc_id, {"titre": "Note", "date_document": "2026-06-01"}, category=None, dtype="autre")
        assert r.status_code == 200 and r.json()["cost"] is None
        d = _doc(doc_id)
        assert "montant" not in d and "business_category" not in d and d["document_data"]["titre"] == "Note"


class TestDeduplication:
    def test_doublon_metier_409_puis_confirmation_explicite(self):
        dup = _seed_scanned(_S["veh_a"])
        r = _validate(dup, GARAGE, "ENTRETIEN")
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert detail["code"] == "DUPLICATE_SUSPECTED" and detail["existing_document_id"] == _S["doc_garage"]
        assert _doc(dup)["extraction_status"] == "done" and "montant" not in _doc(dup)
        assert f"doc:{dup}" not in _costs()
        r = _validate(dup, GARAGE, "ENTRETIEN", duplicate_override=True)
        assert r.status_code == 200, r.text
        assert any(w["code"] == "DUPLICATE_OVERRIDDEN" for w in r.json()["warnings"])
        assert f"doc:{dup}" in _costs()
        _mongo().documents.update_one({"id": dup}, {"$set": {"is_deleted": True}})

    def test_variation_montant_ou_numero_n_est_pas_un_doublon(self):
        doc_id = _seed_scanned(_S["veh_a"])
        assert _validate(doc_id, {**GARAGE, "montant_chf": 510.78}, "ENTRETIEN").status_code == 200
        doc_id = _seed_scanned(_S["veh_a"])
        assert _validate(doc_id, {**GARAGE, "numero_facture": "2026-1843"}, "ENTRETIEN").status_code == 200

    def test_sha256_fichier_identique_avertit_sans_bloquer(self):
        data = PNG + _RUN.encode()
        first = _upload(_S["veh_a"], "ticket.png", data=data)
        assert first["duplicate_of"] is None and _doc(first["id"])["sha256"]
        second = _upload(_S["veh_a"], "ticket-bis.png", data=data)
        assert second["duplicate_of"]["document_id"] == first["id"]
        assert second["duplicate_of"]["original_filename"] == "ticket.png"
        assert _doc(second["id"])["is_deleted"] is False, "jamais de blocage/suppression automatique"
        other = _upload(_S["veh_a"], "autre.png", data=data + b"x")
        assert other["duplicate_of"] is None
        # Même fichier sur un autre véhicule (tenant B) : aucune fuite, aucun avertissement
        cross = _upload(_S["veh_b"], "ticket.png", data=data, creds=ADMIN_B)
        assert cross["duplicate_of"] is None


class TestPlaqueDocument:
    def test_plaque_differente_avertit_sans_reaffecter(self):
        doc_id = _seed_scanned(_S["veh_a"], plaque="ZH 999999")
        r = requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(), timeout=30)
        assert r.status_code == 200
        pl = next(f for f in r.json()["fields"] if f["field"] == "plaque")
        assert pl["conflict"] is True and pl["current_value"] == PLATE_A
        r = _validate(doc_id, {**GARAGE, "numero_facture": "PL-1", "plaque": "ZH 999999"}, "ENTRETIEN")
        assert r.status_code == 200, r.text
        assert any(w["code"] == "PLATE_MISMATCH" for w in r.json()["warnings"])
        d = _doc(doc_id)
        assert d["vehicle_id"] == _S["veh_a"] and d["plaque_mentionnee"] == "ZH 999999"
        v = _mongo().vehicles.find_one({"id": _S["veh_a"]}, {"_id": 0, "plaque": 1})
        assert v["plaque"] == PLATE_A

    def test_plaque_identique_sans_avertissement(self):
        doc_id = _seed_scanned(_S["veh_a"], plaque=PLATE_A.lower())
        r = _validate(doc_id, {**GARAGE, "numero_facture": "PL-2", "plaque": PLATE_A.lower()}, "ENTRETIEN")
        assert r.status_code == 200 and not any(w["code"] == "PLATE_MISMATCH" for w in r.json()["warnings"])


class TestSecurity:
    def test_read_only_403(self):
        doc_id = _seed_scanned(_S["veh_a"])
        assert _validate(doc_id, GARAGE, "ENTRETIEN", creds=RO_A).status_code == 403
        r = requests.patch(f"{_BASE}/api/documents/{doc_id}", json={"business_category": "PNEUS"},
                           headers=_h(RO_A), timeout=30)
        assert r.status_code == 403
        r = requests.get(f"{_BASE}/api/costs", headers=_h(RO_A), timeout=30)
        assert r.status_code == 200 and f"doc:{_S['doc_garage']}" in {i["key"] for i in r.json()["items"]}

    def test_isolation_tenant(self):
        assert _validate(_S["doc_garage"], GARAGE, "ENTRETIEN", creds=ADMIN_B).status_code == 404
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc_garage']}", json={"business_category": "PNEUS"},
                           headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404
        assert f"doc:{_S['doc_garage']}" not in _costs(ADMIN_B)
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_garage']}/extraction", headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404

    def test_business_categories_endpoint(self):
        r = requests.get(f"{_BASE}/api/business-categories", headers={"Authorization": "None"}, timeout=30)
        assert r.status_code == 401
        r = requests.get(f"{_BASE}/api/business-categories", headers=_h(RO_A), timeout=30)
        assert r.status_code == 200
        codes = [c["code"] for c in r.json()]
        assert len(codes) == 12 and "ENTRETIEN" in codes and "CARBURANT" in codes and "AUTRE" in codes
