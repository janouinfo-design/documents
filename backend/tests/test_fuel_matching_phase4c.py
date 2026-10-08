"""Phase 4C — Lot F (6a) : rattachement transaction ↔ véhicule scoré et explicable (fuel_matching) — décision figée :
direct vehicle_id → 100 auto · carte unique + 1 affectation véhicule à date + utilisable → 90 auto (`card_assignment`, déterministe) ·
carte inactive → −50 jamais auto (review, CARD_INACTIVE) · ambiguïté (cartes, affectations, égalité) → review · plaque = 0 point jamais auto ·
conducteur +20 jamais auto seul · carburant +10/−40 · breakdown explicable ; réaffectation manuelle motivée (tx + document) ; run sans écriture véhicule."""
import sys
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
import fuel_matching as fm  # noqa: E402

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A, TENANT_B = f"pytest-fm-a-{_RUN}", f"pytest-fm-b-{_RUN}"
ADMIN_A = (f"fm-adm-a-{_RUN}@pytest.ch", f"FmAdmA-{_RUN}-1")
RO_A = (f"fm-ro-a-{_RUN}@pytest.ch", f"FmRoA-{_RUN}-1")
ADMIN_B = (f"fm-adm-b-{_RUN}@pytest.ch", f"FmAdmB-{_RUN}-1")
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


