"""Phase 4C — Lot G (6b) : rapprochements achats ↔ consommation (CAN prioritaire, tickets indicatifs, ASTRA comparatif, seuils null → INDICATIF,
règle de seuils documentée), décomptes = snapshot Documents (+ relevé fournisseur `declared` manuel), blockers exacts, clôture normale (0 blocker +
intégrité) / clôture par exception (motif + confirmation, blockers snapshotés), verrou serveur 409 STATEMENT_LOCKED (match / card / document /
plein manuel / véhicule), match/run ignore les verrouillées, décisions d'anomalie toujours autorisées, correctifs (jamais de réouverture),
exports CSV/XLSX/PDF audités SHA-256, read_only 403, isolation tenant fail-closed, D7/D8 inchangés."""
import hashlib
import sys
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
import fuel_statements as fst  # noqa: E402

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A, TENANT_B = f"pytest-fg-a-{_RUN}", f"pytest-fg-b-{_RUN}"
ADMIN_A = (f"fg-adm-a-{_RUN}@pytest.ch", f"FgAdmA-{_RUN}-1")
RO_A = (f"fg-ro-a-{_RUN}@pytest.ch", f"FgRoA-{_RUN}-1")
ADMIN_B = (f"fg-adm-b-{_RUN}@pytest.ch", f"FgAdmB-{_RUN}-1")
P_MAY, P_APR, P_MAR = "2026-05", "2026-04", "2026-03"
_S, _cache = {}, {}
LOTG_COLLS = ("fuel_statements", "fuel_statement_lines", "fuel_reconciliations")


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


def _plein(vehicle, date, litres=40, montant=82.0, km=None, creds=ADMIN_A, **over):
    body = {"date": date, "heure": "08:00", "station": "Station Test", "montant": montant, "litres": litres, "prix_litre": round(montant / litres, 3) if litres else None,
            "business_category": "CARBURANT", "motif": "Plein test Lot G", **({"kilometrage": km} if km else {}), **over}
    r = _req("POST", f"/vehicles/{vehicle}/fuel-transactions", body, creds=creds)
    assert r.status_code == 200, r.text
    return r.json()


def _tx(tx_id, creds=ADMIN_A):
    return _req("GET", f"/fuel-transactions/{tx_id}", creds=creds)


def _reco(period, creds=ADMIN_A, **params):
    r = _req("GET", "/fuel/reconciliations", creds=creds, params={"period_month": period, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _reco_of(period, vid):
    items = [i for i in _reco(period)["items"] if i["vehicle_id"] == vid]
    return items[0] if items else None


def _audits(entity, **q):
    return list(_mongo().audit_logs.find({"tenant_id": TENANT_A, "entity": entity, **q}, {"_id": 0}))


def _set_thresholds(pct=None, l=None):  # noqa: E741
    body = {}
    if pct != "skip":
        body["threshold_pct"] = pct
    if l != "skip":
        body["threshold_l"] = l
    r = _req("PATCH", "/tenant-settings/fuel/reconciliation", body)
    assert r.status_code == 200, r.text
    return r.json()["reconciliation"]


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"}, headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"}, headers=sa(), timeout=30).status_code == 200
    tag = _RUN[:4].upper()
    for key, body, creds in (("v1", {"plaque": f"VD {tag} 1", "type_carburant": "Diesel", "kilometrage": 51500, "conso_officielle_l_100km": 6.5, "conso_officielle_norme": "WLTP"}, ADMIN_A),
                             ("v2", {"plaque": f"VD {tag} 2", "type_carburant": "Diesel", "kilometrage": 20000}, ADMIN_A),
                             ("v3", {"plaque": f"VD {tag} 3", "type_carburant": "Diesel", "kilometrage": 30000}, ADMIN_A),
                             ("v4", {"plaque": f"VD {tag} 4", "type_carburant": "Diesel", "kilometrage": 1000}, ADMIN_A),
                             ("vb", {"plaque": f"BE {tag} 1", "type_carburant": "Diesel", "kilometrage": 1000}, ADMIN_B)):
        r = _req("POST", "/vehicles", body, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    db = _mongo()
    # CAN synthétique (fuel_snapshots) : v1 → 100 L mesurés sur 1 500 km en mai ; v3 → CAN seul (aucun achat)
    db.fuel_snapshots.insert_many([{"vehicle_id": _S["v1"], "tenant_id": TENANT_A, "day": "2026-04-30", "litres_cumules": 1000.0, "km": 50000},
                                   {"vehicle_id": _S["v1"], "tenant_id": TENANT_A, "day": "2026-05-15", "litres_cumules": 1050.0, "km": 50800},
                                   {"vehicle_id": _S["v1"], "tenant_id": TENANT_A, "day": "2026-05-31", "litres_cumules": 1100.0, "km": 51500},
                                   {"vehicle_id": _S["v3"], "tenant_id": TENANT_A, "day": "2026-05-01", "litres_cumules": 500.0, "km": 30000},
                                   {"vehicle_id": _S["v3"], "tenant_id": TENANT_A, "day": "2026-05-30", "litres_cumules": 530.0, "km": 30400}])
    # Achats mai : v1 110 L (CAN 100 L → écart +10 L / +10 %) ; v2 tickets seuls ; vb (tenant B)
    _S["tx_v1a"] = _plein(_S["v1"], "2026-05-05", litres=60, montant=120.0, km=50300)["fuel_transaction"]["id"]
    _S["tx_v1b"] = _plein(_S["v1"], "2026-05-20", litres=50, montant=100.0, km=51100)["fuel_transaction"]["id"]
    _S["tx_v2a"] = _plein(_S["v2"], "2026-05-03", litres=45, montant=90.0, km=20000)["fuel_transaction"]["id"]
    _S["tx_v2b"] = _plein(_S["v2"], "2026-05-25", litres=40, montant=80.0, km=20600)["fuel_transaction"]["id"]
    _S["tx_vb"] = _plein(_S["vb"], "2026-05-10", litres=30, montant=60.0, creds=ADMIN_B)["fuel_transaction"]["id"]
    # Avril : décompte « propre » clôturable (v1, legacy_import rejouable)
    r = _plein(_S["v1"], "2026-04-10", litres=50, montant=100.0, motif=None, source="legacy_import", legacy_source="journal", legacy_id=f"synth-{_RUN}")
    _S["tx_apr"], _S["doc_apr"] = r["fuel_transaction"]["id"], r["document_id"]
    _S["costs0"] = _req("GET", "/costs").json()
    _S["fines0"] = _req("GET", "/fines").json()["total"]
    _h(RO_A), _h(ADMIN_B)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations", "doc_categories",
                     "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments", "fuel_cards", "fuel_card_assignments",
                     "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_transaction_matches", "fuel_anomalies", "fuel_snapshots", *LOTG_COLLS):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_one({"id": tenant})
    db.login_attempts.delete_many({"identifier": {"$regex": f"fg-.*{_RUN}"}})


