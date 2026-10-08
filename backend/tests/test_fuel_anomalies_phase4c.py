"""Phase 4C — Lot F (6a) : anomalies carburant (fuel_anomalies) — 8 types spec, CARD_INACTIVE règle figée (statut courant + expiration à la
date tx), CARD_VEHICLE_MISMATCH sans correction automatique, unique (tx, type) jamais recréée après décision, décision humaine motivée + audit +
historique visible, D8 (justified legacy repris uniquement si redétectée / même tx legacy / même type / réel ; issues → commentaire au plus),
read_only 403, isolation tenant, aucun impact Amendes / Coûts."""
import sys
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
import fuel_anomalies as fan  # noqa: E402
import fuel_matching as fm  # noqa: E402

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A, TENANT_B = f"pytest-fa-a-{_RUN}", f"pytest-fa-b-{_RUN}"
ADMIN_A = (f"fa-adm-a-{_RUN}@pytest.ch", f"FaAdmA-{_RUN}-1")
RO_A = (f"fa-ro-a-{_RUN}@pytest.ch", f"FaRoA-{_RUN}-1")
ADMIN_B = (f"fa-adm-b-{_RUN}@pytest.ch", f"FaAdmB-{_RUN}-1")
S = dict(fm.DEFAULT_FUEL_SETTINGS)
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
    return requests.request(method, f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=120, **kw)


def _plein(vehicle, **over):
    body = {"date": "2026-06-01", "heure": "08:00", "station": "Migrol Test", "montant": 82.0, "litres": 40, "prix_litre": 2.05,
            "business_category": "CARBURANT", "motif": "Plein test anomalies Lot F", **over}
    r = _req("POST", f"/vehicles/{vehicle}/fuel-transactions", body)
    assert r.status_code == 200, r.text
    return r.json()


