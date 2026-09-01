"""Carte grise suisse — extraction structurée, review ré-ouvrable (GET /documents/{id}/extraction),
normalisation VIN + garde anti-confusion, mapping canonique, RBAC read_only, isolation multi-tenant."""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A = f"pytest-cgocr-a-{_RUN}"
TENANT_B = f"pytest-cgocr-b-{_RUN}"
ADMIN_A = (f"cgocr-adm-a-{_RUN}@pytest.ch", f"AdmA-{_RUN}-1")
ADMIN_B = (f"cgocr-adm-b-{_RUN}@pytest.ch", f"AdmB-{_RUN}-1")
RO_A = (f"cgocr-ro-a-{_RUN}@pytest.ch", f"RoA-{_RUN}-1")

VIN = "WVWZZZ6RZEY063464"
VIN_OTHER = "WAUZZZ8V5KA011223"
VIN_TENANT_B = "VF1RFB00X66554433"

_S = {}
_cache = {}
_mongo_db = None


def _mongo():
    global _mongo_db
    if _mongo_db is None:
        _mongo_db = MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]
    return _mongo_db


def _h(creds):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login",
                          json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, f"login {creds[0]} -> {r.status_code}"
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _mk_vehicle(creds, plaque, vin=""):
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": plaque, "vin": vin},
                      headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _get_vehicle(creds, vid):
    r = requests.get(f"{_BASE}/api/vehicles/{vid}", headers=_h(creds), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _seed_doc(tenant_id, vehicle_id, fields, dtype="permis_circulation", status="done"):
    """Insère un document analysé (format persisté réel) directement en base."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {"id": str(uuid.uuid4()), "vehicle_id": vehicle_id, "tenant_id": tenant_id,
           "folder": "Carte grise", "original_filename": f"cg-{_RUN}.jpg",
           "storage_path": f"logitrak-fleet/media/{vehicle_id}/{uuid.uuid4()}.jpg",
           "content_type": "image/jpeg", "size": 1234, "is_deleted": False,
           "document_type": dtype, "extraction_status": status,
           "analyzed_at": now, "created_at": now,
           "extracted_fields": [{"field": k, "value": v, "confidence": 0.97, "status": "found"}
                                for k, v in fields.items()]}
    _mongo().documents.insert_one(dict(doc))
    return doc["id"]


SWISS_FIELDS = {
    "plaque": None,  # rempli au setup avec la plaque du véhicule (=> CORRESPONDANCE)
    "vin": VIN,
    "numero_matricule": "215.768.314",
    "numero_homologation": "1VE6 83",
    "marque": "VW",
    "modele": "Polo 1.2",
    "categorie": "Voiture de tourisme",
    "carrosserie": "Limousine",
    "couleur": "blanc",
    "date_mise_circulation": "2013-11-04",
    "cylindree_cm3": 1198,
    "puissance_kw": 51,
    "nombre_places": 5,
    "poids_vide": 1067,
    "charge_utile": 483,
    "poids_total": 1550,
    "charge_toit": 75,
    "code_emissions": "B5b",
    "detenteur": "Hygie-soins Sàrl",
    "adresse_detenteur": "Chemin des Mésanges 3, 1522 Lucens",
    "date_emission": "2023-05-22",
    "lieu_emission": "Yverdon",
    "date_dernier": "2023-05-09",
    "compagnie": "AXA Assurances",
}


def setup_module():
    for tid_, name, admin in ((TENANT_A, "A", ADMIN_A), (TENANT_B, "B", ADMIN_B)):
        r = requests.post(f"{_BASE}/api/admin/tenants",
                          json={"name": f"CgOcr {name} {_RUN}", "id": tid_},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
        r = requests.post(f"{_BASE}/api/admin/tenants/{tid_}/users",
                          json={"email": admin[0], "password": admin[1], "role": "admin"},
                          headers=sa(), timeout=30)
        assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users",
                      json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text

    plaque_a = f"VD {_RUN[:6].upper()}"
    _S["veh_a"] = _mk_vehicle(ADMIN_A, plaque_a)                       # VIN vide
    _S["veh_b"] = _mk_vehicle(ADMIN_A, f"GE {_RUN[:6].upper()}", VIN_OTHER)  # possède VIN_OTHER
    _S["veh_c"] = _mk_vehicle(ADMIN_A, f"FR {_RUN[:6].upper()}")       # VIN vide (tests garde VIN)
    _S["veh_tb"] = _mk_vehicle(ADMIN_B, f"ZH {_RUN[:6].upper()}", VIN_TENANT_B)  # tenant B

    fields = dict(SWISS_FIELDS)
    fields["plaque"] = plaque_a
    _S["doc_a"] = _seed_doc(TENANT_A, _S["veh_a"], fields)
    _S["doc_b"] = _seed_doc(TENANT_B, _S["veh_tb"], {"vin": VIN_TENANT_B, "marque": "Renault"})


def teardown_module():
    db = _mongo()
    for t in (TENANT_A, TENANT_B):
        db.vehicles.delete_many({"tenant_id": t})
        db.documents.delete_many({"tenant_id": t})
        db.vehicle_field_meta.delete_many({"tenant_id": t})
        db.audit_log.delete_many({"tenant_id": t})
        db.users.delete_many({"tenant_id": t})
        db.tenants.delete_many({"id": t})


# ---------------------------------------------------------------------------
# Unitaires — normalisation
# ---------------------------------------------------------------------------
class TestNormalisation:
    def test_vin_uppercase_et_espaces(self):
        import server as srv
        assert srv._norm_vin(" wvw zzz6r zey063464 ") == VIN
        assert len(srv._norm_vin(" WVW ZZZ 6RZ EY06 3464 ")) == 17

    def test_vin_minuscule(self):
        import server as srv
        assert srv._norm_vin("wvwzzz6rzey063464") == VIN

    def test_plaque_canonique(self):
        import server as srv
        assert srv._field_same("plaque", "VD 594 862", "VD 594862")
        assert srv._field_same("plaque", "vd 594 862", "VD 594 862")
        assert not srv._field_same("plaque", "VD 594 862", "VD 594 863")

    def test_date_suisse(self):
        from extraction import normalize_value
        assert normalize_value("04.11.2013", "date") == "2013-11-04"
        assert normalize_value("22.05.2023", "date") == "2023-05-22"
        assert normalize_value("09.05.2023", "date") == "2023-05-09"

    def test_nombres(self):
        from extraction import normalize_value
        assert normalize_value("1198", "int") == 1198
        assert normalize_value(51, "float") == 51
        assert normalize_value("1067", "int") == 1067
        assert normalize_value("pas un nombre", "int") is None

    def test_review_entry_vin_longueur_invalide(self):
        import server as srv
        fd = {"key": "vin", "label": "VIN", "target": "root", "kind": "str"}
        e = srv._review_entry(fd, VIN[:16], 0.95, "found", {"vin": ""})
        assert e["valid_format"] is False
        assert e["status"] == "uncertain"
        assert e["reason"] == "VIN_INVALID_LENGTH"
        assert e["conflict"] is False

    def test_review_entry_vin_18(self):
        import server as srv
        fd = {"key": "vin", "label": "VIN", "target": "root", "kind": "str"}
        e = srv._review_entry(fd, VIN + "X", 0.95, "found", {"vin": ""})
        assert e["valid_format"] is False and e["reason"] == "VIN_INVALID_LENGTH"

    def test_review_entry_vin_match_et_conflit(self):
        import server as srv
        fd = {"key": "vin", "label": "VIN", "target": "root", "kind": "str"}
        m = srv._review_entry(fd, VIN.lower(), 0.98, "found", {"vin": VIN})
        assert m["conflict"] is False and m["reason"] == "VIN_MATCH"
        c = srv._review_entry(fd, VIN, 0.98, "found", {"vin": VIN_OTHER})
        assert c["conflict"] is True and c["reason"] == "VIN_VALUE_CONFLICT"
        n = srv._review_entry(fd, VIN, 0.98, "found", {"vin": ""})
        assert n["conflict"] is False and n["reason"] == "VIN_MISSING_CURRENT_VALUE"


# ---------------------------------------------------------------------------
# GET /documents/{id}/extraction — review ré-ouvrable, recalculée
# ---------------------------------------------------------------------------
class TestExtractionEndpoint:
    def test_champs_structures_et_mapping(self):
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_a']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["fields_count"] >= 20
        by = {f["field"]: f for f in data["fields"]}
        # Mapping canonique — cibles
        assert by["vin"]["target"] == "root"
        assert by["numero_matricule"]["target"] == "carte_grise"
        assert by["carrosserie"]["target"] == "carte_grise"
        assert by["charge_utile"]["target"] == "carte_grise"
        assert by["compagnie"]["target"] == "assurance"
        assert by["date_dernier"]["target"] == "controle_technique"
        # VIN normalisé, format valide, à compléter (véhicule vide)
        assert by["vin"]["value"] == VIN and by["vin"]["valid_format"] is True
        assert by["vin"]["conflict"] is False
        assert by["vin"]["reason"] == "VIN_MISSING_CURRENT_VALUE"
        # Plaque identique => correspondance, pas conflit
        assert by["plaque"]["conflict"] is False
        assert by["plaque"]["current_value"] is not None
        # Champs vides sur le véhicule => à compléter
        assert by["carrosserie"]["current_value"] is None

    def test_read_only_peut_consulter(self):
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_a']}/extraction",
                         headers=_h(RO_A), timeout=30)
        assert r.status_code == 200

    def test_cross_tenant_404(self):
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_a']}/extraction",
                         headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_b']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 404

    def test_document_sans_analyse_404(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents",
                          headers=_h(ADMIN_A),
                          files={"file": ("plain.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 80, "image/png")},
                          data={"folder": "Divers"}, timeout=30)
        assert r.status_code == 200, r.text
        _S["plain_doc"] = r.json()["id"]
        r = requests.get(f"{_BASE}/api/documents/{_S['plain_doc']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Confirmation humaine → mapping canonique + persistence + recalcul
# ---------------------------------------------------------------------------
class TestValidationFlow:
    def test_read_only_confirmation_403(self):
        r = requests.post(f"{_BASE}/api/documents/{_S['doc_a']}/validate",
                          json={"document_type": "permis_circulation", "fields": {"vin": VIN}},
                          headers=_h(RO_A), timeout=30)
        assert r.status_code == 403

    def test_avant_confirmation_vehicule_intact(self):
        v = _get_vehicle(ADMIN_A, _S["veh_a"])
        assert not v.get("vin")
        assert not (v.get("carte_grise") or {}).get("carrosserie")
        assert not (v.get("assurance") or {}).get("compagnie")

    def test_confirmation_applique_champs_canoniques(self):
        fields = {k: v for k, v in SWISS_FIELDS.items() if k != "plaque" and v is not None}
        docs_before = len(requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents",
                                       headers=_h(ADMIN_A), timeout=30).json())
        r = requests.post(f"{_BASE}/api/documents/{_S['doc_a']}/validate",
                          json={"document_type": "permis_circulation", "fields": fields},
                          headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["applied"] >= 20 and res["skipped_fields"] == []
        # Persistence DB — relecture backend
        v = _get_vehicle(ADMIN_A, _S["veh_a"])
        cg = v.get("carte_grise") or {}
        assert v["vin"] == VIN
        assert v["cylindree_cm3"] == 1198 and v["puissance_kw"] == 51
        assert v["poids_vide"] == 1067 and v["categorie"] == "Voiture de tourisme"
        assert v["marque"] == "VW" and v["modele"] == "Polo 1.2"
        assert cg["numero_matricule"] == "215.768.314"
        assert cg["carrosserie"] == "Limousine" and cg["couleur"] == "blanc"
        assert cg["charge_utile"] == 483 and cg["charge_toit"] == 75
        assert cg["poids_total"] == 1550 and cg["nombre_places"] == 5
        assert cg["code_emissions"] == "B5b"
        assert cg["detenteur"] == "Hygie-soins Sàrl"
        assert cg["date_emission"] == "2023-05-22" and cg["lieu_emission"] == "Yverdon"
        assert cg["date_mise_circulation"] == "2013-11-04"
        # Assureur → assurance.compagnie (PAS de doublon d'assurance)
        assert (v.get("assurance") or {}).get("compagnie") == "AXA Assurances"
        # Dernière expertise → controle_technique.date_dernier (PAS de doublon de contrôle)
        assert (v.get("controle_technique") or {}).get("date_dernier") == "2023-05-09"
        # Aucun document créé par la validation
        docs_after = len(requests.get(f"{_BASE}/api/vehicles/{_S['veh_a']}/documents",
                                      headers=_h(ADMIN_A), timeout=30).json())
        assert docs_after == docs_before
        # Statut document
        d = _mongo().documents.find_one({"id": _S["doc_a"]}, {"_id": 0, "extraction_status": 1, "vehicle_id": 1})
        assert d["extraction_status"] == "validated" and d["vehicle_id"] == _S["veh_a"]

    def test_review_recalculee_correspondance(self):
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_a']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200
        by = {f["field"]: f for f in r.json()["fields"]}
        assert by["vin"]["reason"] == "VIN_MATCH" and by["vin"]["conflict"] is False
        assert by["vin"]["current_value"] == VIN
        assert by["carrosserie"]["current_value"] == "Limousine" and by["carrosserie"]["conflict"] is False
        assert by["compagnie"]["current_value"] == "AXA Assurances" and by["compagnie"]["conflict"] is False

    def test_revalidation_idempotente(self):
        fields = {k: v for k, v in SWISS_FIELDS.items() if k != "plaque" and v is not None}
        r = requests.post(f"{_BASE}/api/documents/{_S['doc_a']}/validate",
                          json={"document_type": "permis_circulation", "fields": fields},
                          headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["applied"] == 0  # valeurs identiques => aucune écriture inutile

    def test_conflit_assurance_sans_ecrasement(self):
        requests.put(f"{_BASE}/api/vehicles/{_S['veh_a']}", headers=_h(ADMIN_A),
                     json={"assurance": {"compagnie": "Zurich Assurance"}}, timeout=30)
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_a']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        by = {f["field"]: f for f in r.json()["fields"]}
        assert by["compagnie"]["conflict"] is True
        assert by["compagnie"]["current_value"] == "Zurich Assurance"
        # Pas d'écrasement sans confirmation
        v = _get_vehicle(ADMIN_A, _S["veh_a"])
        assert v["assurance"]["compagnie"] == "Zurich Assurance"

    def test_validation_cross_tenant_404(self):
        r = requests.post(f"{_BASE}/api/documents/{_S['doc_a']}/validate",
                          json={"document_type": "permis_circulation", "fields": {"vin": VIN}},
                          headers=_h(ADMIN_B), timeout=30)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Garde anti-confusion VIN
# ---------------------------------------------------------------------------
class TestVinGuard:
    def test_vin_autre_vehicule_conflit_explicite(self):
        _S["doc_c"] = _seed_doc(TENANT_A, _S["veh_c"], {"vin": VIN_OTHER, "marque": "Audi"})
        r = requests.get(f"{_BASE}/api/documents/{_S['doc_c']}/extraction",
                         headers=_h(ADMIN_A), timeout=30)
        by = {f["field"]: f for f in r.json()["fields"]}
        assert by["vin"]["conflict"] is True
        assert by["vin"]["reason"] == "VIN_BELONGS_TO_ANOTHER_VEHICLE"

    def test_validation_vin_autre_vehicule_refusee(self):
        r = requests.post(f"{_BASE}/api/documents/{_S['doc_c']}/validate",
                          json={"document_type": "permis_circulation",
                                "fields": {"vin": VIN_OTHER, "marque": "Audi"}},
                          headers=_h(ADMIN_A), timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert any(s["reason"] == "VIN_BELONGS_TO_ANOTHER_VEHICLE" for s in res["skipped_fields"])
        # Aucune écriture du VIN, aucune fusion, aucun déplacement
        vc = _get_vehicle(ADMIN_A, _S["veh_c"])
        assert not vc.get("vin")
        assert vc.get("marque") == "Audi"  # les autres champs passent
        vb = _get_vehicle(ADMIN_A, _S["veh_b"])
        assert vb["vin"] == VIN_OTHER  # véhicule tiers non modifié
        d = _mongo().documents.find_one({"id": _S["doc_c"]}, {"_id": 0, "vehicle_id": 1})
        assert d["vehicle_id"] == _S["veh_c"]  # document jamais déplacé

    def test_vin_invalide_pas_de_recherche(self):
        doc = _seed_doc(TENANT_A, _S["veh_c"], {"vin": VIN_OTHER[:16]})
        r = requests.get(f"{_BASE}/api/documents/{doc}/extraction", headers=_h(ADMIN_A), timeout=30)
        by = {f["field"]: f for f in r.json()["fields"]}
        assert by["vin"]["reason"] == "VIN_INVALID_LENGTH"
        assert by["vin"]["status"] == "uncertain" and by["vin"]["conflict"] is False

    def test_vin_autre_tenant_aucune_fuite(self):
        doc = _seed_doc(TENANT_A, _S["veh_c"], {"vin": VIN_TENANT_B})
        r = requests.get(f"{_BASE}/api/documents/{doc}/extraction", headers=_h(ADMIN_A), timeout=30)
        by = {f["field"]: f for f in r.json()["fields"]}
        # Le VIN existe dans le tenant B : AUCUN conflit, AUCUNE métadonnée cross-tenant
        assert by["vin"]["reason"] == "VIN_MISSING_CURRENT_VALUE"
        assert by["vin"]["conflict"] is False
        assert TENANT_B not in r.text and _S["veh_tb"] not in r.text
