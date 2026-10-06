"""Phase 3 — Amendes : document validé = coût (AMENDE) + échéance de paiement, statut payée explicite, intégrité."""
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-fi-a-{_RUN}"
TENANT_B = f"pytest-fi-b-{_RUN}"
ADMIN_A = (f"fi-adm-a-{_RUN}@pytest.ch", f"FiAdmA-{_RUN}-1")
RO_A = (f"fi-ro-a-{_RUN}@pytest.ch", f"FiRoA-{_RUN}-1")
ADMIN_B = (f"fi-adm-b-{_RUN}@pytest.ch", f"FiAdmB-{_RUN}-1")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 80
PLATE_A = f"VD {_RUN[:6].upper()}"
FUTURE = (date.today() + timedelta(days=45)).isoformat()
PAST = (date.today() - timedelta(days=10)).isoformat()

FINE = {"autorite": "Police cantonale vaudoise", "numero_amende": f"PCV-{_RUN}-001", "date_infraction": "2026-06-02",
        "montant_chf": 120.0, "devise": "CHF", "delai_paiement": FUTURE}

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


def _seed_fine(vehicle_id, tenant=TENANT_A, fields=None):
    """Amende déjà analysée (OCR simulé) — aucun appel LLM."""
    fields = dict(fields if fields is not None else FINE)
    doc_id = str(uuid.uuid4())
    _mongo().documents.insert_one({
        "id": doc_id, "vehicle_id": vehicle_id, "tenant_id": tenant, "folder": "Divers",
        "original_filename": f"amende_{doc_id[:8]}.jpg", "storage_path": f"pytest/{doc_id}.jpg",
        "content_type": "image/jpeg", "size": 1, "pages": [], "sha256": uuid.uuid4().hex,
        "document_type": "amende", "extraction_status": "done", "a_verifier": True, "source": "scan",
        "is_deleted": False, "created_at": datetime.now(timezone.utc).isoformat(),
        "extracted_fields": [{"field": k, "value": v, "confidence": 0.95, "status": "found",
                              "target": "document", "current_value": None, "conflict": False}
                             for k, v in fields.items()],
    })
    return doc_id


def _validate(doc_id, fields, category="AMENDE", creds=ADMIN_A, **extra):
    body = {"document_type": "amende", "fields": fields, **extra}
    if category is not None:
        body["business_category"] = category
    return requests.post(f"{_BASE}/api/documents/{doc_id}/validate", json=body, headers=_h(creds), timeout=30)


def _paid(doc_id, payee=True, creds=ADMIN_A):
    return requests.post(f"{_BASE}/api/documents/{doc_id}/paid", json={"payee": payee}, headers=_h(creds), timeout=30)


