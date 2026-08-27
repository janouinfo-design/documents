"""Documents V2 — statuts, fiche PATCH, page centrale, catégories configurables, profils/conformité."""
import uuid
from datetime import date, timedelta

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-docv2-{_RUN}"
ADMIN = (f"docv2-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
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


def _h(creds=ADMIN):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login",
                          json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _upload(vehicle_id, folder="Divers", name="d.png"):
    r = requests.post(f"{_BASE}/api/vehicles/{vehicle_id}/documents", headers=_h(),
                      files={"file": (name, PNG, "image/png")}, data={"folder": folder}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def setup_module():
    assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": TENANT, "id": TENANT},
                         headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                         json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                         headers=sa(), timeout=30).status_code == 200
    # véhicule leasing thermique + véhicule électrique acheté
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD L{_RUN[:4]}"}, headers=_h(), timeout=30)
    _S["veh_leasing"] = r.json()["id"]
    requests.put(f"{_BASE}/api/vehicles/{_S['veh_leasing']}",
                 json={"leasing": {"societe": "TestLease", "date_fin": _iso(200)}}, headers=_h(), timeout=30)
    r = requests.post(f"{_BASE}/api/vehicles", json={"plaque": f"VD E{_RUN[:4]}", "type_carburant": "Électrique"},
                      headers=_h(), timeout=30)
    _S["veh_elec"] = r.json()["id"]
    _S["doc"] = _upload(_S["veh_leasing"], "Divers", "contrat.png")


def teardown_module():
    db = _mongo()
    for coll in ("users", "vehicles", "documents", "files", "audit_logs",
                 "tenant_integrations", "doc_categories", "doc_requirements"):
        db[coll].delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


class TestStatuts:
    def test_default_statut_valide(self):
        assert _S["doc"]["statut"] == "VALIDE"

    def test_expire(self):
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                           json={"date_expiration": _iso(-5)}, headers=_h(), timeout=30)
        assert r.status_code == 200 and r.json()["statut"] == "EXPIRE"

    def test_expire_bientot_avec_preavis(self):
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                           json={"date_expiration": _iso(45), "preavis_jours": 60}, headers=_h(), timeout=30)
        assert r.json()["statut"] == "EXPIRE_BIENTOT"
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                           json={"preavis_jours": 30}, headers=_h(), timeout=30)
        assert r.json()["statut"] == "VALIDE"

    def test_flags_prioritaires(self):
        for flag, expected in (("a_verifier", "A_VERIFIER"), ("en_renouvellement", "EN_RENOUVELLEMENT"),
                               ("archived", "ARCHIVE")):
            r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                               json={flag: True}, headers=_h(), timeout=30)
            assert r.json()["statut"] == expected, flag
        requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                       json={"a_verifier": False, "en_renouvellement": False, "archived": False},
                       headers=_h(), timeout=30)


class TestFicheDocument:
    def test_patch_metadata_complete(self):
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}", json={
            "label": "Contrat leasing 2026", "fournisseur": "TestLease SA", "numero": "CT-889",
            "date_debut": _iso(-100), "montant": 450.5, "devise": "CHF", "frequence": "mensuel",
            "tags": ["leasing", "urgent"], "responsable": "J. Dupont", "notes": "Renégocier",
            "renouvellement_auto": True,
        }, headers=_h(), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["fournisseur"] == "TestLease SA" and d["montant"] == 450.5 and d["tags"] == ["leasing", "urgent"]
        ev = _mongo().audit_logs.find_one({"action": "modify", "entity": "document",
                                           "entity_id": _S["doc"]["id"], "tenant_id": TENANT})
        assert ev, "audit modify manquant"

    def test_patch_validations(self):
        h = _h()
        did = _S["doc"]["id"]
        assert requests.patch(f"{_BASE}/api/documents/{did}", json={"date_expiration": "pas-une-date"},
                              headers=h, timeout=30).status_code == 422
        assert requests.patch(f"{_BASE}/api/documents/{did}", json={"folder": "Inexistante"},
                              headers=h, timeout=30).status_code == 422
        assert requests.patch(f"{_BASE}/api/documents/{did}", json={"montant": -5},
                              headers=h, timeout=30).status_code == 422
        assert requests.patch(f"{_BASE}/api/documents/{did}", json={"frequence": "bizarre"},
                              headers=h, timeout=30).status_code == 422

    def test_patch_cross_tenant_404(self):
        r = requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}", json={"label": "x"},
                           headers={**sa()}, timeout=30)
        assert r.status_code == 404  # superadmin tenant platform sans acting-tenant


class TestPageCentrale:
    def test_liste_avec_plaque_et_statut(self):
        r = requests.get(f"{_BASE}/api/documents", headers=_h(), timeout=30)
        assert r.status_code == 200
        docs = r.json()
        assert any(d["id"] == _S["doc"]["id"] for d in docs)
        d = next(d for d in docs if d["id"] == _S["doc"]["id"])
        assert d["plaque"] and "statut" in d

    def test_filtres(self):
        h = _h()
        _S["doc30"] = _upload(_S["veh_elec"], "Assurance", "police.png")
        requests.patch(f"{_BASE}/api/documents/{_S['doc30']['id']}",
                       json={"date_expiration": _iso(10), "fournisseur": "AXA"}, headers=h, timeout=30)
        r = requests.get(f"{_BASE}/api/documents", params={"folder": "Assurance"}, headers=h, timeout=30)
        assert all(d["folder"] == "Assurance" for d in r.json()) and r.json()
        r = requests.get(f"{_BASE}/api/documents", params={"echeance": "30"}, headers=h, timeout=30)
        assert any(d["id"] == _S["doc30"]["id"] for d in r.json())
        r = requests.get(f"{_BASE}/api/documents", params={"statut": "EXPIRE_BIENTOT"}, headers=h, timeout=30)
        assert any(d["id"] == _S["doc30"]["id"] for d in r.json())
        r = requests.get(f"{_BASE}/api/documents", params={"q": "axa"}, headers=h, timeout=30)
        assert [d["id"] for d in r.json()] and all("AXA" in (d.get("fournisseur") or "") for d in r.json())
        r = requests.get(f"{_BASE}/api/documents", params={"vehicle_id": _S["veh_elec"]}, headers=h, timeout=30)
        assert all(d["vehicle_id"] == _S["veh_elec"] for d in r.json())


