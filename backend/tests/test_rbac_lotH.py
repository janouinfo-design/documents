"""Phase 4C — Lot H : rôles `manager` (scope explicite `users.vehicle_scope`) et `driver` (self-scope `users.driver_id`).
Trois preuves SÉPARÉES : TENANT_ISOLATION · MANAGER_SCOPE_ISOLATION · DRIVER_SELF_SCOPE_ISOLATION, plus console superadmin
(liaison / scope, même tenant, audit avant/après), révocation immédiate (même jeton), notes_internes, exports, non-régression
admin / read_only. Aucun fallback tenant-global : scope [] = 0 donnée, hors scope = 404, chauffeur hors /api/me = 403."""
import io
import sys
import uuid
from datetime import date, timedelta

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TA, TB = f"pytest-lh-a-{_RUN}", f"pytest-lh-b-{_RUN}"
ADMIN_A = (f"lh-adm-a-{_RUN}@pytest.ch", f"LhAdmA-{_RUN}-1")
RO_A = (f"lh-ro-a-{_RUN}@pytest.ch", f"LhRoA-{_RUN}-1")
MGR_A = (f"lh-mgr-a-{_RUN}@pytest.ch", f"LhMgrA-{_RUN}-1")      # scope [V1, V2]
MGR_EMPTY = (f"lh-mgr-e-{_RUN}@pytest.ch", f"LhMgrE-{_RUN}-1")  # scope []
DRV_A = (f"lh-drv-a-{_RUN}@pytest.ch", f"LhDrvA-{_RUN}-1")      # lié à D1
DRV_NONE = (f"lh-drv-n-{_RUN}@pytest.ch", f"LhDrvN-{_RUN}-1")   # lié à D_NONE (aucune affectation)
DRV_UNLINKED = (f"lh-drv-u-{_RUN}@pytest.ch", f"LhDrvU-{_RUN}-1")
DRV_INACT = (f"lh-drv-i-{_RUN}@pytest.ch", f"LhDrvI-{_RUN}-1")  # lié à D_INACT (désactivé)
ADMIN_B = (f"lh-adm-b-{_RUN}@pytest.ch", f"LhAdmB-{_RUN}-1")
MGR_B = (f"lh-mgr-b-{_RUN}@pytest.ch", f"LhMgrB-{_RUN}-1")
S, _cache = {}, {}
TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
PERIOD = TODAY.strftime("%Y-%m")
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def req(method, path, body=None, creds=ADMIN_A, **kw):
    return requests.request(method, f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=120, **kw)


