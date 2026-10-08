"""Phase 4C — Lot F : garde-fous backend (matrices de preuve). Preview = 0 écriture métier finale (hash des collections métier),
confirm idempotent, card_id uniquement si found, plaque = 0 point / jamais auto, action groupée N lignes = N audits,
CARD_INACTIVE (statut courant + expiration à la date tx), CARD_VEHICLE_MISMATCH sans correction, read_only = 403, cross-tenant fail-closed."""
import hashlib
import json
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
TA, TB = f"pytest-fg-a-{_RUN}", f"pytest-fg-b-{_RUN}"
ADM_A, RO_A, ADM_B = (f"fg-a-{_RUN}@pytest.ch", f"FgA-{_RUN}-1"), (f"fg-ro-{_RUN}@pytest.ch", f"FgRo-{_RUN}-1"), (f"fg-b-{_RUN}@pytest.ch", f"FgB-{_RUN}-1")
BUSINESS = ("documents", "fuel_transactions", "fuel_cards", "fuel_card_assignments", "fuel_anomalies", "fuel_transaction_matches", "vehicles", "drivers")
P = _RUN[:4].upper()
HEADER = ["Ref", "Date", "Carte", "Plaque", "vehicle_id", "Montant", "Devise", "Quantite", "Prix", "Station"]
MAPPING = {"external_transaction_id": "Ref", "tx_datetime": "Date", "card_last4": "Carte", "vehicle_hint": "Plaque", "vehicle_id": "vehicle_id",
           "amount_total": "Montant", "currency": "Devise", "quantity": "Quantite", "unit_price": "Prix", "station_name": "Station"}
S, _cache = {}, {}


def _db():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def _sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def R(method, path, body=None, creds=ADM_A):
    return requests.request(method, f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=120)


def _upload(rows, creds=ADM_A):
    content = ("\n".join(";".join(r) for r in [HEADER] + rows) + "\n").encode("utf-8")
    return requests.post(f"{_BASE}/api/fuel/imports", files={"file": ("fg.csv", content)}, data={"fournisseur": "Migrol"}, headers=_h(creds), timeout=120)


def _card(**over):
    r = R("POST", "/fuel-cards", {"fournisseur": "Migrol", "type_affectation": "vehicule", "expire_le": "2030-12-31", **over})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _assign(card_id, vid):
    assert R("POST", f"/fuel-cards/{card_id}/assignments", {"type": "vehicule", "valid_from": "2026-01-01", "vehicle_id": vid}).status_code == 200


def _hash_business():
    """Hash déterministe du contenu (sans _id) des collections métier finales des deux tenants."""
    db = _db()
    out = {}
    for c in BUSINESS:
        docs = list(db[c].find({"tenant_id": {"$in": [TA, TB]}}, {"_id": 0}).sort("id", 1))
        out[c] = (len(docs), hashlib.sha256(json.dumps(docs, sort_keys=True, default=str).encode()).hexdigest()[:16])
    return out


def _counts(tenant=TA):
    db = _db()
    return {c: db[c].count_documents({"tenant_id": tenant}) for c in ("documents", "fuel_transactions", "fuel_anomalies", "fuel_transaction_matches")}


def setup_module():
    for tenant, admin in ((TA, ADM_A), (TB, ADM_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=_sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"}, headers=_sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TA}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"}, headers=_sa(), timeout=30).status_code == 200
    for k in ("v1", "v2", "v3", "v4", "v5"):
        r = R("POST", "/vehicles", {"plaque": f"VD {P} {k[1]}0", "type_carburant": "Diesel", "kilometrage": 1000})
        assert r.status_code == 200, r.text
        S[k] = r.json()["id"]
    r = R("POST", "/vehicles", {"plaque": f"BE {P} 99", "kilometrage": 1}, ADM_B)
    S["vb"] = r.json()["id"]
    S["c_found"] = _card(last4="1111"); _assign(S["c_found"], S["v1"])
    S["c_amb1"] = _card(fournisseur="Shell", last4="2222"); _assign(S["c_amb1"], S["v1"])
    S["c_amb2"] = _card(fournisseur="Shell", last4="2222", collision_confirmed=True); _assign(S["c_amb2"], S["v2"])
    S["c_susp"] = _card(last4="3333"); _assign(S["c_susp"], S["v2"])
    assert R("POST", f"/fuel-cards/{S['c_susp']}/status", {"statut": "suspendue", "motif": "test"}).status_code == 200
    S["c_exp"] = _card(last4="7777", expire_le="2026-03-31"); _assign(S["c_exp"], S["v1"])
    S["c_mis"] = _card(last4="9999"); _assign(S["c_mis"], S["v2"])
    r = R("POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": "1111", "type_affectation": "vehicule"}, ADM_B)
    S["cb"] = r.json()["id"]
    _h(RO_A); _h(ADM_B)


