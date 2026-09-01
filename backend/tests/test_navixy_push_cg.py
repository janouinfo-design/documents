"""Synchronisation carte grise confirmée → véhicule canonique → Navixy.
Mapping whitelist prouvé, tenant strict, lien canonique uniquement, retry, jamais d'OCR direct."""
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-navpush-{_RUN}"
ADMIN = (f"navpush-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
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


def setup_module():
    r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"NavPush {_RUN}", "id": TENANT},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                      json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"NP {_RUN[:6].upper()}", "marque": "VW", "modele": "Polo"})
    assert r.status_code == 200, r.text
    _S["veh"] = r.json()["id"]


def teardown_module():
    db = _mongo()
    db.vehicles.delete_many({"tenant_id": TENANT})
    db.documents.delete_many({"tenant_id": TENANT})
    db.audit_logs.delete_many({"tenant_id": TENANT})
    db.vehicle_field_meta.delete_many({"tenant_id": TENANT})
    db.users.delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


# ---------------------------------------------------------------------------
# Unitaires — mapping whitelist LOGITRAK → Navixy (champs documentés uniquement)
# ---------------------------------------------------------------------------
class TestMergePayload:
    def _veh(self, **kw):
        base = {"plaque": "VD 594 862", "vin": "WVWZZZ6RZEY063464", "marque": "VW",
                "modele": "Polo 1.2", "annee": 2013, "type_carburant": "Essence",
                "capacite_reservoir_l": 45,
                "carte_grise": {"couleur": "blanc", "charge_utile": 483, "poids_total": 1550}}
        base.update(kw)
        return base

    def test_champs_compatibles_mappes(self):
        import server as srv
        payload, changes = srv._navixy_merge_payload({}, self._veh())
        by = dict((k, n) for k, _, n in changes)
        assert by["reg_number"] == "VD 594 862"
        assert by["vin"] == "WVWZZZ6RZEY063464"
        assert by["model"] == "VW Polo 1.2"
        assert by["manufacture_year"] == 2013
        assert by["color"] == "blanc"
        assert by["payload_weight"] == 483
        assert by["gross_weight"] == 1550
        assert by["fuel_tank_volume"] == 45
        assert by["fuel_type"] == "petrol"
        assert payload["gross_weight"] == 1550

    def test_champs_non_compatibles_jamais_pousses(self):
        import server as srv
        veh = self._veh()
        veh["carte_grise"].update({"detenteur": "Hygie-soins Sàrl", "carrosserie": "Limousine",
                                   "numero_matricule": "215.768.314", "charge_toit": 75,
                                   "adresse_detenteur": "Lucens", "lieu_emission": "Yverdon"})
        payload, changes = srv._navixy_merge_payload({}, veh)
        flat = str(payload) + str(changes)
        for interdit in ("Hygie-soins", "Limousine", "215.768.314", "Yverdon"):
            assert interdit not in flat  # aucun détournement de champ Navixy

    def test_valeur_inchangee_aucun_appel(self):
        import server as srv
        remote = {"reg_number": "VD 594 862", "vin": "WVWZZZ6RZEY063464", "model": "VW Polo 1.2",
                  "manufacture_year": 2013, "color": "blanc", "payload_weight": 483,
                  "gross_weight": 1550, "fuel_tank_volume": 45, "fuel_type": "petrol"}
        _, changes = srv._navixy_merge_payload(remote, self._veh())
        assert changes == []  # idempotence : rien à envoyer

    def test_jamais_vider_un_champ_navixy(self):
        import server as srv
        remote = {"reg_number": "GE 111 222", "color": "rouge", "fuel_type": "diesel", "label": "Camion 7"}
        payload, changes = srv._navixy_merge_payload(remote, {"plaque": "", "carte_grise": {}})
        assert payload["reg_number"] == "GE 111 222" and payload["color"] == "rouge"
        assert payload["label"] == "Camion 7"  # read-merge-write : objet complet préservé
        assert changes == []

    def test_electrique_pas_de_fuel_type(self):
        import server as srv
        _, changes = srv._navixy_merge_payload({}, self._veh(type_carburant="Électrique"))
        assert "fuel_type" not in {k for k, _, _ in changes}  # enum Navixy sans équivalent sûr

    def test_gaz_mappe_gas(self):
        import server as srv
        _, changes = srv._navixy_merge_payload({}, self._veh(type_carburant="Gaz naturel"))
        assert dict((k, n) for k, _, n in changes)["fuel_type"] == "gas"


