"""Lot G — tenant UI isolé `lotg-ui-test` (jamais `default`, aucune donnée Journal) : baseline / seed / inventory / verify.
Cas officiels A…AB (identifiants conservés tels quels dans le script, le JSON de résultat et le rapport).
Usage : python3 test_reports/lotg_seed.py baseline | seed | inventory | verify | all   (`all` = baseline → seed → inventory → verify ; jamais de cleanup)
Variables facultatives : LOTG_ADMIN_PASSWORD / LOTG_RO_PASSWORD (réutiliser des mots de passe connus au lieu d'en générer / réinitialiser).
Écritures autorisées : tenant cible uniquement (chaque write DB porte `tenant_id == TARGET_TENANT`) ; API via comptes du tenant ou superadmin
en « vue client » (`X-Acting-Tenant`). Aucun drop, aucun delete_many, aucune lecture Journal."""
import hashlib
import json
import os
import secrets
import sys
import uuid
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET_TENANT = "lotg-ui-test"
ADMIN, RO = f"lotg-admin@{TARGET_TENANT}.ch", f"lotg-ro@{TARGET_TENANT}.ch"
REP = Path("/app/test_reports")
FIX = REP / "fixtures"
BASELINE = REP / "lotg_baseline_before_seed.json"
RESULT = REP / "lotg_seed_result.json"
INVENTORY = REP / "lotg_inventory.json"
VERIFY_OUT = REP / "lotg_verify.json"
P_APR, P_MAY, P_CUR = "2026-04", "2026-05", "2026-10"
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
LOTG_COLLS = ("tenants", "users", "vehicles", "drivers", "documents", "fuel_transactions", "fuel_snapshots", "fuel_reconciliations", "fuel_statements",
              "fuel_statement_lines", "fuel_anomalies", "fuel_cards", "fuel_card_assignments", "fuel_transaction_matches", "fuel_import_jobs", "fuel_import_rows",
              "fuel_import_mappings", "audit_logs", "alerts", "tenant_settings", "files")
VOLATILE = {"vehicles": ("updated_at", "kilometrage", "conso_moyenne_l_100km", "conso_source", "conso_updated_at")}  # champs écrits par les jobs horaires Navixy / conso
HEADER = ["Ref", "Date transaction", "Numero de carte", "Immatriculation", "vehicle_id", "Montant TTC", "Devise", "Montant CHF", "Quantite", "Prix unitaire",
          "Station", "Kilometrage", "Produit", "Commentaire"]
MAPPING = {"external_transaction_id": "Ref", "tx_datetime": "Date transaction", "card_last4": "Numero de carte", "vehicle_hint": "Immatriculation",
           "vehicle_id": "vehicle_id", "amount_total": "Montant TTC", "currency": "Devise", "amount_chf": "Montant CHF", "quantity": "Quantite",
           "unit_price": "Prix unitaire", "station_name": "Station", "mileage": "Kilometrage", "product_type": "Produit", "comment": "Commentaire"}
CASES = {"A": "CAN présent + achats égaux", "B": "CAN présent + achats > consommation CAN", "C": "CAN présent + achats < consommation CAN", "D": "CAN absent",
         "E": "ASTRA disponible comme référence comparative", "F": "Seuils null → INDICATIF", "G": "Seuils configurés → logique de rapprochement",
         "H": "Justification d'un rapprochement", "I": "Statement sans blocker → clôturable", "J": "Blocker pending_fx", "K": "Blocker matched_review",
         "L": "Blocker unmatched", "M": "Blocker open_anomaly", "N": "Blocker forced_duplicate", "O": "Close normal → verrou", "P": "Close normal avec blocker → 409",
         "Q": "Close exception", "R": "Declared complet", "S": "Declared partiel / null = N/A", "T": "Écarts declared", "U": "Transaction verrouillée après clôture",
         "V": "Mutation verrouillée → 409 STATEMENT_LOCKED", "W": "Décision d'anomalie non destructive après clôture", "X": "Correctif : transaction tardive incluse",
         "Y": "Correctif : transaction verrouillée exclue", "Z": "read_only : lecture / export OK, mutations 403", "AA": "Cross-tenant fail-closed", "AB": "Exports audités SHA-256"}
PASS, FAIL = "PASS", "FAIL"


# --- utilitaires -----------------------------------------------------------------------------------------------------
def die(msg):
    print(f"FAIL-FAST : {msg}")
    sys.exit(2)


def guard(tenant):
    if tenant != TARGET_TENANT:
        die(f"écriture hors tenant cible refusée ({tenant})")


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        die(f"login {email} → {r.status_code}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def sa_headers(acting=None):
    h = login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])
    return {**h, "X-Acting-Tenant": acting} if acting else h


def api(h, method, path, body=None, **kw):
    return requests.request(method, f"{BASE}/api{path}", json=body, headers=h, timeout=120, **kw)


def ok(r, *codes):
    if r.status_code not in (codes or (200,)):
        die(f"{r.request.method} {r.url} → {r.status_code} {r.text[:300]}")
    return r.json() if r.content else None


def load_result():
    return json.loads(RESULT.read_text()) if RESULT.exists() else {"tenant": TARGET_TENANT, "ids": {}, "cases": {}, "notes": []}


def save_result(res):
    RESULT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))


def case(res, cid, data, expected, observed, passed, evidence=None):
    res["cases"][cid] = {"case": cid, "description": CASES[cid], "seed_data": data, "expected": expected, "observed": observed,
                         "result": PASS if passed else FAIL, "evidence": evidence}
    print(f"[{PASS if passed else FAIL}] {cid}. {CASES[cid]} — {observed}")
    return passed


# --- baseline / fingerprint --------------------------------------------------------------------------------------------
def fingerprint():
    """Par (collection | tenant ≠ cible) : count + sha256 stable (tri par id, champs volatils exclus). `login_attempts` exclue (sans tenant_id, volatil auth).
    `tenants` : par id (pas de tenant_id)."""
    fp = {"counts": {}, "hashes": {}, "hashes_raw": {}}
    colls = sorted(c for c in db.list_collection_names() if not c.startswith("system.") and c != "login_attempts")
    for c in colls:
        key = "id" if c == "tenants" else "tenant_id"
        tenants = sorted(str(t) for t in db[c].distinct(key, {key: {"$ne": TARGET_TENANT}}))
        for t in tenants:
            h, hr, n = hashlib.sha256(), hashlib.sha256(), 0
            for d in db[c].find({key: t}, {"_id": 0}).sort("id", 1):
                n += 1
                hr.update(json.dumps(d, sort_keys=True, default=str).encode())
                d = {k: v for k, v in d.items() if k not in VOLATILE.get(c, ()) and not k.startswith("navixy_")}
                h.update(json.dumps(d, sort_keys=True, default=str).encode())
            fp["counts"][f"{c}|{t}"] = n
            fp["hashes"][f"{c}|{t}"] = h.hexdigest()
            fp["hashes_raw"][f"{c}|{t}"] = hr.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TARGET_TENANT}}, {"_id": 0, "id": 1}))
    return fp


def baseline():
    if BASELINE.exists():
        print("BASELINE déjà présente (conservée, capturée avant le premier seed) :", BASELINE)
        return
    BASELINE.write_text(json.dumps(fingerprint(), indent=1))
    print("BASELINE écrite", BASELINE)


# --- fixtures import -------------------------------------------------------------------------------------------------
def csv_bytes(rows):
    return ("\ufeff" + "\n".join(";".join(r) for r in [HEADER] + rows) + "\n").encode("utf-8")


def rows_mai_migrol(v):
    return [["G01", "20.05.2026 08:00", "1111", "", "", "102.50", "CHF", "", "50", "2.05", "Migrol Lausanne-Malley", "51100", "Diesel", "LOTG:B import carte 1111 → V1 auto"],
            ["G03", "20.05.2026 10:00", "5555", "", v["v4"], "51.25", "CHF", "", "25", "2.05", "Migrol Gland", "", "Essence", "LOTG:L carte 5555 sans affectation à la date → unmatched après recalcul"],
            ["G04", "23.05.2026 11:00", "6666", "", "", "61.50", "CHF", "", "30", "2.05", "Migrol Morges", "", "Essence", "LOTG:N original (carte 6666 → V4 auto)"],
            ["G04", "23.05.2026 11:00", "6666", "", "", "61.50", "CHF", "", "30", "2.05", "Migrol Morges", "", "Essence", "LOTG: doublon intra-fichier mis de côté (non importé, Lot F)"]]


