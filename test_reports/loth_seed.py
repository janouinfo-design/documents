"""Lot H — tenant UI isolé `loth-ui-test` (jamais `default`, aucune donnée Journal) : baseline / seed / inventory / verify.
Rôles : admin · read_only · manager (scope [V1, V2]) · manager vide (scope []) · driver lié (D1) · driver non lié · driver inactif · driver sans affectation.
Preuves SÉPARÉES : TENANT_ISOLATION · MANAGER_SCOPE_ISOLATION · DRIVER_SELF_SCOPE_ISOLATION · MANAGER_SCOPE_REVOCATION · DRIVER_LINK_REVOCATION ·
EXPORT_SCOPE_ISOLATION · KPI_SCOPE_ISOLATION. Chaque preuve = requêtes API réelles (jamais un masquage UI).
Usage : python3 test_reports/loth_seed.py baseline | seed | inventory | verify | all   (jamais de cleanup — GO séparé requis)
Mots de passe : variables LOTH_PASSWORD_<ROLE> (ADMIN, RO, MANAGER, MANAGER_EMPTY, DRIVER, DRIVER_UNLINKED, DRIVER_INACTIVE, DRIVER_NOASSIGN) ou générés.
Écritures : tenant cible uniquement (guard sur chaque write DB) ; API via comptes du tenant ou superadmin (console)."""
import hashlib
import io
import json
import os
import secrets
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
T = "loth-ui-test"
REP = Path("/app/test_reports")
BASELINE, RESULT, INVENTORY, VERIFY_OUT = REP / "loth_baseline_before_seed.json", REP / "loth_seed_result.json", REP / "loth_inventory.json", REP / "loth_verify.json"
ACCOUNTS = {"ADMIN": ("loth-admin", "admin"), "RO": ("loth-ro", "read_only"), "MANAGER": ("loth-manager", "manager"), "MANAGER_EMPTY": ("loth-manager-vide", "manager"),
            "DRIVER": ("loth-driver", "driver"), "DRIVER_UNLINKED": ("loth-driver-nonlie", "driver"), "DRIVER_INACTIVE": ("loth-driver-inactif", "driver"),
            "DRIVER_NOASSIGN": ("loth-driver-sans", "driver")}
EMAIL = {k: f"{v[0]}@{T}.ch" for k, v in ACCOUNTS.items()}
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
PERIOD = TODAY.strftime("%Y-%m")
VOLATILE = {"vehicles": ("updated_at", "kilometrage", "conso_moyenne_l_100km", "conso_source", "conso_updated_at")}
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")
PASS, FAIL = "PASS", "FAIL"
FAMILIES = ("TENANT_ISOLATION", "MANAGER_SCOPE_ISOLATION", "DRIVER_SELF_SCOPE_ISOLATION", "MANAGER_SCOPE_REVOCATION", "DRIVER_LINK_REVOCATION",
            "EXPORT_SCOPE_ISOLATION", "KPI_SCOPE_ISOLATION")


def die(msg):
    print(f"FAIL-FAST : {msg}")
    sys.exit(2)


def guard(tenant):
    if tenant != T:
        die(f"écriture hors tenant cible refusée ({tenant})")


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        die(f"login {email} → {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def sa_headers():
    return login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])


def api(h, method, path, body=None, **kw):
    return requests.request(method, f"{BASE}/api{path}", json=body, headers=h, timeout=120, **kw)


def ok(r, *codes):
    if r.status_code not in (codes or (200,)):
        die(f"{r.request.method} {r.url} → {r.status_code} {r.text[:300]}")
    return r.json() if r.content else None


def load_result():
    return json.loads(RESULT.read_text()) if RESULT.exists() else {"tenant": T, "ids": {}, "checks": [], "notes": []}


def save_result(res):
    RESULT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))


def chk(res, family, name, passed, detail=""):
    res["checks"] = [c for c in res["checks"] if not (c["family"] == family and c["check"] == name)]
    res["checks"].append({"family": family, "check": name, "result": PASS if passed else FAIL, "detail": str(detail)[:400]})
    print(f"[{PASS if passed else FAIL}] {family} · {name}{' — ' + str(detail)[:160] if detail else ''}")
    return passed


# --- baseline / fingerprint --------------------------------------------------------------------------------------------
def fingerprint():
    fp = {"counts": {}, "hashes": {}}
    for c in sorted(x for x in db.list_collection_names() if not x.startswith("system.") and x != "login_attempts"):
        key = "id" if c == "tenants" else "tenant_id"
        for t in sorted(str(x) for x in db[c].distinct(key, {key: {"$ne": T}})):
            h, n = hashlib.sha256(), 0
            for d in db[c].find({key: t}, {"_id": 0}).sort("id", 1):
                n += 1
                d = {k: v for k, v in d.items() if k not in VOLATILE.get(c, ()) and not k.startswith("navixy_")}
                h.update(json.dumps(d, sort_keys=True, default=str).encode())
            fp["counts"][f"{c}|{t}"], fp["hashes"][f"{c}|{t}"] = n, h.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": T}}, {"_id": 0, "id": 1}))
    return fp


def baseline():
    if BASELINE.exists():
        print("BASELINE déjà présente (conservée, capturée avant le premier seed) :", BASELINE)
        return
    BASELINE.write_text(json.dumps(fingerprint(), indent=1))
    print("BASELINE écrite", BASELINE)


# --- seed helpers ----------------------------------------------------------------------------------------------------
def ensure_tenant_and_users(res, ids):
    sa = sa_headers()
    ok(api(sa, "POST", "/admin/tenants", {"name": "Lot H UI test (synthétique)", "id": T}), 200, 409)
    users = {u["email"]: u for u in ok(api(sa, "GET", f"/admin/tenants/{T}/users"))}
    pw = {}
    for key, (_, role) in ACCOUNTS.items():
        email = EMAIL[key]
        env = f"LOTH_PASSWORD_{key}"
        pw[key] = os.environ.get(env) or f"LotH-{role}-{secrets.token_hex(4)}"
        if email not in users:
            body = {"email": email, "password": pw[key], "role": role, "name": f"Lot H {key.lower().replace('_', ' ')}"}
            if role == "manager":
                body["vehicle_scope"] = []
            users[email] = ok(api(sa, "POST", f"/admin/tenants/{T}/users", body))
        elif not os.environ.get(env):
            ok(api(sa, "PUT", f"/admin/users/{users[email]['id']}", {"password": pw[key]}))
            res["notes"].append(f"re-seed : mot de passe {key} réinitialisé via superadmin")
        ids[f"user_{key}"] = users[email]["id"]
    print("TENANT=" + T)
    for key in ACCOUNTS:
        print(f"{key}_LOGIN={EMAIL[key]}\n{key}_PASSWORD={pw[key]}")
    return sa, pw