def teardown_module():
    db = _db()
    for tenant in (TA, TB):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations", "doc_categories",
                     "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments", "fuel_cards", "fuel_card_assignments",
                     "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_transaction_matches", "fuel_anomalies", "login_attempts"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


ROWS = lambda: [  # noqa: E731
    ["R1", "01.06.2026 08:00", "1111", "", "", "82.00", "CHF", "40", "2.05", "Migrol Lausanne"],
    ["R2", "01.06.2026 09:00", "2222", "", "", "60.00", "CHF", "30", "2.00", "Shell Vevey"],
    ["R3", "01.06.2026 10:00", "0000", "", "", "55.00", "CHF", "25", "2.20", "Migrol Nyon"],
    ["R4", "02.06.2026 10:00", "", f"VD {P} 30", "", "41.00", "CHF", "20", "2.05", "Migrol Nyon"],
    ["R5", "02.06.2026 11:00", "", f"VD {P} 40", "", "41.00", "CHF", "20", "2.05", "Migrol Morges"],
    ["R6", "02.06.2026 12:00", "", f"VD-{P}-50", "", "41.00", "CHF", "20", "2.05", "Migrol Gland"],
    ["R7", "03.06.2026 08:00", "9999", "", S["v1"], "41.00", "CHF", "20", "2.05", "Migrol Rolle"],
    ["R8", "03.06.2026 09:00", "7777", "", S["v1"], "41.00", "CHF", "20", "2.05", "Migrol Aigle"],
    ["R9", "03.06.2026 10:00", "3333", "", S["v2"], "41.00", "CHF", "20", "2.05", "Migrol Sion"],
]