def rows_mai_migrol_doublon():
    """Relevé complémentaire : même référence G04 déjà importée → ligne `duplicate` (external_id) forcée avec motif → forced_duplicate_of (cas N)."""
    return [["G04", "23.05.2026 11:00", "6666", "", "", "61.50", "CHF", "", "30", "2.05", "Migrol Morges", "", "Essence", "LOTG:N doublon (référence déjà importée) forcé avec motif"]]


def rows_mai_shell(v):
    return [["S01", "17.05.2026 12:30", "2222", "", v["v4"], "44.00", "CHF", "", "20", "2.20", "Shell Vevey", "", "Essence", "LOTG:K carte 2222 ambiguë (2 cartes Shell) → matched_review après recalcul"]]


def rows_oct_migrol():
    return [["G10", "03.10.2026 07:50", "1111", "", "", "92.25", "CHF", "", "45", "2.05", "Migrol Lausanne-Malley", "52400", "Diesel", "LOTG:brouillon courant import carte 1111 → V1"]]


# --- seed ------------------------------------------------------------------------------------------------------------
def ensure_users(res):
    sa = sa_headers()
    r = api(sa, "POST", "/admin/tenants", {"name": "Lot G UI test (synthétique)", "id": TARGET_TENANT})
    ok(r, 200, 409)
    created_now = r.status_code == 200
    users = {u["email"]: u for u in ok(api(sa, "GET", f"/admin/tenants/{TARGET_TENANT}/users"))}
    pw = {}
    for email, role, env in ((ADMIN, "admin", "LOTG_ADMIN_PASSWORD"), (RO, "read_only", "LOTG_RO_PASSWORD")):
        pw[email] = os.environ.get(env) or f"LotG-{role}-{secrets.token_hex(4)}"
        if email not in users:
            ok(api(sa, "POST", f"/admin/tenants/{TARGET_TENANT}/users", {"email": email, "password": pw[email], "role": role, "name": f"Lot G {role}"}))
        elif not os.environ.get(env):
            ok(api(sa, "PUT", f"/admin/users/{users[email]['id']}", {"password": pw[email]}))
            res["notes"].append(f"re-seed : mot de passe {role} réinitialisé via superadmin (1 audit admin_user_update)")
    print(f"TENANT={TARGET_TENANT} created_now={created_now}")
    print(f"ADMIN_LOGIN={ADMIN}\nADMIN_PASSWORD={pw[ADMIN]}\nREAD_ONLY_LOGIN={RO}\nREAD_ONLY_PASSWORD={pw[RO]}")
    return login(ADMIN, pw[ADMIN]), login(RO, pw[RO])


def ensure_vehicle(h, key, body, ids):
    guard(TARGET_TENANT)
    cur = db.vehicles.find_one({"tenant_id": TARGET_TENANT, "plaque": body["plaque"]}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", "/vehicles", body))["id"]


def ensure_snapshots(vid, pts):
    for day, litres, km in pts:
        db.fuel_snapshots.update_one({"tenant_id": TARGET_TENANT, "vehicle_id": vid, "day": day},
                                     {"$set": {"litres_cumules": float(litres), "km": km, "source": "synthetic-lotg"}}, upsert=True)


def ensure_card(h, ext, ids, **body):
    cur = db.fuel_cards.find_one({"tenant_id": TARGET_TENANT, "external_card_id": ext}, {"_id": 0, "id": 1})
    cid = cur["id"] if cur else ok(api(h, "POST", "/fuel-cards", {"type_affectation": "vehicule", "external_card_id": ext, **body}))["id"]
    ids[f"card_{ext}"] = cid
    return cid


def ensure_assignment(h, cid, vid, valid_from="2026-01-01", valid_to=None):
    if not db.fuel_card_assignments.find_one({"tenant_id": TARGET_TENANT, "card_id": cid, "vehicle_id": vid}):
        ok(api(h, "POST", f"/fuel-cards/{cid}/assignments", {"type": "vehicule", "vehicle_id": vid, "valid_from": valid_from, "valid_to": valid_to}))


def ensure_plein(h, ids, key, vid, date, montant, litres=None, km=None, heure="08:00", case_tag="", **over):
    cur = db.fuel_transactions.find_one({"tenant_id": TARGET_TENANT, "vehicle_id": vid, "date": date, "montant": montant, "is_deleted": False}, {"_id": 0, "id": 1, "source_document_id": 1})
    if cur:
        ids[key], ids[f"{key}_doc"] = cur["id"], cur.get("source_document_id")
        return
    body = {"date": date, "heure": heure, "station": over.pop("station", "Station synthétique"), "montant": montant, "business_category": "CARBURANT",
            "motif": f"LOTG:{case_tag}", **({"litres": litres, "prix_litre": round(montant / litres, 3)} if litres else {}), **({"kilometrage": km} if km else {}), **over}
    r = ok(api(h, "POST", f"/vehicles/{vid}/fuel-transactions", body))
    ids[key], ids[f"{key}_doc"] = r["fuel_transaction"]["id"], r["document_id"]


def ensure_import(h, ids, key, filename, fournisseur, rows, force_ref=None):
    cur = db.fuel_import_jobs.find_one({"tenant_id": TARGET_TENANT, "filename": filename, "status": "confirmed"}, {"_id": 0, "id": 1})
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / filename).write_bytes(csv_bytes(rows))
    if cur:
        ids[key] = cur["id"]
    else:
        job = ok(requests.post(f"{BASE}/api/fuel/imports", files={"file": (filename, csv_bytes(rows))}, data={"fournisseur": fournisseur}, headers=h, timeout=120))["id"]
        ok(api(h, "POST", f"/fuel/imports/{job}/mapping", {"mapping": MAPPING}))
        ok(api(h, "POST", f"/fuel/imports/{job}/confirm", {}))
        if force_ref:
            dup = [x for x in ok(api(h, "GET", f"/fuel/imports/{job}/rows"))["items"] if x.get("status") == "duplicate" and not x.get("imported")]
            if len(dup) != 1:
                die(f"import {filename} : 1 ligne doublon attendue, {len(dup)} trouvée(s)")
            ok(api(h, "POST", f"/fuel/imports/{job}/rows/{dup[0]['id']}/force", {"reason": "Doublon assumé : deux passages identiques confirmés par le fournisseur (cas N)"}))
        ids[key] = job
    for row in db.fuel_import_rows.find({"tenant_id": TARGET_TENANT, "job_id": ids[key], "imported": True}, {"_id": 0, "transaction_id": 1, "normalized": 1, "forced_reason": 1}):
        ref = (row.get("normalized") or {}).get("external_transaction_id") or ""
        ids[f"tx_{ref.replace('#', '_')}" + ("_forced" if row.get("forced_reason") else "")] = row["transaction_id"]


def tx_api(h, tx_id):
    return ok(api(h, "GET", f"/fuel-transactions/{tx_id}"))


def reco(h, period, vid=None):
    items = ok(api(h, "GET", "/fuel/reconciliations", params={"period_month": period, **({"vehicle_id": vid} if vid else {})}))["items"]
    return items[0] if vid and items else items