def _an(tx_id, type_):
    return _mongo().fuel_anomalies.find_one({"tenant_id": TENANT_A, "transaction_id": tx_id, "type": type_}, {"_id": 0})


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"}, headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"}, headers=sa(), timeout=30).status_code == 200
    for key, body, creds in (("v1", {"plaque": f"VD {_RUN[:4].upper()} 1", "type_carburant": "Diesel", "capacite_reservoir_l": 60, "kilometrage": 50000}, ADMIN_A),
                             ("v2", {"plaque": f"VD {_RUN[:4].upper()} 2", "type_carburant": "Diesel", "kilometrage": 1000}, ADMIN_A),
                             ("vb", {"plaque": f"BE {_RUN[:4].upper()} 1", "kilometrage": 1000}, ADMIN_B)):
        r = _req("POST", "/vehicles", body, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    # carte suspendue affectée à v2 ; carte active expirant le 2026-03-31 affectée à v1 ; carte active saine affectée à v1
    for key, last4, over in (("c_susp", "8001", {}), ("c_exp", "8002", {"expire_le": "2026-03-31"}), ("c_ok", "8003", {"expire_le": "2030-12-31"})):
        r = _req("POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": last4, "type_affectation": "vehicule", **over})
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    assert _req("POST", f"/fuel-cards/{_S['c_susp']}/assignments", {"type": "vehicule", "vehicle_id": _S["v2"], "valid_from": "2026-01-01"}).status_code == 200
    assert _req("POST", f"/fuel-cards/{_S['c_susp']}/status", {"statut": "suspendue", "motif": "test"}).status_code == 200
    for c in ("c_exp", "c_ok"):
        assert _req("POST", f"/fuel-cards/{_S[c]}/assignments", {"type": "vehicule", "vehicle_id": _S["v1"], "valid_from": "2026-01-01"}).status_code == 200
    _S["costs0"] = _req("GET", "/costs").json()["total_annuel"] if "total_annuel" in _req("GET", "/costs").json() else None
    _S["fines0"] = _req("GET", "/fines").json()["total"]
    _h(RO_A), _h(ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations", "doc_categories",
                     "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments", "fuel_cards", "fuel_card_assignments",
                     "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_transaction_matches", "fuel_anomalies"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestCardInactiveRule:
    """CARD_INACTIVE = (statut courant ≠ active) OR (expire_le renseigné ET expire_le < date tx) — sans reconstruction historique."""

    def test_01_matrix(self):
        ev = fm.card_inactive_eval
        assert ev({"statut": "active", "expire_le": "2026-12-31"}, "2026-10-01")["inactive"] is False
        e = ev({"statut": "active", "expire_le": "2026-03-31"}, "2026-06-01")
        assert e["inactive"] is True and e["inactive_by_expiration"] is True and e["inactive_by_status"] is False
        for st in ("suspendue", "bloquee", "remplacee", "expiree"):
            e = ev({"statut": st, "expire_le": "2030-12-31"}, "2026-06-01")
            assert e["inactive"] is True and e["inactive_by_status"] is True and e["inactive_by_expiration"] is False, st
        assert ev({"statut": "active", "expire_le": None}, "2026-06-01")["inactive"] is False
        assert ev({"statut": "active", "expire_le": "2026-12-31"}, "2026-10-01")["inactive_by_expiration"] is False  # tx historique avant expiration
        assert ev({"statut": "active", "expire_le": "2026-12-31"}, "2027-01-01")["inactive_by_expiration"] is True  # tx après expiration
        assert ev({"statut": "active", "expire_le": "2026-12-31"}, "2026-12-31")["inactive_by_expiration"] is False  # jour d'expiration = encore valide
        e = ev({"statut": "active", "expire_le": "2026-12-31"}, "2027-01-01")
        assert {"card_status_current", "expire_le", "transaction_date", "inactive_by_status", "inactive_by_expiration", "evaluation_model"} <= set(e)
        assert e["evaluation_model"] == "current_status_tx_date_expiration"

    def test_02_detect_pure_card_rules(self):
        tx = {"id": "T", "vehicle_id": "V1", "card_id": "C", "date": "2026-06-01", "litres": 40, "prix_litre": 2.05, "montant": 82.0, "devise": "CHF", "energie": "thermique"}
        out = fan.detect(tx, {"card_inactive": fm.card_inactive_eval({"statut": "suspendue"}, "2026-06-01"), "card_assigned_vehicle_ids": ["V2"]}, S)
        types = {a["type"]: a for a in out}
        assert "carte_inactive" in types and types["carte_inactive"]["severity"] == "critical" and types["carte_inactive"]["context"]["inactive_by_status"] is True
        assert "carte_vehicule_different" in types and types["carte_vehicule_different"]["context"]["auto_correction"] is False
        assert fan.WARNING_CODES["carte_inactive"] == "CARD_INACTIVE" and fan.WARNING_CODES["carte_vehicule_different"] == "CARD_VEHICLE_MISMATCH"
        assert fan.detect({**tx, "card_id": None}, {"card_inactive": {"inactive": True}, "card_assigned_vehicle_ids": ["V2"]}, S) == [], "sans carte résolue : aucun warning carte"
        assert set(fan.TYPES) == {"depassement_reservoir", "carte_inactive", "double_plein", "montant_inhabituel", "incoherence_montant", "odometre_incoherent",
                                  "plaque_differente", "carte_vehicule_different"}

    def test_03_detect_pure_other_rules(self):
        tx = {"id": "T", "vehicle_id": "V1", "date": "2026-06-01", "heure": "08:30", "date_heure": "2026-06-01T08:30:00", "litres": 90, "prix_litre": 2.05,
              "montant": 100.0, "devise": "CHF", "energie": "thermique", "kilometrage": 100, "plaque_mentionnee": "VD 2"}
        ctx = {"vehicle": {"capacite_reservoir_l": 60, "kilometrage": 50000, "plaque": "VD 1"}, "neighbors": [{"id": "N", "date_heure": "2026-06-01T08:00:00", "heure": "08:00"}],
               "history_amounts": [20, 20, 20, 20, 20], "prev_km": 500, "plate_hint_norm": "VD2", "vehicle_plate_norm": "VD1"}
        types = {a["type"]: a for a in fan.detect(tx, ctx, S)}
        assert {"depassement_reservoir", "double_plein", "montant_inhabituel", "incoherence_montant", "odometre_incoherent", "plaque_differente"} <= set(types)
        assert types["double_plein"]["related_transaction_id"] == "N" and types["depassement_reservoir"]["severity"] == "critical"
        # muette sans capacité ; muette sans historique suffisant
        t2 = {a["type"] for a in fan.detect(tx, {"vehicle": {}, "history_amounts": [20, 20]}, S)}
        assert "depassement_reservoir" not in t2 and "montant_inhabituel" not in t2


class TestD8Pure:
    TX = {"id": "TX1", "legacy_source": "journal", "legacy_id": "J-1"}
    OPEN = [{"id": "A1", "transaction_id": "TX1", "type": "carte_inactive", "status": "ouverte"}]

    def test_10_justified_reimported_only_if_redetected(self):
        leg = {"legacy_source": "journal", "legacy_transaction_id": "J-1", "type": "carte_inactive", "status": "justified", "reason": "Carte renouvelée", "is_test": False}
        r = fan.reimport_legacy_decision(self.TX, self.OPEN, leg)
        assert r["accepted"] is True and r["anomaly_id"] == "A1" and r["decision"]["status"] == "justifiee" and r["decision"]["legacy_decision"] is True
        assert fan.reimport_legacy_decision(self.TX, [], leg)["accepted"] is False  # non redétectée
        assert fan.reimport_legacy_decision(self.TX, self.OPEN, {**leg, "type": "double_plein"})["accepted"] is False  # type différent
        assert fan.reimport_legacy_decision(self.TX, self.OPEN, {**leg, "legacy_transaction_id": "J-2"})["accepted"] is False  # autre transaction legacy
        assert fan.reimport_legacy_decision({**self.TX, "legacy_source": None}, self.OPEN, leg)["accepted"] is False  # tx non legacy
        assert fan.reimport_legacy_decision(self.TX, self.OPEN, {**leg, "is_test": True})["accepted"] is False  # donnée test
        assert fan.reimport_legacy_decision(self.TX, self.OPEN, {**leg, "status": "open"})["accepted"] is False  # seul `justified` est repris
        decided = [{**self.OPEN[0], "status": "rejetee"}]
        assert fan.reimport_legacy_decision(self.TX, decided, leg)["accepted"] is False, "une anomalie déjà décidée n'est pas re-décidée"

    def test_11_issues_never_become_anomalies(self):
        issue = {"id": "I1", "message": "Ticket illisible", "reported_by": "USER_1", "reported_at": "2026-05-01T10:00:00", "status": "open"}
        assert fan.legacy_issue_to_comment(issue, is_real=True).startswith("Signalement legacy (USER_1) 2026-05-01 : Ticket illisible")
        assert fan.legacy_issue_to_comment(issue, is_real=False) is None
        assert fan.legacy_issue_to_comment({"message": "  "}, is_real=True) is None
        assert "signalement" not in fan.TYPES and not any("issue" in t for t in fan.TYPES)


class TestApi:
    def test_20_manual_fuel_creates_card_inactive_anomalies(self):
        r = _plein(_S["v2"], carte_last4="8001", station="Migrol A")
        tx = r["fuel_transaction"]
        _S["tx_susp"] = tx["id"]
        assert tx["card_id"] == _S["c_susp"] and {w["code"] for w in r["warnings"]} >= {"CARD_INACTIVE"}
        a = _an(tx["id"], "carte_inactive")
        assert a and a["status"] == "ouverte" and a["severity"] == "critical" and a["context"]["card_status_current"] == "suspendue" and a["context"]["inactive_by_status"] is True
        r = _plein(_S["v1"], carte_last4="8002", station="Migrol B", date="2026-06-02")
        _S["tx_exp"] = r["fuel_transaction"]["id"]
        a = _an(_S["tx_exp"], "carte_inactive")
        assert a and a["context"]["inactive_by_expiration"] is True and a["context"]["inactive_by_status"] is False and a["context"]["expire_le"] == "2026-03-31"
        r = _plein(_S["v1"], carte_last4="8002", station="Migrol C", date="2026-03-15")  # transaction historique AVANT expiration → pas inactive
        assert _an(r["fuel_transaction"]["id"], "carte_inactive") is None and not any(w["code"] == "CARD_INACTIVE" for w in r["warnings"])

    def test_21_card_vehicle_mismatch_no_auto_correction(self):
        r = _plein(_S["v2"], carte_last4="8003", station="Migrol D", date="2026-06-03")  # carte affectée à v1, plein saisi sur v2
        tx = r["fuel_transaction"]
        _S["tx_mm"] = tx["id"]
        assert tx["vehicle_id"] == _S["v2"] and tx["card_id"] == _S["c_ok"]
        assert {w["code"] for w in r["warnings"]} >= {"CARD_VEHICLE_MISMATCH"}
        a = _an(tx["id"], "carte_vehicule_different")
        assert a and a["context"]["card_assigned_vehicle_ids"] == [_S["v1"]] and a["context"]["transaction_vehicle_id"] == _S["v2"] and a["context"]["auto_correction"] is False
        assert _mongo().fuel_transactions.find_one({"id": tx["id"]})["vehicle_id"] == _S["v2"], "vehicle_id jamais substitué"
        assert _an(_S["tx_susp"], "carte_vehicule_different") is None  # carte suspendue affectée à v2, plein sur v2 → pas de mismatch

    def test_22_list_filters_and_stats(self):
        r = _req("GET", "/fuel/anomalies")
        assert r.status_code == 200
        out = r.json()
        assert out["stats"]["ouvertes"] >= 3 and out["stats"]["critical_ouvertes"] >= 3 and len(out["types"]) == 8
        assert all(i["transaction"] and i["plaque"] for i in out["items"])
        r = _req("GET", "/fuel/anomalies", params={"type": "carte_inactive", "status": "ouverte"})
        assert {i["type"] for i in r.json()["items"]} == {"carte_inactive"} and r.json()["total"] == 2
        assert _req("GET", "/fuel/anomalies", params={"status": "inconnu"}).status_code == 422
        assert _req("GET", "/fuel/anomalies", creds=RO_A).status_code == 200
        assert _req("GET", "/fuel/anomalies", creds=ADMIN_B).json()["total"] == 0, "isolation tenant"

    def test_23_decide_requires_reason_rbac_tenant(self):
        a = _an(_S["tx_susp"], "carte_inactive")
        assert _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "justify", "reason": ""}).status_code == 422
        assert _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "ignore", "reason": "xxx"}).status_code == 422
        assert _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "justify", "reason": "ro"}, RO_A).status_code == 403
        assert _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "justify", "reason": "cross"}, ADMIN_B).status_code == 404
        assert _req("GET", f"/fuel/anomalies/{a['id']}", creds=ADMIN_B).status_code == 404
        assert _an(_S["tx_susp"], "carte_inactive")["status"] == "ouverte"

    def test_24_decide_justify_with_audit_and_history(self):
        a = _an(_S["tx_susp"], "carte_inactive")
        r = _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "justify", "reason": "Carte réactivée après vérification fournisseur"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "justifiee" and out["decided_by"] == ADMIN_A[0] and out["decided_at"] and out["decision_reason"].startswith("Carte réactivée")
        assert [h["status"] for h in out["history"]] == ["ouverte", "justifiee"] and out["history"][-1]["by"] == ADMIN_A[0]
        au = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_anomaly", "action": "decide", "entity_id": a["id"]})
        assert au and "ouverte → justifiee" in au["detail"] and "motif" in au["detail"]
        assert _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "reject", "reason": "encore"}).status_code == 409  # déjà décidée
        # reste visible (jamais supprimée) et visible dans l'historique de la transaction
        assert _req("GET", f"/fuel/anomalies/{a['id']}").json()["status"] == "justifiee"
        d = _req("GET", f"/fuel-transactions/{_S['tx_susp']}").json()
        assert any(x["id"] == a["id"] and x["status"] == "justifiee" for x in d["anomalies"]) and d["anomalies_open"] == 0

    def test_25_scan_never_recreates_decided(self):
        n = _mongo().fuel_anomalies.count_documents({"tenant_id": TENANT_A})
        assert _req("POST", "/fuel/anomalies/scan", creds=RO_A).status_code == 403
        r = _req("POST", "/fuel/anomalies/scan")
        assert r.status_code == 200 and r.json()["created"] == 0 and r.json()["scanned"] >= 4
        assert _mongo().fuel_anomalies.count_documents({"tenant_id": TENANT_A}) == n
        assert _mongo().fuel_anomalies.count_documents({"tenant_id": TENANT_A, "transaction_id": _S["tx_susp"], "type": "carte_inactive"}) == 1
        assert _an(_S["tx_susp"], "carte_inactive")["status"] == "justifiee"

    def test_26_correct_and_reject_decisions(self):
        a = _an(_S["tx_mm"], "carte_vehicule_different")
        r = _req("POST", f"/fuel/anomalies/{a['id']}/decide", {"decision": "correct", "reason": "Véhicule corrigé manuellement"})
        assert r.status_code == 200 and r.json()["status"] == "corrigee"
        b = _an(_S["tx_exp"], "carte_inactive")
        r = _req("POST", f"/fuel/anomalies/{b['id']}/decide", {"decision": "reject", "reason": "Fausse alerte : date d'expiration erronée dans le référentiel"})
        assert r.status_code == 200 and r.json()["status"] == "rejetee"
        stats = _req("GET", "/fuel/anomalies").json()["stats"]
        assert stats["by_status"]["justifiee"] == 1 and stats["by_status"]["corrigee"] == 1 and stats["by_status"]["rejetee"] == 1

    def test_27_no_impact_fines_costs_lots(self):
        assert _req("GET", "/fines").json()["total"] == _S["fines0"]
        costs = _req("GET", "/costs").json()
        docs = [i for i in costs["items"] if i["source"] == "document" and i["vehicle_id"] in (_S["v1"], _S["v2"])]
        assert len(docs) == 4 and round(sum(i["montant"] for i in docs), 2) == 328.0, "4 pleins = 4 coûts (documents), anomalies sans effet sur Coûts"
        assert _mongo().fuel_anomalies.count_documents({"tenant_id": TENANT_B}) == 0
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A, "card_id": {"$exists": True}}) == 4