def _ctx(**over):
    base = {"direct_vehicle_id": None, "card": {"status": "none"}, "driver_vehicle_id": None, "plate_candidate_ids": [], "fuel_compat": {}}
    base.update(over)
    return base


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"}, headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"}, headers=sa(), timeout=30).status_code == 200
    for key, body, creds in (("v1", {"plaque": f"VD {_RUN[:4].upper()} 1", "type_carburant": "Diesel", "kilometrage": 1000}, ADMIN_A),
                             ("v2", {"plaque": f"VD {_RUN[:4].upper()} 2", "type_carburant": "Diesel", "kilometrage": 1000}, ADMIN_A),
                             ("vb", {"plaque": f"BE {_RUN[:4].upper()} 1", "kilometrage": 1000}, ADMIN_B)):
        r = _req("POST", "/vehicles", body, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    r = _req("POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": "9001", "type_affectation": "vehicule", "expire_le": "2030-12-31"})
    _S["card"] = r.json()["id"]
    assert _req("POST", f"/fuel-cards/{_S['card']}/assignments", {"type": "vehicule", "vehicle_id": _S["v2"], "valid_from": "2026-01-01"}).status_code == 200
    r = _req("POST", "/fuel-cards", {"fournisseur": "Shell", "last4": "9002", "type_affectation": "vehicule"})
    _S["card2"] = r.json()["id"]
    r = _req("POST", "/fuel-cards", {"fournisseur": "Shell", "last4": "9002", "type_affectation": "vehicule", "collision_confirmed": True})
    _S["card3"] = r.json()["id"]
    r = _req("POST", f"/vehicles/{_S['v1']}/fuel-transactions",
             {"date": "2026-06-01", "heure": "08:00", "station": "Migrol Test", "montant": 82.0, "litres": 40, "prix_litre": 2.05, "business_category": "CARBURANT",
              "carte_last4": "9001", "motif": "Plein test matching Lot F"})
    assert r.status_code == 200, r.text
    _S["tx"] = r.json()["fuel_transaction"]["id"]
    _S["doc"] = r.json()["document_id"]
    _S["warn"] = r.json()["warnings"]
    r = _req("POST", f"/vehicles/{_S['v1']}/fuel-transactions",
             {"date": "2026-06-02", "heure": "08:00", "station": "Shell Test", "montant": 50.0, "litres": 25, "prix_litre": 2.0, "business_category": "CARBURANT",
              "carte_last4": "9002", "motif": "Plein test carte ambiguë"})
    assert r.status_code == 200, r.text
    _S["tx_amb"] = r.json()["fuel_transaction"]["id"]
    _h(RO_A), _h(ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations", "doc_categories",
                     "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments", "fuel_cards", "fuel_card_assignments",
                     "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_transaction_matches", "fuel_anomalies"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestScoringPure:
    def test_01_direct_vehicle_id_100_auto(self):
        r = fm.score_vehicle(_ctx(direct_vehicle_id="V1"), S)
        assert (r["vehicle_id"], r["score"], r["status"], r["method"]) == ("V1", 100, "auto_matched", "direct_vehicle_id")
        assert r["breakdown"][0]["rule"] == "direct_vehicle_id" and r["breakdown"][0]["points"] == 100

    def test_02_card_unique_assigned_usable_90_auto(self):
        r = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": True, "assigned_vehicle_ids": ["V1"]}), S)
        assert (r["vehicle_id"], r["score"], r["status"], r["method"], r["deterministic"]) == ("V1", 90, "auto_matched", "card_assignment", True)
        bd = r["breakdown"][0]
        assert bd == {"rule": "card_assignment", "label": fm.RULE_LABELS["card_assignment"], "points": 90, "card_unique": True, "assignment_at_date": True,
                      "assigned_vehicle_id": "V1", "card_usable": True}
        # compatibilité carburant : le lien déterministe reste au score normatif 90 (pas 100)
        r2 = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": True, "assigned_vehicle_ids": ["V1"]}, fuel_compat={"V1": True}), S)
        assert r2["score"] == 90 and r2["status"] == "auto_matched"

    def test_03_card_inactive_never_auto_minus_50(self):
        r = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": False, "assigned_vehicle_ids": ["V1"], "inactive_reasons": ["inactive_by_status"]}), S)
        assert r["status"] == "matched_review" and r["vehicle_id"] is None and "CARD_INACTIVE" in r["review_reasons"]
        assert r["score"] == 40 and {b["rule"]: b["points"] for b in r["breakdown"]} == {"card_assignment": 90, "card_inactive": -50}
        assert r["candidates"][0]["vehicle_id"] == "V1"

    def test_04_card_ambiguous_review(self):
        r = fm.score_vehicle(_ctx(card={"status": "ambiguous", "candidate_vehicle_ids": ["V1", "V2"]}), S)
        assert r["status"] == "matched_review" and r["vehicle_id"] is None and "CARD_AMBIGUOUS" in r["review_reasons"] and len(r["candidates"]) == 2
        r1 = fm.score_vehicle(_ctx(card={"status": "ambiguous", "candidate_vehicle_ids": ["V1"]}), S)
        assert r1["status"] == "matched_review", "même un seul véhicule candidat : carte ambiguë → jamais auto"

    def test_05_two_assignments_same_date_review(self):
        r = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": True, "assigned_vehicle_ids": ["V1", "V2"]}), S)
        assert r["status"] == "matched_review" and r["vehicle_id"] is None and "MULTIPLE_CARD_ASSIGNMENTS" in r["review_reasons"] and "TIE" in r["review_reasons"]

    def test_06_plate_alone_zero_never_auto(self):
        r = fm.score_vehicle(_ctx(plate_candidate_ids=["V1"], plate_hint="VD 1"), S)
        assert r["status"] == "matched_review" and r["vehicle_id"] is None and r["candidates"][0]["partial_score"] == 0 and r["candidates"][0]["proposed"] is False
        assert r["candidates"][0]["breakdown"][0]["rule"] == "plate_candidate" and r["candidates"][0]["breakdown"][0]["points"] == 0
        r2 = fm.score_vehicle(_ctx(plate_candidate_ids=["V1", "V2"]), S)
        assert r2["status"] == "matched_review" and "PLATE_AMBIGUOUS" in r2["review_reasons"]

    def test_07_driver_alone_no_auto(self):
        r = fm.score_vehicle(_ctx(driver_vehicle_id="V1"), S)
        assert r["status"] == "matched_review" and r["vehicle_id"] is None and r["score"] == 20 and "BELOW_REVIEW_THRESHOLD" in r["review_reasons"]

    def test_08_fuel_penalty_and_bonus(self):
        r = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": True, "assigned_vehicle_ids": ["V1"]}, fuel_compat={"V1": False}), S)
        assert r["status"] == "matched_review" and r["score"] == 50 and "FUEL_INCOMPATIBLE" in r["review_reasons"]
        assert {b["rule"]: b["points"] for b in r["breakdown"]}["fuel_incompatible"] == -40
        r2 = fm.score_vehicle(_ctx(driver_vehicle_id="V1", fuel_compat={"V1": True}), S)
        assert r2["score"] == 30 and r2["status"] == "matched_review"
        assert fm.fuel_compatible("thermique", "Diesel", "Essence") is True and fm.fuel_compatible("electrique", None, "Diesel") is False
        assert fm.fuel_compatible("thermique", None, None) is None

    def test_09_no_candidate_unmatched_and_thresholds(self):
        r = fm.score_vehicle(_ctx(), S)
        assert r["status"] == "unmatched" and r["candidates"] == [] and r["score"] == 0
        strict = {**S, "score_auto": 95}
        r = fm.score_vehicle(_ctx(card={"status": "found", "card_id": "C", "usable": True, "assigned_vehicle_ids": ["V1"]}), strict)
        assert r["status"] == "matched_review", "seuil tenant respecté : 90 < 95 → revue"
        assert r["candidates"][0]["proposed"] is True  # ≥ score_review

    def test_10_card_inactive_eval_rule(self):
        e = fm.card_inactive_eval({"statut": "active", "expire_le": "2026-12-31"}, "2026-10-01")
        assert e["inactive"] is False and e["evaluation_model"] == "current_status_tx_date_expiration"
        assert fm.card_inactive_eval({"statut": "active", "expire_le": "2026-12-31"}, "2027-01-01")["inactive_by_expiration"] is True


class TestApi:
    def test_20_manual_fuel_hook_resolves_card_and_match(self):
        tx = _mongo().fuel_transactions.find_one({"tenant_id": TENANT_A, "id": _S["tx"]}, {"_id": 0})
        assert tx["card_id"] == _S["card"] and tx["card_resolution"]["status"] == "found" and tx["match_status"] == "manual" and tx["match_method"] == "document"
        assert {w["code"] for w in _S["warn"]} >= {"CARD_VEHICLE_MISMATCH"}  # carte affectée à v2, plein saisi sur v1 → warning, véhicule inchangé
        assert tx["vehicle_id"] == _S["v1"]
        amb = _mongo().fuel_transactions.find_one({"tenant_id": TENANT_A, "id": _S["tx_amb"]}, {"_id": 0})
        assert amb["card_id"] is None and amb["card_resolution"]["status"] == "ambiguous" and len(amb["card_resolution"]["candidates"]) == 2

    def test_21_manual_match_requires_reason_and_tenant(self):
        assert _req("PATCH", f"/fuel-transactions/{_S['tx']}/match", {"vehicle_id": _S["v2"], "reason": ""}).status_code == 422
        assert _req("PATCH", f"/fuel-transactions/{_S['tx']}/match", {"vehicle_id": _S["vb"], "reason": "cross tenant"}).status_code == 404
        assert _req("PATCH", f"/fuel-transactions/{_S['tx']}/match", {"vehicle_id": _S["v2"], "reason": "cross"}, ADMIN_B).status_code == 404
        assert _req("PATCH", f"/fuel-transactions/{_S['tx']}/match", {"vehicle_id": _S["v2"], "reason": "ro"}, RO_A).status_code == 403

    def test_22_manual_match_moves_tx_and_document_with_audit(self):
        db = _mongo()
        r = _req("PATCH", f"/fuel-transactions/{_S['tx']}/match", {"vehicle_id": _S["v2"], "reason": "Le plein concerne le véhicule porteur de la carte"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["transaction"]["vehicle_id"] == _S["v2"] and out["match"]["status"] == "manual" and out["match"]["reason"]
        assert db.documents.find_one({"id": _S["doc"]})["vehicle_id"] == _S["v2"], "le document (coût) suit la transaction"
        assert len(out["match"]["history"]) == 2 and out["match"]["history"][-1]["by"] == ADMIN_A[0]
        a = db.audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_transaction", "action": "match", "entity_id": _S["tx"]})
        assert a and _S["v1"] in a["detail"] and _S["v2"] in a["detail"] and "motif" in a["detail"]
        d = _req("GET", f"/fuel-transactions/{_S['tx']}").json()
        assert d["match"]["breakdown"][0]["rule"] == "manual" and d["plaque"].endswith(" 2")

    def test_23_manual_card_choice(self):
        assert _req("PATCH", f"/fuel-transactions/{_S['tx_amb']}/card", {"card_id": _S["card2"], "reason": ""}).status_code == 422
        assert _req("PATCH", f"/fuel-transactions/{_S['tx_amb']}/card", {"card_id": _S["card2"], "reason": "ro"}, RO_A).status_code == 403
        assert _req("PATCH", f"/fuel-transactions/{_S['tx_amb']}/card", {"card_id": "inexistante", "reason": "test"}).status_code == 404
        r = _req("PATCH", f"/fuel-transactions/{_S['tx_amb']}/card", {"card_id": _S["card2"], "reason": "Carte identifiée via le relevé Shell"})
        assert r.status_code == 200 and r.json()["transaction"]["card_id"] == _S["card2"] and r.json()["transaction"]["card_resolution"]["status"] == "manual"
        a = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_transaction", "action": "card", "entity_id": _S["tx_amb"]})
        assert a and "motif" in a["detail"]
        r = _req("PATCH", f"/fuel-transactions/{_S['tx_amb']}/card", {"card_id": None, "reason": "Retrait : carte non confirmée"})
        assert r.status_code == 200 and r.json()["transaction"]["card_id"] is None

    def test_24_match_run_never_changes_vehicle(self):
        db = _mongo()
        before = {x["id"]: x["vehicle_id"] for x in db.fuel_transactions.find({"tenant_id": TENANT_A}, {"_id": 0, "id": 1, "vehicle_id": 1})}
        assert _req("POST", "/fuel/match/run", creds=RO_A).status_code == 403
        r = _req("POST", "/fuel/match/run")
        assert r.status_code == 200 and r.json()["written_vehicle_changes"] == 0
        assert {x["id"]: x["vehicle_id"] for x in db.fuel_transactions.find({"tenant_id": TENANT_A}, {"_id": 0, "id": 1, "vehicle_id": 1})} == before
        assert db.fuel_transactions.find_one({"id": _S["tx"]})["match_status"] == "manual", "une décision manuelle n'est jamais écrasée par le run"

    def test_25_settings_tenant(self):
        assert _req("GET", "/tenant-settings/fuel").json()["fuel"]["score_auto"] == 90
        assert _req("PATCH", "/tenant-settings/fuel", {"score_review": 95}).status_code == 422
        assert _req("PATCH", "/tenant-settings/fuel", {"score_auto": 95}, RO_A).status_code == 403
        r = _req("PATCH", "/tenant-settings/fuel", {"score_auto": 95})
        assert r.status_code == 200 and r.json()["fuel"]["score_auto"] == 95
        assert _req("GET", "/tenant-settings/fuel", creds=ADMIN_B).json()["fuel"]["score_auto"] == 90, "paramètres tenant-scopés"
        assert _req("PATCH", "/tenant-settings/fuel", {"score_auto": 90}).status_code == 200