def _admin_user(tenant, creds, role, **extra):
    r = requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": creds[0], "password": creds[1], "role": role, **extra},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _vehicle(plaque, creds=ADMIN_A):
    r = req("POST", "/vehicles", {"plaque": plaque, "marque": "Test", "modele": f"LotH {plaque}", "type_carburant": "Diesel"}, creds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _driver(nom, creds=ADMIN_A, **extra):
    r = req("POST", "/drivers", {"nom": nom, "prenom": "Lot", "email": f"{nom.lower()}-{_RUN}@pytest.ch", "telephone": "+41790000000",
                                 "matricule_interne": f"M-{nom}", "notes": "fiche admin privée", **extra}, creds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _assign(vehicle, driver, valid_from, valid_to=None, creds=ADMIN_A, principal=True):
    r = req("POST", f"/vehicles/{vehicle}/driver-assignments", {"driver_id": driver, "valid_from": valid_from, "valid_to": valid_to,
                                                                 "principal": principal}, creds)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _plein(vehicle, driver, station, litres=40, montant=80.0, creds=ADMIN_A, day=None):
    r = req("POST", f"/vehicles/{vehicle}/fuel-transactions", {"date": day or D(-2), "heure": "08:00", "station": station, "montant": montant,
                                                                "litres": litres, "prix_litre": round(montant / litres, 3),
                                                                "business_category": "CARBURANT", "motif": "Plein Lot H", "driver_id": driver}, creds)
    assert r.status_code == 200, r.text
    return r.json()["fuel_transaction"]["id"], r.json()["document_id"]


def _fine(vehicle, driver, numero, notes, creds=ADMIN_A, delai=20):
    r = req("POST", f"/vehicles/{vehicle}/fines", {"autorite": "Police LotH", "numero_amende": numero, "date_infraction": D(-5), "montant": 120.0,
                                                   "delai_paiement": D(delai), "motif": "Amende Lot H", "driver_id": driver,
                                                   "notes_internes": notes, "dossier_interne": f"DOSSIER-{numero}"}, creds)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _card(last4, vehicle, creds=ADMIN_A, valid_from=None, valid_to=None):
    r = req("POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": last4, "expire_le": D(400)}, creds)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    r = req("POST", f"/fuel-cards/{cid}/assignments", {"type": "vehicule", "vehicle_id": vehicle, "valid_from": valid_from or D(-30), "valid_to": valid_to}, creds)
    assert r.status_code == 200, r.text
    return cid


def _upload_doc(vehicle, creds=ADMIN_A):
    r = requests.post(f"{_BASE}/api/vehicles/{vehicle}/documents", files={"file": ("photo.png", io.BytesIO(PNG), "image/png")},
                      data={"folder": "Divers"}, headers=_h(creds), timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _audits(tenant, **q):
    return list(_mongo().audit_logs.find({"tenant_id": tenant, **q}, {"_id": 0}))


def setup_module():
    for tenant, admin in ((TA, ADMIN_A), (TB, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        _admin_user(tenant, admin, "admin")
    _admin_user(TA, RO_A, "read_only")
    S["V1"], S["V2"], S["V3"] = _vehicle(f"LH-{_RUN[:4]}-1"), _vehicle(f"LH-{_RUN[:4]}-2"), _vehicle(f"LH-{_RUN[:4]}-3")
    S["VB1"] = _vehicle(f"LHB-{_RUN[:4]}-1", ADMIN_B)
    S["D1"], S["D2"], S["D_NONE"], S["D_INACT"] = _driver("Dun"), _driver("Deux"), _driver("Dsans"), _driver("Dinactif")
    S["DB1"] = _driver("DriverB", ADMIN_B)
    S["A_D1_V1"] = _assign(S["V1"], S["D1"], D(-10))                 # active
    S["A_D1_V3_PAST"] = _assign(S["V3"], S["D1"], D(-60), D(-1))     # terminée hier
    S["A_D1_V2_FUT"] = _assign(S["V2"], S["D1"], D(1))               # future (demain)
    S["A_D2_V3"] = _assign(S["V3"], S["D2"], D(0))                  # active hors scope manager (débute aujourd'hui, après D1)
    S["TX1"], S["DOC_TX1"] = _plein(S["V1"], S["D1"], "Station V1-D1")
    S["TX2"], S["DOC_TX2"] = _plein(S["V3"], S["D2"], "Station V3-D2")
    S["TX3"], S["DOC_TX3"] = _plein(S["V3"], S["D1"], "Station V3-D1-ancien", day=D(-40))
    S["FINE1"] = _fine(S["V1"], S["D1"], f"F1-{_RUN}", "SECRET-NOTE-1")
    S["FINE2"] = _fine(S["V3"], S["D2"], f"F2-{_RUN}", "SECRET-NOTE-2")
    S["DOC_V1"] = _upload_doc(S["V1"])
    S["DOC_V3"] = _upload_doc(S["V3"])
    S["CARD_IN"] = _card("1111", S["V1"])
    S["CARD_OUT"] = _card("2222", S["V3"])
    S["CARD_MIX"] = _card("3333", S["V3"], valid_from=D(-90), valid_to=D(-31))  # passé hors scope + courant V1
    assert req("POST", f"/fuel-cards/{S['CARD_MIX']}/assignments", {"type": "vehicule", "vehicle_id": S["V1"], "valid_from": D(-30)}).status_code == 200
    db = _mongo()
    for key, vid, txid in (("AN_IN", S["V1"], S["TX1"]), ("AN_OUT", S["V3"], S["TX2"])):
        S[key] = str(uuid.uuid4())
        db.fuel_anomalies.insert_one({"id": S[key], "tenant_id": TA, "vehicle_id": vid, "transaction_id": txid, "type": "DUPLICATE_SUSPECTED",
                                      "severity": "warning", "status": "ouverte", "detected_at": D(-1), "detail": "test", "history": []})
    _admin_user(TA, MGR_A, "manager", vehicle_scope=[S["V1"], S["V2"]])
    _admin_user(TA, MGR_EMPTY, "manager")
    _admin_user(TA, DRV_A, "driver", driver_id=S["D1"])
    _admin_user(TA, DRV_NONE, "driver", driver_id=S["D_NONE"])
    _admin_user(TA, DRV_UNLINKED, "driver")
    _admin_user(TA, DRV_INACT, "driver", driver_id=S["D_INACT"])
    assert req("PATCH", f"/drivers/{S['D_INACT']}", {"actif": False}).status_code == 200
    _admin_user(TB, MGR_B, "manager", vehicle_scope=[S["VB1"]])


def teardown_module():
    db = _mongo()
    for tenant in (TA, TB):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations", "doc_categories",
                     "doc_requirements", "tenant_settings", "inspections", "fuel_transactions", "drivers", "driver_assignments", "fuel_cards",
                     "fuel_card_assignments", "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_transaction_matches",
                     "fuel_anomalies", "fuel_snapshots", "fuel_statements", "fuel_statement_lines", "fuel_reconciliations"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_one({"id": tenant})
    db.login_attempts.delete_many({"identifier": {"$regex": f"lh-.*{_RUN}"}})


def _user_id(email):
    return _mongo().users.find_one({"email": email}, {"_id": 0, "id": 1})["id"]


# ============================================================ CONSOLE SUPERADMIN — liaison / scope
def test_console_roles_enum_and_links_same_tenant_only():
    bad = requests.post(f"{_BASE}/api/admin/tenants/{TA}/users", json={"email": f"x-{_RUN}@p.ch", "password": "Xx-12345678", "role": "root"}, headers=sa(), timeout=30)
    assert bad.status_code == 422
    # driver_id cross-tenant / inexistant / rôle incompatible → 422 (aucune correspondance implicite)
    for body in ({"role": "driver", "driver_id": S["DB1"]}, {"role": "driver", "driver_id": "nope"}, {"role": "admin", "driver_id": S["D2"]},
                 {"role": "manager", "vehicle_scope": [S["VB1"]]}, {"role": "manager", "vehicle_scope": [S["V1"], "ghost"]},
                 {"role": "read_only", "vehicle_scope": [S["V1"]]}):
        r = requests.post(f"{_BASE}/api/admin/tenants/{TA}/users", json={"email": f"x-{uuid.uuid4().hex[:6]}@p.ch", "password": "Xx-12345678", **body},
                          headers=sa(), timeout=30)
        assert r.status_code == 422, (body, r.text)
    users = {u["email"]: u for u in requests.get(f"{_BASE}/api/admin/tenants/{TA}/users", headers=sa(), timeout=30).json()}
    assert users[MGR_A[0]]["vehicle_scope"] == [S["V1"], S["V2"]] and users[MGR_EMPTY[0]]["vehicle_scope"] == []
    assert users[DRV_A[0]]["driver_id"] == S["D1"] and users[DRV_UNLINKED[0]]["driver_id"] is None
    a = _audits(TA, action="admin_user_create", entity_id=users[DRV_A[0]]["id"])
    assert a and a[0]["after"]["driver_id"] == S["D1"]
    drivers = requests.get(f"{_BASE}/api/admin/tenants/{TA}/drivers", headers=sa(), timeout=30).json()
    by_id = {d["id"]: d for d in drivers}
    assert by_id[S["D1"]]["linked_user_email"] == DRV_A[0] and "email" not in by_id[S["D1"]] and "notes" not in by_id[S["D1"]]
    # admin tenant ne peut pas gérer les utilisateurs (console superadmin seule)
    assert req("GET", f"/admin/tenants/{TA}/drivers").status_code == 403


def test_console_update_role_change_clears_links_and_audits():
    uid = _admin_user(TA, (f"lh-tmp-{_RUN}@pytest.ch", f"LhTmp-{_RUN}-1"), "manager", vehicle_scope=[S["V3"]])["id"]
    r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"role": "admin"}, headers=sa(), timeout=30)
    assert r.status_code == 200 and r.json()["vehicle_scope"] is None
    r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"role": "manager"}, headers=sa(), timeout=30)
    assert r.json()["vehicle_scope"] == []  # jamais de fallback tenant
    r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"role": "driver", "driver_id": S["D2"]}, headers=sa(), timeout=30)
    assert r.json()["driver_id"] == S["D2"] and r.json()["vehicle_scope"] is None
    r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"driver_id": ""}, headers=sa(), timeout=30)
    assert r.json()["driver_id"] is None
    assert requests.put(f"{_BASE}/api/admin/users/{uid}", json={"driver_id": S["DB1"]}, headers=sa(), timeout=30).status_code == 422
    auds = _audits(TA, action="admin_user_update", entity_id=uid)
    assert len(auds) >= 4 and all("before" in a and "after" in a for a in auds)
    assert any(a["before"]["driver_id"] == S["D2"] and a["after"]["driver_id"] is None for a in auds)