def ensure_vehicle(h, key, body, ids):
    guard(T)
    cur = db.vehicles.find_one({"tenant_id": T, "plaque": body["plaque"]}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", "/vehicles", body))["id"]


def ensure_driver(h, key, body, ids):
    cur = db.drivers.find_one({"tenant_id": T, "matricule_interne": body["matricule_interne"]}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", "/drivers", body))["id"]


def ensure_assignment(h, key, vid, did, valid_from, valid_to=None, principal=True, ids=None):
    cur = db.driver_assignments.find_one({"tenant_id": T, "vehicle_id": vid, "driver_id": did, "valid_from": valid_from}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", f"/vehicles/{vid}/driver-assignments", {"driver_id": did, "valid_from": valid_from, "valid_to": valid_to, "principal": principal}))["id"]


def ensure_plein(h, ids, key, vid, day, montant, litres, station, driver_id=None, **over):
    cur = db.fuel_transactions.find_one({"tenant_id": T, "vehicle_id": vid, "date": day, "montant": montant, "is_deleted": False}, {"_id": 0, "id": 1, "source_document_id": 1})
    if cur:
        ids[key], ids[f"{key}_doc"] = cur["id"], cur.get("source_document_id")
        return
    body = {"date": day, "heure": over.pop("heure", "08:00"), "station": station, "montant": montant, "litres": litres, "prix_litre": round(montant / litres, 3),
            "business_category": "CARBURANT", "motif": f"LOTH:{key}", **({"driver_id": driver_id} if driver_id else {}), **over}
    r = ok(api(h, "POST", f"/vehicles/{vid}/fuel-transactions", body))
    ids[key], ids[f"{key}_doc"] = r["fuel_transaction"]["id"], r["document_id"]


def ensure_fine(h, ids, key, vid, numero, driver_id, notes, montant=120.0, delai=20):
    cur = db.documents.find_one({"tenant_id": T, "numero": numero, "is_deleted": False}, {"_id": 0, "id": 1})
    if cur:
        ids[key] = cur["id"]
        return
    r = ok(api(h, "POST", f"/vehicles/{vid}/fines", {"autorite": "Police cantonale VD", "numero_amende": numero, "date_infraction": D(-8), "montant": montant,
                                                       "delai_paiement": D(delai), "motif": f"LOTH:{key}", "driver_id": driver_id, "notes_internes": notes,
                                                       "dossier_interne": f"DOSSIER-{numero}", "type_infraction": "speeding", "lieu_infraction": {"lieu": "av. de Rhodanie", "ville": "Lausanne", "canton": "VD"}}))
    ids[key] = r["document_id"]


def ensure_card(h, ids, key, last4, assigns):
    cur = db.fuel_cards.find_one({"tenant_id": T, "last4": last4}, {"_id": 0, "id": 1})
    cid = cur["id"] if cur else ok(api(h, "POST", "/fuel-cards", {"fournisseur": "Migrol", "last4": last4, "expire_le": D(400)}))["id"]
    ids[key] = cid
    for vid, vf, vt in assigns:
        if not db.fuel_card_assignments.find_one({"tenant_id": T, "card_id": cid, "vehicle_id": vid}):
            ok(api(h, "POST", f"/fuel-cards/{cid}/assignments", {"type": "vehicule", "vehicle_id": vid, "valid_from": vf, "valid_to": vt}))
    return cid


def ensure_doc_upload(h, ids, key, vid, filename):
    cur = db.documents.find_one({"tenant_id": T, "vehicle_id": vid, "original_filename": filename, "is_deleted": False}, {"_id": 0, "id": 1, "storage_path": 1})
    if cur:
        ids[key], ids[f"{key}_path"] = cur["id"], cur["storage_path"]
        return
    r = requests.post(f"{BASE}/api/vehicles/{vid}/documents", files={"file": (filename, io.BytesIO(PNG), "image/png")}, data={"folder": "Divers"}, headers=h, timeout=60)
    j = ok(r)
    ids[key], ids[f"{key}_path"] = j["id"], j["storage_path"]


def ensure_anomaly(ids, key, vid, txid):
    guard(T)
    cur = db.fuel_anomalies.find_one({"tenant_id": T, "transaction_id": txid, "type": "DUPLICATE_SUSPECTED"}, {"_id": 0, "id": 1})
    if cur:
        ids[key] = cur["id"]
        return
    ids[key] = str(uuid.uuid4())
    db.fuel_anomalies.insert_one({"id": ids[key], "tenant_id": T, "vehicle_id": vid, "transaction_id": txid, "type": "DUPLICATE_SUSPECTED", "severity": "warning",
                                  "status": "ouverte", "detected_at": D(-1), "detail": "Lot H — anomalie synthétique (scope)", "history": []})


def ensure_inspection(h, ids, key, vid):
    rows = ok(api(h, "GET", f"/vehicles/{vid}/inspections"))
    if rows:
        ids[key] = rows[0]["id"]
        return
    ids[key] = ok(api(h, "POST", f"/vehicles/{vid}/inspections", {"date": D(-2), "type": "depart", "notes": "État des lieux Lot H (admin)", "photos": []}))["id"]


# --- preuves ---------------------------------------------------------------------------------------------------------
def code_of(r):
    try:
        d = r.json().get("detail")
        return d.get("code") if isinstance(d, dict) else None
    except Exception:
        return None


def prove(res, ids, H):
    """H = headers par rôle. Toutes les preuves relisent le SERVEUR (aucune UI)."""
    v1, v2, v3, v4 = ids["v1"], ids["v2"], ids["v3"], ids["v4"]
    hA, hRO, hM, hME, hD, hDU, hDI, hDN = (H[k] for k in ("ADMIN", "RO", "MANAGER", "MANAGER_EMPTY", "DRIVER", "DRIVER_UNLINKED", "DRIVER_INACTIVE", "DRIVER_NOASSIGN"))
    F = "TENANT_ISOLATION"
    foreign = (db.vehicles.find_one({"tenant_id": "default"}, {"_id": 0, "id": 1}) or {}).get("id") or str(uuid.uuid4())
    ids["foreign_vehicle_default"] = foreign
    probes = {"admin_vehicle_default": api(hA, "GET", f"/vehicles/{foreign}").status_code, "manager_vehicle_default": api(hM, "GET", f"/vehicles/{foreign}").status_code,
              "manager_documents_default": api(hM, "GET", f"/vehicles/{foreign}/documents").status_code, "admin_energy_default": api(hA, "GET", f"/vehicles/{foreign}/energy").status_code,
              "driver_vehicle_default": api(hD, "GET", f"/vehicles/{foreign}").status_code}
    chk(res, F, "véhicule d'un autre tenant (default) → 404 admin / manager, 403 driver", probes["admin_vehicle_default"] == probes["manager_vehicle_default"] == probes["manager_documents_default"]
        == probes["admin_energy_default"] == 404 and probes["driver_vehicle_default"] == 403, probes)
    own_v = {x["id"] for x in db.vehicles.find({"tenant_id": T}, {"_id": 0, "id": 1})}
    tx_v = {x.get("vehicle_id") for x in db.fuel_transactions.find({"tenant_id": T}, {"_id": 0, "vehicle_id": 1})}
    doc_v = {x.get("vehicle_id") for x in db.documents.find({"tenant_id": T, "vehicle_id": {"$ne": None}}, {"_id": 0, "vehicle_id": 1})}
    chk(res, F, "toutes les transactions / documents du tenant référencent des véhicules du tenant", tx_v <= own_v and doc_v <= own_v, f"tx={len(tx_v)} docs={len(doc_v)} vehicules={len(own_v)}")
    lst = [x["id"] for x in ok(api(hA, "GET", "/vehicles"))]
    chk(res, F, "admin : liste véhicules = tenant complet (4) sans fuite", sorted(lst) == sorted(own_v) and len(lst) == 4, lst)

    F = "MANAGER_SCOPE_ISOLATION"
    me = ok(api(hM, "GET", "/auth/me"))
    chk(res, F, "auth/me manager : rôle + vehicle_scope [V1, V2]", me["role"] == "manager" and sorted(me["vehicle_scope"]) == sorted([v1, v2]), me.get("vehicle_scope"))
    lst = sorted(x["id"] for x in ok(api(hM, "GET", "/vehicles")))
    chk(res, F, "liste véhicules manager = exactement [V1, V2]", lst == sorted([v1, v2]), lst)
    direct = {"vehicle": api(hM, "GET", f"/vehicles/{v3}").status_code, "documents": api(hM, "GET", f"/vehicles/{v3}/documents").status_code,
              "inspections": api(hM, "GET", f"/vehicles/{v3}/inspections").status_code, "energy": api(hM, "GET", f"/vehicles/{v3}/energy").status_code,
              "fine": api(hM, "GET", f"/fines/{ids['fine_v3']}").status_code, "transaction": api(hM, "GET", f"/fuel-transactions/{ids['tx_v3_d2']}").status_code,
              "anomaly": api(hM, "GET", f"/fuel/anomalies/{ids['anomaly_out']}").status_code,
              "reconciliation": api(hM, "GET", "/fuel/reconciliations", params={"period_month": PERIOD, "vehicle_id": v3}).status_code,
              "document_patch": api(hM, "PATCH", f"/documents/{ids['doc_v3']}", {"notes": "x"}).status_code,
              "document_history": api(hM, "GET", f"/documents/{ids['doc_v3']}/history").status_code,
              "assignment_close": api(hM, "POST", f"/driver-assignments/{ids['a_d2_v3']}/close", {"motif": "hors scope"}).status_code,
              "assignments_list": api(hM, "GET", f"/vehicles/{v3}/driver-assignments").status_code,
              "fine_status": api(hM, "POST", f"/documents/{ids['fine_v3']}/fine-status", {"fine_status": "contestee"}).status_code,
              "file": api(hM, "GET", f"/files/{ids['doc_v3_path']}").status_code, "export_vehicle_pdf": api(hM, "GET", f"/reports/vehicule/{v3}.pdf").status_code,
              "vehicle_update": api(hM, "PUT", f"/vehicles/{v3}", {"modele": "x"}).status_code,
              "inspection_create": api(hM, "POST", f"/vehicles/{v3}/inspections", {"date": D(0), "type": "depart", "notes": "x", "photos": []}).status_code,
              "fuel_manual": api(hM, "POST", f"/vehicles/{v3}/fuel-transactions", {"date": D(0), "montant": 10, "litres": 5, "business_category": "CARBURANT", "motif": "x"}).status_code,
              "card_out": api(hM, "GET", f"/fuel-cards/{ids['card_out']}").status_code}
    chk(res, F, "accès DIRECT par ID hors scope (V3) → 404 fail-closed sur 19 familles", all(c == 404 for c in direct.values()), direct)
    in_scope = {"vehicle": api(hM, "GET", f"/vehicles/{v1}").status_code, "fine": api(hM, "GET", f"/fines/{ids['fine_v1']}").status_code,
                "transaction": api(hM, "GET", f"/fuel-transactions/{ids['tx_v1_d1']}").status_code, "anomaly": api(hM, "GET", f"/fuel/anomalies/{ids['anomaly_in']}").status_code,
                "file": api(hM, "GET", f"/files/{ids['doc_v1_path']}").status_code, "inspections": api(hM, "GET", f"/vehicles/{v1}/inspections").status_code}
    chk(res, F, "accès DIRECT par ID dans le scope (V1) → 200", all(c == 200 for c in in_scope.values()), in_scope)
    forbidden = {"vehicle_create": api(hM, "POST", "/vehicles", {"plaque": "LOTH-NEW", "marque": "X", "modele": "Y"}).status_code,
                 "vehicle_delete": api(hM, "DELETE", f"/vehicles/{v1}").status_code, "photo_delete": api(hM, "DELETE", f"/vehicles/{v1}/photo").status_code,
                 "document_delete": api(hM, "DELETE", f"/documents/{ids['doc_v1']}").status_code, "inspection_delete": api(hM, "DELETE", f"/inspections/{ids['insp_v1']}").status_code,
                 "archive_list": api(hM, "GET", "/vehicles-archive").status_code, "statements": api(hM, "GET", "/fuel/statements").status_code,
                 "imports": api(hM, "GET", "/fuel/imports").status_code, "settings_fuel": api(hM, "GET", "/tenant-settings/fuel").status_code,
                 "card_create": api(hM, "POST", "/fuel-cards", {"fournisseur": "Shell", "last4": "9999"}).status_code, "card_history": api(hM, "GET", f"/fuel-cards/{ids['card_in']}/history").status_code,
                 "driver_create": api(hM, "POST", "/drivers", {"nom": "X", "prenom": "Y"}).status_code, "navixy_sync": api(hM, "POST", "/navixy/sync").status_code,
                 "alerts_log": api(hM, "GET", "/alerts/log").status_code, "alerts_run": api(hM, "POST", "/alerts/run").status_code,
                 "legacy": api(hM, "GET", "/legacy/vehicle-map").status_code, "console": api(hM, "GET", "/admin/overview").status_code,
                 "deadline_settings": api(hM, "PUT", "/settings/deadlines", {"urgent_days": 1, "warning_days": 2}).status_code}
    chk(res, F, "fonctions interdites au manager (création / suppressions / archives / décomptes / imports / cartes / paramètres / intégrations / console) → 403", all(c == 403 for c in forbidden.values()), forbidden)
    allowed = {"vehicle_update": api(hM, "PUT", f"/vehicles/{v1}", {"modele": "Octavia Combi (manager)"}).status_code,
               "document_patch": api(hM, "PATCH", f"/documents/{ids['tx_v1_d1_doc']}", {"notes": "note manager Lot H"}).status_code,
               "fine_status": api(hM, "POST", f"/documents/{ids['fine_v1']}/fine-status", {"fine_status": "contestee", "motif": "contestation déposée par le manager"}).status_code}
    if ids.get("insp_v2_manager"):
        allowed["inspection_create_v2"] = 200  # déjà créée lors d'un seed précédent (idempotent)
    else:
        insp = api(hM, "POST", f"/vehicles/{v2}/inspections", {"date": D(0), "type": "depart", "notes": "inspection manager Lot H", "photos": []})
        allowed["inspection_create_v2"] = insp.status_code
        if insp.status_code == 200:
            ids["insp_v2_manager"] = insp.json()["id"]
    chk(res, F, "mutations autorisées au manager DANS le scope (fiche, document, statut amende, inspection) → 200", all(c == 200 for c in allowed.values()), allowed)
    au = list(db.audit_logs.find({"tenant_id": T, "role": "manager"}, {"_id": 0, "action": 1, "entity": 1, "vehicle_id": 1, "role": 1, "user": 1}))
    chk(res, F, "audit des mutations manager : role=manager + vehicle_id ∈ scope, aucun véhicule hors scope", bool(au) and all(a.get("vehicle_id") in (v1, v2, None) for a in au)
        and any(a.get("vehicle_id") in (v1, v2) for a in au), f"{len(au)} audit(s) manager")
    f1 = ok(api(hM, "GET", f"/fines/{ids['fine_v1']}"))
    chk(res, F, "notes internes : visibles au manager dans le scope, jamais hors scope (404), absentes pour read_only", str(f1.get("notes_internes") or "").startswith("INTERNE-F1")
        and api(hM, "GET", f"/fines/{ids['fine_v3']}").status_code == 404 and "notes_internes" not in ok(api(hRO, "GET", f"/fines/{ids['fine_v1']}")), f1.get("notes_internes"))
    cards = ok(api(hM, "GET", "/fuel-cards"))
    cids = {c["id"] for c in cards["items"]}
    mix = ok(api(hM, "GET", f"/fuel-cards/{ids['card_mix']}"))
    chk(res, F, "cartes : scope visible · hors scope invisible · mixte visible sans affectation hors scope · stats = 2", ids["card_in"] in cids and ids["card_mix"] in cids and ids["card_out"] not in cids
        and cards["stats"]["total"] == 2 and {a["vehicle_id"] for a in mix["assignments"]} == {v1}, f"items={len(cids)} mix_assign={[a['vehicle_id'] for a in mix['assignments']]}")
    drivers = ok(api(hM, "GET", "/drivers"))
    d2 = next(x for x in drivers if x["id"] == ids["d2"])
    chk(res, F, "conducteurs : liste minimale (sans email/téléphone/notes), affectations hors scope jamais exposées", all(set(x) <= {"id", "nom", "prenom", "matricule_interne", "actif", "display", "affectations"} for x in drivers)
        and d2["affectations"] == [], f"D2 affectations={d2['affectations']}")
    empty = {"vehicles": ok(api(hME, "GET", "/vehicles")), "dashboard": ok(api(hME, "GET", "/dashboard"))["total_vehicles"], "fines": ok(api(hME, "GET", "/fines"))["total"],
             "energy": len(ok(api(hME, "GET", "/energy"))["transactions"]), "cards": len(ok(api(hME, "GET", "/fuel-cards"))["items"]), "documents": len(ok(api(hME, "GET", "/documents"))),
             "deadlines": ok(api(hME, "GET", "/deadlines"))["count"], "anomalies": ok(api(hME, "GET", "/fuel/anomalies"))["total"], "v1_direct": api(hME, "GET", f"/vehicles/{v1}").status_code}
    chk(res, F, "scope [] = zéro véhicule, zéro donnée (jamais fallback tenant)", empty["vehicles"] == [] and empty["v1_direct"] == 404
        and all(empty[k] == 0 for k in ("dashboard", "fines", "energy", "cards", "documents", "deadlines", "anomalies")), empty)

    F = "KPI_SCOPE_ISOLATION"
    dash_m, dash_a = ok(api(hM, "GET", "/dashboard")), ok(api(hA, "GET", "/dashboard"))
    fines_m, fines_a = ok(api(hM, "GET", "/fines")), ok(api(hA, "GET", "/fines"))
    fs_m, fs_a = ok(api(hM, "GET", "/fines/stats")), ok(api(hA, "GET", "/fines/stats"))
    en_m, en_a = ok(api(hM, "GET", "/energy")), ok(api(hA, "GET", "/energy"))
    an_m, an_a = ok(api(hM, "GET", "/fuel/anomalies")), ok(api(hA, "GET", "/fuel/anomalies"))
    dl_m, dl_a = ok(api(hM, "GET", "/deadlines")), ok(api(hA, "GET", "/deadlines"))
    costs_m = ok(api(hM, "GET", "/costs"))
    al_m = ok(api(hM, "GET", "/alerts"))
    chk(res, F, "dashboard : total_vehicles manager = 2 < admin = 4", dash_m["total_vehicles"] == 2 and dash_a["total_vehicles"] == 4, f"manager={dash_m['total_vehicles']} admin={dash_a['total_vehicles']}")
    chk(res, F, "amendes : total / pagination / KPI calculés sur le scope (manager 2 : F1 V1 + F3 V2 ; admin 3)", fines_m["total"] == 2 and fines_a["total"] == 3 and len(fines_m["items"]) == 2
        and {f["vehicle_id"] for f in fines_m["items"]} == {v1, v2} and fs_m["counts"]["total"] == 2 and fs_a["counts"]["total"] == 3
        and {p["vehicle_id"] for p in fs_m.get("top_vehicles", fs_m.get("per_vehicle", []))} <= {v1, v2},
        f"manager total={fines_m['total']} stats={fs_m['counts']['total']} admin={fines_a['total']}")
    chk(res, F, "énergie : transactions / by_vehicle / totaux manager uniquement V1-V2 (3 tx) vs admin (6 tx)", {x["vehicle_id"] for x in en_m["transactions"]} == {v1, v2}
        and len(en_m["transactions"]) == 3 and len(en_a["transactions"]) == 6 and {b["vehicle_id"] for b in en_m["by_vehicle"]} == {v1, v2}
        and en_m["totals"]["transactions"] == 3 and round(en_m["totals"]["depenses"], 2) == round(sum(x["montant"] for x in en_m["transactions"]), 2),
        f"manager={en_m['totals']} admin_tx={len(en_a['transactions'])}")
    chk(res, F, "anomalies : total / stats manager = 1 (V1) vs admin = 2", an_m["total"] == 1 and an_m["stats"]["total"] == 1 and an_a["total"] == 2 and [a["id"] for a in an_m["items"]] == [ids["anomaly_in"]],
        f"manager={an_m['stats']} admin_total={an_a['total']}")
    chk(res, F, "échéances / alertes / coûts / timeline : uniquement V1-V2, count < admin, recipients tenant-global = []",
        all(i.get("vehicle_id") in (v1, v2) for i in dl_m["items"]) and dl_m["count"] < dl_a["count"] and all(i.get("vehicle_id") in (v1, v2) for i in al_m["items"]) and al_m["recipients"] == []
        and {i["vehicle_id"] for i in costs_m["items"]} <= {v1, v2} and {b["vehicle_id"] for b in costs_m["by_vehicle"]} <= {v1, v2}
        and all(e["vehicle_id"] in (v1, v2) for e in ok(api(hM, "GET", "/timeline"))), f"deadlines manager={dl_m['count']} admin={dl_a['count']}")
    reco_m = ok(api(hM, "GET", "/fuel/reconciliations", params={"period_month": PERIOD}))
    chk(res, F, "rapprochements : items / total manager ⊆ scope", {r["vehicle_id"] for r in reco_m["items"]} <= {v1, v2} and reco_m["total"] == len(reco_m["items"]), f"total={reco_m['total']}")

    F = "EXPORT_SCOPE_ISOLATION"
    csv_m = api(hM, "GET", "/reports/amendes.csv").text
    csv_a = api(hA, "GET", "/reports/amendes.csv").text
    chk(res, F, "export amendes CSV manager : F1/F3 présentes, F2 (V3) absente, aucune note interne ; admin : F2 présente", "LOTH-F1" in csv_m and "LOTH-F3" in csv_m and "LOTH-F2" not in csv_m
        and "INTERNE-" not in csv_m and "INTERNE-" not in csv_a and "LOTH-F2" in csv_a)
    tx_csv = api(hM, "GET", "/fuel/transactions/export", params={"period_month": PERIOD, "format": "csv"}).text
    tx_csv_out = api(hM, "GET", "/fuel/transactions/export", params={"period_month": PERIOD, "vehicle_id": v3, "format": "csv"}).text
    chk(res, F, "export transactions CSV manager : stations V1/V2 présentes, V3/V4 absentes ; filtre vehicle_id=V3 → 0 ligne", "Migrol Lausanne-Malley" in tx_csv and "Agrola Aigle" in tx_csv
        and "Coop Pronto Sion" not in tx_csv and "Tamoil Genève" not in tx_csv and "# Transactions;0" in tx_csv_out)
    couts = api(hM, "GET", "/reports/couts.csv").text
    chk(res, F, "export coûts CSV manager : plaques V1/V2 présentes, V3/V4 absentes", "VD 800 001" in couts and "VD 800 002" in couts and "VD 800 003" not in couts and "GE 800 004" not in couts)
    pdfs = {"conformite": api(hM, "GET", "/reports/conformite.pdf").status_code, "vehicule_v1": api(hM, "GET", f"/reports/vehicule/{v1}.pdf").status_code,
            "vehicule_v3": api(hM, "GET", f"/reports/vehicule/{v3}.pdf").status_code, "reco_v3": api(hM, "GET", "/fuel/reconciliations/export", params={"period_month": PERIOD, "vehicle_id": v3, "format": "csv"}).status_code,
            "reco_all": api(hM, "GET", "/fuel/reconciliations/export", params={"period_month": PERIOD, "format": "csv"}).status_code}
    chk(res, F, "exports PDF / rapprochements : scope 200, hors scope 404", pdfs["conformite"] == pdfs["vehicule_v1"] == pdfs["reco_all"] == 200 and pdfs["vehicule_v3"] == pdfs["reco_v3"] == 404, pdfs)

    F = "DRIVER_SELF_SCOPE_ISOLATION"
    outside = {p: api(hD, "GET", p) for p in ("/vehicles", "/dashboard", "/fines", "/energy", "/drivers", "/documents", "/deadlines", "/fuel-cards", f"/vehicles/{v1}",
                                                f"/fuel-transactions/{ids['tx_v1_d1']}", f"/fines/{ids['fine_v1']}", "/fuel/statements", "/costs", "/alerts", "/fuel/anomalies")}
    chk(res, F, "driver hors /api/me → 403 DRIVER_FORBIDDEN sur 15 routes (listes ET accès directs)", all(r.status_code == 403 and code_of(r) == "DRIVER_FORBIDDEN" for r in outside.values()),
        {p: r.status_code for p, r in outside.items()})
    muts = {"fuel_manual": api(hD, "POST", f"/vehicles/{v1}/fuel-transactions", {"date": D(0), "montant": 1, "business_category": "CARBURANT", "motif": "x"}).status_code,
            "vehicle_update": api(hD, "PUT", f"/vehicles/{v1}", {"modele": "x"}).status_code, "fine_status": api(hD, "POST", f"/documents/{ids['fine_v1']}/fine-status", {"fine_status": "payee"}).status_code,
            "attach_admin_route": api(hD, "POST", f"/documents/{ids['tx_v1_d1_doc']}/attach-file").status_code}
    chk(res, F, "driver : toute mutation hors /api/me → 403", all(c == 403 for c in muts.values()), muts)
    prof = ok(api(hD, "GET", "/me/profile"))
    chk(res, F, "me/profile : conducteur D1 sans email / téléphone / notes", prof["driver"]["id"] == ids["d1"] and not ({"email", "telephone", "notes"} & set(prof["driver"])), prof["driver"].get("display"))
    mv = ok(api(hD, "GET", "/me/vehicles"))
    chk(res, F, "me/vehicles : affectation ACTIVE uniquement (V1) ; V3 terminée et V2 future exclues ; aucune donnée leasing/assurance", [x["id"] for x in mv["items"]] == [v1] and mv["total"] == 1
        and not ({"leasing", "assurance"} & set(mv["items"][0])), [x["plaque"] for x in mv["items"]])
    mf = ok(api(hD, "GET", "/me/fuel-transactions"))
    mf_ids = {x["id"] for x in mf["items"]}
    chk(res, F, "me/fuel-transactions : pleins avec driver_id = D1 (V1 ×2 + V3 historique), jamais ceux de D2 / sans conducteur ; total = items",
        mf_ids == {ids["tx_v1_d1"], ids["tx_v1_d1_b"], ids["tx_v3_d1_old"]} and mf["total"] == len(mf["items"]) == 3 and all("notes_internes" not in x for x in mf["items"]), f"{len(mf_ids)} pleins")
    mfi = ok(api(hD, "GET", "/me/fines"))
    f = mfi["items"]
    chk(res, F, "me/fines : amendes D1 (F1 V1 + F3 V2), sans notes_internes / dossier_interne / priorite", {x["id"] for x in f} == {ids["fine_v1"], ids["fine_v3_d1_v2"]}
        and all(not ({"notes_internes", "dossier_interne", "priorite"} & set(x)) for x in f) and mfi["total"] == 2, f"{len(f)} amendes")
    att_other = requests.post(f"{BASE}/api/me/fuel-transactions/{ids['tx_v3_d2']}/attachment", files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, headers=hD, timeout=60)
    att_nodriver = requests.post(f"{BASE}/api/me/fuel-transactions/{ids['tx_v4_nodriver']}/attachment", files={"file": ("t.png", io.BytesIO(PNG), "image/png")}, headers=hD, timeout=60)
    chk(res, F, "justificatif : plein d'un autre conducteur / sans conducteur → 404 (aucune fuite)", att_other.status_code == 404 and att_nodriver.status_code == 404, (att_other.status_code, att_nodriver.status_code))
    tx_hist = next(x for x in mf["items"] if x["id"] == ids["tx_v3_d1_old"])
    if not tx_hist["justificatif"]["present"]:
        r1 = requests.post(f"{BASE}/api/me/fuel-transactions/{ids['tx_v3_d1_old']}/attachment", files={"file": ("ticket.png", io.BytesIO(PNG), "image/png")}, headers=hD, timeout=60)
        chk(res, F, "justificatif image : 1er dépôt → 200, present=true", r1.status_code == 200 and r1.json()["justificatif"]["present"], r1.status_code)
    pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    tx_b = next(x for x in mf["items"] if x["id"] == ids["tx_v1_d1_b"])
    if not tx_b["justificatif"]["present"]:
        r2 = requests.post(f"{BASE}/api/me/fuel-transactions/{ids['tx_v1_d1_b']}/attachment", files={"file": ("ticket.pdf", io.BytesIO(pdf_bytes), "application/pdf")}, headers=hD, timeout=60)
        chk(res, F, "justificatif PDF : 1er dépôt → 200", r2.status_code == 200, r2.text[:120])
    r3 = requests.post(f"{BASE}/api/me/fuel-transactions/{ids['tx_v3_d1_old']}/attachment", files={"file": ("again.png", io.BytesIO(PNG), "image/png")}, headers=hD, timeout=60)
    after = next(x for x in ok(api(hD, "GET", "/me/fuel-transactions"))["items"] if x["id"] == ids["tx_v3_d1_old"])
    chk(res, F, "justificatif : 2e fichier → 409 FILE_ALREADY_PRESENT, fichier existant jamais écrasé", r3.status_code == 409 and code_of(r3) == "FILE_ALREADY_PRESENT"
        and after["justificatif"]["present"] and after["justificatif"]["filename"] == "ticket.png", (r3.status_code, code_of(r3), after["justificatif"].get("filename")))
    ids["tx_v3_d1_old_path"] = after["justificatif"]["path"]
    au = list(db.audit_logs.find({"tenant_id": T, "action": "attach_file", "role": "driver"}, {"_id": 0, "entity_id": 1, "role": 1, "user": 1}))
    chk(res, F, "audit attach_file role=driver présent", len(au) >= 1 and all(a["role"] == "driver" for a in au), f"{len(au)} audit(s)")
    files = {"own_receipt": api(hD, "GET", f"/files/{ids['tx_v3_d1_old_path']}").status_code, "vehicle_doc": api(hD, "GET", f"/files/{ids['doc_v1_path']}").status_code,
             "other_driver_sees_mine": api(hDN, "GET", f"/files/{ids['tx_v3_d1_old_path']}").status_code, "manager_out_of_scope_v3": api(hM, "GET", f"/files/{ids['tx_v3_d1_old_path']}").status_code,
             "admin": api(hA, "GET", f"/files/{ids['tx_v3_d1_old_path']}").status_code}
    chk(res, F, "fichiers : son justificatif 200 · document véhicule 404 · autre chauffeur 404 · manager hors scope 404 · admin 200",
        files["own_receipt"] == files["admin"] == 200 and files["vehicle_doc"] == files["other_driver_sees_mine"] == files["manager_out_of_scope_v3"] == 404, files)
    states = {"unlinked": (api(hDU, "GET", "/me/profile").status_code, code_of(api(hDU, "GET", "/me/profile"))), "unlinked_fuel": code_of(api(hDU, "GET", "/me/fuel-transactions")),
              "inactive": (api(hDI, "GET", "/me/vehicles").status_code, code_of(api(hDI, "GET", "/me/vehicles"))), "noassign_profile": api(hDN, "GET", "/me/profile").status_code,
              "noassign_vehicles": ok(api(hDN, "GET", "/me/vehicles"))["items"], "noassign_fuel": ok(api(hDN, "GET", "/me/fuel-transactions"))["total"], "noassign_fines": ok(api(hDN, "GET", "/me/fines"))["total"],
              "admin_me": api(hA, "GET", "/me/profile").status_code, "ro_me": api(hRO, "GET", "/me/vehicles").status_code}
    chk(res, F, "états de liaison : non lié → 403 DRIVER_ACCOUNT_NOT_LINKED · inactif → 403 DRIVER_INACTIVE · lié sans affectation → 200 listes vides · admin/read_only sur /me → 403",
        states["unlinked"] == (403, "DRIVER_ACCOUNT_NOT_LINKED") and states["unlinked_fuel"] == "DRIVER_ACCOUNT_NOT_LINKED" and states["inactive"] == (403, "DRIVER_INACTIVE")
        and states["noassign_profile"] == 200 and states["noassign_vehicles"] == [] and states["noassign_fuel"] == 0 and states["noassign_fines"] == 0 and states["admin_me"] == states["ro_me"] == 403, states)

    F = "MANAGER_SCOPE_REVOCATION"
    sa = sa_headers()
    uid = ids["user_MANAGER"]
    before = api(hM, "GET", f"/vehicles/{v1}").status_code
    ok(api(sa, "PUT", f"/admin/users/{uid}", {"vehicle_scope": [v2]}))
    try:
        during = api(hM, "GET", f"/vehicles/{v1}").status_code
        during_list = [x["id"] for x in ok(api(hM, "GET", "/vehicles"))]
        during_dash = ok(api(hM, "GET", "/dashboard"))["total_vehicles"]
        during_fine = api(hM, "GET", f"/fines/{ids['fine_v1']}").status_code
    finally:
        ok(api(sa, "PUT", f"/admin/users/{uid}", {"vehicle_scope": [v1, v2]}))
    after_ = api(hM, "GET", f"/vehicles/{v1}").status_code
    chk(res, F, "même jeton : V1 200 → retrait du scope par le superadmin → V1 404, liste [V2], dashboard 1, amende V1 404 → restauration → 200",
        before == 200 and during == 404 and during_list == [v2] and during_dash == 1 and during_fine == 404 and after_ == 200, (before, during, during_list, during_dash, during_fine, after_))
    auds = list(db.audit_logs.find({"tenant_id": T, "action": "admin_user_update", "entity_id": uid}, {"_id": 0, "before": 1, "after": 1}))
    chk(res, F, "audit console avant/après du scope (superadmin)", any((a.get("before") or {}).get("vehicle_scope") == [v1, v2] and (a.get("after") or {}).get("vehicle_scope") == [v2] for a in auds), f"{len(auds)} audit(s)")

    F = "DRIVER_LINK_REVOCATION"
    uid = ids["user_DRIVER"]
    b = api(hD, "GET", "/me/profile").status_code
    ok(api(sa, "PUT", f"/admin/users/{uid}", {"driver_id": ""}))
    try:
        unl = (api(hD, "GET", "/me/profile").status_code, code_of(api(hD, "GET", "/me/profile")))
    finally:
        ok(api(sa, "PUT", f"/admin/users/{uid}", {"driver_id": ids["d1"]}))
    rel = api(hD, "GET", "/me/profile").status_code
    chk(res, F, "même jeton : lié 200 → déliaison superadmin → 403 DRIVER_ACCOUNT_NOT_LINKED → re-liaison → 200", b == 200 and unl == (403, "DRIVER_ACCOUNT_NOT_LINKED") and rel == 200, (b, unl, rel))
    ok(api(hA, "PATCH", f"/drivers/{ids['d1']}", {"actif": False}))
    try:
        ina = (api(hD, "GET", "/me/vehicles").status_code, code_of(api(hD, "GET", "/me/vehicles")), code_of(api(hD, "GET", "/me/fines")))
    finally:
        ok(api(hA, "PATCH", f"/drivers/{ids['d1']}", {"actif": True}))
    back = api(hD, "GET", "/me/vehicles").status_code
    chk(res, F, "même jeton : conducteur désactivé par l'admin → 403 DRIVER_INACTIVE sur /me/* → réactivé → 200", ina == (403, "DRIVER_INACTIVE", "DRIVER_INACTIVE") and back == 200, (ina, back))
    aid = ok(api(hA, "POST", f"/vehicles/{v2}/driver-assignments", {"driver_id": ids["d_none"], "valid_from": D(-3), "principal": False}))["id"]
    with_ = [x["id"] for x in ok(api(hDN, "GET", "/me/vehicles"))["items"]]
    ok(api(hA, "POST", f"/driver-assignments/{aid}/close", {"valid_to": D(-1), "motif": "fin de mission Lot H"}))
    without = ok(api(hDN, "GET", "/me/vehicles"))["items"]
    chk(res, F, "affectation active → V2 visible ; clôturée à J-1 → disparaît immédiatement (règle de date serveur)", with_ == [v2] and without == [], (with_, without))
    auds = list(db.audit_logs.find({"tenant_id": T, "action": "admin_user_update", "entity_id": uid}, {"_id": 0, "before": 1, "after": 1}))
    chk(res, F, "audit console avant/après de la liaison conducteur", any((a.get("before") or {}).get("driver_id") == ids["d1"] and (a.get("after") or {}).get("driver_id") is None for a in auds), f"{len(auds)} audit(s)")


def seed():
    if not BASELINE.exists():
        die("baseline absente : exécuter `baseline` AVANT le seed (ou le mode `all`)")
    res = load_result()
    ids = res["ids"]
    sa, pw = ensure_tenant_and_users(res, ids)
    hA = login(EMAIL["ADMIN"], pw["ADMIN"])
    # flotte : V1, V2 (scope manager) · V3, V4 (hors scope)
    ensure_vehicle(hA, "v1", {"plaque": "VD 800 001", "marque": "Skoda", "modele": "Octavia Combi", "type_carburant": "Diesel", "kilometrage": 51500, "annee": 2022, "couleur": "Gris"}, ids)
    ensure_vehicle(hA, "v2", {"plaque": "VD 800 002", "marque": "VW", "modele": "Caddy", "type_carburant": "Diesel", "kilometrage": 31200, "annee": 2021}, ids)
    ensure_vehicle(hA, "v3", {"plaque": "VD 800 003", "marque": "Ford", "modele": "Transit", "type_carburant": "Diesel", "kilometrage": 20600, "annee": 2020}, ids)
    ensure_vehicle(hA, "v4", {"plaque": "GE 800 004", "marque": "Renault", "modele": "Kangoo", "type_carburant": "Essence", "kilometrage": 15000, "annee": 2023}, ids)
    v1, v2, v3, v4 = ids["v1"], ids["v2"], ids["v3"], ids["v4"]
    # conducteurs
    ensure_driver(hA, "d1", {"nom": "Dupont", "prenom": "Marc", "matricule_interne": "LOTH-M001", "email": f"marc.dupont@{T}.ch", "telephone": "+41790000001", "notes": "fiche RH privée D1"}, ids)
    ensure_driver(hA, "d2", {"nom": "Martin", "prenom": "Julie", "matricule_interne": "LOTH-M002", "email": f"julie.martin@{T}.ch", "telephone": "+41790000002", "notes": "fiche RH privée D2"}, ids)
    ensure_driver(hA, "d_none", {"nom": "Sansaffectation", "prenom": "Paul", "matricule_interne": "LOTH-M003"}, ids)
    ensure_driver(hA, "d_inact", {"nom": "Inactif", "prenom": "Léa", "matricule_interne": "LOTH-M004"}, ids)
    ok(api(hA, "PATCH", f"/drivers/{ids['d_inact']}", {"actif": False}))
    # affectations : D1→V1 active · D1→V3 terminée · D1→V2 future · D2→V3 active
    ensure_assignment(hA, "a_d1_v1", v1, ids["d1"], D(-30), ids=ids)
    ensure_assignment(hA, "a_d1_v3_past", v3, ids["d1"], D(-120), D(-31), ids=ids)
    ensure_assignment(hA, "a_d1_v2_future", v2, ids["d1"], D(5), ids=ids)
    ensure_assignment(hA, "a_d2_v3", v3, ids["d2"], D(-20), ids=ids)
    # pleins (documents sans justificatif) : 6 transactions
    ensure_plein(hA, ids, "tx_v1_d1", v1, D(-3), 85.0, 40, "Migrol Lausanne-Malley", ids["d1"], kilometrage=51400)
    ensure_plein(hA, ids, "tx_v1_d1_b", v1, D(-15), 92.0, 45, "Migrol Renens", ids["d1"], heure="17:30", kilometrage=50900)
    ensure_plein(hA, ids, "tx_v2_d2", v2, D(-2), 66.0, 30, "Agrola Aigle", ids["d2"])
    ensure_plein(hA, ids, "tx_v3_d2", v3, D(-4), 90.0, 45, "Coop Pronto Sion", ids["d2"])
    ensure_plein(hA, ids, "tx_v3_d1_old", v3, D(-45), 78.0, 38, "Coop Pronto Sion", ids["d1"], heure="07:10")
    ensure_plein(hA, ids, "tx_v4_nodriver", v4, D(-1), 50.0, 25, "Tamoil Genève")
    # amendes : F1 V1/D1 · F2 V3/D2 · F3 V2/D1 — notes internes sensibles
    ensure_fine(hA, ids, "fine_v1", v1, "LOTH-F1", ids["d1"], "INTERNE-F1 : récidive, à surveiller")
    ensure_fine(hA, ids, "fine_v3", v3, "LOTH-F2", ids["d2"], "INTERNE-F2 : à refacturer", montant=250.0)
    ensure_fine(hA, ids, "fine_v3_d1_v2", v2, "LOTH-F3", ids["d1"], "INTERNE-F3 : contestation envisagée", montant=40.0, delai=-3)
    # cartes : scope / hors scope / mixte (V3 passé + V1 courant)
    ensure_card(hA, ids, "card_in", "1111", [(v1, D(-60), None)])
    ensure_card(hA, ids, "card_out", "2222", [(v3, D(-60), None)])
    ensure_card(hA, ids, "card_mix", "3333", [(v3, D(-120), D(-31)), (v1, D(-30), None)])
    # documents fichiers (storage) · anomalies synthétiques · inspection admin V1
    ensure_doc_upload(hA, ids, "doc_v1", v1, "loth-photo-v1.png")
    ensure_doc_upload(hA, ids, "doc_v3", v3, "loth-photo-v3.png")
    ensure_anomaly(ids, "anomaly_in", v1, ids["tx_v1_d1"])
    ensure_anomaly(ids, "anomaly_out", v3, ids["tx_v3_d2"])
    ensure_inspection(hA, ids, "insp_v1", v1)
    # liaisons / scopes (console superadmin, même tenant) — idempotent
    ok(api(sa, "PUT", f"/admin/users/{ids['user_MANAGER']}", {"vehicle_scope": [v1, v2]}))
    ok(api(sa, "PUT", f"/admin/users/{ids['user_MANAGER_EMPTY']}", {"vehicle_scope": []}))
    ok(api(sa, "PUT", f"/admin/users/{ids['user_DRIVER']}", {"driver_id": ids["d1"]}))
    ok(api(sa, "PUT", f"/admin/users/{ids['user_DRIVER_INACTIVE']}", {"driver_id": ids["d_inact"]}))
    ok(api(sa, "PUT", f"/admin/users/{ids['user_DRIVER_NOASSIGN']}", {"driver_id": ids["d_none"]}))
    ok(api(sa, "PUT", f"/admin/users/{ids['user_DRIVER_UNLINKED']}", {"driver_id": ""}))
    save_result(res)
    H = {k: login(EMAIL[k], pw[k]) for k in ACCOUNTS}
    prove(res, ids, H)
    save_result(res)
    failed = [c for c in res["checks"] if c["result"] != PASS]
    print("SEED RESULT →", RESULT, "| checks FAIL :", [f"{c['family']}·{c['check']}" for c in failed] or "aucun")
    inventory()
    return not failed


def inventory():
    out = {"tenant": {"id": T, "exists": db.tenants.count_documents({"id": T})},
           "counts": {c: db[c].count_documents({"tenant_id": T}) for c in sorted(db.list_collection_names()) if c not in ("tenants", "login_attempts") and db[c].count_documents({"tenant_id": T})},
           "users": [{k: u.get(k) for k in ("email", "role", "driver_id", "vehicle_scope", "disabled")} for u in db.users.find({"tenant_id": T}, {"_id": 0}).sort("email", 1)],
           "vehicles": [{k: x.get(k) for k in ("id", "plaque", "marque", "modele")} for x in db.vehicles.find({"tenant_id": T}, {"_id": 0}).sort("plaque", 1)],
           "drivers": [{k: x.get(k) for k in ("id", "nom", "prenom", "matricule_interne", "actif", "is_deleted")} for x in db.drivers.find({"tenant_id": T}, {"_id": 0})],
           "driver_assignments": [{k: x.get(k) for k in ("id", "vehicle_id", "driver_id", "valid_from", "valid_to", "principal")} for x in db.driver_assignments.find({"tenant_id": T}, {"_id": 0})],
           "fuel_transactions": [{k: x.get(k) for k in ("id", "vehicle_id", "driver_id", "date", "montant", "station")} for x in db.fuel_transactions.find({"tenant_id": T}, {"_id": 0}).sort("date", 1)],
           "fines": [{k: x.get(k) for k in ("id", "vehicle_id", "driver_id", "numero", "fine_status")} for x in db.documents.find({"tenant_id": T, "business_category": "AMENDE"}, {"_id": 0})],
           "fuel_cards": [{k: x.get(k) for k in ("id", "last4", "statut")} for x in db.fuel_cards.find({"tenant_id": T}, {"_id": 0})],
           "audit": {"total": db.audit_logs.count_documents({"tenant_id": T}), "by_role": {s["_id"]: s["n"] for s in db.audit_logs.aggregate([{"$match": {"tenant_id": T}}, {"$group": {"_id": "$role", "n": {"$sum": 1}}}])}},
           "files": db.files.count_documents({"tenant_id": T}), "documents_with_storage": db.documents.count_documents({"tenant_id": T, "storage_path": {"$nin": [None, ""]}})}
    INVENTORY.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print("INVENTORY →", INVENTORY, json.dumps({"counts": out["counts"], "users": [(u["email"], u["role"]) for u in out["users"]], "audit": out["audit"]}, ensure_ascii=False, default=str))
    return out


def verify():
    if not BASELINE.exists() or not RESULT.exists():
        die("baseline / résultat de seed absents")
    res, before, after = load_result(), json.loads(BASELINE.read_text()), fingerprint()
    keys = sorted(set(before["counts"]) | set(after["counts"]))
    diff = {k: (before["counts"].get(k), after["counts"].get(k)) for k in keys if before["counts"].get(k) != after["counts"].get(k) or before["hashes"].get(k) != after["hashes"].get(k)}
    diff_default = {k: v for k, v in diff.items() if k.endswith("|default")}
    diff_others = {k: v for k, v in diff.items() if not k.endswith("|default")}
    checks = [{"check": "DEFAULT_UNCHANGED", "result": PASS if not diff_default else FAIL, "detail": diff_default or "aucune différence"},
              {"check": "OTHER_TENANTS_UNCHANGED", "result": PASS if not diff_others and before["tenants_ids"] == after["tenants_ids"] else FAIL, "detail": diff_others or "aucune différence"},
              {"check": "TARGET_TENANT_PRESENT", "result": PASS if db.tenants.count_documents({"id": T}) == 1 else FAIL, "detail": T}]
    fam = {f: [c for c in res["checks"] if c["family"] == f] for f in FAMILIES}
    for f, cs in fam.items():
        checks.append({"check": f, "result": PASS if cs and all(c["result"] == PASS for c in cs) else FAIL, "detail": f"{sum(1 for c in cs if c['result'] == PASS)}/{len(cs)} preuves API"})
    for c in checks:
        print(f"[{c['result']}] {c['check']} — {c['detail']}")
    verdict = all(c["result"] == PASS for c in checks)
    VERIFY_OUT.write_text(json.dumps({"checks": checks, "verdict": PASS if verdict else FAIL, "families": fam, "note": "verify = lecture seule (fingerprint + relecture du résultat de seed)"}, indent=1, ensure_ascii=False, default=str))
    print(f"LOT H SEED VERIFY = {PASS if verdict else FAIL}  →", VERIFY_OUT)
    return verdict


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    if cmd == "baseline":
        baseline()
    elif cmd == "seed":
        sys.exit(0 if seed() else 1)
    elif cmd == "inventory":
        inventory()
    elif cmd == "verify":
        sys.exit(0 if verify() else 1)
    elif cmd == "all":
        baseline()
        s = seed()
        sys.exit(0 if (verify() and s) else 1)
    else:
        die(f"mode inconnu {cmd} (baseline | seed | inventory | verify | all)")