def _costs(creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/costs", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _veh_total(vehicle_id, creds=ADMIN_A):
    return round(sum(i["cout_annuel"] for i in _costs(creds)["items"] if i["vehicle_id"] == vehicle_id), 2)


def _deadlines(creds=ADMIN_A, **params):
    r = requests.get(f"{_BASE}/api/deadlines", params=params, headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _dl(doc_id, creds=ADMIN_A):
    return next((i for i in _deadlines(creds)["items"] if i["key"] == f"doc:{doc_id}"), None)


def _doc(doc_id):
    return _mongo().documents.find_one({"id": doc_id}, {"_id": 0})


def _doc_api(doc_id, creds=ADMIN_A):
    r = requests.get(f"{_BASE}/api/documents", headers=_h(creds), timeout=30)
    assert r.status_code == 200
    return next((d for d in r.json() if d["id"] == doc_id), None)


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
    _S["veh_a"] = _vehicle({"plaque": PLATE_A, "kilometrage": 12345})
    _S["veh_b"] = _vehicle({"plaque": f"BE {_RUN[:6].upper()}"}, creds=ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta",
                     "tenant_integrations", "doc_categories", "doc_requirements", "tenant_settings",
                     "fuel_transactions"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestAmendeComplete:
    def test_amende_validee_cout_et_echeance(self):
        before = _veh_total(_S["veh_a"])
        doc_id = _seed_fine(_S["veh_a"])
        r = requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(), timeout=30)
        assert r.status_code == 200 and r.json()["suggested_business_category"] == "AMENDE"
        r = _validate(doc_id, FINE)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["cost"] == {"document_id": doc_id, "montant": 120.0, "devise": "CHF", "frequence": "unique",
                               "business_category": "AMENDE", "category_label": "Amende"}
        assert res["fuel_transaction"] is None and res["warnings"] == []
        d = _doc(doc_id)
        assert d["document_type"] == "amende" and d["business_category"] == "AMENDE"
        assert d["montant"] == 120.0 and d["devise"] == "CHF" and d["frequence"] == "unique"
        assert d["numero"] == FINE["numero_amende"] and d["date_debut"] == "2026-06-02"
        assert d["date_expiration"] == FUTURE and d["fournisseur"] == "Police cantonale vaudoise"
        assert d["payee"] is False and d["paid_at"] is None and d["extraction_status"] == "validated"
        assert d["document_data"]["montant_chf"] == 120.0  # détail OCR conservé
        # Coûts : exactement une fois, catégorie Amende, source document
        items = [i for i in _costs()["items"] if i["document_id"] == doc_id]
        assert len(items) == 1 and items[0]["montant"] == 120.0 and items[0]["category"] == "Amende"
        assert items[0]["business_category"] == "AMENDE" and items[0]["frequence"] == "unique" and items[0]["source"] == "document"
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 120.0
        # Échéances : délai de paiement actif
        dl = _dl(doc_id)
        assert dl and dl["type"] == "amende" and dl["category"] == "Amende" and dl["is_fine"] is True
        assert dl["date"] == FUTURE and dl["statut"] in ("URGENT", "A_PLANIFIER", "OK") and dl["days_remaining"] > 0
        assert "Police cantonale vaudoise" in dl["label"] and FINE["numero_amende"] in dl["label"] and "120.00 CHF" in dl["label"]
        # Statut documentaire : À payer
        assert _doc_api(doc_id)["statut"] == "A_PAYER"
        _S["doc_fine"] = doc_id

    def test_montant_centimes_conserve(self):
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-CENT", "montant_chf": 87.35}
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        r = _validate(doc_id, f)
        assert r.status_code == 200, r.text
        assert _doc(doc_id)["montant"] == 87.35
        item = next(i for i in _costs()["items"] if i["document_id"] == doc_id)
        assert item["montant"] == 87.35 and item["cout_annuel"] == 87.35
        _S["doc_cent"] = doc_id

    def test_revalidation_idempotente(self):
        doc_id = _S["doc_fine"]
        before = _veh_total(_S["veh_a"])
        r = _validate(doc_id, {**FINE, "autorite": "Police cantonale vaudoise (corrigé)"})
        assert r.status_code == 200, r.text
        assert _doc(doc_id)["fournisseur"] == "Police cantonale vaudoise (corrigé)"
        assert len([i for i in _costs()["items"] if i["document_id"] == doc_id]) == 1
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 0.0
        assert len([i for i in _deadlines()["items"] if i["key"] == f"doc:{doc_id}"]) == 1

    def test_amende_incomplete_sans_montant_ni_delai(self):
        f = {"autorite": "Ville de Lausanne", "date_infraction": "2026-06-05"}
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        r = _validate(doc_id, f)
        assert r.status_code == 200, r.text
        codes = {w["code"] for w in r.json()["warnings"]}
        assert {"AMOUNT_MISSING", "DEADLINE_MISSING"} <= codes and r.json()["cost"] is None
        d = _doc(doc_id)
        assert "montant" not in d and "date_expiration" not in d and d["fournisseur"] == "Ville de Lausanne"
        assert not [i for i in _costs()["items"] if i["document_id"] == doc_id]  # rien d'inventé
        dl = _dl(doc_id)
        assert dl and dl["statut"] == "SANS_ECHEANCE" and dl["is_fine"] is True
        assert _doc_api(doc_id)["statut"] == "A_PAYER"


class TestPaiementEtRetard:
    def test_echeance_passee_en_retard_reste_active(self):
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-LATE", "delai_paiement": PAST}
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        assert _validate(doc_id, f).status_code == 200
        assert _doc_api(doc_id)["statut"] == "EN_RETARD"
        dl = _dl(doc_id)
        assert dl and dl["statut"] == "EXPIRE" and dl["level"] == "expired" and dl["is_fine"] is True
        assert dl["days_remaining"] < 0
        assert _deadlines(statut="EXPIRE")["count"] >= 1
        _S["doc_late"] = doc_id

    def test_marquer_payee(self):
        doc_id = _S["doc_late"]
        before = _veh_total(_S["veh_a"])
        r = _paid(doc_id, True)
        assert r.status_code == 200, r.text
        assert r.json()["statut"] == "PAYEE" and r.json()["payee"] is True
        d = _doc(doc_id)
        assert d["payee"] is True and d["paid_at"] and d["paid_by"] == ADMIN_A[0] and d["is_deleted"] is False
        assert _doc_api(doc_id)["statut"] == "PAYEE"
        assert _dl(doc_id) is None  # plus d'échéance active
        assert len([i for i in _costs()["items"] if i["document_id"] == doc_id]) == 1  # historique coûts conservé
        assert round(_veh_total(_S["veh_a"]) - before, 2) == 0.0
        audit = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity_id": doc_id, "detail": {"$regex": "payée"}})
        assert audit

    def test_revalidation_conserve_le_statut_payee(self):
        doc_id = _S["doc_late"]
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-LATE", "delai_paiement": PAST}
        assert _validate(doc_id, f).status_code == 200
        assert _doc(doc_id)["payee"] is True and _dl(doc_id) is None

    def test_annuler_paiement(self):
        doc_id = _S["doc_late"]
        r = _paid(doc_id, False)
        assert r.status_code == 200, r.text
        d = _doc(doc_id)
        assert d["payee"] is False and d["paid_at"] is None and d["paid_by"] is None
        assert _doc_api(doc_id)["statut"] == "EN_RETARD"
        assert _dl(doc_id) and _dl(doc_id)["statut"] == "EXPIRE"

    def test_paid_sur_non_amende_422(self):
        doc_id = str(uuid.uuid4())
        _mongo().documents.insert_one({"id": doc_id, "vehicle_id": _S["veh_a"], "tenant_id": TENANT_A, "folder": "Divers",
                                       "original_filename": "note.pdf", "storage_path": "pytest/n.pdf", "is_deleted": False,
                                       "document_type": "autre", "created_at": datetime.now(timezone.utc).isoformat()})
        assert _paid(doc_id, True).status_code == 422
        assert "payee" not in _doc(doc_id)

    def test_filtre_echeance_ignore_les_amendes_payees(self):
        doc_id = _S["doc_late"]
        assert _paid(doc_id, True).status_code == 200
        r = requests.get(f"{_BASE}/api/documents", params={"echeance": "expired"}, headers=_h(), timeout=30)
        assert doc_id not in {d["id"] for d in r.json()}
        assert _paid(doc_id, False).status_code == 200


class TestPlaqueEtDoublons:
    def test_plaque_differente_avertissement_sans_reaffectation(self):
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-PLATE", "plaque": "GE 123 456"}
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        r = _validate(doc_id, f)
        assert r.status_code == 200, r.text
        w = next(w for w in r.json()["warnings"] if w["code"] == "PLATE_MISMATCH")
        assert w["document_plate"] == "GE 123 456" and w["vehicle_plate"] == PLATE_A
        assert _doc(doc_id)["vehicle_id"] == _S["veh_a"] and _doc(doc_id)["plaque_mentionnee"] == "GE 123 456"

    def test_doublon_fichier_sha256_signale(self):
        data = PNG + _RUN.encode() + b"fine"
        r1 = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents", headers=_h(),
                           files={"file": ("a1.png", data, "image/png")}, data={"folder": "Divers"}, timeout=30)
        r2 = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents", headers=_h(),
                           files={"file": ("a2.png", data, "image/png")}, data={"folder": "Divers"}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["duplicate_of"] is None and r2.json()["duplicate_of"]["document_id"] == r1.json()["id"]

    def test_doublon_metier_par_numero_409_puis_override(self):
        f = {**FINE, "autorite": "Autre autorité", "montant_chf": 999.0}  # même n° d'amende → doublon
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        r = _validate(doc_id, f)
        assert r.status_code == 409, r.text
        det = r.json()["detail"]
        assert det["code"] == "DUPLICATE_SUSPECTED" and det["kind"] == "amende"
        assert det["existing_document_id"] == _S["doc_fine"]
        assert _doc(doc_id)["extraction_status"] == "done" and "montant" not in _doc(doc_id)
        assert not [i for i in _costs()["items"] if i["document_id"] == doc_id]
        r = _validate(doc_id, f, duplicate_override=True)
        assert r.status_code == 200, r.text
        assert "DUPLICATE_OVERRIDDEN" in {w["code"] for w in r.json()["warnings"]}
        assert len([i for i in _costs()["items"] if i["document_id"] == doc_id]) == 1

    def test_doublon_metier_sans_numero_autorite_date_montant(self):
        base = {"autorite": "Police municipale Vevey", "date_infraction": "2026-05-30", "montant_chf": 40.0,
                "delai_paiement": FUTURE}
        d1 = _seed_fine(_S["veh_a"], fields=base)
        assert _validate(d1, base).status_code == 200
        d2 = _seed_fine(_S["veh_a"], fields=base)
        r = _validate(d2, base)
        assert r.status_code == 409 and r.json()["detail"]["kind"] == "amende"
        assert r.json()["detail"]["existing_document_id"] == d1
        other = {**base, "montant_chf": 40.5}
        d3 = _seed_fine(_S["veh_a"], fields=other)
        assert _validate(d3, other).status_code == 200  # montant différent → pas un doublon


class TestSecurite:
    def test_read_only_validate_403_base_inchangee(self):
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-RO"}
        doc_id = _seed_fine(_S["veh_a"], fields=f)
        snap = _doc(doc_id)
        r = _validate(doc_id, f, creds=RO_A)
        assert r.status_code == 403, r.text
        assert _doc(doc_id) == snap and "validated_at" not in _doc(doc_id) and "payee" not in _doc(doc_id)
        assert not [i for i in _costs()["items"] if i["document_id"] == doc_id]
        _S["doc_ro"] = doc_id

    def test_read_only_mark_paid_delete_patch_403(self):
        doc_id = _S["doc_fine"]
        snap = _doc(doc_id)
        assert _paid(doc_id, True, creds=RO_A).status_code == 403
        assert requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(RO_A), timeout=30).status_code == 403
        assert requests.patch(f"{_BASE}/api/documents/{doc_id}", json={"montant": 1}, headers=_h(RO_A), timeout=30).status_code == 403
        assert _doc(doc_id) == snap
        r = requests.get(f"{_BASE}/api/documents", headers=_h(RO_A), timeout=30)  # lecture autorisée
        assert r.status_code == 200 and doc_id in {d["id"] for d in r.json()}
        assert _deadlines(RO_A)["count"] >= 1

    def test_cross_tenant_404(self):
        doc_id = _S["doc_fine"]
        assert _validate(_S["doc_ro"], FINE, creds=ADMIN_B).status_code == 404
        assert _paid(doc_id, True, creds=ADMIN_B).status_code == 404
        assert requests.get(f"{_BASE}/api/documents/{doc_id}/extraction", headers=_h(ADMIN_B), timeout=30).status_code == 404
        assert requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(ADMIN_B), timeout=30).status_code == 404
        assert doc_id not in {d["id"] for d in requests.get(f"{_BASE}/api/documents", headers=_h(ADMIN_B), timeout=30).json()}
        assert not [i for i in _costs(ADMIN_B)["items"] if i["document_id"] == doc_id]
        assert _dl(doc_id, ADMIN_B) is None
        assert _doc(doc_id)["payee"] is False and _doc(_S["doc_ro"])["extraction_status"] == "done"

    def test_admin_temoin_valide_le_document_refuse_au_read_only(self):
        f = {**FINE, "numero_amende": f"PCV-{_RUN}-RO"}
        assert _validate(_S["doc_ro"], f).status_code == 200
        assert _doc(_S["doc_ro"])["extraction_status"] == "validated"

    def test_suppression_amende_validee_409(self):
        doc_id = _S["doc_fine"]
        r = requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(), timeout=30)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "VALIDATED_FINE"
        assert _doc(doc_id)["is_deleted"] is False
        assert len([i for i in _costs()["items"] if i["document_id"] == doc_id]) == 1 and _dl(doc_id)

    def test_suppression_amende_non_validee_ok(self):
        doc_id = _seed_fine(_S["veh_a"], fields={**FINE, "numero_amende": f"PCV-{_RUN}-DEL"})
        assert requests.delete(f"{_BASE}/api/documents/{doc_id}", headers=_h(), timeout=30).status_code == 200
        assert _doc(doc_id)["is_deleted"] is True