# ============================================================ TENANT_ISOLATION
def test_tenant_isolation_manager_and_driver():
    assert req("GET", f"/vehicles/{S['VB1']}", creds=MGR_A).status_code == 404
    assert req("GET", f"/vehicles/{S['VB1']}").status_code == 404
    assert req("GET", f"/vehicles/{S['V1']}", creds=MGR_B).status_code == 404
    assert [v["id"] for v in req("GET", "/vehicles", creds=MGR_B).json()] == [S["VB1"]]
    assert req("POST", f"/vehicles/{S['V2']}/driver-assignments", {"driver_id": S["DB1"], "valid_from": D(0)}, creds=MGR_A).status_code == 404
    assert req("GET", f"/fines/{S['FINE1']}", creds=ADMIN_B).status_code == 404
    assert req("GET", f"/fuel-transactions/{S['TX1']}", creds=MGR_B).status_code == 404
    # chauffeur dont le lien pointe vers un conducteur d'un AUTRE tenant (simulation DB) → DRIVER_LINK_INVALID
    db = _mongo()
    uid = _user_id(DRV_NONE[0])
    db.users.update_one({"id": uid}, {"$set": {"driver_id": S["DB1"]}})
    try:
        r = req("GET", "/me/profile", creds=DRV_NONE)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "DRIVER_LINK_INVALID"
    finally:
        db.users.update_one({"id": uid}, {"$set": {"driver_id": S["D_NONE"]}})


# ============================================================ MANAGER_SCOPE_ISOLATION
def test_manager_vehicles_scope_and_mutations():
    me = req("GET", "/auth/me", creds=MGR_A).json()
    assert me["role"] == "manager" and me["vehicle_scope"] == [S["V1"], S["V2"]]
    assert sorted(v["id"] for v in req("GET", "/vehicles", creds=MGR_A).json()) == sorted([S["V1"], S["V2"]])
    assert req("GET", f"/vehicles/{S['V3']}", creds=MGR_A).status_code == 404
    assert req("GET", f"/vehicles/{S['V3']}/documents", creds=MGR_A).status_code == 404
    assert req("GET", f"/vehicles/{S['V3']}/energy", creds=MGR_A).status_code == 404
    assert req("PUT", f"/vehicles/{S['V3']}", {"modele": "Hors scope"}, creds=MGR_A).status_code == 404
    r = req("PUT", f"/vehicles/{S['V1']}", {"modele": "Modèle LotH"}, creds=MGR_A)
    assert r.status_code == 200 and r.json()["modele"] == "Modèle LotH"
    assert req("POST", "/vehicles", {"plaque": "NEW-1", "marque": "X", "modele": "Y"}, creds=MGR_A).status_code == 403
    assert req("DELETE", f"/vehicles/{S['V1']}", creds=MGR_A).status_code == 403
    assert req("DELETE", f"/vehicles/{S['V1']}/photo", creds=MGR_A).status_code == 403
    assert req("GET", "/vehicles-archive", creds=MGR_A).status_code == 403
    assert req("POST", f"/vehicles-archive/{S['V3']}/restore", creds=MGR_A).status_code == 403
    r = req("POST", f"/vehicles/{S['V1']}/inspections", {"date": D(0), "type": "depart", "notes": "ok", "photos": []}, creds=MGR_A)
    assert r.status_code == 200
    assert req("DELETE", f"/inspections/{r.json()['id']}", creds=MGR_A).status_code == 403
    assert req("POST", f"/vehicles/{S['V3']}/inspections", {"date": D(0), "type": "depart", "notes": "x", "photos": []}, creds=MGR_A).status_code == 404


