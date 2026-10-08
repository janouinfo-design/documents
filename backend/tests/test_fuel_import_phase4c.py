"""Phase 4C — Lot F (6a) : import CSV/XLSX carburant — pipeline job → mapping → preview (0 écriture métier finale) → confirm / force.
Dédup Documents propre (ext id → dedup_key → intra-fichier), idempotence, résolution carte (found/ambiguous/not_found, card_id écrit
uniquement si found), plaque = candidats de revue (jamais auto), action groupée = N décisions humaines auditées, D1 (document sans
fichier, 1 doc = 1 tx), D7 (CHF / devise + montant_chf / pending_fx exclu), RBAC read_only, isolation tenant. Données synthétiques."""
import io
import uuid

import openpyxl
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A, TENANT_B = f"pytest-fi-a-{_RUN}", f"pytest-fi-b-{_RUN}"
ADMIN_A = (f"fi-adm-a-{_RUN}@pytest.ch", f"FiAdmA-{_RUN}-1")
RO_A = (f"fi-ro-a-{_RUN}@pytest.ch", f"FiRoA-{_RUN}-1")
ADMIN_B = (f"fi-adm-b-{_RUN}@pytest.ch", f"FiAdmB-{_RUN}-1")
BUSINESS = ("documents", "fuel_transactions", "fuel_cards", "fuel_card_assignments", "fuel_anomalies", "fuel_transaction_matches", "vehicles", "drivers")
P = _RUN[:4].upper()
PL = {"va1": f"VD {P} 01", "va2": f"VD {P} 02", "va3": f"VD {P} 03", "dup": f"GE {P} 09", "vb1": f"BE {P} 01"}
HEADER = ["Ref", "Date transaction", "Numero de carte", "Immatriculation", "vehicle_id", "Montant TTC", "Devise", "Montant CHF", "Quantite", "Prix unitaire", "Station", "Kilometrage", "Produit"]
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


def _upload(content: bytes, filename: str, creds=ADMIN_A, fournisseur="Migrol"):
    return requests.post(f"{_BASE}/api/fuel/imports", files={"file": (filename, content)}, data={"fournisseur": fournisseur} if fournisseur else {},
                         headers=_h(creds), timeout=120)


def _card(**over):
    r = _req("POST", "/fuel-cards", {"fournisseur": "Migrol", "type_affectation": "vehicule", "expire_le": "2030-12-31", **over})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _assign(card_id, **over):
    r = _req("POST", f"/fuel-cards/{card_id}/assignments", {"type": "vehicule", "valid_from": "2026-01-01", **over})
    assert r.status_code == 200, r.text
    return r.json()


def _snapshot():
    db = _mongo()
    return {c: db[c].count_documents({"tenant_id": {"$in": [TENANT_A, TENANT_B]}}) for c in BUSINESS}


def _rows():
    """Fixture synthétique Lot F (13+ cas) — aucune donnée Journal."""
    va1, va2 = _S["va1"], _S["va2"]
    return [
        ["T1", "01.06.2026 08:00", "**** 1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne", "50500", "Diesel"],
        ["T2", "01.06.2026 09:00", "2222", PL["va1"], "", "60.00", "CHF", "", "30", "2.00", "Shell Vevey", "", "Diesel"],
        ["T3", "01.06.2026 10:00", "3333", "", "", "55.00", "CHF", "", "25", "2.20", "Migrol Nyon", "", "Essence"],
        ["T4", "02.06.2026 10:00", "4444", "", "", "41.00", "CHF", "", "20", "2.05", "Migrol Nyon", "", "Diesel"],
        ["T5", "02.06.2026 11:00", "5555", PL["va2"], va1, "61.50", "CHF", "", "30", "2.05", "Migrol Morges", "", "Diesel"],
        ["T6", "02.06.2026 12:00", "", PL["va2"], "", "44.00", "CHF", "", "20", "2.20", "Agrola Gland", "", "Essence"],
        ["T7", "02.06.2026 13:00", "", PL["dup"], "", "44.00", "CHF", "", "20", "2.20", "Agrola Rolle", "", "Essence"],
        ["T8", "02.06.2026 14:00", "", "ZH 999 999", "", "33.00", "CHF", "", "15", "2.20", "Coop Zurich", "", "Essence"],
        ["T1", "01.06.2026 08:00", "**** 1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne", "50500", "Diesel"],
        ["T11", "03.06.2026 08:00", "1111", "", "", "50.00", "EUR", "48.50", "25", "2.00", "Total Annemasse", "", "Diesel"],
        ["T12", "03.06.2026 09:00", "1111", "", "", "30.00", "EUR", "", "15", "2.00", "Total Annemasse", "", "Diesel"],
        ["T13", "03.06.2026 10:00", "1111", "", "", "", "CHF", "", "10", "2.00", "Migrol Lausanne", "", "Diesel"],
        ["T15", "04.06.2026 08:00", "1111", "", "", "100.00", "CHF", "", "40", "2.05", "Migrol Lausanne", "", "Diesel"],
        ["T16", "04.06.2026 12:00", "1111", "", "", "184.50", "CHF", "", "90", "2.05", "Migrol Lausanne", "", "Diesel"],
        ["T17", "01.06.2026 08:30", "1111", "", "", "41.00", "CHF", "", "20", "2.05", "Migrol Lausanne", "", "Diesel"],
        ["T18", "05.06.2026 08:00", "1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne", "50100", "Diesel"],
        ["T20", "05.06.2026 09:00", "6666", "", "", "40.00", "CHF", "", "20", "2.00", "Agrola Aigle", "", "Diesel"],
        ["T21", "05.06.2026 10:00", "7777", "", "", "25.00", "CHF", "", "50", "0.50", "Ionity Bursins", "", "Électricité"],
        ["T22", "10.06.2026 08:00", "1111", "", "", "1000.00", "CHF", "", "", "", "Migrol Lausanne", "", "Diesel"],
    ]