# ---------------------------------------------------------------------------------------------------------------------
# 1. Fonctions pures : règle de seuils, blockers, deltas, période
# ---------------------------------------------------------------------------------------------------------------------
def test_pure_threshold_rule_single_or_both():
    assert fst.threshold_verdict(10, 10.0, None, None) is None
    assert fst.threshold_verdict(10, 10.0, 5, None) == "A_CONTROLER" and fst.threshold_verdict(10, 10.0, 15, None) == "OK"
    assert fst.threshold_verdict(10, 10.0, None, 5) == "A_CONTROLER" and fst.threshold_verdict(10, 10.0, None, 20) == "OK"
    assert fst.threshold_verdict(10, 10.0, 5, 20) == "OK"  # deux seuils : les deux doivent être dépassés
    assert fst.threshold_verdict(10, 10.0, 5, 5) == "A_CONTROLER"
    assert fst.threshold_verdict(None, None, 5, 5) == "OK"  # écart non calculable → pas de dépassement prouvé
    assert fst.THRESHOLD_RULE["code"] == "single_or_both"


def test_pure_blockers_and_deltas():
    assert fst.line_blockers({"montant": 10, "devise": "EUR", "match_status": "matched_review", "forced_duplicate_of": "x"}, 2) == ["pending_fx", "matched_review", "open_anomaly", "forced_duplicate"]
    assert fst.line_blockers({"montant": 10, "devise": "CHF", "match_status": "unmatched"}, 0) == ["unmatched"]
    assert fst.line_blockers({"montant": 10, "devise": "EUR", "montant_chf": 9.5, "match_status": "manual"}, 0) == []
    t = {"n_lignes": 3, "montant_chf": 300.0, "litres": 120.0, "kwh": 0.0}
    d = fst.declared_deltas(t, {"montant": 290, "devise": "CHF", "volume_l": None, "kwh": None, "nb_lignes": 4})
    assert d["delta_montant"] == 10.0 and d["delta_volume_l"] is None and d["delta_kwh"] is None and d["delta_nb_lignes"] == -1
    assert fst.declared_deltas(t, {"montant": 290, "devise": "EUR"})["montant_comparable"] is False
    assert fst.declared_deltas(t, None) == {"delta_montant": None, "delta_montant_pct": None, "montant_comparable": None, "delta_volume_l": None, "delta_kwh": None, "delta_nb_lignes": None}
    assert fst.period_bounds("2026-02") == ("2026-02-01", "2026-02-28") and fst.period_bounds("2026-12") == ("2026-12-01", "2026-12-31")
    assert fst.valid_period("2026-13") is False and fst.valid_period("2026-05") is True
    assert fst.STATEMENT_STATUSES == ("brouillon", "cloture")


# ---------------------------------------------------------------------------------------------------------------------
# 2. Paramètres de seuils : null par défaut, read_only, validation, audit
# ---------------------------------------------------------------------------------------------------------------------
def test_reconciliation_settings_default_null_and_rbac():
    r = _req("GET", "/tenant-settings/fuel/reconciliation", creds=RO_A)
    assert r.status_code == 200 and r.json()["reconciliation"] == {"threshold_pct": None, "threshold_l": None}
    assert _req("PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": 5}, creds=RO_A).status_code == 403
    assert _req("PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": -1}).status_code == 422
    assert _req("PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_l": 0}).status_code == 422
    assert _req("PATCH", "/tenant-settings/fuel/reconciliation", {}).status_code == 422
    assert _set_thresholds(pct=5, l=20) == {"threshold_pct": 5.0, "threshold_l": 20.0}
    a = _audits("tenant_settings")
    assert any("Seuils de rapprochement" in x["detail"] and x.get("before") == {"threshold_pct": None, "threshold_l": None} for x in a)
    assert _set_thresholds(pct=None, l="skip") == {"threshold_pct": None, "threshold_l": 20.0}  # null = seuil désactivé, l'autre conservé
    assert _set_thresholds(pct=None, l=None) == {"threshold_pct": None, "threshold_l": None}
    # Lot F : PATCH des paramètres carburant ne doit pas écraser le bloc reconciliation
    _set_thresholds(pct=7, l=20)
    assert _req("PATCH", "/tenant-settings/fuel", {"score_review": 65}).status_code == 200
    assert _req("GET", "/tenant-settings/fuel/reconciliation").json()["reconciliation"] == {"threshold_pct": 7.0, "threshold_l": 20.0}
    _set_thresholds(pct=None, l=None)


# ---------------------------------------------------------------------------------------------------------------------
# 3. Rapprochements : CAN prioritaire, tickets indicatifs, ASTRA comparatif, INDICATIF sans seuil, seuils, filtres
# ---------------------------------------------------------------------------------------------------------------------
def test_reconciliation_can_priority_astra_reference_no_threshold():
    assert _req("GET", "/fuel/reconciliations").status_code == 422
    assert _req("GET", "/fuel/reconciliations", params={"period_month": "2026-13"}).status_code == 422
    d = _reco(P_MAY, creds=RO_A)
    assert d["settings"]["configured"] is False and d["settings"]["rule"]["code"] == "single_or_both"
    r = _reco_of(P_MAY, _S["v1"])
    assert r["source_consumption"] == "can" and r["consommation"]["litres"] == 100.0 and r["consommation"]["km"] == 1500 and r["consommation"]["l_100km"] == 6.7
    assert r["achats"]["litres"] == 110.0 and r["achats"]["n_tx"] == 2 and r["achats"]["chf"] == 220.0
    assert r["ecart_l"] == 10.0 and r["ecart_pct"] == 10.0
    assert r["estimation_tickets"]["source"] == "tickets" and r["estimation_tickets"]["litres"] == 50.0  # jamais utilisé comme conso réelle
    assert r["status"] == "INDICATIF" and "aucun seuil" in r["status_reason"] and r["thresholds"]["configured"] is False
    assert r["astra"]["conso_officielle_l_100km"] == 6.5 and r["astra"]["norme"] == "WLTP" and r["astra"]["ecart_l_100km"] == 0.2 and r["astra"]["role"] == "reference_comparative"
    assert r["blockers"] == {"count": 0, "by_type": {}} and r["justification"] is None
    assert sorted(r["transaction_ids"]) == sorted([_S["tx_v1a"], _S["tx_v1b"]])


def test_reconciliation_tickets_only_and_can_only():
    r2 = _reco_of(P_MAY, _S["v2"])
    assert r2["source_consumption"] == "unavailable" and r2["consommation"]["litres"] is None and r2["ecart_l"] is None and r2["ecart_pct"] is None
    assert r2["status"] == "INDICATIF" and r2["estimation_tickets"]["litres"] == 40.0 and r2["estimation_tickets"]["km"] == 600
    assert r2["astra"]["conso_officielle_l_100km"] is None  # ASTRA seul absent → pas de référence
    r3 = _reco_of(P_MAY, _S["v3"])
    assert r3["source_consumption"] == "can" and r3["consommation"]["litres"] == 30.0 and r3["achats"]["n_tx"] == 0 and r3["status"] == "INDICATIF"
    assert _reco_of(P_MAY, _S["v4"]) is None  # ni achat ni CAN → absent
    assert _reco_of(P_MAR, _S["v1"]) is None