def test_manager_documents_fines_energy_scope():
    docs = req("GET", "/documents", creds=MGR_A).json()
    assert docs and {d["vehicle_id"] for d in docs} <= {S["V1"], S["V2"]}
    assert req("GET", "/documents", creds=MGR_A, params={"vehicle_id": S["V3"]}).json() == []
    assert req("PATCH", f"/documents/{S['DOC_TX2']}", {"notes": "x"}, creds=MGR_A).status_code == 404
    assert req("PATCH", f"/documents/{S['DOC_TX1']}", {"notes": "note manager"}, creds=MGR_A).status_code == 200
    fines = req("GET", "/fines", creds=MGR_A).json()
    assert [f["id"] for f in fines["items"]] == [S["FINE1"]] and fines["total"] == 1
    f1 = req("GET", f"/fines/{S['FINE1']}", creds=MGR_A).json()
    assert f1["notes_internes"] == "SECRET-NOTE-1"  # notes internes en lecture, dans le scope uniquement
    assert req("GET", f"/fines/{S['FINE2']}", creds=MGR_A).status_code == 404
    assert req("POST", f"/documents/{S['FINE2']}/fine-status", {"fine_status": "contestee"}, creds=MGR_A).status_code == 404
    assert req("POST", f"/documents/{S['FINE1']}/fine-status", {"fine_status": "contestee"}, creds=MGR_A).status_code == 200
    assert req("GET", "/fines", creds=MGR_A, params={"vehicle_id": S["V3"]}).json()["total"] == 0
    en = req("GET", "/energy", creds=MGR_A).json()
    assert {x["vehicle_id"] for x in en["transactions"]} == {S["V1"]} and {b["vehicle_id"] for b in en["by_vehicle"]} == {S["V1"]}
    assert req("GET", "/energy", creds=MGR_A, params={"vehicle_id": S["V3"]}).json()["transactions"] == []
    assert req("GET", f"/fuel-transactions/{S['TX2']}", creds=MGR_A).status_code == 404
    assert req("GET", f"/fuel-transactions/{S['TX1']}", creds=MGR_A).status_code == 200
    assert req("PATCH", f"/fuel-transactions/{S['TX1']}/match", {"vehicle_id": S["V3"], "reason": "hors scope"}, creds=MGR_A).status_code == 404
    assert req("PATCH", f"/fuel-transactions/{S['TX2']}/match", {"vehicle_id": S["V1"], "reason": "tx hors scope"}, creds=MGR_A).status_code == 404
    r = req("PATCH", f"/fuel-transactions/{S['TX1']}/match", {"vehicle_id": S["V2"], "reason": "réaffectation scope"}, creds=MGR_A)
    assert r.status_code == 200 and r.json()["transaction"]["vehicle_id"] == S["V2"]
    assert req("PATCH", f"/fuel-transactions/{S['TX1']}/match", {"vehicle_id": S["V1"], "reason": "retour"}, creds=MGR_A).status_code == 200
    # plein / amende sans justificatif : véhicule du scope uniquement
    assert req("POST", f"/vehicles/{S['V3']}/fuel-transactions", {"date": D(0), "montant": 10, "litres": 5, "business_category": "CARBURANT", "motif": "x"}, creds=MGR_A).status_code == 404
    tx, _ = _plein(S["V2"], S["D2"], "Station manager", creds=MGR_A, day=D(-1))
    assert tx
    aud = _audits(TA, entity="fuel_transaction", entity_id=tx)
    assert aud and aud[0]["role"] == "manager" and aud[0]["vehicle_id"] == S["V2"]


def test_manager_anomalies_reconciliations_kpi_scope():
    an = req("GET", "/fuel/anomalies", creds=MGR_A).json()
    assert [a["id"] for a in an["items"]] == [S["AN_IN"]] and an["stats"]["total"] == 1
    assert req("GET", f"/fuel/anomalies/{S['AN_OUT']}", creds=MGR_A).status_code == 404
    assert req("POST", f"/fuel/anomalies/{S['AN_OUT']}/decide", {"decision": "justify", "reason": "hors scope"}, creds=MGR_A).status_code == 404
    assert req("POST", f"/fuel/anomalies/{S['AN_IN']}/decide", {"decision": "justify", "reason": "justifiée par le manager"}, creds=MGR_A).status_code == 200
    reco = req("GET", "/fuel/reconciliations", creds=MGR_A, params={"period_month": PERIOD}).json()
    assert {r["vehicle_id"] for r in reco["items"]} <= {S["V1"], S["V2"]}
    assert req("GET", "/fuel/reconciliations", creds=MGR_A, params={"period_month": PERIOD, "vehicle_id": S["V3"]}).status_code == 404
    assert req("POST", f"/fuel/reconciliations/{S['V3']}/{PERIOD}/justify", {"reason": "hors scope"}, creds=MGR_A).status_code == 404
    assert req("POST", f"/fuel/reconciliations/{S['V1']}/{PERIOD}/justify", {"reason": "justification manager"}, creds=MGR_A).status_code == 200
    for path in ("/deadlines", "/alerts"):
        items = req("GET", path, creds=MGR_A).json()["items"]
        assert all(i["vehicle_id"] in (S["V1"], S["V2"]) for i in items), path
    assert all(e["vehicle_id"] in (S["V1"], S["V2"]) for e in req("GET", "/timeline", creds=MGR_A).json())
    costs = req("GET", "/costs", creds=MGR_A).json()
    assert costs["items"] and {i["vehicle_id"] for i in costs["items"]} <= {S["V1"], S["V2"]}
    assert {b["vehicle_id"] for b in costs["by_vehicle"]} <= {S["V1"], S["V2"]}
    dash = req("GET", "/dashboard", creds=MGR_A).json()
    assert dash["total_vehicles"] == 2
    assert req("GET", "/dashboard").json()["total_vehicles"] == 3
    assert req("GET", "/alerts", creds=MGR_A).json()["recipients"] == []