def _csv(rows=None, delimiter=";") -> bytes:
    rows = rows if rows is not None else _rows()
    return ("\ufeff" + "\n".join(delimiter.join(r) for r in [HEADER] + rows) + "\n").encode("utf-8")


def _xlsx(rows=None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in (rows if rows is not None else _rows()):
        ws.append([None if v == "" else v for v in r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


MAPPING = {"external_transaction_id": "Ref", "tx_datetime": "Date transaction", "card_last4": "Numero de carte", "vehicle_hint": "Immatriculation",
           "vehicle_id": "vehicle_id", "amount_total": "Montant TTC", "currency": "Devise", "amount_chf": "Montant CHF", "quantity": "Quantite",
           "unit_price": "Prix unitaire", "station_name": "Station", "mileage": "Kilometrage", "product_type": "Produit"}


def _by_ref(rows):
    out = {}
    for r in rows:
        out.setdefault(r["raw"]["Ref"], []).append(r)
    return out


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"}, headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"}, headers=sa(), timeout=30).status_code == 200
    for key, body, creds in (("va1", {"plaque": PL["va1"], "type_carburant": "Diesel", "capacite_reservoir_l": 60, "kilometrage": 50000}, ADMIN_A),
                             ("va2", {"plaque": PL["va2"], "type_carburant": "Essence", "kilometrage": 1000}, ADMIN_A),
                             ("va3", {"plaque": PL["va3"], "kilometrage": 1000}, ADMIN_A),
                             ("dup1", {"plaque": PL["dup"], "kilometrage": 1000}, ADMIN_A), ("dup2", {"plaque": PL["dup"].replace(" ", ""), "kilometrage": 1000}, ADMIN_A),
                             ("vb1", {"plaque": PL["vb1"], "kilometrage": 1000}, ADMIN_B)):
        r = _req("POST", "/vehicles", body, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    r = _req("POST", "/drivers", {"nom": "Lambert", "prenom": "Test", "matricule_interne": f"LA-{_RUN[:4]}"})
    assert r.status_code == 200, r.text
    _S["d1"] = r.json()["id"]
    assert _req("POST", f"/vehicles/{_S['va3']}/driver-assignments", {"driver_id": _S["d1"], "valid_from": "2026-01-01"}).status_code == 200
    _S["c1"] = _card(last4="1111")
    _assign(_S["c1"], vehicle_id=_S["va1"])
    _S["c2"] = _card(fournisseur="Shell", last4="2222")
    _S["c3"] = _card(fournisseur="Shell", last4="2222", collision_confirmed=True)
    _assign(_S["c2"], vehicle_id=_S["va1"])
    _assign(_S["c3"], vehicle_id=_S["va2"])
    _S["c4"] = _card(last4="3333")
    _assign(_S["c4"], vehicle_id=_S["va2"])
    assert _req("POST", f"/fuel-cards/{_S['c4']}/status", {"statut": "suspendue", "motif": "test suspension"}).status_code == 200
    _S["c5"] = _card(last4="4444", expire_le="2026-03-31")
    _assign(_S["c5"], vehicle_id=_S["va1"])
    _S["c6"] = _card(last4="5555")
    _assign(_S["c6"], vehicle_id=_S["va2"])
    _S["c7"] = _card(fournisseur="Agrola", last4="6666", type_affectation="conducteur")
    _assign(_S["c7"], type="conducteur", driver_id=_S["d1"])
    _S["c8"] = _card(last4="7777")
    _assign(_S["c8"], vehicle_id=_S["va2"])
    _S["cb"] = None
    r = _req("POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": "1111", "type_affectation": "vehicule"}, ADMIN_B)
    assert r.status_code == 200, r.text
    _S["cb"] = r.json()["id"]
    _S["costs0"] = _req("GET", "/costs").json()
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


class TestUploadMappingPreview:
    def test_01_fields_and_upload_csv_creates_job_only(self):
        r = _req("GET", "/fuel/import-fields")
        assert r.status_code == 200 and {"tx_datetime", "amount_total"} == set(r.json()["required"])
        snap = _snapshot()
        r = _upload(_csv(), "migrol_juin.csv")
        assert r.status_code == 200, r.text
        job = r.json()
        _S["job"] = job["id"]
        assert job["status"] == "mapping" and job["row_count"] == len(_rows()) and job["meta"]["delimiter"] == ";"
        assert job["suggested_mapping"]["amount_total"] == "Montant TTC" and job["suggested_mapping"]["tx_datetime"] == "Date transaction"
        assert job["suggested_mapping"].get("vehicle_hint") == "Immatriculation" and job["suggested_mapping"].get("card_last4") == "Numero de carte"
        assert job["examples"]["Station"][0] == "Migrol Lausanne"
        assert _snapshot() == snap, "upload = 0 écriture métier finale"
        assert job["same_file_warning"] is None

    def test_02_mapping_missing_required_422(self):
        r = _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": {"tx_datetime": "Date transaction"}})
        assert r.status_code == 422 and "amount_total" in r.text
        r = _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": {"tx_datetime": "Date transaction", "amount_total": "Colonne inexistante"}})
        assert r.status_code == 422 and "absente" in r.text
        r = _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": {**MAPPING, "champ_inconnu": "Ref"}})
        assert r.status_code == 422

    def test_03_preview_statuses_zero_business_writes(self):
        snap = _snapshot()
        r = _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": MAPPING, "save_mapping": True})
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["status"] == "preview" and job["written_business"] == 0
        assert _snapshot() == snap, "preview = 0 écriture métier finale (seuls fuel_import_jobs/rows varient)"
        rows = _by_ref(job["rows"])
        st = {k: [x["status"] for x in v] for k, v in rows.items()}
        assert st["T1"] == ["ok", "duplicate"], st["T1"]  # 2e T1 = doublon intra-fichier
        assert rows["T1"][1]["duplicate_of"]["kind"] in ("intra_file", "intra_file_external_id")
        assert st["T2"] == ["unknown_vehicle"] and rows["T2"][0]["resolution"]["card"]["status"] == "ambiguous"
        assert len(rows["T2"][0]["resolution"]["card"]["candidates"]) == 2
        assert st["T3"] == ["unknown_vehicle"] and "CARD_INACTIVE" in rows["T3"][0]["resolution"]["vehicle"]["review_reasons"]
        assert st["T4"] == ["unknown_vehicle"] and rows["T4"][0]["resolution"]["card"]["candidates"][0]["inactive"]["inactive_by_expiration"] is True
        assert st["T5"] == ["ok"] and rows["T5"][0]["resolution"]["vehicle"]["method"] == "direct_vehicle_id" and rows["T5"][0]["resolution"]["vehicle"]["score"] == 100
        assert st["T6"] == ["unknown_vehicle"] and ["plate_candidate" in c["sources"] for c in rows["T6"][0]["resolution"]["vehicle"]["candidates"]] == [True]
        assert next(b for b in rows["T6"][0]["resolution"]["vehicle"]["candidates"][0]["breakdown"] if b["rule"] == "plate_candidate")["points"] == 0
        assert st["T7"] == ["unknown_vehicle"] and len(rows["T7"][0]["resolution"]["vehicle"]["candidates"]) == 2  # plaque ambiguë (2 véhicules)
        assert st["T8"] == ["unknown_vehicle"] and rows["T8"][0]["resolution"]["vehicle"]["candidates"] == []
        assert st["T11"] == ["ok"] and rows["T11"][0]["normalized"]["montant_chf"] == 48.5
        assert st["T12"] == ["ok"] and rows["T12"][0]["normalized"]["montant_chf"] is None and rows["T12"][0]["normalized"]["devise"] == "EUR"
        assert st["T13"] == ["invalid"] and "montant" in rows["T13"][0]["errors"][0]
        assert st["T15"] == ["amount_mismatch"]
        assert st["T20"] == ["unknown_vehicle"] and rows["T20"][0]["resolution"]["vehicle"]["candidates"][0]["sources"] == ["driver_assignment"]
        assert st["T21"] == ["unknown_vehicle"] and "FUEL_INCOMPATIBLE" in rows["T21"][0]["resolution"]["vehicle"]["review_reasons"]
        v1 = rows["T1"][0]["resolution"]["vehicle"]
        assert v1["status"] == "auto_matched" and v1["method"] == "card_assignment" and v1["score"] == 90 and v1["vehicle_id"] == _S["va1"]
        bd = v1["breakdown"][0]
        assert bd["rule"] == "card_assignment" and bd["card_unique"] is True and bd["assignment_at_date"] is True and bd["card_usable"] is True and bd["assigned_vehicle_id"] == _S["va1"]
        assert rows["T1"][0]["resolution"]["card"]["status"] == "found" and rows["T1"][0]["resolution"]["card"]["card_id"] == _S["c1"]
        assert rows["T1"][0]["normalized"]["card_last4"] == "1111" and rows["T1"][0]["normalized"]["heure"] == "08:00"
        assert rows["T1"][0]["dedup_key"] and len(rows["T1"][0]["dedup_key"]) == 64
        _S["rows"] = rows
        m = _mongo().fuel_import_mappings.find_one({"tenant_id": TENANT_A, "fournisseur": "Migrol"}, {"_id": 0})
        assert m and m["mapping"]["amount_total"] == "Montant TTC"

    def test_04_xlsx_preview_zero_business_writes(self):
        snap = _snapshot()
        r = _upload(_xlsx(), "migrol_juin.xlsx")
        assert r.status_code == 200, r.text
        jx = r.json()
        assert jx["meta"]["format"] == "xlsx" and jx["saved_mapping"]["amount_total"] == "Montant TTC"
        r = _req("POST", f"/fuel/imports/{jx['id']}/mapping", {"mapping": MAPPING})
        assert r.status_code == 200, r.text
        rows = _by_ref(r.json()["rows"])
        assert rows["T1"][0]["status"] == "ok" and rows["T1"][0]["normalized"]["montant"] == 82.0 and rows["T13"][0]["status"] == "invalid"
        assert rows["T1"][0]["normalized"]["date"] == "2026-06-01"
        assert _snapshot() == snap
        _S["job_x"] = jx["id"]

    def test_05_csv_comma_and_tab_delimiters(self):
        for d in (",", "\t"):
            r = _upload(_csv([_rows()[0]], delimiter=d), "f.csv")
            assert r.status_code == 200 and r.json()["meta"]["delimiter"] == d, r.text

    def test_06_read_only_can_view_but_not_mutate(self):
        assert _req("GET", f"/fuel/imports/{_S['job']}", creds=RO_A).status_code == 200
        assert _req("GET", f"/fuel/imports/{_S['job']}/rows", creds=RO_A).status_code == 200
        assert _upload(_csv(), "ro.csv", creds=RO_A).status_code == 403
        assert _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": MAPPING}, RO_A).status_code == 403
        assert _req("POST", f"/fuel/imports/{_S['job']}/confirm", creds=RO_A).status_code == 403
        rid = _S["rows"]["T6"][0]["id"]
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{rid}", {"vehicle_id": _S["va2"], "reason": "ro"}, RO_A).status_code == 403
        assert _req("POST", f"/fuel/imports/{_S['job']}/rows/accept-unique", {"row_ids": [rid], "reason": "ro"}, RO_A).status_code == 403
        assert _req("POST", f"/fuel/imports/{_S['job']}/rows/{rid}/force", {"reason": "ro"}, RO_A).status_code == 403

    def test_07_cross_tenant_fail_closed(self):
        assert _req("GET", f"/fuel/imports/{_S['job']}", creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/fuel/imports/{_S['job']}/confirm", creds=ADMIN_B).status_code == 404
        rid = _S["rows"]["T6"][0]["id"]
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{rid}", {"vehicle_id": _S["vb1"], "reason": "cross"}, ADMIN_B).status_code == 404
        # véhicule d'un autre tenant refusé pour une résolution manuelle (fail-closed)
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{rid}", {"vehicle_id": _S["vb1"], "reason": "cross tenant"}).status_code == 404
        # carte d'un autre tenant jamais résolue : T1 (Migrol 1111) ne doit pas voir la carte Migrol 1111 du tenant B
        assert all(c["id"] != _S["cb"] for c in _S["rows"]["T1"][0]["resolution"]["card"]["candidates"])
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{rid}", {"card_id": _S["cb"], "reason": "cross tenant carte"}).status_code == 404


class TestManualResolution:
    def test_10_plate_candidate_stays_unknown_until_human(self):
        row = _S["rows"]["T6"][0]
        assert row["status"] == "unknown_vehicle" and row["resolution"]["vehicle"]["status"] == "matched_review"
        assert row["resolution"]["vehicle"]["candidates"][0]["partial_score"] < 70 and row["resolution"]["vehicle"]["vehicle_id"] is None  # plaque = 0 point, jamais auto

    def test_11_resolve_row_requires_reason(self):
        row = _S["rows"]["T3"][0]
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{row['id']}", {"vehicle_id": _S["va2"], "reason": ""}).status_code == 422
        assert _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{row['id']}", {"reason": "sans cible"}).status_code == 422

    def test_12_resolve_row_manual_vehicle(self):
        for ref, vid in (("T3", _S["va2"]), ("T4", _S["va1"]), ("T20", _S["va3"]), ("T21", _S["va2"])):
            row = _S["rows"][ref][0]
            r = _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{row['id']}", {"vehicle_id": vid, "reason": f"Véhicule confirmé par le gestionnaire ({ref})"})
            assert r.status_code == 200, r.text
            new = r.json()["row"]
            assert new["status"] in ("ok", "unknown_card", "amount_mismatch"), new["status"]
            assert new["resolution"]["vehicle"]["status"] == "manual" and new["resolution"]["vehicle"]["vehicle_id"] == vid
            assert new["resolution"]["vehicle"]["breakdown"][0]["rule"] == "manual"
        a = list(_mongo().audit_logs.find({"tenant_id": TENANT_A, "entity": "fuel_import", "action": "row_resolve"}))
        assert len(a) >= 4 and all("motif" in x["detail"] for x in a)

    def test_13_bulk_accept_unique_eligibility_and_audit(self):
        ids = [_S["rows"][k][0]["id"] for k in ("T6", "T7", "T8", "T2", "T1")]
        assert _req("POST", f"/fuel/imports/{_S['job']}/rows/accept-unique", {"row_ids": ids, "reason": ""}).status_code == 422
        n_audit = _mongo().audit_logs.count_documents({"tenant_id": TENANT_A, "entity": "fuel_import", "action": "row_resolve"})
        r = _req("POST", f"/fuel/imports/{_S['job']}/rows/accept-unique", {"row_ids": ids, "reason": "Plaques vérifiées sur le relevé fournisseur"})
        assert r.status_code == 200, r.text
        out = r.json()
        acc = {a["row_id"] for a in out["accepted"]}
        ref = {x["row_id"]: x["reason"] for x in out["refused"]}
        assert acc == {_S["rows"]["T6"][0]["id"]}, out
        assert "2 candidat" in ref[_S["rows"]["T7"][0]["id"]]  # plaque ambiguë exclue
        assert "0 candidat" in ref[_S["rows"]["T8"][0]["id"]]  # 0 candidat exclue
        assert "2 candidat" in ref[_S["rows"]["T2"][0]["id"]]  # carte ambiguë → 2 candidats véhicule, exclue
        assert "statut ok" in ref[_S["rows"]["T1"][0]["id"]]  # déjà résolue, exclue
        assert out["accepted"][0]["plaque_source"] == PL["va2"] and out["accepted"][0]["vehicle_id"] == _S["va2"]
        assert _mongo().audit_logs.count_documents({"tenant_id": TENANT_A, "entity": "fuel_import", "action": "row_resolve"}) == n_audit + 1
        a = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_import", "action": "row_resolve", "detail": {"$regex": out["batch_id"]}})
        assert a and "décision humaine" in a["detail"] and "motif" in a["detail"] and PL["va2"] in a["detail"]
        row = _req("GET", f"/fuel/imports/{_S['job']}/rows").json()["items"]
        t6 = next(x for x in row if x["id"] == _S["rows"]["T6"][0]["id"])
        assert t6["status"] == "ok" and t6["resolution"]["vehicle"]["status"] == "manual" and t6["resolution"]["vehicle"]["breakdown"][0]["provenance"] == "plate_candidate"
        assert t6["resolution"]["vehicle"]["breakdown"][0]["batch_id"] == out["batch_id"]

    def test_14_bulk_fail_closed_if_candidate_vanished(self):
        """Modification concurrente : le candidat unique est supprimé entre preview et confirmation → ligne refusée, rien d'écrit."""
        r = _req("POST", "/vehicles", {"plaque": f"TI {P} 77", "kilometrage": 10})
        vid = r.json()["id"]
        r = _upload(_csv([["X1", "06.06.2026 08:00", "", f"TI {P} 77", "", "20.00", "CHF", "", "10", "2.00", "S", "", "Diesel"]]), "x.csv")
        jid = r.json()["id"]
        rows = _req("POST", f"/fuel/imports/{jid}/mapping", {"mapping": MAPPING}).json()["rows"]
        assert rows[0]["status"] == "unknown_vehicle" and rows[0]["resolution"]["vehicle"]["candidates"][0]["vehicle_id"] == vid
        _mongo().vehicles.delete_one({"tenant_id": TENANT_A, "id": vid})
        r = _req("POST", f"/fuel/imports/{jid}/rows/accept-unique", {"row_ids": [rows[0]["id"]], "reason": "test concurrence"})
        assert r.status_code == 200 and r.json()["accepted"] == [] and "fail-closed" in r.json()["refused"][0]["reason"]
        assert _req("GET", f"/fuel/imports/{jid}/rows").json()["items"][0]["status"] == "unknown_vehicle"


class TestConfirm:
    def test_20_confirm_imports_and_sets_aside(self):
        db = _mongo()
        before = {c: db[c].count_documents({"tenant_id": TENANT_A}) for c in ("documents", "fuel_transactions")}
        r = _req("POST", f"/fuel/imports/{_S['job']}/confirm")
        assert r.status_code == 200, r.text
        out = r.json()
        # importables : T1 ok, T2 unknown_card (véhicule résolu ? non → T2 reste unknown_vehicle), T3, T4, T5, T6, T11, T12, T15, T16, T17, T18, T20, T21, T22
        assert out["status"] == "confirmed" and out["imported"] == 14, out
        assert out["set_aside"] == {"duplicate": 1, "unknown_vehicle": 3, "invalid": 1}, out["set_aside"]  # T1bis, (T2, T7, T8), T13
        assert db.documents.count_documents({"tenant_id": TENANT_A}) == before["documents"] + 14
        assert db.fuel_transactions.count_documents({"tenant_id": TENANT_A}) == before["fuel_transactions"] + 14
        _S["confirm"] = out
        rows = _by_ref(_req("GET", f"/fuel/imports/{_S['job']}/rows").json()["items"])
        _S["rows"] = rows
        assert rows["T1"][0]["imported"] is True and rows["T1"][0]["transaction_id"] and rows["T1"][0]["document_id"]
        assert rows["T13"][0]["imported"] is False and rows["T2"][0]["imported"] is False
        job = _req("GET", f"/fuel/imports/{_S['job']}").json()
        assert job["status"] == "confirmed" and job["imported_count"] == 14 and job["confirmed_at"]

    def test_21_confirm_is_idempotent(self):
        db = _mongo()
        n_tx, n_doc = db.fuel_transactions.count_documents({"tenant_id": TENANT_A}), db.documents.count_documents({"tenant_id": TENANT_A})
        r = _req("POST", f"/fuel/imports/{_S['job']}/confirm")
        assert r.status_code == 200 and r.json()["imported"] == 0 and r.json()["already_imported"] == 14
        assert db.fuel_transactions.count_documents({"tenant_id": TENANT_A}) == n_tx and db.documents.count_documents({"tenant_id": TENANT_A}) == n_doc
        assert _req("POST", f"/fuel/imports/{_S['job']}/mapping", {"mapping": MAPPING}).status_code == 409  # mapping figé

    def test_22_reimport_same_file_all_duplicates(self):
        r = _upload(_csv(), "migrol_juin.csv")
        assert r.status_code == 200 and r.json()["same_file_warning"] and r.json()["same_file_warning"][0]["job_id"] == _S["job"]
        jid = r.json()["id"]
        rows = _by_ref(_req("POST", f"/fuel/imports/{jid}/mapping", {"mapping": MAPPING}).json()["rows"])
        for ref in ("T1", "T3", "T5", "T11", "T12", "T15", "T22"):
            assert rows[ref][0]["status"] == "duplicate", (ref, rows[ref][0]["status"])
        assert rows["T1"][0]["duplicate_of"]["kind"] == "external_id" and rows["T1"][0]["duplicate_of"]["id"] == _S["rows"]["T1"][0]["transaction_id"]
        n_tx = _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A})
        r = _req("POST", f"/fuel/imports/{jid}/confirm")
        assert r.status_code == 200 and r.json()["imported"] == 0, r.text
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A}) == n_tx, "ré-import = 0 doublon"
        _S["job2"] = jid
        _S["rows2"] = rows

    def test_23_dedup_key_without_external_id(self):
        rows = [["", "07.06.2026 08:00", "1111", "", "", "70.00", "CHF", "", "35", "2.00", "Migrol Lausanne", "", "Diesel"]]
        jid = _upload(_csv(rows), "noref.csv").json()["id"]
        m = {k: v for k, v in MAPPING.items() if k != "external_transaction_id"}
        assert _req("POST", f"/fuel/imports/{jid}/mapping", {"mapping": m}).json()["rows"][0]["status"] == "ok"
        assert _req("POST", f"/fuel/imports/{jid}/confirm").json()["imported"] == 1
        jid2 = _upload(_csv(rows), "noref2.csv").json()["id"]
        row = _req("POST", f"/fuel/imports/{jid2}/mapping", {"mapping": m}).json()["rows"][0]
        assert row["status"] == "duplicate" and row["duplicate_of"]["kind"] == "dedup_key"

    def test_24_force_duplicate_with_reason(self):
        dup = _S["rows2"]["T1"][0]
        assert _req("POST", f"/fuel/imports/{_S['job2']}/rows/{dup['id']}/force", {"reason": ""}).status_code == 422
        ok_row = _S["rows2"]["T13"][0]
        assert _req("POST", f"/fuel/imports/{_S['job2']}/rows/{ok_row['id']}/force", {"reason": "invalide non forçable"}).status_code == 409
        r = _req("POST", f"/fuel/imports/{_S['job2']}/rows/{dup['id']}/force", {"reason": "Deux pleins identiques réels le même jour (confirmé par le conducteur)"})
        assert r.status_code == 200, r.text
        tx = _mongo().fuel_transactions.find_one({"tenant_id": TENANT_A, "id": r.json()["transaction_id"]}, {"_id": 0})
        assert tx["forced_duplicate_of"] == _S["rows"]["T1"][0]["transaction_id"] and tx["external_transaction_id"] == "T1#dup-1" and tx["forced_reason"]
        assert _req("POST", f"/fuel/imports/{_S['job2']}/rows/{dup['id']}/force", {"reason": "encore"}).status_code == 409  # déjà importée
        a = _mongo().audit_logs.find_one({"tenant_id": TENANT_A, "entity": "fuel_import", "action": "force"})
        assert a and "FORCÉE" in a["detail"]

    def test_25_confirm_requires_mapping(self):
        jid = _upload(_csv([_rows()[0]]), "nomap.csv").json()["id"]
        assert _req("POST", f"/fuel/imports/{jid}/confirm").status_code == 409