def test_reconciliation_thresholds_single_and_both():
    try:
        _set_thresholds(pct=5, l="skip")
        r = _reco_of(P_MAY, _S["v1"])
        assert r["status"] == "A_CONTROLER" and r["thresholds"]["configured"] is True and r["ecart_l"] == 10.0  # écart brut inchangé
        _set_thresholds(pct=None, l=20)
        assert _reco_of(P_MAY, _S["v1"])["status"] == "OK"
        _set_thresholds(pct=5, l=20)
        assert _reco_of(P_MAY, _S["v1"])["status"] == "OK"  # deux seuils : 10 L < 20 L → pas les deux dépassés
        _set_thresholds(pct=5, l=5)
        r = _reco_of(P_MAY, _S["v1"])
        assert r["status"] == "A_CONTROLER" and "au-delà des seuils" in r["status_reason"]
        assert _reco_of(P_MAY, _S["v2"])["status"] == "INDICATIF"  # tickets seuls : jamais OK / A_CONTROLER même avec seuils
        d = _reco(P_MAY, status="A_CONTROLER")
        assert [i["vehicle_id"] for i in d["items"]] == [_S["v1"]]
    finally:
        _set_thresholds(pct=None, l=None)
    assert _reco_of(P_MAY, _S["v1"])["status"] == "INDICATIF"


def test_reconciliation_filters_and_tenant_isolation():
    d = _reco(P_MAY, vehicle_id=_S["v2"])
    assert d["total"] == 1 and d["items"][0]["vehicle_id"] == _S["v2"]
    assert _req("GET", "/fuel/reconciliations", params={"period_month": P_MAY, "status": "BIDON"}).status_code == 422
    assert _reco(P_MAY, status="INDICATIF")["total"] == 3 and _reco(P_MAY, justified="true")["total"] == 0
    assert _req("GET", "/fuel/reconciliations", params={"period_month": P_MAY, "vehicle_id": _S["vb"]}).status_code == 404  # véhicule du tenant B
    db_ = _reco(P_MAY, creds=ADMIN_B)
    assert [i["vehicle_id"] for i in db_["items"]] == [_S["vb"]]