def test_manager_exports_same_server_scope():
    csv = req("GET", "/reports/amendes.csv", creds=MGR_A).text
    assert f"F1-{_RUN}" in csv and f"F2-{_RUN}" not in csv and "SECRET-NOTE" not in csv
    tx_csv = req("GET", "/fuel/transactions/export", creds=MGR_A, params={"period_month": PERIOD, "format": "csv"}).text
    assert "Station V1-D1" in tx_csv and "Station V3-D2" not in tx_csv
    out_csv = req("GET", "/fuel/transactions/export", creds=MGR_A, params={"period_month": PERIOD, "vehicle_id": S["V3"], "format": "csv"}).text
    assert "Station V3" not in out_csv and "# Transactions;0" in out_csv
    assert req("GET", "/fuel/reconciliations/export", creds=MGR_A, params={"period_month": PERIOD, "format": "csv"}).status_code == 200
    assert req("GET", "/fuel/reconciliations/export", creds=MGR_A, params={"period_month": PERIOD, "vehicle_id": S["V3"], "format": "csv"}).status_code == 404
    couts = req("GET", "/reports/couts.csv", creds=MGR_A).text
    assert f"LH-{_RUN[:4]}-1" in couts and f"LH-{_RUN[:4]}-3" not in couts
    assert req("GET", "/reports/conformite.pdf", creds=MGR_A).status_code == 200
    assert req("GET", f"/reports/vehicule/{S['V3']}.pdf", creds=MGR_A).status_code == 404
    assert req("GET", f"/reports/vehicule/{S['V1']}.pdf", creds=MGR_A).status_code == 200


def test_manager_fuel_cards_visibility_rules():
    cards = req("GET", "/fuel-cards", creds=MGR_A).json()
    ids = {c["id"] for c in cards["items"]}
    assert S["CARD_IN"] in ids and S["CARD_MIX"] in ids and S["CARD_OUT"] not in ids
    assert cards["stats"]["total"] == 2
    assert req("GET", f"/fuel-cards/{S['CARD_OUT']}", creds=MGR_A).status_code == 404
    mix = req("GET", f"/fuel-cards/{S['CARD_MIX']}", creds=MGR_A).json()
    assert {a["vehicle_id"] for a in mix["assignments"]} == {S["V1"]}  # affectation passée V3 jamais exposée
    assert {a["vehicle_id"] for a in req("GET", f"/fuel-cards/{S['CARD_MIX']}/assignments", creds=MGR_A).json()} == {S["V1"]}
    assert len(req("GET", f"/fuel-cards/{S['CARD_MIX']}", ).json()["assignments"]) == 2  # admin : tout
    assert req("GET", "/fuel-cards/resolve", creds=MGR_A, params={"last4": "2222"}).json()["status"] == "not_found"
    assert req("GET", "/fuel-cards/resolve", creds=MGR_A, params={"last4": "1111"}).json()["status"] == "found"
    for method, path, body in (("POST", "/fuel-cards", {"fournisseur": "Shell", "last4": "9999"}), ("PATCH", f"/fuel-cards/{S['CARD_IN']}", {"notes": "x"}),
                               ("POST", f"/fuel-cards/{S['CARD_IN']}/status", {"statut": "bloquee", "motif": "x"}),
                               ("POST", f"/fuel-cards/{S['CARD_IN']}/assignments", {"type": "vehicule", "vehicle_id": S["V2"], "valid_from": D(0)})):
        assert req(method, path, body, creds=MGR_A).status_code == 403, path
    assert req("GET", f"/fuel-cards/{S['CARD_IN']}/history", creds=MGR_A).status_code == 403
    assert req("GET", f"/fuel-cards/{S['CARD_IN']}/history", creds=RO_A).status_code == 200
    # échéance de carte : carte du scope visible, carte hors scope invisible
    keys = {i["key"] for i in req("GET", "/deadlines", creds=MGR_A).json()["items"]}
    assert f"fuel_card:{S['CARD_IN']}" in keys and f"fuel_card:{S['CARD_OUT']}" not in keys
    assert f"fuel_card:{S['CARD_OUT']}" in {i["key"] for i in req("GET", "/deadlines").json()["items"]}


def test_manager_drivers_minimal_and_assignments():
    rows = req("GET", "/drivers", creds=MGR_A).json()
    assert rows and all(set(r.keys()) <= {"id", "nom", "prenom", "matricule_interne", "actif", "display", "affectations"} for r in rows)
    d2 = next(r for r in rows if r["id"] == S["D2"])
    assert d2["affectations"] == []  # D2 → V3 hors scope : jamais exposée
    d1 = next(r for r in rows if r["id"] == S["D1"])
    assert {a["vehicle_id"] for a in d1["affectations"]} == {S["V1"]}
    det = req("GET", f"/drivers/{S['D2']}", creds=MGR_A).json()
    assert "email" not in det and "telephone" not in det and "notes" not in det and det["assignments"] == []
    full = req("GET", f"/drivers/{S['D2']}").json()
    assert full["email"] and len(full["assignments"]) == 1  # admin : fiche complète
    for method, path in (("POST", "/drivers"), ("PATCH", f"/drivers/{S['D2']}"), ("POST", f"/drivers/{S['D2']}/archive")):
        assert req(method, path, {"nom": "X", "actif": True}, creds=MGR_A).status_code == 403, path
    assert req("POST", f"/vehicles/{S['V3']}/driver-assignments", {"driver_id": S["D2"], "valid_from": D(0), "principal": False}, creds=MGR_A).status_code == 404
    r = req("POST", f"/vehicles/{S['V2']}/driver-assignments", {"driver_id": S["D2"], "valid_from": D(0), "principal": False}, creds=MGR_A)
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    aud = _audits(TA, entity="driver_assignment", entity_id=aid)
    assert aud and aud[0]["role"] == "manager" and aud[0]["vehicle_id"] == S["V2"]
    assert req("POST", f"/driver-assignments/{S['A_D2_V3']}/close", {"motif": "hors scope"}, creds=MGR_A).status_code == 404
    assert req("POST", f"/driver-assignments/{aid}/close", {"motif": "fin test manager"}, creds=MGR_A).status_code == 200