def ensure_statement(h, ids, key, period, scope_type="tenant"):
    cur = db.fuel_statements.find_one({"tenant_id": TARGET_TENANT, "type": "regulier", "period_month": period, "scope.type": scope_type}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", "/fuel/statements", {"period_month": period, "scope_type": scope_type}))["id"]
    return ok(api(h, "GET", f"/fuel/statements/{ids[key]}"))


def seed():
    if not BASELINE.exists():
        die("baseline absente : exécuter `baseline` AVANT le seed (ou le mode `all`)")
    res = load_result()
    ids = res["ids"]
    h, hro = ensure_users(res)
    # 1. flotte synthétique (ASTRA = conso_officielle sur V1 uniquement)
    ensure_vehicle(h, "v1", {"plaque": "VD 700 001", "marque": "Skoda", "modele": "Octavia Combi", "type_carburant": "Diesel", "kilometrage": 51500, "conso_officielle_l_100km": 6.5, "conso_officielle_norme": "WLTP"}, ids)
    ensure_vehicle(h, "v2", {"plaque": "VD 700 002", "marque": "VW", "modele": "Caddy", "type_carburant": "Diesel", "kilometrage": 31200}, ids)
    ensure_vehicle(h, "v3", {"plaque": "VD 700 003", "marque": "Ford", "modele": "Transit", "type_carburant": "Diesel", "kilometrage": 20600}, ids)
    ensure_vehicle(h, "v4", {"plaque": "VD 700 004", "marque": "Renault", "modele": "Kangoo", "type_carburant": "Essence", "kilometrage": 15000}, ids)
    ensure_vehicle(h, "v5", {"plaque": "GE 700 005", "marque": "VW", "modele": "ID.Buzz", "type_carburant": "Électrique", "kilometrage": 18000}, ids)
    v = ids
    # 2. CAN synthétique (litres cumulés / odomètre) : V1 avril 50 L / 1 500 km, mai 100 L / 1 500 km ; V2 mai 80 L / 1 200 km ; V3 aucun CAN
    ensure_snapshots(v["v1"], [("2026-03-31", 950, 48500), ("2026-04-15", 975, 49200), ("2026-04-30", 1000, 50000), ("2026-05-15", 1050, 50800), ("2026-05-31", 1100, 51500)])
    ensure_snapshots(v["v2"], [("2026-04-30", 500, 30000), ("2026-05-31", 580, 31200)])
    # 3. cartes : 1111 Migrol → V1 · 2222 Shell ×2 (V1 / V4, ambiguë) · 5555 Migrol → V4 jusqu'au 30.04 · 6666 Migrol → V4
    ensure_assignment(h, ensure_card(h, "LOTG-1111", ids, fournisseur="Migrol", last4="1111", expire_le="2030-12-31"), v["v1"])
    ensure_assignment(h, ensure_card(h, "LOTG-2222-A", ids, fournisseur="Shell", last4="2222", expire_le="2030-12-31"), v["v1"])
    ensure_assignment(h, ensure_card(h, "LOTG-2222-B", ids, fournisseur="Shell", last4="2222", expire_le="2030-12-31", collision_confirmed=True), v["v4"])
    ensure_assignment(h, ensure_card(h, "LOTG-5555", ids, fournisseur="Migrol", last4="5555", expire_le="2030-12-31"), v["v4"], valid_to="2026-04-30")
    ensure_assignment(h, ensure_card(h, "LOTG-6666", ids, fournisseur="Migrol", last4="6666", expire_le="2030-12-31"), v["v4"])
    # 4. pleins manuels (documents sans justificatif = coût D7)
    ensure_plein(h, ids, "tx_apr_v1", v["v1"], "2026-04-10", 100.0, litres=50, km=49300, case_tag="A avril V1 (= CAN 50 L)", station="Migrol Lausanne-Malley")
    ensure_plein(h, ids, "tx_may_v1", v["v1"], "2026-05-05", 120.0, litres=60, km=50300, case_tag="B mai V1 (achats 110 L vs CAN 100 L)", station="Migrol Renens")
    ensure_plein(h, ids, "tx_may_v2", v["v2"], "2026-05-10", 132.0, litres=60, km=30500, case_tag="C mai V2 (achats 60 L vs CAN 80 L)", station="Agrola Aigle")
    ensure_plein(h, ids, "tx_may_v3a", v["v3"], "2026-05-03", 92.25, litres=45, km=20000, case_tag="D mai V3 sans CAN (tickets indicatifs)", station="Coop Pronto Sion")
    ensure_plein(h, ids, "tx_may_v3b", v["v3"], "2026-05-25", 82.0, litres=40, km=20600, case_tag="D mai V3 sans CAN (tickets indicatifs)", station="Coop Pronto Sion")
    ensure_plein(h, ids, "tx_fx", v["v4"], "2026-05-12", 55.0, litres=30, case_tag="J pending_fx (EUR sans contre-valeur)", station="Total Annemasse", devise="EUR")
    ensure_plein(h, ids, "tx_dbl1", v["v4"], "2026-05-22", 70.0, litres=35, heure="09:00", case_tag="M double plein 1/2", station="Migrol Nyon")
    ensure_plein(h, ids, "tx_dbl2", v["v4"], "2026-05-22", 72.0, litres=36, heure="09:20", case_tag="M double plein 2/2 (anomalie ouverte)", station="Migrol Nyon")
    ensure_plein(h, ids, "tx_incoh", v["v4"], "2026-05-26", 200.0, litres=40, case_tag="M incohérence quantité × prix (anomalie ouverte conservée)", station="Migrol Rolle", prix_litre=2.05)
    ensure_plein(h, ids, "tx_ev", v["v5"], "2026-05-15", 25.0, case_tag="R recharge électrique (kWh)", station="Ionity Bursins", business_category="ENERGIE_ELECTRIQUE", energie_kwh=50, prix_kwh=0.5)
    ensure_plein(h, ids, "tx_cur_v2", v["v2"], "2026-10-05", 88.0, litres=40, km=31500, case_tag="brouillon période courante V2", station="Agrola Bex")
    # 5. imports Lot F (règles réelles) + recalcul des rattachements → K (ambiguë → matched_review), L (sans affectation → unmatched), N (doublon forcé)
    ensure_import(h, ids, "job_mai_migrol", "lotg_releve_mai_migrol.csv", "Migrol", rows_mai_migrol(v))
    ensure_import(h, ids, "job_mai_migrol_doublon", "lotg_releve_mai_migrol_doublon.csv", "Migrol", rows_mai_migrol_doublon(), force_ref="G04")
    ensure_import(h, ids, "job_mai_shell", "lotg_releve_mai_shell.csv", "Shell", rows_mai_shell(v))
    ensure_import(h, ids, "job_oct_migrol", "lotg_releve_oct_migrol.csv", "Migrol", rows_oct_migrol())
    if not db.fuel_statements.find_one({"tenant_id": TARGET_TENANT, "period_month": P_MAY}):
        ok(api(h, "POST", "/fuel/match/run"))
    # 6. rapprochements : A–G (seuils null par défaut → INDICATIF ; bascule 5 % / 5 L puis retour null = preuve G)
    r_apr, r_may1, r_may2, r_may3 = reco(h, P_APR, v["v1"]), reco(h, P_MAY, v["v1"]), reco(h, P_MAY, v["v2"]), reco(h, P_MAY, v["v3"])
    case(res, "A", {"vehicle": v["v1"], "period": P_APR, "can_l": 50, "purchases_l": 50}, "ecart_l = 0, source can", f"ecart_l={r_apr['ecart_l']} source={r_apr['source_consumption']}",
         r_apr["ecart_l"] == 0 and r_apr["source_consumption"] == "can", {"reconciliation": {k: r_apr[k] for k in ("achats", "consommation", "ecart_l", "ecart_pct", "status")}})
    case(res, "B", {"vehicle": v["v1"], "period": P_MAY, "can_l": 100, "purchases_l": 110}, "ecart_l = +10 (+10 %), CAN prioritaire (tickets ≠ conso)",
         f"ecart_l={r_may1['ecart_l']} pct={r_may1['ecart_pct']} source={r_may1['source_consumption']} tickets={(r_may1.get('estimation_tickets') or {}).get('litres')}",
         r_may1["ecart_l"] == 10.0 and r_may1["ecart_pct"] == 10.0 and r_may1["source_consumption"] == "can" and r_may1["consommation"]["litres"] == 100.0,
         {"transaction_ids": r_may1["transaction_ids"]})
    case(res, "C", {"vehicle": v["v2"], "period": P_MAY, "can_l": 80, "purchases_l": 60}, "ecart_l = −20 (−25 %)", f"ecart_l={r_may2['ecart_l']} pct={r_may2['ecart_pct']}",
         r_may2["ecart_l"] == -20.0 and r_may2["ecart_pct"] == -25.0 and r_may2["source_consumption"] == "can")
    case(res, "D", {"vehicle": v["v3"], "period": P_MAY, "can": None, "purchases_l": 85}, "source unavailable, ecart None, estimation tickets indicative, statut INDICATIF",
         f"source={r_may3['source_consumption']} ecart={r_may3['ecart_l']} status={r_may3['status']} tickets={(r_may3.get('estimation_tickets') or {}).get('litres')}",
         r_may3["source_consumption"] == "unavailable" and r_may3["ecart_l"] is None and r_may3["status"] == "INDICATIF" and r_may3["consommation"]["litres"] is None)
    a = r_may1["astra"]
    case(res, "E", {"vehicle": v["v1"], "conso_officielle_l_100km": 6.5, "norme": "WLTP"}, "ASTRA 6.5 référence comparative ; conso réelle CAN 6.7 conservée (jamais écrasée)",
         f"astra={a['conso_officielle_l_100km']} role={a['role']} reelle={r_may1['consommation']['l_100km']} ecart_l_100={a['ecart_l_100km']}",
         a["conso_officielle_l_100km"] == 6.5 and a["role"] == "reference_comparative" and r_may1["consommation"]["l_100km"] == 6.7 and a["ecart_l_100km"] == 0.2)
    settings = ok(api(h, "GET", "/tenant-settings/fuel/reconciliation"))["reconciliation"]
    case(res, "F", {"threshold_pct": None, "threshold_l": None}, "statut INDICATIF pour V1 / V2 (CAN + achats) sans seuil", f"settings={settings} V1={r_may1['status']} V2={r_may2['status']} V1avr={r_apr['status']}",
         settings == {"threshold_pct": None, "threshold_l": None} and r_may1["status"] == r_may2["status"] == r_apr["status"] == "INDICATIF")
    if "G" not in res["cases"]:
        ok(api(h, "PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": 5, "threshold_l": 5}))
        g1, g2, g0 = reco(h, P_MAY, v["v1"])["status"], reco(h, P_MAY, v["v2"])["status"], reco(h, P_APR, v["v1"])["status"]
        ok(api(h, "PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": None, "threshold_l": None}))
        back = reco(h, P_MAY, v["v1"])["status"]
        case(res, "G", {"threshold_pct": 5, "threshold_l": 5, "rule": "single_or_both"}, "V1 mai (+10 L / +10 %) A_CONTROLER · V2 mai (−20 L / −25 %) A_CONTROLER · V1 avril (0) OK · retour null → INDICATIF",
             f"V1={g1} V2={g2} V1avr={g0} après_reset={back}", g1 == "A_CONTROLER" and g2 == "A_CONTROLER" and g0 == "OK" and back == "INDICATIF",
             {"note": "seuils remis à null à la fin (état final du tenant = aucun seuil) ; 2 audits tenant_settings"})
    if not r_may1.get("justification"):
        ok(api(h, "POST", f"/fuel/reconciliations/{v['v1']}/{P_MAY}/justify", {"reason": "Jerrican de 10 L pour la tondeuse du dépôt (achat sans consommation véhicule)"}))
    j = reco(h, P_MAY, v["v1"])
    au = db.audit_logs.find_one({"tenant_id": TARGET_TENANT, "entity": "fuel_reconciliation", "action": "justify", "vehicle_id": v["v1"]}, {"_id": 0, "id": 1})
    case(res, "H", {"vehicle": v["v1"], "period": P_MAY}, "justification persistée + audit, achats / CAN / écart inchangés",
         f"reason={j['justification']['reason'][:30]}… audit={'oui' if au else 'non'} ecart={j['ecart_l']} achats={j['achats']['litres']} can={j['consommation']['litres']}",
         bool(j.get("justification")) and au is not None and j["ecart_l"] == 10.0 and j["achats"]["litres"] == 110.0 and j["consommation"]["litres"] == 100.0,
         {"fuel_reconciliations_id": (db.fuel_reconciliations.find_one({"tenant_id": TARGET_TENANT, "vehicle_id": v["v1"], "period_month": P_MAY}, {"_id": 0, "id": 1}) or {}).get("id")})
    # 7. décompte AVRIL : propre → declared complet → clôture normale → verrou (I, O, R, U)
    st_apr = ensure_statement(h, ids, "st_apr", P_APR)
    if st_apr["status"] == "brouillon":
        ok(api(h, "PATCH", f"/fuel/statements/{st_apr['id']}/declared", {"montant": 100, "devise": "CHF", "volume_l": 50, "kwh": 0, "nb_lignes": 1}))
        ok(api(h, "POST", f"/fuel/statements/{st_apr['id']}/close"))
        st_apr = ok(api(h, "GET", f"/fuel/statements/{st_apr['id']}"))
    case(res, "I", {"statement": st_apr["id"], "number": st_apr["number"]}, "0 blocker, intégrité PASS → clôturable", f"blocker_count={st_apr['totals']['blocker_count']} status={st_apr['status']}",
         st_apr["totals"]["blocker_count"] == 0 and st_apr["status"] == "cloture")
    tx_apr = tx_api(h, ids["tx_apr_v1"])
    case(res, "O", {"statement": st_apr["id"]}, "status cloture, close_exception false, transactions snapshot locked", f"status={st_apr['status']} exception={st_apr['close_exception']} locked={tx_apr.get('locked')}",
         st_apr["status"] == "cloture" and st_apr["close_exception"] is False and tx_apr.get("locked") is True and all(ln["locked"] for ln in st_apr["lines"]))
    case(res, "R", {"statement": st_apr["id"], "declared": st_apr["declared"]}, "5 champs declared renseignés", f"declared={st_apr['declared']}",
         st_apr["declared"] == {"montant": 100.0, "devise": "CHF", "volume_l": 50.0, "kwh": 0.0, "nb_lignes": 1})
    case(res, "U", {"transaction": ids["tx_apr_v1"]}, "locked=true, statement_id, locked_at", f"locked={tx_apr.get('locked')} statement_id={tx_apr.get('statement_id')} locked_at={tx_apr.get('locked_at')}",
         tx_apr.get("locked") is True and tx_apr.get("statement_id") == st_apr["id"] and bool(tx_apr.get("locked_at")))
    # 8. décompte MAI : blockers J–N → declared partiel → close normal 409 (P) → clôture par exception (Q) → anomalie décidée après verrou (W)
    st_may = ensure_statement(h, ids, "st_may", P_MAY)
    if st_may["status"] == "brouillon":
        ok(api(h, "PATCH", f"/fuel/statements/{st_may['id']}/declared", {"montant": 1000, "devise": "CHF"}))
        r = api(h, "POST", f"/fuel/statements/{st_may['id']}/close")
        res["evidence_P"] = {"status_code": r.status_code, "detail": r.json().get("detail") if r.status_code == 409 else r.json()}
        save_result(res)
        r = ok(api(h, "POST", f"/fuel/statements/{st_may['id']}/close-exception", {"reason": "Clôture mensuelle imposée par la comptabilité — écarts à traiter en correctif", "confirm": True}))
        st_may = ok(api(h, "GET", f"/fuel/statements/{st_may['id']}"))
    by = {ln["transaction_id"]: ln for ln in st_may["lines"]}
    bt = st_may["totals"]["blockers_by_type"]
    case(res, "J", {"transaction": ids["tx_fx"]}, "blockers == [pending_fx], montant_chf None", f"blockers={by.get(ids['tx_fx'], {}).get('blockers')} chf={by.get(ids['tx_fx'], {}).get('montant_chf')}",
         by.get(ids["tx_fx"], {}).get("blockers") == ["pending_fx"] and by[ids["tx_fx"]]["montant_chf"] is None)
    case(res, "K", {"transaction": ids.get("tx_S01")}, "blockers == [matched_review] (carte ambiguë après recalcul)", f"blockers={by.get(ids.get('tx_S01'), {}).get('blockers')}",
         by.get(ids.get("tx_S01"), {}).get("blockers") == ["matched_review"])
    case(res, "L", {"transaction": ids.get("tx_G03")}, "blockers == [unmatched] (carte sans affectation à la date après recalcul)", f"blockers={by.get(ids.get('tx_G03'), {}).get('blockers')}",
         by.get(ids.get("tx_G03"), {}).get("blockers") == ["unmatched"])
    case(res, "M", {"transaction": ids["tx_dbl2"], "anomaly": "double_plein"}, "blockers contient open_anomaly (anomalie détectée par Documents, D8)", f"blockers={by.get(ids['tx_dbl2'], {}).get('blockers')} open={by.get(ids['tx_dbl2'], {}).get('open_anomalies')}",
         "open_anomaly" in by.get(ids["tx_dbl2"], {}).get("blockers", []))
    case(res, "N", {"transaction": ids.get("tx_G04_forced"), "forced_duplicate_of": ids.get("tx_G04")}, "blockers contient forced_duplicate (doublon forcé avec motif, règle Lot F réelle ; le double passage déclenche aussi une anomalie double_plein D8)",
         f"blockers={by.get(ids.get('tx_G04_forced'), {}).get('blockers')} forced_duplicate_of={by.get(ids.get('tx_G04_forced'), {}).get('forced_duplicate_of')}",
         "forced_duplicate" in by.get(ids.get("tx_G04_forced"), {}).get("blockers", []) and by.get(ids.get("tx_G04_forced"), {}).get("forced_duplicate_of") == ids.get("tx_G04"))
    ev_p = res.get("evidence_P") or {}
    case(res, "P", {"statement": st_may["id"]}, "HTTP 409 CLOSE_BLOCKED avec blocker_count / breakdown / lignes", f"status_code={ev_p.get('status_code')} code={(ev_p.get('detail') or {}).get('code')} blockers={(ev_p.get('detail') or {}).get('blockers_by_type')}",
         ev_p.get("status_code") == 409 and (ev_p.get("detail") or {}).get("code") == "CLOSE_BLOCKED" and set((ev_p.get("detail") or {}).get("blockers_by_type") or {}) == set(bt), ev_p)
    ex = st_may.get("exception") or {}
    case(res, "Q", {"statement": st_may["id"], "number": st_may["number"]}, "cloture + close_exception true, motif / acteur / date, blockers snapshotés = conservés, lignes verrouillées",
         f"status={st_may['status']} exception={st_may['close_exception']} by={ex.get('by')} snapshot={ (ex.get('blockers_snapshot') or {}).get('blocker_count')} totals={st_may['totals']['blocker_count']} types={sorted(bt)}",
         st_may["status"] == "cloture" and st_may["close_exception"] is True and ex.get("reason") and ex.get("by") and ex.get("at")
         and (ex.get("blockers_snapshot") or {}).get("blocker_count") == st_may["totals"]["blocker_count"] > 0 and all(ln["locked"] for ln in st_may["lines"])
         and set(bt) == {"pending_fx", "matched_review", "unmatched", "open_anomaly", "forced_duplicate"})
    d = st_may["declared"]
    case(res, "S", {"statement": st_may["id"], "declared": d}, "montant/devise renseignés, volume_l / kwh / nb_lignes = null (N/A, jamais 0)", f"declared={d}",
         d["montant"] == 1000.0 and d["devise"] == "CHF" and d["volume_l"] is None and d["kwh"] is None and d["nb_lignes"] is None)
    dl, dl_apr = st_may["deltas"], st_apr["deltas"]
    case(res, "T", {"may": dl, "apr": dl_apr}, "mai : delta_montant calculé, delta_volume/kwh/nb_lignes None · avril : 4 deltas = 0", f"mai={dl} avril={dl_apr}",
         dl["delta_montant"] == round(st_may["totals"]["montant_chf"] - 1000, 2) and dl["delta_volume_l"] is None and dl["delta_kwh"] is None and dl["delta_nb_lignes"] is None
         and dl_apr["delta_montant"] == 0 and dl_apr["delta_volume_l"] == 0 and dl_apr["delta_kwh"] == 0 and dl_apr["delta_nb_lignes"] == 0)
    # V : mutations impactantes refusées (aucune écriture) — match / card / document champ métier / suppression document / plein manuel même clé legacy / décompte clôturé
    tx_locked = ids["tx_apr_v1"]
    doc_locked = tx_api(h, tx_locked)["document"]["id"]
    sub = {}
    sub["V.1 match"] = api(h, "PATCH", f"/fuel-transactions/{tx_locked}/match", {"vehicle_id": v["v2"], "reason": "tentative après clôture"})
    sub["V.2 card"] = api(h, "PATCH", f"/fuel-transactions/{tx_locked}/card", {"card_id": None, "reason": "tentative après clôture"})
    sub["V.3 document montant"] = api(h, "PATCH", f"/documents/{doc_locked}", {"montant": 150.0})
    sub["V.3b document mixte notes+montant"] = api(h, "PATCH", f"/documents/{doc_locked}", {"notes": "mixte", "montant": 151.0})
    sub["V.4 delete document"] = api(h, "DELETE", f"/documents/{doc_locked}")
    sub["V.4b validate document"] = api(h, "POST", f"/documents/{doc_locked}/validate", {"document_type": "ticket_carburant", "fields": {"montant": 100, "litres": 50, "date": "2026-04-10"}})
    sub["V.5 declared décompte clôturé"] = api(h, "PATCH", f"/fuel/statements/{st_apr['id']}/declared", {"montant": 1})
    sub["V.5b recalcul décompte clôturé"] = api(h, "POST", f"/fuel/statements/{st_apr['id']}/recalculate")
    sub["V.6 suppression véhicule verrouillé"] = api(h, "DELETE", f"/vehicles/{v['v1']}")
    obs = {k: (r.status_code, (r.json().get("detail") or {}).get("code") if r.status_code == 409 else None) for k, r in sub.items()}
    notes_ok = api(h, "PATCH", f"/documents/{doc_locked}", {"notes": "Note documentaire autorisée après clôture (Lot G)"}).status_code if "V" not in res["cases"] else res["cases"]["V"]["evidence"]["notes_patch_status"]
    case(res, "V", {"transaction": tx_locked, "document": doc_locked, "statement": st_apr["id"]}, "toutes les mutations impactantes → 409 STATEMENT_LOCKED ; notes documentaires → 200",
         f"{ {k: f'{c} {code}' for k, (c, code) in obs.items()} } notes={notes_ok}", all(c == 409 and code == "STATEMENT_LOCKED" for c, code in obs.values()) and notes_ok == 200,
         {"sub_cases": {k: {"status": c, "code": code} for k, (c, code) in obs.items()}, "notes_patch_status": notes_ok})
    # W : décision d'anomalie (double plein) après clôture — autorisée, aucune donnée source modifiée ; l'anomalie « incohérence montant » reste ouverte (parcours UI)
    an = db.fuel_anomalies.find_one({"tenant_id": TARGET_TENANT, "transaction_id": ids["tx_dbl2"], "type": "double_plein"}, {"_id": 0})
    before = db.fuel_transactions.find_one({"tenant_id": TARGET_TENANT, "id": ids["tx_dbl2"]}, {"_id": 0})
    if an and an["status"] == "ouverte":
        ok(api(h, "POST", f"/fuel/anomalies/{an['id']}/decide", {"decision": "justify", "reason": "Deux pleins successifs justifiés (jerrican du dépôt) — décision prise après clôture"}))
    an = db.fuel_anomalies.find_one({"tenant_id": TARGET_TENANT, "transaction_id": ids["tx_dbl2"], "type": "double_plein"}, {"_id": 0})
    after = db.fuel_transactions.find_one({"tenant_id": TARGET_TENANT, "id": ids["tx_dbl2"]}, {"_id": 0})
    st_may2 = ok(api(h, "GET", f"/fuel/statements/{st_may['id']}"))
    ids["anomaly_double_plein"], ids["anomaly_open_incoherence"] = (an or {}).get("id"), (db.fuel_anomalies.find_one({"tenant_id": TARGET_TENANT, "transaction_id": ids["tx_incoh"], "status": "ouverte"}, {"_id": 0, "id": 1}) or {}).get("id")
    case(res, "W", {"anomaly": ids["anomaly_double_plein"], "transaction": ids["tx_dbl2"]}, "décision justify acceptée (200) sur transaction verrouillée ; transaction source identique ; snapshot du décompte inchangé",
         f"status={(an or {}).get('status')} tx_identique={before == after} blockers_snapshot={st_may2['totals']['blocker_count']}=={st_may['totals']['blocker_count']}",
         (an or {}).get("status") == "justifiee" and before == after and before.get("locked") is True and st_may2["totals"] == st_may["totals"])
    # 9. correctif : transaction tardive (non verrouillée) incluse, verrouillées exclues, parent immuable (X, Y)
    ensure_plein(h, ids, "tx_late_v3", v["v3"], "2026-05-28", 67.65, litres=33, km=20900, case_tag="X ticket tardif après clôture (correctif)", station="Coop Pronto Sion")
    cur = db.fuel_statements.find_one({"tenant_id": TARGET_TENANT, "type": "correctif", "parent_statement_id": st_may["id"]}, {"_id": 0, "id": 1})
    ids["st_cor"] = cur["id"] if cur else ok(api(h, "POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": st_may["id"], "reason": "Ticket tardif du 28 mai reçu après la clôture"}))["id"]
    cor = ok(api(h, "GET", f"/fuel/statements/{ids['st_cor']}"))
    parent_after = ok(api(h, "GET", f"/fuel/statements/{st_may['id']}"))
    case(res, "X", {"correctif": cor["id"], "number": cor["number"], "late_tx": ids["tx_late_v3"]}, "correctif brouillon, parent = décompte mai, même période / périmètre, ligne tardive incluse (late=true)",
         f"type={cor['type']} parent={cor['parent_statement_id'] == st_may['id']} period={cor['period_month']} lines={[ln['transaction_id'] for ln in cor['lines']]} late={[ln.get('late') for ln in cor['lines']]}",
         cor["type"] == "correctif" and cor["parent_statement_id"] == st_may["id"] and cor["period_month"] == P_MAY and cor["scope"] == st_may["scope"]
         and [ln["transaction_id"] for ln in cor["lines"]] == [ids["tx_late_v3"]] and cor["lines"][0].get("late") is True and cor["status"] == "brouillon")
    locked_ids = {ln["transaction_id"] for ln in st_may["lines"]}
    case(res, "Y", {"correctif": cor["id"], "parent_locked_lines": len(locked_ids)}, "aucune transaction verrouillée du parent dans le correctif ; parent (totaux / lignes / clôture) inchangé",
         f"intersection={len(locked_ids & {ln['transaction_id'] for ln in cor['lines']})} parent_inchangé={all(parent_after[k] == st_may2[k] for k in ('totals', 'declared', 'closed_at', 'exception', 'status'))}",
         not (locked_ids & {ln["transaction_id"] for ln in cor["lines"]}) and all(parent_after[k] == st_may2[k] for k in ("totals", "declared", "closed_at", "exception", "status"))
         and len(parent_after["lines"]) == len(st_may["lines"]))
    # 10. décompte période courante (brouillon, declared complet) — support du parcours UI (recalcul, close normal, scope fournisseur)
    st_cur = ensure_statement(h, ids, "st_cur", P_CUR)
    if st_cur["status"] == "brouillon" and not st_cur.get("declared"):
        ok(api(h, "PATCH", f"/fuel/statements/{st_cur['id']}/declared", {"montant": 175.0, "devise": "CHF", "volume_l": 85, "kwh": 0, "nb_lignes": 2}))
        st_cur = ok(api(h, "GET", f"/fuel/statements/{st_cur['id']}"))
    res["notes"].append(f"brouillon période courante {st_cur['number']} : {st_cur['totals']['n_lignes']} ligne(s), declared complet, aucune transaction verrouillée")
    # Z : read_only (lecture / filtres / drawers / exports autorisés ; toute mutation Lot G → 403 serveur)
    if "Z" not in res["cases"]:
        reads = {"reco": api(hro, "GET", "/fuel/reconciliations", params={"period_month": P_MAY}).status_code, "statements": api(hro, "GET", "/fuel/statements").status_code,
                 "statement": api(hro, "GET", f"/fuel/statements/{st_may['id']}").status_code, "settings": api(hro, "GET", "/tenant-settings/fuel/reconciliation").status_code,
                 "export": api(hro, "GET", f"/fuel/statements/{st_apr['id']}/export", params={"format": "csv"}).status_code}
        muts = {"thresholds": api(hro, "PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": 5}), "justify": api(hro, "POST", f"/fuel/reconciliations/{v['v1']}/{P_MAY}/justify", {"reason": "ro"}),
                "create": api(hro, "POST", "/fuel/statements", {"period_month": "2026-03"}), "declared": api(hro, "PATCH", f"/fuel/statements/{st_cur['id']}/declared", {"montant": 1}),
                "recalculate": api(hro, "POST", f"/fuel/statements/{st_cur['id']}/recalculate"), "close": api(hro, "POST", f"/fuel/statements/{st_cur['id']}/close"),
                "close_exception": api(hro, "POST", f"/fuel/statements/{st_cur['id']}/close-exception", {"reason": "ro", "confirm": True}),
                "correctif": api(hro, "POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": st_apr["id"], "reason": "ro"}),
                "tx_match": api(hro, "PATCH", f"/fuel-transactions/{ids['tx_cur_v2']}/match", {"vehicle_id": v["v1"], "reason": "ro"})}
        mo = {k: r.status_code for k, r in muts.items()}
        case(res, "Z", {"user": RO}, "lectures + export → 200 ; 9 mutations → 403", f"reads={reads} mutations={mo}", all(c == 200 for c in reads.values()) and all(c == 403 for c in mo.values()),
             {"reads": reads, "mutations": mo})
    # AA : cross-tenant fail-closed (ids d'autres tenants / inexistants → 404 ; aucune lecture de données Journal)
    foreign_vehicle = (db.vehicles.find_one({"tenant_id": {"$ne": TARGET_TENANT}}, {"_id": 0, "id": 1}) or {}).get("id")
    aa = {"statement_inconnu": api(h, "GET", f"/fuel/statements/{uuid.uuid4()}").status_code, "export_inconnu": api(h, "GET", f"/fuel/statements/{uuid.uuid4()}/export", params={"format": "csv"}).status_code,
          "reco_vehicule_autre_tenant": api(h, "GET", "/fuel/reconciliations", params={"period_month": P_MAY, "vehicle_id": foreign_vehicle or "x"}).status_code,
          "justify_vehicule_autre_tenant": api(h, "POST", f"/fuel/reconciliations/{foreign_vehicle or 'x'}/{P_MAY}/justify", {"reason": "cross"}).status_code,
          "correctif_parent_inconnu": api(h, "POST", "/fuel/statements", {"type": "correctif", "parent_statement_id": str(uuid.uuid4()), "reason": "cross"}).status_code}
    lotg_vids = {x["id"] for x in db.vehicles.find({"tenant_id": TARGET_TENANT}, {"_id": 0, "id": 1})}
    tx_vids = {x.get("vehicle_id") for x in db.fuel_transactions.find({"tenant_id": TARGET_TENANT}, {"_id": 0, "vehicle_id": 1})}
    st_t = {x["tenant_id"] for c in ("fuel_statements", "fuel_statement_lines", "fuel_reconciliations") for x in db[c].find({"id": {"$in": [ids.get(k) for k in ("st_apr", "st_may", "st_cor", "st_cur")]}}, {"_id": 0, "tenant_id": 1})}
    case(res, "AA", {"probes": list(aa)}, "toutes les sondes → 404 ; toutes les transactions du tenant référencent des véhicules du tenant ; décomptes du tenant uniquement",
         f"probes={aa} tx_vehicules_ok={tx_vids <= lotg_vids} statements_tenants={st_t}", all(c == 404 for c in aa.values()) and tx_vids <= lotg_vids and st_t <= {TARGET_TENANT}, aa)
    # AB : exports (statement CSV/XLSX/PDF, rapprochements CSV/XLSX/PDF, transactions CSV/XLSX) — hash des octets = en-tête = audit
    if "AB" not in res["cases"]:
        ev = {}
        for label, path, params in (("statement", f"/fuel/statements/{st_may['id']}/export", {}), ("reconciliations", "/fuel/reconciliations/export", {"period_month": P_MAY}),
                                    ("transactions", "/fuel/transactions/export", {"period_month": P_MAY})):
            for fmt in (("csv", "xlsx") if label == "transactions" else ("csv", "xlsx", "pdf")):
                r = api(h, "GET", path, params={**params, "format": fmt})
                sha = hashlib.sha256(r.content).hexdigest()
                au = db.audit_logs.find_one({"tenant_id": TARGET_TENANT, "entity": "fuel_export", "action": "download", "sha256": sha}, {"_id": 0, "size": 1, "format": 1, "export_type": 1})
                ev[f"{label}.{fmt}"] = {"status": r.status_code, "size": len(r.content), "sha256": sha, "header_sha256": r.headers.get("x-content-sha256"), "audit_found": bool(au),
                                        "audit_size": (au or {}).get("size"), "match": r.status_code == 200 and len(r.content) > 0 and r.headers.get("x-content-sha256") == sha and bool(au) and (au or {}).get("size") == len(r.content)}
        case(res, "AB", {"statement": st_may["id"], "period": P_MAY}, "8 exports : 200, non vides, SHA-256 recalculé = en-tête = audit download", f"{ {k: e['match'] for k, e in ev.items()} }", all(e["match"] for e in ev.values()), ev)
    res["statements"] = {k: ids.get(k) for k in ("st_apr", "st_may", "st_cor", "st_cur")}
    save_result(res)
    failed = [c for c, x in res["cases"].items() if x["result"] != PASS]
    print("SEED RESULT →", RESULT, "| cas FAIL :", failed or "aucun")
    inventory()
    return not failed