class TestGuardrails:
    def test_01_preview_zero_final_business_writes(self):
        r = _upload(ROWS())
        assert r.status_code == 200, r.text
        S["job"] = r.json()["id"]
        before = _hash_business()
        r = R("POST", f"/fuel/imports/{S['job']}/mapping", {"mapping": MAPPING})
        assert r.status_code == 200, r.text
        after = _hash_business()
        assert before == after, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
        S["rows"] = {x["raw"]["Ref"]: x for x in r.json()["rows"]}
        S["preview_hash"] = after
        print("\nPREVIEW_FINAL_BUSINESS_WRITES = 0 —", json.dumps(after))

    def test_02_card_id_matrix_preview(self):
        rows = S["rows"]
        assert rows["R1"]["resolution"]["card"]["status"] == "found" and rows["R1"]["resolution"]["card"]["card_id"] == S["c_found"]
        assert rows["R2"]["resolution"]["card"]["status"] == "ambiguous" and rows["R2"]["resolution"]["card"]["card_id"] is None
        assert len(rows["R2"]["resolution"]["card"]["candidates"]) == 2 and rows["R2"]["status"] == "unknown_vehicle"
        assert rows["R3"]["resolution"]["card"]["status"] == "not_found" and rows["R3"]["resolution"]["card"]["card_id"] is None
        assert all(c["id"] != S["cb"] for c in rows["R1"]["resolution"]["card"]["candidates"])

    def test_03_scoring_rules(self):
        v = S["rows"]["R1"]["resolution"]["vehicle"]
        assert v["status"] == "auto_matched" and v["method"] == "card_assignment" and v["score"] == 90 and v["vehicle_id"] == S["v1"]
        v7 = S["rows"]["R7"]["resolution"]["vehicle"]
        assert v7["status"] == "auto_matched" and v7["method"] == "direct_vehicle_id" and v7["score"] == 100 and v7["vehicle_id"] == S["v1"]
        v8 = S["rows"]["R8"]["resolution"]["vehicle"]  # direct id prime, mais la carte expirée est signalée à l'import (anomalie)
        assert v8["method"] == "direct_vehicle_id"

    def test_04_plate_unique_never_auto(self):
        for ref in ("R4", "R5", "R6"):
            row = S["rows"][ref]
            v = row["resolution"]["vehicle"]
            assert row["status"] == "unknown_vehicle" and v["status"] == "matched_review" and v["vehicle_id"] is None and v["method"] is None
            assert len(v["candidates"]) == 1 and "plate_candidate" in v["candidates"][0]["sources"]
            assert next(b for b in v["candidates"][0]["breakdown"] if b["rule"] == "plate_candidate")["points"] == 0 and v["candidates"][0]["partial_score"] < 70
        assert S["rows"]["R6"]["resolution"]["vehicle"]["candidates"][0]["vehicle_id"] == S["v5"]  # plaque normalisée (tirets)

    def test_05_bulk_accept_n_rows_n_audits(self):
        ids = [S["rows"][k]["id"] for k in ("R4", "R5", "R6")]
        assert R("POST", f"/fuel/imports/{S['job']}/rows/accept-unique", {"row_ids": ids, "reason": ""}).status_code == 422
        assert R("POST", f"/fuel/imports/{S['job']}/rows/accept-unique", {"row_ids": ids, "reason": "  "}).status_code == 422
        db = _db()
        q = {"tenant_id": TA, "entity": "fuel_import", "action": "row_resolve"}
        n0 = db.audit_logs.count_documents(q)
        r = R("POST", f"/fuel/imports/{S['job']}/rows/accept-unique", {"row_ids": ids, "reason": "Plaques vérifiées sur le relevé"})
        assert r.status_code == 200, r.text
        out = r.json()
        assert len(out["accepted"]) == 3 and out["refused"] == []
        audits = list(db.audit_logs.find({**q, "detail": {"$regex": out["batch_id"]}}))
        assert db.audit_logs.count_documents(q) == n0 + 3 and len(audits) == 3
        for a, acc in zip(sorted(audits, key=lambda a: a["detail"]), sorted(out["accepted"], key=lambda a: f"ligne {a['row_index']} ")):
            assert a["user"] == ADM_A[0] and a["tenant_id"] == TA and a["entity_id"] == S["job"] and a["created_at"]
            assert "unknown_vehicle →" in a["detail"] and "motif : Plaques vérifiées" in a["detail"] and "plaque source" in a["detail"]
        for acc in out["accepted"]:
            a = db.audit_logs.find_one({**q, "detail": {"$regex": f"row_id {acc['row_id']}"}})
            assert a and a["vehicle_id"] == acc["vehicle_id"] and acc["plaque_source"] in a["detail"]
        rows = {x["raw"]["Ref"]: x for x in R("GET", f"/fuel/imports/{S['job']}/rows").json()["items"]}
        for ref in ("R4", "R5", "R6"):
            assert rows[ref]["status"] == "ok" and rows[ref]["resolution"]["vehicle"]["status"] == "manual" and rows[ref]["resolution"]["vehicle"]["breakdown"][0]["provenance"] == "plate_candidate"
        S["rows"] = rows

    def test_06_card_inactive_matrix(self):
        cases = [({"statut": "active", "expire_le": "2026-12-31"}, "2026-06-01", False, False),
                 ({"statut": "active", "expire_le": "2026-03-31"}, "2026-06-01", False, True),
                 ({"statut": "suspendue", "expire_le": "2030-12-31"}, "2026-06-01", True, False),
                 ({"statut": "bloquee", "expire_le": "2030-12-31"}, "2026-06-01", True, False),
                 ({"statut": "remplacee", "expire_le": "2030-12-31"}, "2026-06-01", True, False),
                 ({"statut": "expiree", "expire_le": "2030-12-31"}, "2026-06-01", True, False),
                 ({"statut": "active", "expire_le": None}, "2026-06-01", False, False),
                 ({"statut": "active", "expire_le": "2026-06-01"}, "2026-06-01", False, False)]  # expire_le == date tx : pas strictement antérieure
        for card, day, by_status, by_exp in cases:
            e = fm.card_inactive_eval(card, day)
            assert (e["inactive_by_status"], e["inactive_by_expiration"], e["inactive"]) == (by_status, by_exp, by_status or by_exp), (card, e)
            assert e["card_status_current"] == card["statut"] and e["expire_le"] == card["expire_le"] and e["transaction_date"] == day
            assert e["evaluation_model"] == "current_status_tx_date_expiration"

    def test_07_confirm_idempotent(self):
        c0 = _counts()
        r1 = R("POST", f"/fuel/imports/{S['job']}/confirm")
        assert r1.status_code == 200, r1.text
        c1 = _counts()
        assert r1.json()["imported"] == 7 and r1.json()["set_aside"] == {"unknown_vehicle": 2}  # R2 (carte ambiguë) / R3 (carte introuvable) sans véhicule → mises de côté
        assert c1["documents"] == c0["documents"] + 7 and c1["fuel_transactions"] == c0["fuel_transactions"] + 7 and c1["fuel_transaction_matches"] == c0["fuel_transaction_matches"] + 7
        r2 = R("POST", f"/fuel/imports/{S['job']}/confirm")
        assert r2.status_code == 200 and r2.json()["imported"] == 0 and r2.json()["already_imported"] == 7
        assert _counts() == c1, (c1, _counts())
        for ref, vid in (("R2", S["v1"]), ("R3", S["v2"])):  # décision humaine véhicule ; la carte reste non résolue (card_id null)
            r = R("PATCH", f"/fuel/imports/{S['job']}/rows/{S['rows'][ref]['id']}", {"vehicle_id": vid, "reason": f"Véhicule confirmé ({ref})"})
            assert r.status_code == 200 and r.json()["row"]["status"] == "unknown_card" and r.json()["row"]["resolution"]["card"]["card_id"] is None, r.text
        r3 = R("POST", f"/fuel/imports/{S['job']}/confirm")
        assert r3.status_code == 200 and r3.json()["imported"] == 2 and r3.json()["already_imported"] == 7
        c3 = _counts()
        assert c3["documents"] == c1["documents"] + 2 and c3["fuel_transactions"] == c1["fuel_transactions"] + 2
        r4 = R("POST", f"/fuel/imports/{S['job']}/confirm")
        assert r4.status_code == 200 and r4.json()["imported"] == 0 and r4.json()["already_imported"] == 9 and _counts() == c3
        S["tx"] = {k: v["transaction_id"] for k, v in {x["raw"]["Ref"]: x for x in R("GET", f"/fuel/imports/{S['job']}/rows").json()["items"]}.items() if v.get("transaction_id")}
        assert len(S["tx"]) == 9
        print("\nCONFIRM counts avant / après 1 / après 2 (idem) / après 3 (+2 résolues) / après 4 (idem) :", c0, c1, c3)

    def test_08_card_id_matrix_final(self):
        db = _db()
        tx = {k: db.fuel_transactions.find_one({"tenant_id": TA, "id": v}, {"_id": 0}) for k, v in S["tx"].items()}
        assert tx["R1"]["card_id"] == S["c_found"] and tx["R1"]["card_resolution"]["status"] == "found"
        assert tx["R2"]["card_id"] is None and tx["R2"]["card_resolution"]["status"] == "ambiguous"
        assert tx["R3"]["card_id"] is None and tx["R3"]["card_resolution"]["status"] == "not_found"
        assert db.fuel_cards.count_documents({"tenant_id": TA, "fournisseur": "Shell", "last4": "2222", "is_deleted": False}) == 2  # identité non unique

    def test_09_mismatch_and_inactive_anomalies_no_correction(self):
        db = _db()
        t7 = db.fuel_transactions.find_one({"tenant_id": TA, "id": S["tx"]["R7"]}, {"_id": 0})
        assert t7["vehicle_id"] == S["v1"] and t7["card_id"] == S["c_mis"]
        a = db.fuel_anomalies.find_one({"tenant_id": TA, "transaction_id": t7["id"], "type": "carte_vehicule_different"}, {"_id": 0})
        assert a and a["status"] == "ouverte" and a["context"]["auto_correction"] is False and a["context"]["card_assigned_vehicle_ids"] == [S["v2"]]
        t8 = db.fuel_transactions.find_one({"tenant_id": TA, "id": S["tx"]["R8"]}, {"_id": 0})
        a8 = db.fuel_anomalies.find_one({"tenant_id": TA, "transaction_id": t8["id"], "type": "carte_inactive"}, {"_id": 0})
        assert a8 and a8["context"]["inactive_by_expiration"] is True and a8["context"]["inactive_by_status"] is False and a8["context"]["expire_le"] == "2026-03-31"
        assert a8["context"]["transaction_date"] == "2026-06-03" and a8["context"]["card_status_current"] == "active"
        a9 = db.fuel_anomalies.find_one({"tenant_id": TA, "transaction_id": S["tx"]["R9"], "type": "carte_inactive"}, {"_id": 0})
        assert a9 and a9["context"]["inactive_by_status"] is True and a9["context"]["card_status_current"] == "suspendue"
        S["anomaly"] = a["id"]

    def test_10_read_only_403_matrix(self):
        job, rid, txid = S["job"], S["rows"]["R2"]["id"], S["tx"]["R2"]
        matrix = [("upload", _upload(ROWS(), RO_A)),
                  ("mapping", R("POST", f"/fuel/imports/{job}/mapping", {"mapping": MAPPING}, RO_A)),
                  ("confirm", R("POST", f"/fuel/imports/{job}/confirm", creds=RO_A)),
                  ("row_resolve", R("PATCH", f"/fuel/imports/{job}/rows/{rid}", {"vehicle_id": S["v1"], "reason": "ro"}, RO_A)),
                  ("accept_unique", R("POST", f"/fuel/imports/{job}/rows/accept-unique", {"row_ids": [rid], "reason": "ro"}, RO_A)),
                  ("force", R("POST", f"/fuel/imports/{job}/rows/{rid}/force", {"reason": "ro"}, RO_A)),
                  ("tx_match", R("PATCH", f"/fuel-transactions/{txid}/match", {"vehicle_id": S["v1"], "reason": "ro"}, RO_A)),
                  ("tx_card", R("PATCH", f"/fuel-transactions/{txid}/card", {"card_id": S["c_amb1"], "reason": "ro"}, RO_A)),
                  ("match_run", R("POST", "/fuel/match/run", creds=RO_A)),
                  ("anomaly_scan", R("POST", "/fuel/anomalies/scan", creds=RO_A)),
                  ("anomaly_decide", R("POST", f"/fuel/anomalies/{S['anomaly']}/decide", {"decision": "justify", "reason": "ro"}, RO_A)),
                  ("settings", R("PATCH", "/tenant-settings/fuel", {"score_auto": 95}, RO_A))]
        bad = [(k, r.status_code) for k, r in matrix if r.status_code != 403]
        assert not bad, bad
        for path in (f"/fuel/imports/{job}", f"/fuel/imports/{job}/rows", f"/fuel-transactions/{txid}", "/fuel/anomalies", "/fuel/import-fields", "/tenant-settings/fuel"):
            assert R("GET", path, creds=RO_A).status_code == 200, path
        print("\nREAD_ONLY 403 :", [k for k, _ in matrix])

    def test_11_cross_tenant_fail_closed_matrix(self):
        job, rid, txid = S["job"], S["rows"]["R2"]["id"], S["tx"]["R2"]
        matrix = [("job_get", R("GET", f"/fuel/imports/{job}", creds=ADM_B)),
                  ("rows_get", R("GET", f"/fuel/imports/{job}/rows", creds=ADM_B)),
                  ("mapping", R("POST", f"/fuel/imports/{job}/mapping", {"mapping": MAPPING}, ADM_B)),
                  ("confirm", R("POST", f"/fuel/imports/{job}/confirm", creds=ADM_B)),
                  ("row_resolve", R("PATCH", f"/fuel/imports/{job}/rows/{rid}", {"vehicle_id": S["vb"], "reason": "x"}, ADM_B)),
                  ("accept_unique", R("POST", f"/fuel/imports/{job}/rows/accept-unique", {"row_ids": [rid], "reason": "x"}, ADM_B)),
                  ("force", R("POST", f"/fuel/imports/{job}/rows/{rid}/force", {"reason": "x"}, ADM_B)),
                  ("tx_get", R("GET", f"/fuel-transactions/{txid}", creds=ADM_B)),
                  ("tx_match", R("PATCH", f"/fuel-transactions/{txid}/match", {"vehicle_id": S["vb"], "reason": "x"}, ADM_B)),
                  ("tx_card", R("PATCH", f"/fuel-transactions/{txid}/card", {"card_id": S["cb"], "reason": "x"}, ADM_B)),
                  ("anomaly_get", R("GET", f"/fuel/anomalies/{S['anomaly']}", creds=ADM_B)),
                  ("anomaly_decide", R("POST", f"/fuel/anomalies/{S['anomaly']}/decide", {"decision": "justify", "reason": "x"}, ADM_B)),
                  ("A_uses_vehicle_B_in_match", R("PATCH", f"/fuel-transactions/{txid}/match", {"vehicle_id": S["vb"], "reason": "cross tenant"})),
                  ("A_uses_card_B_in_card", R("PATCH", f"/fuel-transactions/{txid}/card", {"card_id": S["cb"], "reason": "cross tenant"}))]
        bad = [(k, r.status_code) for k, r in matrix if r.status_code != 404]
        assert not bad, bad
        assert R("GET", "/fuel/anomalies", creds=ADM_B).json()["total"] == 0 and R("GET", "/fuel/imports", creds=ADM_B).json()["total"] == 0
        db = _db()
        assert db.fuel_transactions.find_one({"tenant_id": TA, "id": txid})["vehicle_id"] == S["v1"]  # rien muté
        assert db.fuel_anomalies.find_one({"tenant_id": TA, "id": S["anomaly"]})["status"] == "ouverte"
        print("\nCROSS_TENANT 404 :", [k for k, _ in matrix])

    def test_12_justify_keeps_history_and_d7_costs(self):
        r = R("POST", f"/fuel/anomalies/{S['anomaly']}/decide", {"decision": "justify", "reason": "Véhicule de remplacement ce jour-là"})
        assert r.status_code == 200 and r.json()["status"] == "justifiee" and r.json()["decided_by"] == ADM_A[0]
        assert R("GET", f"/fuel/anomalies/{S['anomaly']}").json()["status"] == "justifiee"  # reste visible
        assert R("POST", f"/fuel/anomalies/{S['anomaly']}/decide", {"decision": "reject", "reason": "again"}).status_code == 409
        docs_total = round(sum(float(x[5]) for x in ROWS()), 2)
        db = _db()
        tx_sum = round(sum(t["montant"] for t in db.fuel_transactions.find({"tenant_id": TA, "is_deleted": False})), 2)
        doc_sum = round(sum((d.get("montant_chf") if d.get("montant_chf") is not None else d["document_data"]["montant"]) for d in db.documents.find({"tenant_id": TA, "is_deleted": False, "source": "import"})), 2)
        assert tx_sum == doc_sum == docs_total and db.documents.count_documents({"tenant_id": TA, "source": "import"}) == db.fuel_transactions.count_documents({"tenant_id": TA, "created_from": "import"})