def test_manager_forbidden_tenant_global_functions():
    checks = [("GET", "/fuel/statements"), ("POST", "/fuel/statements"), ("GET", "/fuel/imports"), ("GET", "/fuel/import-fields"),
              ("GET", "/tenant-settings/fuel"), ("PATCH", "/tenant-settings/fuel"), ("GET", "/tenant-settings/fuel/reconciliation"),
              ("GET", "/legacy/vehicle-map"), ("POST", "/navixy/sync"), ("GET", "/navixy/status"), ("POST", "/astra/import"),
              ("POST", "/demo/fill-admin"), ("POST", "/alerts/run"), ("GET", "/alerts/log"), ("GET", "/admin/overview"),
              ("DELETE", f"/documents/{S['DOC_V1']['id']}"), ("POST", "/doc-categories"), ("PUT", "/settings/deadlines"),
              ("PUT", "/doc-requirements"), ("GET", "/integrations/navixy/link-suggestions"), ("POST", "/integrations/navixy/link"),
              ("POST", f"/vehicles/{S['V1']}/navixy/push"), ("POST", f"/vehicles/{S['V1']}/photo/navixy/import"),
              ("DELETE", f"/documents/{S['FINE1']}/attachments/x")]
    for method, path in checks:
        r = req(method, path, {"name": "x", "urgent_days": 1, "warning_days": 2, "profil": "x", "categories": [], "period_month": PERIOD, "fournisseur": "x", "replace": False}, creds=MGR_A)
        assert r.status_code == 403, (method, path, r.status_code, r.text[:120])
    # read_only conserve ses lectures tenant-globales (non-régression)
    assert req("GET", "/fuel/statements", creds=RO_A).status_code == 200
    assert req("GET", "/tenant-settings/fuel", creds=RO_A).status_code == 200


def test_manager_empty_scope_sees_nothing():
    assert req("GET", "/vehicles", creds=MGR_EMPTY).json() == []
    assert req("GET", "/dashboard", creds=MGR_EMPTY).json()["total_vehicles"] == 0
    assert req("GET", "/fines", creds=MGR_EMPTY).json()["total"] == 0
    assert req("GET", "/energy", creds=MGR_EMPTY).json()["transactions"] == []
    assert req("GET", "/fuel-cards", creds=MGR_EMPTY).json()["items"] == []
    assert req("GET", "/documents", creds=MGR_EMPTY).json() == []
    assert req("GET", "/deadlines", creds=MGR_EMPTY).json()["count"] == 0
    assert req("GET", "/fuel/anomalies", creds=MGR_EMPTY).json()["total"] == 0
    assert req("GET", "/fuel/reconciliations", creds=MGR_EMPTY, params={"period_month": PERIOD}).json()["total"] == 0
    assert req("GET", f"/vehicles/{S['V1']}", creds=MGR_EMPTY).status_code == 404
    assert all(r["affectations"] == [] for r in req("GET", "/drivers", creds=MGR_EMPTY).json())


def test_manager_scope_revocation_same_token():
    assert req("GET", f"/vehicles/{S['V1']}", creds=MGR_A).status_code == 200
    uid = _user_id(MGR_A[0])
    r = requests.put(f"{_BASE}/api/admin/users/{uid}", json={"vehicle_scope": [S["V2"]]}, headers=sa(), timeout=30)
    assert r.status_code == 200 and r.json()["vehicle_scope"] == [S["V2"]]
    try:
        assert req("GET", f"/vehicles/{S['V1']}", creds=MGR_A).status_code == 404  # même jeton, requête suivante : refus
        assert [v["id"] for v in req("GET", "/vehicles", creds=MGR_A).json()] == [S["V2"]]
    finally:
        requests.put(f"{_BASE}/api/admin/users/{uid}", json={"vehicle_scope": [S["V1"], S["V2"]]}, headers=sa(), timeout=30)
    assert req("GET", f"/vehicles/{S['V1']}", creds=MGR_A).status_code == 200
    auds = _audits(TA, action="admin_user_update", entity_id=uid)
    assert any(a["before"]["vehicle_scope"] == [S["V1"], S["V2"]] and a["after"]["vehicle_scope"] == [S["V2"]] for a in auds)


def test_manager_files_scoped():
    assert req("GET", f"/files/{S['DOC_V1']['storage_path']}", creds=MGR_A).status_code == 200
    assert req("GET", f"/files/{S['DOC_V3']['storage_path']}", creds=MGR_A).status_code == 404
    assert req("GET", f"/files/{S['DOC_V3']['storage_path']}", creds=RO_A).status_code == 200