class TestResultingData:
    def _tx(self, ref):
        return _mongo().fuel_transactions.find_one({"tenant_id": TENANT_A, "id": _S["rows"][ref][0]["transaction_id"]}, {"_id": 0})

    def test_30_card_id_only_when_found(self):
        assert self._tx("T1")["card_id"] == _S["c1"] and self._tx("T1")["card_resolution"]["status"] == "found"
        assert self._tx("T5")["card_id"] == _S["c6"]
        assert self._tx("T6")["card_id"] is None and self._tx("T6")["card_resolution"]["status"] == "none"
        t2 = _S["rows"]["T2"][0]
        assert t2["imported"] is False and t2["resolution"]["card"]["status"] == "ambiguous" and t2["resolution"]["card"]["card_id"] is None
        # resolve T2 manuellement (véhicule) puis importer : carte reste null (ambiguë, jamais choisie automatiquement)
        r = _req("PATCH", f"/fuel/imports/{_S['job']}/rows/{t2['id']}", {"vehicle_id": _S["va1"], "reason": "Véhicule confirmé"})
        assert r.status_code == 200 and r.json()["row"]["status"] == "unknown_card"
        r = _req("POST", f"/fuel/imports/{_S['job']}/confirm")
        assert r.status_code == 200 and r.json()["imported"] == 1
        tx = _mongo().fuel_transactions.find_one({"tenant_id": TENANT_A, "external_transaction_id": "T2"}, {"_id": 0})
        assert tx["card_id"] is None and tx["card_resolution"]["status"] == "ambiguous" and len(tx["card_resolution"]["candidates"]) == 2
        _S["tx_t2"] = tx["id"]

    def test_31_vehicle_matching_results(self):
        assert self._tx("T1")["vehicle_id"] == _S["va1"] and self._tx("T1")["match_status"] == "auto_matched" and self._tx("T1")["match_method"] == "card_assignment"
        assert self._tx("T5")["vehicle_id"] == _S["va1"] and self._tx("T5")["match_method"] == "direct_vehicle_id"
        assert self._tx("T6")["vehicle_id"] == _S["va2"] and self._tx("T6")["match_status"] == "manual"
        m = _mongo().fuel_transaction_matches.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T1")["id"]}, {"_id": 0})
        assert m and m["score"] == 90 and m["history"][0]["by"] == "auto"

    def test_32_card_warnings_and_anomalies(self):
        an = _mongo().fuel_anomalies
        t3 = an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T3")["id"], "type": "carte_inactive"}, {"_id": 0})
        assert t3 and t3["severity"] == "critical" and t3["context"]["inactive_by_status"] is True and t3["context"]["evaluation_model"] == "current_status_tx_date_expiration"
        t4 = an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T4")["id"], "type": "carte_inactive"}, {"_id": 0})
        assert t4 and t4["context"]["inactive_by_expiration"] is True and t4["context"]["inactive_by_status"] is False
        t5 = an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T5")["id"], "type": "carte_vehicule_different"}, {"_id": 0})
        assert t5 and t5["context"]["card_assigned_vehicle_ids"] == [_S["va2"]] and t5["context"]["auto_correction"] is False
        assert self._tx("T5")["vehicle_id"] == _S["va1"], "aucune substitution silencieuse de vehicle_id"
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T5")["id"], "type": "plaque_differente"})
        codes = {w["code"] for w in _S["confirm"]["warnings"]}
        assert {"CARD_INACTIVE", "CARD_VEHICLE_MISMATCH"} <= codes
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T15")["id"], "type": "incoherence_montant"})
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T16")["id"], "type": "depassement_reservoir", "severity": "critical"})
        d = an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T17")["id"], "type": "double_plein"}, {"_id": 0})
        assert d and d["related_transaction_id"] == self._tx("T1")["id"]
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T18")["id"], "type": "odometre_incoherent"})
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T22")["id"], "type": "montant_inhabituel"})
        assert an.find_one({"tenant_id": TENANT_A, "transaction_id": self._tx("T1")["id"], "type": "carte_inactive"}) is None

    def test_33_nofile_document_one_tx_and_d7_costs(self):
        db = _mongo()
        for ref in ("T1", "T11", "T12"):
            tx = self._tx(ref)
            doc = db.documents.find_one({"tenant_id": TENANT_A, "id": tx["source_document_id"]}, {"_id": 0})
            assert doc["justificatif_absent"] is True and doc["storage_path"] is None and doc["source"] == "import" and doc["document_type"] == "ticket_carburant"
            assert db.fuel_transactions.count_documents({"tenant_id": TENANT_A, "source_document_id": doc["id"]}) == 1
            assert doc["import_job_id"] == _S["job"]
            assert _req("GET", f"/documents/{doc['id']}/history").status_code == 200
            assert _req("GET", f"/documents/{doc['id']}/extraction").status_code < 500  # endpoints fichier : jamais d'erreur technique
        costs = _req("GET", "/costs").json()
        items = {i["document_id"]: i for i in costs["items"]}
        d1, d11, d12 = (self._tx(r)["source_document_id"] for r in ("T1", "T11", "T12"))
        assert items[d1]["montant"] == 82.0 and items[d1].get("devise") == "CHF"
        assert d11 in items and items[d11]["montant"] == 48.5 and items[d11]["montant_origine"] == 50.0 and items[d11]["devise_origine"] == "EUR"
        assert d12 not in items and any(p["document_id"] == d12 for p in costs["pending_fx"]), "EUR sans montant_chf = pending_fx, exclu du total"
        tx12 = self._tx("T12")
        assert tx12["fx_status"] == "pending" and self._tx("T11")["fx_status"] == "converted" and self._tx("T1")["fx_status"] == "not_needed"
        # anti double comptage : total = Σ documents (jamais fuel_transactions)
        tot = sum(i["montant"] for i in costs["items"] if i["source"] == "document")
        docs_sum = 0.0
        for d in db.documents.find({"tenant_id": TENANT_A, "is_deleted": False, "montant": {"$gt": 0}}, {"_id": 0, "montant": 1, "devise": 1, "montant_chf": 1}):
            if d.get("devise", "CHF") == "CHF":
                docs_sum += d["montant"]
            elif d.get("montant_chf") is not None:
                docs_sum += d["montant_chf"]
        assert round(tot, 2) == round(docs_sum, 2)

    def test_34_energy_and_detail_endpoints(self):
        e = _req("GET", "/energy").json()
        tx1 = next(x for x in e["transactions"] if x["id"] == self._tx("T1")["id"])
        assert tx1["anomalies_open"] >= 0 and tx1["match_label"] == "Rattaché automatiquement" and tx1["created_from"] == "import"
        assert e["totals"]["anomalies_ouvertes"] >= 7
        d = _req("GET", f"/fuel-transactions/{self._tx('T5')['id']}").json()
        assert d["card"]["id"] == _S["c6"] and d["match"]["method"] == "direct_vehicle_id" and any(a["type"] == "carte_vehicule_different" for a in d["anomalies"])
        assert d["document"]["cost"]["montant"] == 61.5 and d["plaque"] == PL["va1"]
        assert _req("GET", f"/fuel-transactions/{self._tx('T5')['id']}", creds=ADMIN_B).status_code == 404

    def test_35_no_impact_fines_and_other_lots(self):
        assert _req("GET", "/fines").json()["total"] == _S["fines0"]
        assert _req("GET", "/fuel-cards").json()["stats"]["total"] == 8
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_B}) == 0
        assert _mongo().documents.count_documents({"tenant_id": TENANT_B}) == 0
        assert _mongo().fuel_anomalies.count_documents({"tenant_id": TENANT_B}) == 0
        assert _req("GET", "/fuel/imports", creds=ADMIN_B).json()["total"] == 0