def test_reconciliation_justify_rbac_reason_audit_no_source_change():
    path = f"/fuel/reconciliations/{_S['v1']}/{P_MAY}/justify"
    assert _req("POST", path, {"reason": "Explication"}, creds=RO_A).status_code == 403
    assert _req("POST", path, {"reason": "  "}).status_code == 422
    assert _req("POST", f"/fuel/reconciliations/{_S['v1']}/2026-99/justify", {"reason": "Explication"}).status_code == 422
    assert _req("POST", f"/fuel/reconciliations/{_S['vb']}/{P_MAY}/justify", {"reason": "Cross tenant"}).status_code == 404
    assert _req("POST", f"/fuel/reconciliations/{_S['v4']}/{P_MAY}/justify", {"reason": "Sans données"}).status_code == 404
    before = _reco_of(P_MAY, _S["v1"])
    r = _req("POST", path, {"reason": "Jerrican de 10 L pour la tondeuse"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["justification"]["reason"] == "Jerrican de 10 L pour la tondeuse" and j["justification"]["by"] == ADMIN_A[0] and j["justification"]["status_at"] == "INDICATIF"
    assert len(j["justification_history"]) == 1
    for k in ("achats", "consommation", "astra", "ecart_l", "ecart_pct", "status"):
        assert j[k] == before[k], k  # la justification explique, ne corrige jamais
    assert _reco(P_MAY, justified="true")["total"] == 1 and _reco(P_MAY, justified="false")["total"] == 2
    a = _audits("fuel_reconciliation", action="justify")
    assert len(a) == 1 and a[0]["vehicle_id"] == _S["v1"] and "Jerrican" in a[0]["detail"] and a[0]["before"] is None and a[0]["after"]["reason"].startswith("Jerrican")
    r = _req("POST", path, {"reason": "Seconde explication"})
    assert r.status_code == 200 and len(r.json()["justification_history"]) == 2
    assert _audits("fuel_reconciliation", action="justify")[-1]["before"]["reason"].startswith("Jerrican")
    assert _mongo().fuel_reconciliations.count_documents({"tenant_id": TENANT_A}) == 1


# ---------------------------------------------------------------------------------------------------------------------
# 4. Décompte régulier : création snapshot, unicité, aucune transaction verrouillée en brouillon, lignes = transactions Documents
# ---------------------------------------------------------------------------------------------------------------------
def test_statement_create_snapshot_unique_no_lock_in_draft():
    assert _req("POST", "/fuel/statements", {"period_month": P_MAY}, creds=RO_A).status_code == 403
    assert _req("POST", "/fuel/statements", {"period_month": "mai"}).status_code == 422
    assert _req("POST", "/fuel/statements", {"period_month": P_MAY, "scope_type": "fournisseur"}).status_code == 422
    assert _req("POST", "/fuel/statements", {"period_month": P_MAY, "type": "autre"}).status_code == 422
    r = _req("POST", "/fuel/statements", {"period_month": P_MAY})
    assert r.status_code == 200, r.text
    st = r.json()
    _S["st_may"] = st["id"]
    assert st["number"].startswith(f"DEC-{P_MAY}-") and st["type"] == "regulier" and st["status"] == "brouillon" and st["scope"] == {"type": "tenant", "fournisseur": None}
    assert st["period_from"] == "2026-05-01" and st["period_to"] == "2026-05-31" and st["declared"] is None
    assert sorted(ln["transaction_id"] for ln in st["lines"]) == sorted([_S["tx_v1a"], _S["tx_v1b"], _S["tx_v2a"], _S["tx_v2b"]])
    assert st["totals"]["n_lignes"] == 4 and st["totals"]["montant_chf"] == 390.0 and st["totals"]["litres"] == 195.0 and st["totals"]["blocker_count"] == 0
    assert st["deltas"]["delta_montant"] is None and all(not ln["locked"] for ln in st["lines"])
    assert _mongo().fuel_statement_lines.count_documents({"tenant_id": TENANT_A, "statement_id": st["id"]}) == 4
    tx = _tx(_S["tx_v1a"]).json()
    assert not tx.get("locked") and not tx.get("statement_id") and not tx.get("locked_at")  # brouillon ≠ verrou
    dup = _req("POST", "/fuel/statements", {"period_month": P_MAY})
    assert dup.status_code == 409 and dup.json()["detail"]["code"] == "STATEMENT_EXISTS" and dup.json()["detail"]["statement_id"] == st["id"]
    assert _mongo().fuel_statements.count_documents({"tenant_id": TENANT_A, "type": "regulier", "period_month": P_MAY}) == 1
    a = _audits("fuel_statement", action="create")
    assert len(a) == 1 and a[0]["entity_id"] == st["id"] and "snapshot 4 ligne(s)" in a[0]["detail"]
    # modification d'une transaction pendant le brouillon → autorisée (aucun verrou)
    r = _req("PATCH", f"/fuel-transactions/{_S['tx_v2a']}/card", {"card_id": None, "reason": "Pas de carte (test brouillon)"})
    assert r.status_code == 200, r.text


def test_statement_scope_fournisseur_and_list_filters():
    db = _mongo()
    db.fuel_transactions.update_many({"tenant_id": TENANT_A, "id": {"$in": [_S["tx_v1a"], _S["tx_v1b"]]}}, {"$set": {"fournisseur": "Migrol"}})
    db.fuel_transactions.update_many({"tenant_id": TENANT_A, "id": {"$in": [_S["tx_v2a"], _S["tx_v2b"]]}}, {"$set": {"fournisseur": "Shell"}})
    r = _req("POST", "/fuel/statements", {"period_month": P_MAY, "scope_type": "fournisseur", "fournisseur": "migrol"})
    assert r.status_code == 200, r.text
    st = r.json()
    _S["st_migrol"] = st["id"]
    assert st["scope"] == {"type": "fournisseur", "fournisseur": "migrol"} and st["scope_label"] == "Fournisseur migrol"
    assert sorted(ln["transaction_id"] for ln in st["lines"]) == sorted([_S["tx_v1a"], _S["tx_v1b"]]) and st["totals"]["montant_chf"] == 220.0
    assert _req("POST", "/fuel/statements", {"period_month": P_MAY, "scope_type": "fournisseur", "fournisseur": "Migrol"}).status_code == 200  # casse différente = autre clé
    _S["st_migrol2"] = _req("GET", "/fuel/statements", params={"fournisseur": "Migrol", "period_month": P_MAY}).json()["items"]
    lst = _req("GET", "/fuel/statements", creds=RO_A).json()
    assert lst["stats"]["total"] == 3 and lst["stats"]["brouillons"] == 3 and "Migrol" in lst["fournisseurs"] and "Shell" in lst["fournisseurs"]
    assert _req("GET", "/fuel/statements", params={"type": "correctif"}).json()["total"] == 0
    assert _req("GET", "/fuel/statements", params={"status": "cloture"}).json()["total"] == 0
    assert _req("GET", "/fuel/statements", params={"status": "x"}).status_code == 422
    assert _req("GET", "/fuel/statements", params={"period_month": P_APR}).json()["total"] == 0
    det = _req("GET", f"/fuel/statements/{st['id']}", creds=RO_A)
    assert det.status_code == 200 and det.json()["lines"][0]["plaque"] and det.json()["corrective_eligible"] is None and det.json()["correctifs"] == []


# ---------------------------------------------------------------------------------------------------------------------
# 5. Relevé fournisseur déclaré : facultatif, N/A ≠ 0, deltas, devise, audit, read_only
# ---------------------------------------------------------------------------------------------------------------------
def test_statement_declared_deltas_na_currency_rbac_audit():
    sid = _S["st_may"]
    assert _req("PATCH", f"/fuel/statements/{sid}/declared", {"montant": 400}, creds=RO_A).status_code == 403
    assert _req("PATCH", f"/fuel/statements/{sid}/declared", {"montant": -1}).status_code == 422
    assert _req("PATCH", f"/fuel/statements/{sid}/declared", {"nb_lignes": -2}).status_code == 422
    assert _req("PATCH", f"/fuel/statements/{sid}/declared", {"devise": "CHFF"}).status_code == 422
    r = _req("PATCH", f"/fuel/statements/{sid}/declared", {"montant": 400, "devise": "chf", "volume_l": 200, "kwh": None, "nb_lignes": 5})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["declared"] == {"montant": 400.0, "devise": "CHF", "volume_l": 200.0, "kwh": None, "nb_lignes": 5}
    assert st["deltas"]["delta_montant"] == -10.0 and st["deltas"]["delta_montant_pct"] == -2.5 and st["deltas"]["montant_comparable"] is True
    assert st["deltas"]["delta_volume_l"] == -5.0 and st["deltas"]["delta_kwh"] is None and st["deltas"]["delta_nb_lignes"] == -1
    r = _req("PATCH", f"/fuel/statements/{sid}/declared", {"montant": 380})  # partiel : les autres champs redeviennent N/A, jamais 0
    st = r.json()
    assert st["declared"]["volume_l"] is None and st["declared"]["nb_lignes"] is None and st["deltas"]["delta_volume_l"] is None and st["deltas"]["delta_montant"] == 10.0
    r = _req("PATCH", f"/fuel/statements/{sid}/declared", {"montant": 380, "devise": "EUR"})
    assert r.json()["deltas"]["montant_comparable"] is False and r.json()["deltas"]["delta_montant"] is None  # D7 : pas de comparaison sans conversion
    a = _audits("fuel_statement", action="declared")
    assert len(a) == 3 and a[0]["before"] is None and a[0]["after"]["montant"] == 400.0 and a[1]["before"]["montant"] == 400.0
    assert _mongo().fuel_transactions.find_one({"id": _S["tx_v1a"]}, {"_id": 0, "montant": 1})["montant"] == 120.0


# ---------------------------------------------------------------------------------------------------------------------
# 6. Blockers exacts + clôture refusée (409 détaillé) + recalcul explicite du snapshot
# ---------------------------------------------------------------------------------------------------------------------
def test_statement_blockers_all_types_and_close_blocked():
    db = _mongo()
    # pending_fx : plein en EUR sans contre-valeur ; forced_duplicate / matched_review / unmatched : état Documents posé directement (synthétique)
    _S["tx_fx"] = _plein(_S["v4"], "2026-05-12", litres=30, montant=55.0, devise="EUR")["fuel_transaction"]["id"]
    _S["tx_dup"] = _plein(_S["v4"], "2026-05-14", litres=20, montant=40.0)["fuel_transaction"]["id"]
    _S["tx_rev"] = _plein(_S["v4"], "2026-05-16", litres=22, montant=44.0)["fuel_transaction"]["id"]
    _S["tx_unm"] = _plein(_S["v4"], "2026-05-18", litres=24, montant=48.0)["fuel_transaction"]["id"]
    db.fuel_transactions.update_one({"id": _S["tx_dup"]}, {"$set": {"forced_duplicate_of": _S["tx_rev"]}})
    db.fuel_transactions.update_one({"id": _S["tx_rev"]}, {"$set": {"match_status": "matched_review"}})
    db.fuel_transactions.update_one({"id": _S["tx_unm"]}, {"$set": {"match_status": "unmatched"}})
    # open_anomaly : double plein réel (même véhicule, même jour, < 60 min) → anomalie détectée par Documents (D8)
    _S["tx_an1"] = _plein(_S["v3"], "2026-05-22", litres=35, montant=70.0, heure="09:00", km=30350)["fuel_transaction"]["id"]
    _S["tx_an2"] = _plein(_S["v3"], "2026-05-22", litres=36, montant=72.0, heure="09:20", km=30350)["fuel_transaction"]["id"]
    an = db.fuel_anomalies.find_one({"tenant_id": TENANT_A, "transaction_id": _S["tx_an2"], "status": "ouverte"}, {"_id": 0})
    assert an, "anomalie double_plein attendue"
    _S["anomaly_id"] = an["id"]
    r = _req("POST", f"/fuel/statements/{_S['st_may']}/recalculate", creds=RO_A)
    assert r.status_code == 403
    r = _req("POST", f"/fuel/statements/{_S['st_may']}/recalculate")
    assert r.status_code == 200, r.text
    st = r.json()
    assert sorted(st["added"]) == sorted([_S["tx_fx"], _S["tx_dup"], _S["tx_rev"], _S["tx_unm"], _S["tx_an1"], _S["tx_an2"]]) and st["removed"] == []
    assert st["totals"]["n_lignes"] == 10 and st["snapshot_count"] == 2 and st["declared"]["montant"] == 380.0  # declared conservé
    by = {ln["transaction_id"]: ln for ln in st["lines"]}
    assert by[_S["tx_fx"]]["blockers"] == ["pending_fx"] and by[_S["tx_fx"]]["montant_chf"] is None
    assert by[_S["tx_dup"]]["blockers"] == ["forced_duplicate"] and by[_S["tx_rev"]]["blockers"] == ["matched_review"] and by[_S["tx_unm"]]["blockers"] == ["unmatched"]
    assert by[_S["tx_an2"]]["blockers"] == ["open_anomaly"] and by[_S["tx_an2"]]["open_anomalies"] >= 1 and by[_S["tx_v1a"]]["blockers"] == []
    t = st["totals"]
    assert t["blocker_count"] >= 5 and t["blocked_line_count"] >= 5 and set(t["blockers_by_type"]) == set(fst.BLOCKER_TYPES)
    assert t["pending_fx"] == 1 and t["montant_chf"] == 390.0 + 40 + 44 + 48 + 70 + 72
    hist = [h for h in st["history"] if h["event"] == "recalculated"]
    assert len(hist) == 1 and hist[0]["lines_before"] == 4 and hist[0]["lines_after"] == 10 and hist[0]["totals_before"]["blocker_count"] == 0
    a = _audits("fuel_statement", action="recalculate")
    assert len(a) == 1 and "4 → 10 ligne(s)" in a[0]["detail"] and a[0]["totals_after"]["blocker_count"] == t["blocker_count"]
    # clôture normale refusée : 409 + détail exploitable
    assert _req("POST", f"/fuel/statements/{_S['st_may']}/close", creds=RO_A).status_code == 403
    r = _req("POST", f"/fuel/statements/{_S['st_may']}/close")
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "CLOSE_BLOCKED" and d["blocker_count"] == t["blocker_count"] and d["blocked_line_count"] == t["blocked_line_count"]
    assert d["blockers_by_type"] == t["blockers_by_type"] and {ln["transaction_id"] for ln in d["lines"]} >= {_S["tx_fx"], _S["tx_dup"], _S["tx_rev"], _S["tx_unm"], _S["tx_an2"]}
    assert d["integrity_errors"] == []
    assert _req("GET", f"/fuel/statements/{_S['st_may']}").json()["status"] == "brouillon"
    assert not _tx(_S["tx_fx"]).json().get("locked")


def test_statement_recalculate_removes_ineligible_and_detects_stale_snapshot():
    sid = _S["st_migrol"]
    db = _mongo()
    db.fuel_transactions.update_one({"id": _S["tx_v1b"]}, {"$set": {"fournisseur": "Shell"}})  # n'est plus dans le périmètre Migrol
    r = _req("POST", f"/fuel/statements/{sid}/close")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CLOSE_BLOCKED"
    assert [e["code"] for e in r.json()["detail"]["integrity_errors"]] == ["SNAPSHOT_STALE"]  # empreinte modifiée → recalcul explicite requis
    r = _req("POST", f"/fuel/statements/{sid}/recalculate")
    assert r.status_code == 200 and r.json()["removed"] == [_S["tx_v1b"]] and r.json()["totals"]["n_lignes"] == 1
    db.fuel_transactions.update_one({"id": _S["tx_v1b"]}, {"$set": {"fournisseur": "Migrol"}})
    r = _req("POST", f"/fuel/statements/{sid}/recalculate")
    assert r.status_code == 200 and r.json()["added"] == [_S["tx_v1b"]] and r.json()["totals"]["n_lignes"] == 2


# ---------------------------------------------------------------------------------------------------------------------
# 7. Clôture normale (0 blocker, intégrité PASS) → verrou serveur sur toutes les mutations impactantes
# ---------------------------------------------------------------------------------------------------------------------
def test_statement_close_clean_locks_transactions_idempotent():
    r = _req("POST", "/fuel/statements", {"period_month": P_APR})
    assert r.status_code == 200, r.text
    st = r.json()
    _S["st_apr"] = st["id"]
    assert [ln["transaction_id"] for ln in st["lines"]] == [_S["tx_apr"]] and st["totals"]["blocker_count"] == 0
    assert not _tx(_S["tx_apr"]).json().get("locked")
    r = _req("POST", f"/fuel/statements/{st['id']}/close")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["already_closed"] is False and body["statement"]["status"] == "cloture" and body["statement"]["close_exception"] is False
    assert body["statement"]["closed_by"] == ADMIN_A[0] and body["statement"]["closed_at"] and all(ln["locked"] for ln in body["statement"]["lines"])
    tx = _tx(_S["tx_apr"]).json()
    assert tx["locked"] is True and tx["statement_id"] == st["id"] and tx["locked_at"] == body["statement"]["closed_at"] and tx["statement_number"] == st["number"]
    n_audit = len(_audits("fuel_statement", action="close"))
    assert n_audit == 1 and "intégrité PASS" in _audits("fuel_statement", action="close")[0]["detail"]
    r = _req("POST", f"/fuel/statements/{st['id']}/close")  # double close : idempotent, aucun second événement
    assert r.status_code == 200 and r.json()["already_closed"] is True
    assert len(_audits("fuel_statement", action="close")) == n_audit
    assert len([h for h in _req("GET", f"/fuel/statements/{st['id']}").json()["history"] if h["event"] == "closed"]) == 1
    # décompte clôturé : declared / recalcul → 409 STATEMENT_LOCKED
    for path in (f"/fuel/statements/{st['id']}/declared", f"/fuel/statements/{st['id']}/recalculate"):
        r = _req("PATCH" if "declared" in path else "POST", path, {"montant": 1} if "declared" in path else None)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "STATEMENT_LOCKED" and r.json()["detail"]["statement_id"] == st["id"], path


def _assert_locked(r, **fields):
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "STATEMENT_LOCKED" and d["statement_id"] == _S["st_apr"] and d["period_month"] == P_APR and d["locked_at"]
    for k, v in fields.items():
        assert d.get(k) == v, (k, d)


def test_lock_blocks_match_card_vehicle_delete_and_match_run_ignores():
    tx_id = _S["tx_apr"]
    before = _mongo().fuel_transactions.find_one({"id": tx_id}, {"_id": 0})
    _assert_locked(_req("PATCH", f"/fuel-transactions/{tx_id}/match", {"vehicle_id": _S["v2"], "reason": "Tentative après clôture"}))
    _assert_locked(_req("PATCH", f"/fuel-transactions/{tx_id}/card", {"card_id": None, "reason": "Tentative après clôture"}))
    _assert_locked(_req("DELETE", f"/vehicles/{_S['v1']}"), vehicle_id=_S["v1"])
    r = _req("POST", "/fuel/match/run")
    assert r.status_code == 200 and r.json()["locked_ignored"] >= 1
    after = _mongo().fuel_transactions.find_one({"id": tx_id}, {"_id": 0})
    assert after == before  # aucune réécriture (vehicle_id, card_id, match_status, score, méthode…)
    assert _req("GET", f"/vehicles/{_S['v1']}").status_code == 200


def _doc(doc_id):
    return _mongo().documents.find_one({"tenant_id": TENANT_A, "id": doc_id}, {"_id": 0, "pages": 0, "extracted_fields": 0})


def test_lock_document_granular_patch_delete_validate_manual():
    doc = _S["doc_apr"]
    base = _doc(doc)
    for field, value in (("montant", 150.0), ("devise", "EUR"), ("date_debut", "2026-04-11"), ("date_expiration", "2026-05-11"),
                         ("fournisseur", "Autre"), ("numero", "X-1"), ("kilometrage_releve", 123), ("business_category", "ENERGIE_ELECTRIQUE"), ("frequence", "mensuel")):
        _assert_locked(_req("PATCH", f"/documents/{doc}", {field: value}), blocked_fields=[field])
    _assert_locked(_req("PATCH", f"/documents/{doc}", {"devise": "EUR", "montant_chf": 99.0}), blocked_fields=["devise", "montant_chf"])  # D7 : contre-valeur protégée
    assert _req("PATCH", f"/documents/{doc}", {"montant_chf": 99.0}).status_code == 200  # devise CHF : montant_chf ignoré (D7) → aucun champ effectivement modifié
    r = _req("POST", "/drivers", {"nom": "Lock", "prenom": "Test"})
    assert r.status_code == 200, r.text
    _assert_locked(_req("PATCH", f"/documents/{doc}", {"driver_id": r.json()["id"]}), blocked_fields=["driver_id"])
    _assert_locked(_req("PATCH", f"/documents/{doc}", {"notes": "mixte", "montant": 151.0}), blocked_fields=["montant"])  # PATCH mixte refusé en entier
    cur = _doc(doc)
    assert cur.get("notes") == base.get("notes") and cur["montant"] == base["montant"]
    for body in ({"notes": "Note documentaire après clôture"}, {"tags": ["lotg", "clos"]}, {"folder": base["folder"]}, {"label": "Libellé documentaire"}):
        r = _req("PATCH", f"/documents/{doc}", body)
        assert r.status_code == 200, (body, r.text)
    assert _req("PATCH", f"/documents/{doc}", {"montant": base["montant"]}).status_code == 200  # même valeur = aucun champ effectivement modifié
    cur = _doc(doc)
    assert cur["notes"] == "Note documentaire après clôture" and cur["tags"] == ["lotg", "clos"] and cur["montant"] == base["montant"]
    _assert_locked(_req("DELETE", f"/documents/{doc}"))
    _assert_locked(_req("POST", f"/documents/{doc}/validate", {"document_type": "ticket_carburant", "fields": {"montant": 100, "litres": 50, "date": "2026-04-10"}}))
    _assert_locked(_req("POST", f"/vehicles/{_S['v1']}/fuel-transactions", {"date": "2026-04-10", "montant": 101.0, "litres": 50, "business_category": "CARBURANT",
                                                                             "source": "legacy_import", "legacy_source": "journal", "legacy_id": f"synth-{_RUN}"}))
    assert _doc(doc)["is_deleted"] is False
    assert _mongo().fuel_transactions.find_one({"id": _S["tx_apr"]}, {"_id": 0, "montant": 1})["montant"] == 100.0
    # document non lié à une transaction verrouillée : comportement normal
    other = _tx(_S["tx_v2b"]).json()["document"]["id"]
    assert _req("PATCH", f"/documents/{other}", {"notes": "libre"}).status_code == 200


# ---------------------------------------------------------------------------------------------------------------------
# 8. Clôture par exception : motif + confirmation, blockers snapshotés et conservés, même verrou ; anomalies toujours décidables
# ---------------------------------------------------------------------------------------------------------------------
def test_statement_close_exception_requires_reason_confirm_admin_and_locks():
    sid = _S["st_may"]
    assert _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "Clôture mensuelle", "confirm": True}, creds=RO_A).status_code == 403
    assert _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "", "confirm": True}).status_code == 422
    assert _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "Clôture mensuelle imposée"}).status_code == 422  # confirmation explicite
    before = _req("GET", f"/fuel/statements/{sid}").json()
    assert before["status"] == "brouillon" and before["totals"]["blocker_count"] >= 5
    # le match/run précédent a recalculé des transactions du brouillon → snapshot obsolète : l'exception exige aussi l'intégrité (recalcul explicite)
    r = _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "Clôture mensuelle imposée", "confirm": True})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "INTEGRITY_FAILED" and r.json()["detail"]["integrity_errors"][0]["code"] == "SNAPSHOT_STALE"
    db = _mongo()
    db.fuel_transactions.update_one({"id": _S["tx_rev"]}, {"$set": {"match_status": "matched_review"}})
    db.fuel_transactions.update_one({"id": _S["tx_unm"]}, {"$set": {"match_status": "unmatched"}})
    assert _req("POST", f"/fuel/statements/{sid}/recalculate").status_code == 200
    before = _req("GET", f"/fuel/statements/{sid}").json()
    assert set(before["totals"]["blockers_by_type"]) == set(fst.BLOCKER_TYPES)
    r = _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "Clôture mensuelle imposée — écarts à traiter en correctif", "confirm": True})
    assert r.status_code == 200, r.text
    st = r.json()["statement"]
    assert st["status"] == "cloture" and st["close_exception"] is True and st["exception"]["reason"].startswith("Clôture mensuelle") and st["exception"]["by"] == ADMIN_A[0]
    bs = st["exception"]["blockers_snapshot"]
    assert bs["blocker_count"] == before["totals"]["blocker_count"] and bs["blockers_by_type"] == before["totals"]["blockers_by_type"] and len(bs["lines"]) == before["totals"]["blocked_line_count"]
    assert st["totals"]["blocker_count"] == before["totals"]["blocker_count"]  # blockers conservés, jamais marqués résolus
    assert all(ln["locked"] for ln in st["lines"]) and any(ln["blockers"] for ln in st["lines"])
    for tx_id in (_S["tx_fx"], _S["tx_v1a"], _S["tx_an2"]):
        tx = _tx(tx_id).json()
        assert tx["locked"] is True and tx["statement_id"] == sid and tx["locked_at"] == st["closed_at"]
    a = _audits("fuel_statement", action="close_exception")
    assert len(a) == 1 and "CLÔTURÉ AVEC EXCEPTION" in a[0]["detail"] and a[0]["blockers_snapshot"]["blocker_count"] == bs["blocker_count"] and a[0]["after"]["close_exception"] is True
    r = _req("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "Rejeu", "confirm": True})
    assert r.status_code == 200 and r.json()["already_closed"] is True and len(_audits("fuel_statement", action="close_exception")) == 1
    assert _req("POST", f"/fuel/statements/{sid}/close").json()["already_closed"] is True
    # mutation d'une transaction verrouillée par exception → même verrou
    r = _req("PATCH", f"/fuel-transactions/{_S['tx_rev']}/match", {"vehicle_id": _S["v2"], "reason": "Après exception"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "STATEMENT_LOCKED" and r.json()["detail"]["statement_id"] == sid
    assert _req("GET", f"/fuel/statements/{sid}", creds=RO_A).json()["close_exception"] is True


def test_anomaly_decision_allowed_after_lock_without_source_change():
    before = _mongo().fuel_transactions.find_one({"id": _S["tx_an2"]}, {"_id": 0})
    assert before["locked"] is True
    r = _req("POST", f"/fuel/anomalies/{_S['anomaly_id']}/decide", {"decision": "justify", "reason": "Deux pleins justifiés (jerrican) — après clôture"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "justifiee" and r.json()["decision_reason"].startswith("Deux pleins")
    assert _mongo().fuel_transactions.find_one({"id": _S["tx_an2"]}, {"_id": 0}) == before  # aucune donnée source modifiée
    st = _req("GET", f"/fuel/statements/{_S['st_may']}").json()
    assert st["totals"]["blocker_count"] == st["exception"]["blockers_snapshot"]["blocker_count"]  # snapshot clôturé immuable


def test_no_reopen_endpoint_or_equivalent():
    sid = _S["st_apr"]
    for method, path in (("POST", f"/fuel/statements/{sid}/reopen"), ("POST", f"/fuel/statements/{sid}/unlock"), ("DELETE", f"/fuel/statements/{sid}"),
                         ("PATCH", f"/fuel/statements/{sid}"), ("PUT", f"/fuel/statements/{sid}")):
        r = _req(method, path, {})
        assert r.status_code in (404, 405), (method, path, r.status_code)
    assert _req("GET", f"/fuel/statements/{sid}").json()["status"] == "cloture"


# ---------------------------------------------------------------------------------------------------------------------
# 9. Correctifs : parent clôturé, même période / périmètre, uniquement transactions non verrouillées, parent immuable
# ---------------------------------------------------------------------------------------------------------------------
def test_corrective_statement_only_unlocked_transactions_parent_unchanged():
    parent_before = _req("GET", f"/fuel/statements/{_S['st_may']}").json()
    assert _req("POST", "/fuel/statements", {"type": "correctif", "reason": "Tardif"}).status_code == 422  # parent obligatoire
    assert _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_may"]}).status_code == 422  # motif obligatoire
    assert _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": "inconnu", "reason": "Tardif"}).status_code == 404
    r = _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_migrol"], "reason": "Parent non clôturé"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PARENT_NOT_CLOSED"
    assert _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_may"], "reason": "Cross"}, creds=ADMIN_B).status_code == 404
    assert _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_may"], "reason": "RO"}, creds=RO_A).status_code == 403
    _S["tx_late"] = _plein(_S["v2"], "2026-05-28", litres=33, montant=66.0, km=20900)["fuel_transaction"]["id"]  # transaction tardive, non verrouillée
    assert _req("GET", f"/fuel/statements/{_S['st_may']}").json()["corrective_eligible"] == 1
    r = _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_may"], "reason": "Ticket tardif du 28 mai", "period_month": "2030-01", "scope_type": "fournisseur", "fournisseur": "X"})
    assert r.status_code == 200, r.text
    cor = r.json()
    _S["st_cor"] = cor["id"]
    assert cor["type"] == "correctif" and cor["number"].startswith(f"COR-{P_MAY}-") and cor["period_month"] == P_MAY and cor["scope"] == parent_before["scope"]  # hérités du parent
    assert cor["parent_statement_id"] == _S["st_may"] and cor["parent_number"] == parent_before["number"] and cor["reason"] == "Ticket tardif du 28 mai" and cor["status"] == "brouillon"
    assert [ln["transaction_id"] for ln in cor["lines"]] == [_S["tx_late"]] and cor["lines"][0]["late"] is True and not cor["lines"][0]["locked"]
    assert not any(ln["transaction_id"] in {_S["tx_v1a"], _S["tx_fx"]} for ln in cor["lines"])  # jamais une transaction déjà verrouillée
    r = _req("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_may"], "reason": "Second correctif"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "CORRECTIVE_OPEN"
    parent_after = _req("GET", f"/fuel/statements/{_S['st_may']}").json()
    assert parent_after["correctifs"][0]["id"] == cor["id"]
    for k in ("totals", "lines", "declared", "closed_at", "exception", "history", "status", "snapshot_at"):
        assert parent_after[k] == parent_before[k], k  # parent immuable
    assert _mongo().fuel_statement_lines.count_documents({"statement_id": _S["st_may"]}) == 10
    r = _req("POST", f"/fuel/statements/{cor['id']}/close")
    assert r.status_code == 200 and r.json()["statement"]["status"] == "cloture"
    tx = _tx(_S["tx_late"]).json()
    assert tx["locked"] is True and tx["statement_id"] == cor["id"]
    assert _req("GET", "/fuel/statements", params={"type": "correctif"}).json()["total"] == 1
    assert _req("GET", "/fuel/statements", params={"close_exception": "true"}).json()["items"][0]["id"] == _S["st_may"]
    assert _req("GET", "/fuel/statements", params={"with_blockers": "true"}).json()["total"] >= 1


# ---------------------------------------------------------------------------------------------------------------------
# 10. Exports CSV / XLSX / PDF : admin + read_only, SHA-256 audité = octets renvoyés, aucune mutation, clôturé exportable, isolation
# ---------------------------------------------------------------------------------------------------------------------
def _export_ok(path, params, mime_start, creds=ADMIN_A):
    r = _req("GET", path, creds=creds, params=params)
    assert r.status_code == 200, (path, params, r.text[:200])
    assert r.headers["content-type"].startswith(mime_start) and "attachment" in r.headers["content-disposition"]
    sha = hashlib.sha256(r.content).hexdigest()
    assert r.headers["x-content-sha256"] == sha
    a = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_export", "action": "download", "sha256": sha}, {"_id": 0})
    assert a and a["size"] == len(r.content) and a["format"] == params["format"] and a["user"] == creds[0] and f"sha256={sha}" in a["detail"], (path, params)
    return r, a


def test_exports_statement_reconciliations_transactions_sha256_audited():
    db = _mongo()
    tx_before = list(db.fuel_transactions.find({"tenant_id": TENANT_A}, {"_id": 0}).sort("id", 1))
    st_before = list(db.fuel_statements.find({"tenant_id": TENANT_A}, {"_id": 0}).sort("id", 1))
    mimes = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats", "pdf": "application/pdf"}
    for fmt, mime in mimes.items():
        r, a = _export_ok(f"/fuel/statements/{_S['st_may']}/export", {"format": fmt}, mime)  # clôturé avec exception : exportable
        assert a["export_type"] == "statement" and a["statement_id"] == _S["st_may"] and a["period_month"] == P_MAY and a["rows"] == 10
        if fmt == "csv":
            txt = r.content.decode("utf-8-sig")
            assert "# Statut;Clôturé AVEC EXCEPTION" in txt and "# Relevé déclaré — volume L;N/A" in txt and _S["tx_fx"] in txt and "pending_fx" in txt
        _export_ok(f"/fuel/statements/{_S['st_apr']}/export", {"format": fmt}, mime, creds=RO_A)
        r, a = _export_ok("/fuel/reconciliations/export", {"period_month": P_MAY, "format": fmt}, mime)
        assert a["export_type"] == "reconciliations" and a["filters"]["period_month"] == P_MAY
        if fmt == "csv":
            txt = r.content.decode("utf-8-sig")
            assert "INDICATIF" in txt and "Jerrican" not in txt and "Seconde explication" in txt and "can" in txt
        _export_ok("/fuel/reconciliations/export", {"period_month": P_MAY, "format": fmt, "status": "INDICATIF", "vehicle_id": _S["v1"]}, mime, creds=RO_A)
    for fmt in ("csv", "xlsx"):
        r, a = _export_ok("/fuel/transactions/export", {"period_month": P_MAY, "format": fmt}, mimes[fmt], creds=RO_A)
        assert a["export_type"] == "transactions" and a["rows"] == 11
        if fmt == "csv":
            txt = r.content.decode("utf-8-sig")
            assert _S["tx_v1a"] in txt and "oui" in txt and _S["tx_apr"] not in txt
        r, a = _export_ok("/fuel/transactions/export", {"period_month": P_MAY, "format": fmt, "vehicle_id": _S["v1"], "fournisseur": "migrol"}, mimes[fmt])
        assert a["rows"] == 2
    assert _req("GET", "/fuel/transactions/export", params={"period_month": P_MAY, "format": "pdf"}).status_code == 422
    assert _req("GET", "/fuel/reconciliations/export", params={"format": "csv"}).status_code == 422
    assert _req("GET", f"/fuel/statements/{_S['st_may']}/export", params={"format": "doc"}).status_code == 422
    assert list(db.fuel_transactions.find({"tenant_id": TENANT_A}, {"_id": 0}).sort("id", 1)) == tx_before  # export = 0 mutation métier
    assert list(db.fuel_statements.find({"tenant_id": TENANT_A}, {"_id": 0}).sort("id", 1)) == st_before
    assert db.audit_logs.count_documents({"tenant_id": TENANT_A, "entity": "fuel_export"}) == 3 * 4 + 2 * 2
    assert db.audit_logs.count_documents({"tenant_id": TENANT_B, "entity": "fuel_export"}) == 0


# ---------------------------------------------------------------------------------------------------------------------
# 11. Isolation tenant fail-closed sur toutes les routes Lot G + read_only 403 sur toutes les mutations
# ---------------------------------------------------------------------------------------------------------------------
def test_cross_tenant_fail_closed_everywhere():
    sid = _S["st_may"]
    assert _req("GET", f"/fuel/statements/{sid}", creds=ADMIN_B).status_code == 404
    assert _req("GET", f"/fuel/statements/{sid}/export", creds=ADMIN_B, params={"format": "csv"}).status_code == 404
    assert _req("PATCH", f"/fuel/statements/{_S['st_migrol']}/declared", {"montant": 1}, creds=ADMIN_B).status_code == 404
    assert _req("POST", f"/fuel/statements/{_S['st_migrol']}/recalculate", creds=ADMIN_B).status_code == 404
    assert _req("POST", f"/fuel/statements/{_S['st_migrol']}/close", creds=ADMIN_B).status_code == 404
    assert _req("POST", f"/fuel/statements/{_S['st_migrol']}/close-exception", {"reason": "cross", "confirm": True}, creds=ADMIN_B).status_code == 404
    assert _req("GET", "/fuel/statements", creds=ADMIN_B).json()["total"] == 0
    assert _req("GET", "/fuel/reconciliations/export", creds=ADMIN_B, params={"period_month": P_MAY, "vehicle_id": _S["v1"], "format": "csv"}).status_code == 404
    r = _req("GET", "/fuel/transactions/export", creds=ADMIN_B, params={"period_month": P_MAY, "format": "csv"})
    assert r.status_code == 200 and _S["tx_v1a"] not in r.content.decode("utf-8-sig") and _S["tx_vb"] in r.content.decode("utf-8-sig")
    assert _tx(_S["tx_apr"], creds=ADMIN_B).status_code == 404
    r = _req("POST", "/fuel/statements", {"period_month": P_MAY}, creds=ADMIN_B)  # tenant B : son propre décompte, lignes B uniquement
    assert r.status_code == 200 and [ln["transaction_id"] for ln in r.json()["lines"]] == [_S["tx_vb"]]
    assert _mongo().fuel_statement_lines.count_documents({"tenant_id": TENANT_B}) == 1


def test_read_only_all_mutations_403():
    sid = _S["st_migrol"]
    cases = (("PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": 5}), ("POST", f"/fuel/reconciliations/{_S['v1']}/{P_MAY}/justify", {"reason": "ro"}),
             ("POST", "/fuel/statements", {"period_month": P_MAR}), ("PATCH", f"/fuel/statements/{sid}/declared", {"montant": 1}),
             ("POST", f"/fuel/statements/{sid}/recalculate", None), ("POST", f"/fuel/statements/{sid}/close", None),
             ("POST", f"/fuel/statements/{sid}/close-exception", {"reason": "ro", "confirm": True}),
             ("POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": _S["st_apr"], "reason": "ro"}),
             ("PATCH", f"/fuel-transactions/{_S['tx_v2b']}/match", {"vehicle_id": _S["v1"], "reason": "ro"}))
    for method, path, body in cases:
        assert _req(method, path, body, creds=RO_A).status_code == 403, (method, path)
    for path in ("/fuel/statements", f"/fuel/statements/{sid}", "/tenant-settings/fuel/reconciliation"):
        assert _req("GET", path, creds=RO_A).status_code == 200, path
    assert _reco(P_MAY, creds=RO_A)["total"] == 4  # v1, v2, v3 (CAN seul) et v4 (achats blockers)


# ---------------------------------------------------------------------------------------------------------------------
# 12. D7 / D8 et non-impact Lots A–F
# ---------------------------------------------------------------------------------------------------------------------
def test_d7_d8_and_energy_overview_unaffected():
    costs = _req("GET", "/costs").json()["totals"]["annuel"]
    added = 40 + 44 + 48 + 70 + 72 + 66  # pleins CHF créés par cette suite ; le plein EUR (55) sans contre-valeur est exclu (D7, pending_fx)
    assert costs == round(_S["costs0"]["totals"]["annuel"] + added, 2)  # Lot G n'ajoute aucun coût : seuls les documents comptent
    assert _req("GET", "/fines").json()["total"] == _S["fines0"]
    assert _mongo().fuel_statements.count_documents({"tenant_id": "default"}) == 0 and _mongo().fuel_statement_lines.count_documents({"tenant_id": "default"}) == 0
    assert _mongo().fuel_reconciliations.count_documents({"tenant_id": "default"}) == 0
    e = _req("GET", "/energy").json()
    locked = [t for t in e["transactions"] if t.get("locked")]
    assert len(locked) == 12 and all(t["statement_id"] for t in locked)  # 1 (avril) + 10 (mai) + 1 (correctif)
    an = _req("GET", "/fuel/anomalies", params={"transaction_id": _S["tx_an2"]}).json()
    assert an["items"][0]["status"] == "justifiee"  # D8 : décision conservée, jamais recréée
    assert _req("POST", "/fuel/anomalies/scan").status_code == 200
    assert _req("GET", "/fuel/anomalies", params={"transaction_id": _S["tx_an2"]}).json()["items"][0]["status"] == "justifiee"