# ============================================================ DRIVER_SELF_SCOPE_ISOLATION
def test_driver_fail_closed_outside_me():
    for path in ("/vehicles", "/dashboard", "/fines", "/energy", "/drivers", "/documents", "/deadlines", "/fuel-cards", f"/vehicles/{S['V1']}",
                 f"/fuel-transactions/{S['TX1']}", f"/fines/{S['FINE1']}", "/fuel/statements", "/costs", "/alerts"):
        r = req("GET", path, creds=DRV_A)
        assert r.status_code == 403 and r.json()["detail"]["code"] == "DRIVER_FORBIDDEN", path
    assert req("POST", f"/vehicles/{S['V1']}/fuel-transactions", {"date": D(0), "montant": 1, "business_category": "CARBURANT", "motif": "x"}, creds=DRV_A).status_code == 403
    assert req("GET", "/auth/me", creds=DRV_A).json()["driver_id"] == S["D1"]
    assert req("GET", "/me/profile").status_code == 403  # admin : pas une vue chauffeur


def test_driver_profile_vehicles_active_only():
    p = req("GET", "/me/profile", creds=DRV_A).json()
    assert p["driver"]["id"] == S["D1"] and "email" not in p["driver"]
    v = req("GET", "/me/vehicles", creds=DRV_A).json()
    assert [x["id"] for x in v["items"]] == [S["V1"]]  # V3 (terminée hier) et V2 (future) exclues
    assert v["items"][0]["assignment"]["id"] == S["A_D1_V1"] and "leasing" not in v["items"][0] and "assurance" not in v["items"][0]


def test_driver_fuel_and_fines_self_scope_no_internal_notes():
    fuel = req("GET", "/me/fuel-transactions", creds=DRV_A).json()
    ids = {x["id"] for x in fuel["items"]}
    assert S["TX1"] in ids and S["TX3"] in ids and S["TX2"] not in ids  # TX3 : son plein historique sur V3 (événement), TX2 : autre conducteur
    assert all(x.get("vehicle_id") in (S["V1"], S["V3"]) for x in fuel["items"]) and fuel["totals"]["transactions"] == len(ids)
    assert all("notes_internes" not in x for x in fuel["items"])
    assert req("GET", "/me/fuel-transactions", creds=DRV_A, params={"period_month": PERIOD}).json()["total"] >= 1
    fines = req("GET", "/me/fines", creds=DRV_A).json()
    assert [f["id"] for f in fines["items"]] == [S["FINE1"]]
    f = fines["items"][0]
    assert "notes_internes" not in f and "dossier_interne" not in f and "priorite" not in f and f["fine_status"] == "contestee"
    # self-scope par ID : plein d'un autre conducteur → 404 ; aucune fuite via justificatif
    r = requests.post(f"{_BASE}/api/me/fuel-transactions/{S['TX2']}/attachment", files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, headers=_h(DRV_A), timeout=60)
    assert r.status_code == 404
    r = requests.post(f"{_BASE}/api/me/fuel-transactions/{S['TX3']}/attachment", files={"file": ("ticket.png", io.BytesIO(PNG), "image/png")}, headers=_h(DRV_A), timeout=60)
    assert r.status_code == 200, r.text
    just = r.json()["justificatif"]
    assert just["present"] and just["path"] and "duplicate_of" not in r.json()
    r = requests.post(f"{_BASE}/api/me/fuel-transactions/{S['TX3']}/attachment", files={"file": ("t2.png", io.BytesIO(PNG), "image/png")}, headers=_h(DRV_A), timeout=60)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "FILE_ALREADY_PRESENT"
    aud = _audits(TA, action="attach_file", entity_id=S["DOC_TX3"])
    assert aud and aud[0]["role"] == "driver"
    S["TX3_PATH"] = just["path"]
    tx3 = next(x for x in req("GET", "/me/fuel-transactions", creds=DRV_A).json()["items"] if x["id"] == S["TX3"])
    assert tx3["justificatif"]["present"] is True


def test_driver_fines_kpi_calc_fields_used_server_side_never_exposed():
    """Bug it.48 : `_ME_FINE_PROJ` omettait `document_type` / `business_category` → `_is_fine` faux → `deadline_active` jamais posé → KPI à 0."""
    import fines as fin
    S["FINE_LATE"] = _fine(S["V1"], S["D1"], f"F3-{_RUN}", "SECRET-NOTE-3", delai=-3)                # échéance dépassée depuis 3 jours
    S["FINE_NODRIVER"] = _fine(S["V1"], None, f"F4-{_RUN}", "SECRET-NOTE-4")                        # véhicule de D1, sans driver_id
    # A. les 2 champs de calcul existent dans la source (documents)
    src = {d["id"]: d for d in _mongo().documents.find({"tenant_id": TA, "id": {"$in": [S["FINE1"], S["FINE_LATE"]]}}, {"_id": 0})}
    assert all(d.get("document_type") == "amende" and d.get("business_category") == "AMENDE" for d in src.values())
    fines = req("GET", "/me/fines", creds=DRV_A).json()
    items = {f["id"]: f for f in fines["items"]}
    # E. self-scope : F1 + F3 (driver D1) uniquement ; F2 (D2/V3) et F4 (V1 sans driver_id) jamais dans liste / total / KPI
    assert set(items) == {S["FINE1"], S["FINE_LATE"]} and fines["total"] == 2
    # B. KPI corrects grâce aux champs de calcul (deadline_active posé côté serveur)
    late = items[S["FINE_LATE"]]
    assert late["deadline_active"] is True and late["days_remaining"] == -3 and late["fine_status_label"] and late["payee"] is False
    f1_open = fin.deadline_active(items[S["FINE1"]]["fine_status"])
    assert items[S["FINE1"]]["deadline_active"] is f1_open
    assert fines["totals"]["en_retard"] == 1 and fines["totals"]["ouvertes"] == 1 + int(f1_open)
    assert fines["totals"]["montant_ouvert_chf"] == round(120.0 * (1 + int(f1_open)), 2)
    # C + D. les champs de calcul et les notes internes ne sont jamais renvoyés au chauffeur
    for f in fines["items"]:
        assert "document_type" not in f and "business_category" not in f
        assert "notes_internes" not in f and "dossier_interne" not in f and "priorite" not in f
    # admin : F4 existe bien (le filtre driver_id est la seule raison de son absence côté chauffeur)
    assert S["FINE_NODRIVER"] in {f["id"] for f in req("GET", "/fines", params={"vehicle_id": S["V1"]}).json()["items"]}