# ---------------------------------------------------------------------------
# Endpoint retry + tenant/RBAC + ordre validation → local → navixy
# ---------------------------------------------------------------------------
class TestPushEndpoint:
    def test_integration_absente_local_intact(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/navixy/push", headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["navixy_push"]["status"] == "integration_absente"

    def test_read_only_403(self):
        vb = _mongo().vehicles.find_one({"tenant_id": "client-test-e2e"}, {"_id": 0, "id": 1})
        if not vb:
            pytest.skip("pas de véhicule tenant read_only")
        r = requests.post(f"{_BASE}/api/vehicles/{vb['id']}/navixy/push", headers=ro(), timeout=30)
        assert r.status_code == 403

    def test_cross_tenant_404(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/navixy/push", headers=sa(), timeout=30)
        # superadmin agit sur tenant default par défaut => véhicule d'un autre tenant introuvable
        assert r.status_code == 404

    def test_vehicule_default_non_lie(self):
        """Véhicule du tenant default (intégration présente) mais sans lien navixy_vehicle_id => not_linked.
        Aucune écriture Navixy réelle (production protégée)."""
        v = _mongo().vehicles.find_one({"tenant_id": "default", "plaque": "VD 594 862",
                                        "navixy_vehicle_id": None}, {"_id": 0, "id": 1})
        if not v:
            pytest.skip("VD 594 862 absent ou lié")
        adm_h = _h(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"])
        r = requests.post(f"{_BASE}/api/vehicles/{v['id']}/navixy/push", headers=adm_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["navixy_push"]["status"] == "not_linked"


class TestValidateFlowOrder:
    def test_validation_locale_ok_navixy_skippe(self):
        """Ordre prouvé : confirmation humaine -> écriture canonique OK -> navixy_push renvoyé
        (ici integration_absente) sans jamais faire échouer la sauvegarde locale."""
        now = datetime.now(timezone.utc).isoformat()
        doc_id = str(uuid.uuid4())
        _mongo().documents.insert_one({
            "id": doc_id, "vehicle_id": _S["veh"], "tenant_id": TENANT, "folder": "Carte grise",
            "original_filename": f"cg-{_RUN}.jpg", "storage_path": f"logitrak-fleet/media/{_S['veh']}/x.jpg",
            "content_type": "image/jpeg", "size": 10, "is_deleted": False,
            "document_type": "permis_circulation", "extraction_status": "done",
            "analyzed_at": now, "created_at": now,
            "extracted_fields": [
                {"field": "couleur", "value": "blanc", "confidence": 0.97, "status": "found"},
                {"field": "charge_utile", "value": 483, "confidence": 0.95, "status": "found"},
                {"field": "detenteur", "value": "Hygie-soins Sàrl", "confidence": 0.95, "status": "found"},
            ]})
        r = requests.post(f"{_BASE}/api/documents/{doc_id}/validate",
                          json={"document_type": "permis_circulation",
                                "fields": {"couleur": "blanc", "charge_utile": 483,
                                           "detenteur": "Hygie-soins Sàrl"}},
                          headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["applied"] == 3
        assert res["navixy_push"]["status"] == "integration_absente"
        # Persistence locale intacte malgré Navixy non configuré
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30).json()
        assert v["carte_grise"]["couleur"] == "blanc" and v["carte_grise"]["charge_utile"] == 483

    def test_champ_non_confirme_jamais_candidat(self):
        """Champ OCR non coché (non envoyé au validate) => jamais écrit, donc jamais poussé."""
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30).json()
        assert v["carte_grise"].get("poids_total") in (None, 0)  # jamais validé => absent du canonique


class TestSyncLinkPreservation:
    """La sync quotidienne ne doit JAMAIS effacer un lien fiche véhicule Navixy existant."""

    def test_lien_absent_cote_navixy_aucune_cle(self):
        import server as srv
        assert srv._sync_link_fields({}) == {}
        assert srv._sync_link_fields({"id": None}) == {}

    def test_lien_present_cote_navixy_renvoye(self):
        import server as srv
        out = srv._sync_link_fields({"id": 178973})
        assert out["navixy_vehicle_id"] == 178973
        assert out["integrations.navixy.external_vehicle_id"] == 178973

    def test_sync_reelle_preserve_lien_manuel(self):
        """E2E : lien sentinelle posé sur un véhicule tracker-only du tenant default,
        sync réelle (lectures Navixy uniquement), le lien doit survivre. Restauration garantie."""
        if not (_ENV.get("NAVIXY_API_HASH") or "").strip():
            pytest.skip("pas d'intégration Navixy configurée")
        db = _mongo()
        v = db.vehicles.find_one({"tenant_id": "default", "navixy_tracker_id": {"$ne": None},
                                  "navixy_vehicle_id": None}, {"_id": 0, "id": 1})
        if not v:
            pytest.skip("aucun véhicule default tracker-only disponible")
        sentinel = 999999999
        adm_h = _h(_ENV["ADMIN_EMAIL"], _ENV["ADMIN_PASSWORD"])
        db.vehicles.update_one({"id": v["id"]}, {"$set": {"navixy_vehicle_id": sentinel}})
        try:
            r = requests.post(f"{_BASE}/api/navixy/sync", headers=adm_h, timeout=120)
            assert r.status_code == 200, r.text
            after = db.vehicles.find_one({"id": v["id"]}, {"_id": 0, "navixy_vehicle_id": 1})
            assert after["navixy_vehicle_id"] == sentinel, "la sync a effacé le lien manuel"
        finally:
            db.vehicles.update_one({"id": v["id"]}, {"$set": {"navixy_vehicle_id": None}})


class TestReservoirApplyPush:
    """Validation réservoir IA => même service de sync Navixy que la carte grise."""

    def test_apply_sans_integration_local_intact(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/reservoir/apply",
                          json={"value_l": 55}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["navixy_push"]["status"] == "integration_absente"
        assert res["vehicle"]["capacite_reservoir_l"] == 55
        v = requests.get(f"{_BASE}/api/vehicles/{_S['veh']}", headers=_h(*ADMIN), timeout=30).json()
        assert v["capacite_reservoir_l"] == 55  # échec/absence Navixy ne bloque jamais le local
