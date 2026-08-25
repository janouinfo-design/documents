"""Véhicule canonique : Documents = Dashboard = Navixy (whitelist) + contrôle d'intégrité.

Le test d'écriture Navixy RÉELLE (réversible) n'est exécuté que si NAVIXY_WRITE_TEST=1
pour ne pas écrire dans le compte Navixy de production à chaque exécution de la suite.
"""
import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

COMMON_FIELDS = ["plaque", "marque", "modele", "vin", "annee", "kilometrage", "type_carburant"]


def _fleet():
    r = requests.get(f"{API}/vehicles")
    assert r.status_code == 200
    return r.json()


class TestMergePure:
    REMOTE = {"id": 164367, "tracker_id": 781479, "label": "Audi A3 2018",
              "model": "Audi A3 2018", "reg_number": "VD 602 548", "vin": "",
              "manufacture_year": 2018, "color": "Noir", "type": "car",
              "subtype": "universal", "garage_id": 1164, "max_speed": 90}

    def test_merge_changes_only_whitelist(self):
        from server import _navixy_merge_payload
        vehicle = {"plaque": "VD 602 548", "marque": "Audi", "modele": "A3",
                   "vin": "WAUZZZ8V0JA000000", "annee": 2018,
                   "carte_grise": {"couleur": "Gris"}}
        payload, changes = _navixy_merge_payload(self.REMOTE, vehicle)
        changed_keys = {k for k, _, _ in changes}
        assert changed_keys == {"vin", "model", "color"}
        # objet COMPLET préservé (read-merge-write) : rien d'autre n'est touché
        assert payload["tracker_id"] == 781479 and payload["garage_id"] == 1164
        assert payload["type"] == "car" and payload["max_speed"] == 90
        assert payload["vin"] == "WAUZZZ8V0JA000000" and payload["color"] == "Gris"
        assert payload["model"] == "Audi A3"

    def test_merge_in_sync_no_changes(self):
        from server import _navixy_merge_payload
        vehicle = {"plaque": "VD 602 548", "marque": "Audi", "modele": "A3 2018",
                   "vin": "", "annee": 2018, "carte_grise": {"couleur": "Noir"}}
        _, changes = _navixy_merge_payload(self.REMOTE, vehicle)
        assert changes == []

    def test_merge_never_clears_fields(self):
        from server import _navixy_merge_payload
        vehicle = {"plaque": "", "marque": "", "modele": "", "vin": "", "annee": 0,
                   "carte_grise": {}}
        payload, changes = _navixy_merge_payload(self.REMOTE, vehicle)
        assert changes == []
        assert payload["reg_number"] == "VD 602 548" and payload["color"] == "Noir"


class TestPushHooks:
    def test_put_unlinked_vehicle_reports_not_linked(self):
        r = requests.post(f"{API}/vehicles", json={"plaque": "ZZ 33333"})
        vid = r.json()["id"]
        try:
            resp = requests.put(f"{API}/vehicles/{vid}", json={"marque": "Test"}).json()
            assert resp.get("navixy_push", {}).get("status") == "not_linked"
        finally:
            requests.delete(f"{API}/vehicles/{vid}")

    def test_put_non_common_field_does_not_push(self):
        r = requests.post(f"{API}/vehicles", json={"plaque": "ZZ 33334"})
        vid = r.json()["id"]
        try:
            resp = requests.put(f"{API}/vehicles/{vid}", json={"responsable": "X"}).json()
            assert "navixy_push" not in resp
        finally:
            requests.delete(f"{API}/vehicles/{vid}")


class TestDocumentsEqualsDashboard:
    def test_same_canonical_vehicle_everywhere(self):
        """La page Véhicules (liste = Dashboard) et la fiche (drawer = Documents) doivent
        renvoyer strictement les mêmes valeurs : même document canonique."""
        for v in _fleet():
            detail = requests.get(f"{API}/vehicles/{v['id']}").json()
            for f in COMMON_FIELDS:
                assert detail.get(f) == v.get(f), f"{v['plaque']} champ {f} divergent"
            assert (detail.get("carte_grise") or {}) == (v.get("carte_grise") or {})


class TestIntegrityEndpoint:
    def test_integrity_structure_and_statuses(self):
        r = requests.get(f"{API}/fleet/integrity")
        assert r.status_code == 200
        body = r.json()
        assert body["navixy_status"] == "ok"
        assert body["total"] >= 1 and body["linked"] >= 1
        allowed = {"IDENTIQUE", "DIFFERENT", "NON_DISPONIBLE", "NON_SUPPORTE"}
        for e in body["vehicles"]:
            assert e["link_status"] in ("LIE", "NON_LIE", "ERREUR_INTEGRATION", "INTEGRATION_ABSENTE")
            if e["link_status"] != "LIE":
                assert e["fields"] is None and e["note"]
                continue
            for name in ("nom", "plaque", "vin", "marque_modele", "annee", "couleur",
                         "type", "garage", "departement"):
                f = e["fields"][name]
                assert f["status"] in allowed, f"{name}: {f['status']}"
            assert e["fields"]["departement"]["status"] == "NON_SUPPORTE"
            assert e["divergences"] == sum(
                1 for f in e["fields"].values() if f["status"] == "DIFFERENT")

    def test_integrity_is_audited(self):
        before = requests.get(f"{API}/fleet/integrity").json()
        assert "divergences" in before  # l'appel audite (vérifié via audit_logs en E2E)


@pytest.mark.skipif(os.environ.get("NAVIXY_WRITE_TEST") != "1",
                    reason="écriture Navixy réelle — exécuter avec NAVIXY_WRITE_TEST=1")
class TestRealNavixyPushReversible:
    def test_push_color_and_restore(self):
        fleet = _fleet()
        v = next(x for x in fleet if x.get("navixy_vehicle_id"))
        orig_local = ((v.get("carte_grise") or {}).get("couleur")) or ""
        # 1. push d'une couleur de test
        r = requests.put(f"{API}/vehicles/{v['id']}",
                         json={"carte_grise": {"couleur": "SyncTest"}}).json()
        assert r["navixy_push"]["status"] == "pushed", r["navixy_push"]
        assert "color" in r["navixy_push"]["fields"]
        # 2. vérification côté Navixy réel + intégrité IDENTIQUE
        integ = requests.get(f"{API}/fleet/integrity").json()
        entry = next(e for e in integ["vehicles"] if e["vehicle_id"] == v["id"])
        assert entry["fields"]["couleur"]["navixy"] == "SyncTest"
        assert entry["fields"]["couleur"]["status"] == "IDENTIQUE"
        # 3. restauration des deux côtés
        r2 = requests.put(f"{API}/vehicles/{v['id']}",
                          json={"carte_grise": {"couleur": orig_local or "Noir"}}).json()
        assert r2["navixy_push"]["status"] == "pushed"