class TestCategories:
    def test_defaults_9_categories(self):
        r = requests.get(f"{_BASE}/api/doc-categories", headers=_h(), timeout=30)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert len(names) == 9 and "Vignette" in names

    def test_create_rename_propagation_delete(self):
        h = _h()
        r = requests.post(f"{_BASE}/api/doc-categories", json={"name": "Amendes"}, headers=h, timeout=30)
        assert r.status_code == 200
        cat_id = r.json()["id"]
        assert requests.post(f"{_BASE}/api/doc-categories", json={"name": "Amendes"},
                             headers=h, timeout=30).status_code == 409
        doc = _upload(_S["veh_leasing"], "Amendes", "amende.png")
        assert doc["folder"] == "Amendes"
        r = requests.put(f"{_BASE}/api/doc-categories/{cat_id}",
                         json={"name": "Contraventions", "sub_categories": ["Stationnement", "Vitesse"]},
                         headers=h, timeout=30)
        assert r.status_code == 200
        moved = _mongo().documents.find_one({"id": doc["id"]})
        assert moved["folder"] == "Contraventions", "renommage non propagé aux documents"
        assert requests.delete(f"{_BASE}/api/doc-categories/{cat_id}",
                               headers=h, timeout=30).status_code == 409  # utilisée
        requests.delete(f"{_BASE}/api/documents/{doc['id']}", headers=h, timeout=30)
        assert requests.delete(f"{_BASE}/api/doc-categories/{cat_id}",
                               headers=h, timeout=30).status_code == 200

    def test_upload_unknown_category_coerced_divers(self):
        d = _upload(_S["veh_leasing"], "CategorieFantome", "x.png")
        assert d["folder"] == "Divers"
        requests.delete(f"{_BASE}/api/documents/{d['id']}", headers=_h(), timeout=30)

    def test_isolation_tenant(self):
        cats_default = requests.get(f"{_BASE}/api/doc-categories",
                                    headers={**sa(), "X-Acting-Tenant": "default"}, timeout=30).json()
        assert all(c.get("tenant_id") != TENANT for c in cats_default)


class TestProfilsConformite:
    def test_requirements_defaults(self):
        r = requests.get(f"{_BASE}/api/doc-requirements", headers=_h(), timeout=30)
        assert r.status_code == 200
        reqs = r.json()["requirements"]
        assert reqs["base"] == ["Carte grise", "Assurance", "Contrôle technique"]
        assert reqs["leasing"] == ["Leasing"]

    def test_conformite_leasing_vs_achete(self):
        h = _h()
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_leasing']}/conformite-documents", headers=h, timeout=30)
        c = r.json()
        assert "leasing" in c["profils"] and "Leasing" in c["required"]
        assert "Leasing" in c["manquants"] and c["conforme"] is False
        r = requests.get(f"{_BASE}/api/vehicles/{_S['veh_elec']}/conformite-documents", headers=h, timeout=30)
        c2 = r.json()
        assert "achete" in c2["profils"] and "electrique" in c2["profils"]
        assert "Leasing" not in c2["required"]

    def test_conformite_devient_ok_apres_uploads(self):
        h = _h()
        ids = []
        for folder in ("Carte grise", "Assurance", "Contrôle technique", "Leasing"):
            ids.append(_upload(_S["veh_leasing"], folder, f"{folder}.png")["id"])
        c = requests.get(f"{_BASE}/api/vehicles/{_S['veh_leasing']}/conformite-documents",
                         headers=h, timeout=30).json()
        assert c["manquants"] == [] and c["conforme"] is True
        for i in ids:
            requests.delete(f"{_BASE}/api/documents/{i}", headers=h, timeout=30)

    def test_requirements_custom(self):
        h = _h()
        r = requests.put(f"{_BASE}/api/doc-requirements",
                         json={"profil": "electrique", "categories": ["Contrats"]}, headers=h, timeout=30)
        assert r.status_code == 200
        c = requests.get(f"{_BASE}/api/vehicles/{_S['veh_elec']}/conformite-documents",
                         headers=h, timeout=30).json()
        assert "Contrats" in c["required"]
        assert requests.put(f"{_BASE}/api/doc-requirements",
                            json={"profil": "inconnu", "categories": []}, headers=h, timeout=30).status_code == 422


class TestDashboardV2:
    def test_nouvelles_cles(self):
        requests.patch(f"{_BASE}/api/documents/{_S['doc']['id']}",
                       json={"date_expiration": _iso(-5)}, headers=_h(), timeout=30)
        k = requests.get(f"{_BASE}/api/dashboard", headers=_h(), timeout=30).json()
        for key in ("docs_expires", "docs_expire_30", "docs_expire_31_90",
                    "docs_a_verifier", "vehicles_docs_conformes", "documents_missing"):
            assert key in k, key
        assert k["docs_expires"] >= 1
        assert k["documents_missing"] >= 1  # véhicules sans docs requis