# --- inventory -------------------------------------------------------------------------------------------------------
def inventory():
    T = TARGET_TENANT
    out = {"tenant": {"id": T, "name": (db.tenants.find_one({"id": T}, {"_id": 0, "name": 1}) or {}).get("name"), "exists": db.tenants.count_documents({"id": T})},
           "counts": {c: db[c].count_documents({"tenant_id": T}) for c in sorted(db.list_collection_names()) if c not in ("tenants", "login_attempts") and db[c].count_documents({"tenant_id": T})},
           "users": {"count": db.users.count_documents({"tenant_id": T}), "roles": {u["email"]: u["role"] for u in db.users.find({"tenant_id": T}, {"_id": 0, "email": 1, "role": 1})}},
           "vehicles": [{k: x.get(k) for k in ("id", "plaque", "marque", "modele", "type_carburant", "conso_officielle_l_100km")} for x in db.vehicles.find({"tenant_id": T}, {"_id": 0}).sort("plaque", 1)],
           "fuel_snapshots": db.fuel_snapshots.count_documents({"tenant_id": T}),
           "login_attempts(identifier)": db.login_attempts.count_documents({"identifier": {"$regex": T}}) if "login_attempts" in db.list_collection_names() else 0}
    txs = list(db.fuel_transactions.find({"tenant_id": T}, {"_id": 0, "id": 1, "vehicle_id": 1, "date": 1, "montant": 1, "devise": 1, "locked": 1, "statement_id": 1, "locked_at": 1, "match_status": 1,
                                                            "motif_saisie": 1, "commentaire": 1, "created_from": 1, "forced_duplicate_of": 1}).sort([("date", 1), ("montant", 1)]))
    out["fuel_transactions"] = {"total": len(txs), "locked": sum(1 for x in txs if x.get("locked")), "unlocked": sum(1 for x in txs if not x.get("locked")),
                                "by_statement": {}, "items": [{**x, "lotg_case": x.get("motif_saisie") or x.get("commentaire")} for x in txs]}
    for x in txs:
        if x.get("locked"):
            out["fuel_transactions"]["by_statement"].setdefault(x.get("statement_id"), []).append({"transaction_id": x["id"], "locked_at": x.get("locked_at")})
    out["fuel_reconciliations"] = [{k: j.get(k) for k in ("id", "vehicle_id", "period_month")} | {"justification": (j.get("justification") or {}).get("reason"), "history": len(j.get("history") or [])}
                                   for j in db.fuel_reconciliations.find({"tenant_id": T}, {"_id": 0})]
    out["fuel_statements"] = [{**{k: s.get(k) for k in ("id", "number", "type", "parent_statement_id", "period_month", "scope", "status", "declared", "closed_at", "closed_by", "close_exception")},
                               "lines_count": db.fuel_statement_lines.count_documents({"tenant_id": T, "statement_id": s["id"]}), "blocker_count": s["totals"]["blocker_count"],
                               "blockers_by_type": s["totals"]["blockers_by_type"], "montant_chf": s["totals"]["montant_chf"], "exception_reason": (s.get("exception") or {}).get("reason")}
                              for s in db.fuel_statements.find({"tenant_id": T}, {"_id": 0}).sort("period_month", 1)]
    out["fuel_anomalies_by_status"] = {s["_id"]: s["n"] for s in db.fuel_anomalies.aggregate([{"$match": {"tenant_id": T}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    out["fuel_anomalies_by_type"] = {s["_id"]: s["n"] for s in db.fuel_anomalies.aggregate([{"$match": {"tenant_id": T}}, {"$group": {"_id": "$type", "n": {"$sum": 1}}}])}
    out["documents"] = {"total": db.documents.count_documents({"tenant_id": T}), "fuel_tickets": db.documents.count_documents({"tenant_id": T, "document_type": "ticket_carburant"}),
                        "with_storage": db.documents.count_documents({"tenant_id": T, "storage_path": {"$nin": [None, ""]}}), "files": db.files.count_documents({"tenant_id": T})}
    out["fuel_import_jobs_by_status"] = {s["_id"]: s["n"] for s in db.fuel_import_jobs.aggregate([{"$match": {"tenant_id": T}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    out["audit"] = {"count": db.audit_logs.count_documents({"tenant_id": T}),
                    "lotg_events": {f"{s['_id']['entity']}.{s['_id']['action']}": s["n"] for s in db.audit_logs.aggregate([{"$match": {"tenant_id": T, "entity": {"$in": ["fuel_statement", "fuel_reconciliation", "fuel_export", "tenant_settings"]}}},
                                                                                                                         {"$group": {"_id": {"entity": "$entity", "action": "$action"}, "n": {"$sum": 1}}}])}}
    out["tenant_settings"] = (db.tenant_settings.find_one({"tenant_id": T}, {"_id": 0, "fuel": 1}) or {}).get("fuel")
    INVENTORY.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    short = {k: v for k, v in out.items() if k not in ("fuel_transactions", "vehicles", "fuel_statements", "fuel_reconciliations")}
    short["fuel_transactions"] = {k: v for k, v in out["fuel_transactions"].items() if k != "items"}
    short["fuel_statements"] = [{k: s[k] for k in ("number", "type", "status", "lines_count", "blocker_count", "close_exception")} for s in out["fuel_statements"]]
    print("INVENTORY →", INVENTORY, json.dumps(short, indent=1, ensure_ascii=False, default=str))
    return out


# --- verify ----------------------------------------------------------------------------------------------------------
def verify():
    if not BASELINE.exists():
        die("baseline absente : impossible de prouver default / autres tenants inchangés")
    if not RESULT.exists():
        die("résultat de seed absent (lotg_seed_result.json) : exécuter `seed` d'abord")
    res, before, after = load_result(), json.loads(BASELINE.read_text()), fingerprint()
    ids, checks, T = res["ids"], [], TARGET_TENANT
    h = sa_headers(acting=T)  # superadmin en vue client : lectures + sondes 409 (aucune écriture) + bascule des seuils (2 audits tenant_settings par verify)

    def chk(name, passed, detail=""):
        checks.append({"check": name, "result": PASS if passed else FAIL, "detail": detail})
        print(f"[{PASS if passed else FAIL}] {name}{' — ' + detail if detail else ''}")

    # isolation / default / autres tenants
    keys = sorted(set(before["counts"]) | set(after["counts"]))
    diff_default = {k: (before["counts"].get(k), after["counts"].get(k), before["hashes"].get(k, "")[:12], after["hashes"].get(k, "")[:12]) for k in keys
                    if k.endswith("|default") and (before["counts"].get(k) != after["counts"].get(k) or before["hashes"].get(k) != after["hashes"].get(k))}
    diff_others = {k: (before["counts"].get(k), after["counts"].get(k)) for k in keys if not k.endswith("|default")
                   and (before["counts"].get(k) != after["counts"].get(k) or before["hashes"].get(k) != after["hashes"].get(k))}
    raw_default_diff = [k for k in keys if k.endswith("|default") and before["hashes_raw"].get(k) != after["hashes_raw"].get(k)]
    chk("tenant isolation (aucune écriture Lot G hors tenant cible)", not any(k.split("|")[0] in ("fuel_statements", "fuel_statement_lines", "fuel_reconciliations", "fuel_snapshots") for k in diff_others)
        and T not in before["tenants_ids"] and T not in after["tenants_ids"], f"collections Lot G hors cible inchangées ; tenants hors cible : {len(after['tenants_ids'])}")
    chk("default unchanged (counts + hash stable, PREEXISTING_UNCHANGED)", not diff_default, f"{sum(1 for k in keys if k.endswith('|default'))} collections · diff={diff_default or 'aucune'}"
        + (f" · hash brut différent (champs volatils Navixy/conso exclus du hash stable) : {raw_default_diff}" if raw_default_diff else ""))
    chk("other tenants unchanged (counts + hash stable)", not diff_others, f"diff={diff_others or 'aucune'} · tenants={before['tenants_ids'] == after['tenants_ids']}")
    # rapprochements
    r1, r2, r3, ra = reco(h, P_MAY, ids["v1"]), reco(h, P_MAY, ids["v2"]), reco(h, P_MAY, ids["v3"]), reco(h, P_APR, ids["v1"])
    chk("CAN priority (V1 mai : conso = CAN 100 L, tickets ≠ conso)", r1["source_consumption"] == "can" and r1["consommation"]["litres"] == 100.0 and r1["achats"]["litres"] == 110.0 and r1["ecart_l"] == 10.0
        and (r1.get("estimation_tickets") or {}).get("litres") != r1["consommation"]["litres"], f"ecart={r1['ecart_l']} L tickets={(r1.get('estimation_tickets') or {}).get('litres')}")
    chk("CAN absent → aucune consommation inventée (V3)", r3["source_consumption"] == "unavailable" and r3["consommation"]["litres"] is None and r3["status"] == "INDICATIF")
    chk("ASTRA comparative (6.5 référence, réelle 6.7 conservée)", r1["astra"]["conso_officielle_l_100km"] == 6.5 and r1["astra"]["role"] == "reference_comparative" and r1["consommation"]["l_100km"] == 6.7)
    settings = ok(api(h, "GET", "/tenant-settings/fuel/reconciliation"))["reconciliation"]
    chk("thresholds null => INDICATIF", settings == {"threshold_pct": None, "threshold_l": None} and r1["status"] == r2["status"] == ra["status"] == "INDICATIF", f"settings={settings}")
    ok(api(h, "PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": 5, "threshold_l": 5}))
    g = (reco(h, P_MAY, ids["v1"])["status"], reco(h, P_MAY, ids["v2"])["status"], reco(h, P_APR, ids["v1"])["status"])
    ok(api(h, "PATCH", "/tenant-settings/fuel/reconciliation", {"threshold_pct": None, "threshold_l": None}))
    chk("thresholds configured (5 % / 5 L) => A_CONTROLER / A_CONTROLER / OK, puis retour null", g == ("A_CONTROLER", "A_CONTROLER", "OK") and reco(h, P_MAY, ids["v1"])["status"] == "INDICATIF", f"{g}")
    chk("justification persistée (explique, ne corrige pas)", bool(r1.get("justification")) and r1["ecart_l"] == 10.0, (r1.get("justification") or {}).get("reason", "")[:40])
    # décomptes
    st = {k: ok(api(h, "GET", f"/fuel/statements/{ids[k]}")) for k in ("st_apr", "st_may", "st_cor", "st_cur")}
    bt = st["st_may"]["totals"]["blockers_by_type"]
    chk("all blocker types covered (décompte mai)", set(bt) == {"pending_fx", "matched_review", "unmatched", "open_anomaly", "forced_duplicate"}, f"{bt}")
    chk("blocker_count / blocked_line_count / breakdown cohérents", st["st_may"]["totals"]["blocker_count"] == sum(bt.values()) and st["st_may"]["totals"]["blocked_line_count"] == sum(1 for ln in st["st_may"]["lines"] if ln["blockers"]),
        f"count={st['st_may']['totals']['blocker_count']} lines={st['st_may']['totals']['blocked_line_count']}")
    draft_tx = [tx_api(h, ln["transaction_id"]) for k in ("st_cor", "st_cur") for ln in st[k]["lines"]]
    chk("draft transactions unlocked (correctif + période courante)", all(not x.get("locked") and not x.get("statement_id") and not x.get("locked_at") for x in draft_tx) and all(s["status"] == "brouillon" for s in (st["st_cor"], st["st_cur"])),
        f"{len(draft_tx)} transaction(s) de brouillon, aucune verrouillée")
    closed_tx = [(k, tx_api(h, ln["transaction_id"])) for k in ("st_apr", "st_may") for ln in st[k]["lines"]]
    chk("closed transactions locked (locked / statement_id / locked_at)", all(x.get("locked") is True and x.get("statement_id") == ids[k] and x.get("locked_at") == st[k]["closed_at"] for k, x in closed_tx),
        f"{len(closed_tx)} transaction(s) verrouillée(s) par 2 décomptes clôturés")
    ex = st["st_may"].get("exception") or {}
    chk("close_exception blockers preserved", st["st_may"]["close_exception"] is True and ex.get("reason") and ex.get("by") and ex.get("at") and (ex.get("blockers_snapshot") or {}).get("blocker_count") == st["st_may"]["totals"]["blocker_count"] > 0
        and any(ln["blockers"] for ln in st["st_may"]["lines"]), f"snapshot={ (ex.get('blockers_snapshot') or {}).get('blocker_count')} par={ex.get('by')}")
    chk("close normal = 0 blocker (décompte avril)", st["st_apr"]["status"] == "cloture" and st["st_apr"]["close_exception"] is False and st["st_apr"]["totals"]["blocker_count"] == 0)
    locked_ids = {ln["transaction_id"] for ln in st["st_may"]["lines"]}
    chk("corrective excludes locked transactions (tardive incluse)", st["st_cor"]["parent_statement_id"] == ids["st_may"] and [ln["transaction_id"] for ln in st["st_cor"]["lines"]] == [ids["tx_late_v3"]]
        and not (locked_ids & {ln["transaction_id"] for ln in st["st_cor"]["lines"]}) and st["st_cor"]["period_month"] == st["st_may"]["period_month"])
    chk("declared preserved (avril complet · mai partiel null=N/A · courant complet)", st["st_apr"]["declared"] == {"montant": 100.0, "devise": "CHF", "volume_l": 50.0, "kwh": 0.0, "nb_lignes": 1}
        and st["st_may"]["declared"]["montant"] == 1000.0 and st["st_may"]["declared"]["volume_l"] is None and st["st_may"]["deltas"]["delta_volume_l"] is None
        and (st["st_cur"]["declared"] or {}).get("montant") is not None, f"mai deltas={st['st_may']['deltas']}")
    # verrou : sondes non destructives (409 avant toute écriture)
    probes = {"match": api(h, "PATCH", f"/fuel-transactions/{ids['tx_apr_v1']}/match", {"vehicle_id": ids["v2"], "reason": "verify"}), "card": api(h, "PATCH", f"/fuel-transactions/{ids['tx_apr_v1']}/card", {"card_id": None, "reason": "verify"}),
              "doc_montant": api(h, "PATCH", f"/documents/{ids['tx_apr_v1_doc']}", {"montant": 999.0}), "doc_delete": api(h, "DELETE", f"/documents/{ids['tx_apr_v1_doc']}"),
              "declared_closed": api(h, "PATCH", f"/fuel/statements/{ids['st_apr']}/declared", {"montant": 1}), "recalc_closed": api(h, "POST", f"/fuel/statements/{ids['st_apr']}/recalculate")}
    po = {k: (r.status_code, (r.json().get("detail") or {}).get("code") if r.status_code == 409 else None) for k, r in probes.items()}
    chk("STATEMENT_LOCKED 409 sur mutations impactantes (match / card / document / delete / declared / recalcul)", all(c == 409 and code == "STATEMENT_LOCKED" for c, code in po.values()), f"{po}")
    chk("aucun endpoint de réouverture", api(h, "POST", f"/fuel/statements/{ids['st_apr']}/reopen", {}).status_code in (404, 405) and api(h, "POST", f"/fuel/statements/{ids['st_apr']}/unlock", {}).status_code in (404, 405)
        and api(h, "DELETE", f"/fuel/statements/{ids['st_apr']}").status_code in (404, 405))
    an = db.fuel_anomalies.find_one({"tenant_id": T, "id": ids.get("anomaly_double_plein")}, {"_id": 0, "status": 1})
    chk("anomaly decision after lock (justifiée, source inchangée)", (an or {}).get("status") == "justifiee" and db.fuel_transactions.find_one({"tenant_id": T, "id": ids["tx_dbl2"]}, {"_id": 0, "montant": 1})["montant"] == 72.0)
    chk("no cross-tenant writes (toutes les transactions / décomptes du tenant référencent le tenant)", res["cases"].get("AA", {}).get("result") == PASS
        and db.fuel_statements.count_documents({"tenant_id": {"$ne": T}, "id": {"$in": [ids[k] for k in ("st_apr", "st_may", "st_cor", "st_cur")]}}) == 0)
    ro_live = None
    if os.environ.get("LOTG_RO_PASSWORD"):
        hro = login(RO, os.environ["LOTG_RO_PASSWORD"])
        ro_live = (api(hro, "GET", "/fuel/statements").status_code, api(hro, "POST", f"/fuel/statements/{ids['st_cur']}/close").status_code)
    chk("read_only : lecture 200 / mutations 403" + (" (live)" if ro_live else " (preuve phase seed)"), (ro_live == (200, 403)) if ro_live else res["cases"].get("Z", {}).get("result") == PASS,
        json.dumps(res["cases"].get("Z", {}).get("evidence", {}), ensure_ascii=False)[:160])
    chk("exports SHA-256 audités (preuve phase seed : 8 exports)", res["cases"].get("AB", {}).get("result") == PASS, f"{sum(1 for e in (res['cases'].get('AB', {}).get('evidence') or {}).values() if e.get('match'))}/8")
    seed_fail = [c for c, x in res["cases"].items() if x["result"] != PASS]
    chk("cas A–AB (phase seed) tous PASS", not seed_fail, f"FAIL={seed_fail or 'aucun'}")
    verdict = all(c["result"] == PASS for c in checks)
    VERIFY_OUT.write_text(json.dumps({"checks": checks, "verdict": PASS if verdict else FAIL, "default_diff": diff_default, "others_diff": diff_others, "raw_default_hash_diff": raw_default_diff,
                                      "baseline": str(BASELINE), "cases": res["cases"], "note": "verify écrit 2 audits tenant_settings (bascule seuils 5/5 puis null) ; aucune autre écriture"},
                                     indent=1, ensure_ascii=False, default=str))
    print(f"LOT G SEED VERIFY = {PASS if verdict else FAIL}  →", VERIFY_OUT)
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
        inventory()
        sys.exit(0 if (verify() and s) else 1)
    else:
        die(f"mode inconnu {cmd} (baseline | seed | inventory | verify | all)")