def test_driver_files_only_own():
    assert req("GET", f"/files/{S['TX3_PATH']}", creds=DRV_A).status_code == 200
    assert req("GET", f"/files/{S['DOC_V1']['storage_path']}", creds=DRV_A).status_code == 404  # document du véhicule, pas SON plein
    assert req("GET", f"/files/{S['TX3_PATH']}", creds=DRV_NONE).status_code == 404  # autre chauffeur
    assert req("GET", f"/files/{S['TX3_PATH']}", creds=MGR_A).status_code == 404  # TX3 sur V3 : hors scope manager
    assert req("GET", f"/files/{S['TX3_PATH']}").status_code == 200
    # jeton fichier (query string) : même self-scope
    tok = req("GET", "/auth/file-token", creds=DRV_A).json()["token"]
    no_bearer = {"Authorization": ""}  # neutralise l'injection conftest : seul le jeton `file` en query compte
    assert requests.get(f"{_BASE}/api/files/{S['TX3_PATH']}", params={"token": tok}, headers=no_bearer, timeout=30).status_code == 200
    assert requests.get(f"{_BASE}/api/files/{S['DOC_V1']['storage_path']}", params={"token": tok}, headers=no_bearer, timeout=30).status_code == 404


def test_driver_link_states_and_no_assignment():
    r = req("GET", "/me/profile", creds=DRV_UNLINKED)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "DRIVER_ACCOUNT_NOT_LINKED"
    for path in ("/me/vehicles", "/me/fuel-transactions", "/me/fines"):
        assert req("GET", path, creds=DRV_UNLINKED).json()["detail"]["code"] == "DRIVER_ACCOUNT_NOT_LINKED", path
    r = req("GET", "/me/vehicles", creds=DRV_INACT)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "DRIVER_INACTIVE"
    # lié + actif mais SANS affectation : 200 et listes vides (≠ compte non lié)
    assert req("GET", "/me/profile", creds=DRV_NONE).status_code == 200
    assert req("GET", "/me/vehicles", creds=DRV_NONE).json() == {"items": [], "total": 0, "date": req("GET", "/me/vehicles", creds=DRV_NONE).json()["date"]}
    assert req("GET", "/me/fuel-transactions", creds=DRV_NONE).json()["total"] == 0
    assert req("GET", "/me/fines", creds=DRV_NONE).json()["total"] == 0


def test_driver_revocation_same_token_unlink_inactive_assignment_end():
    uid = _user_id(DRV_A[0])
    assert req("GET", "/me/profile", creds=DRV_A).status_code == 200
    requests.put(f"{_BASE}/api/admin/users/{uid}", json={"driver_id": ""}, headers=sa(), timeout=30)
    try:
        assert req("GET", "/me/profile", creds=DRV_A).json()["detail"]["code"] == "DRIVER_ACCOUNT_NOT_LINKED"
    finally:
        requests.put(f"{_BASE}/api/admin/users/{uid}", json={"driver_id": S["D1"]}, headers=sa(), timeout=30)
    assert req("GET", "/me/profile", creds=DRV_A).status_code == 200
    # conducteur désactivé par l'admin → même session : DRIVER_INACTIVE ; réactivation → OK
    assert req("PATCH", f"/drivers/{S['D1']}", {"actif": False}).status_code == 200
    try:
        assert req("GET", "/me/vehicles", creds=DRV_A).json()["detail"]["code"] == "DRIVER_INACTIVE"
    finally:
        assert req("PATCH", f"/drivers/{S['D1']}", {"actif": True}).status_code == 200
    # affectation terminée → véhicule disparaît de « mes véhicules »
    aid = _assign(S["V2"], S["D_NONE"], D(-10), principal=False)
    assert [x["id"] for x in req("GET", "/me/vehicles", creds=DRV_NONE).json()["items"]] == [S["V2"]]
    assert req("POST", f"/driver-assignments/{aid}/close", {"valid_to": D(-1), "motif": "fin de mission"}).status_code == 200
    assert req("GET", "/me/vehicles", creds=DRV_NONE).json()["items"] == []
    # conducteur archivé → lien invalide
    assert req("POST", f"/drivers/{S['D_NONE']}/archive").status_code == 200
    assert req("GET", "/me/profile", creds=DRV_NONE).json()["detail"]["code"] == "DRIVER_LINK_INVALID"


# ============================================================ NON-RÉGRESSION admin / read_only
def test_admin_and_read_only_unchanged():
    assert sorted(v["id"] for v in req("GET", "/vehicles").json()) == sorted([S["V1"], S["V2"], S["V3"]])
    assert req("GET", f"/fines/{S['FINE1']}").json()["notes_internes"] == "SECRET-NOTE-1"
    assert "notes_internes" not in req("GET", f"/fines/{S['FINE1']}", creds=RO_A).json()
    assert len(req("GET", "/vehicles", creds=RO_A).json()) == 3
    assert req("POST", "/vehicles", {"plaque": "RO-1", "marque": "X", "modele": "Y"}, creds=RO_A).status_code == 403
    assert req("GET", "/fuel-cards", creds=RO_A).json()["stats"]["total"] == 3
    assert "email" in req("GET", "/drivers").json()[0]
    assert req("GET", "/me/vehicles", creds=RO_A).status_code == 403
    dash = req("GET", "/dashboard").json()
    assert dash["total_vehicles"] == 3
