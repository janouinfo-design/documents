"""Lot F — tenant UI isolé `lotf-ui-test` (jamais `default`, aucune donnée Journal) : flotte, conducteur, cartes carburant (cas found /
ambiguë / inactive / expirée / mismatch), fixtures CSV + XLSX, 1 import confirmé via API (mai), 1 import laissé en preview (juillet),
1 anomalie justifiée. Le relevé `juin.csv` est réservé au parcours UI (testing agent). Baseline/fingerprint des autres tenants.
Usage : python lotf_seed.py baseline | seed | inventory | verify"""
import hashlib
import io
import json
import secrets
import sys
from pathlib import Path

import openpyxl
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TENANT = "lotf-ui-test"
ADMIN, RO = f"lotf-admin@{TENANT}.ch", f"lotf-ro@{TENANT}.ch"
FIX = Path("/app/test_reports/fixtures")
BASELINE = Path("/app/test_reports/lotf_baseline.json")
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
HEADER = ["Ref", "Date transaction", "Numero de carte", "Immatriculation", "vehicle_id", "Montant TTC", "Devise", "Montant CHF", "Quantite", "Prix unitaire", "Station", "Kilometrage", "Produit"]
MAPPING = {"external_transaction_id": "Ref", "tx_datetime": "Date transaction", "card_last4": "Numero de carte", "vehicle_hint": "Immatriculation",
           "vehicle_id": "vehicle_id", "amount_total": "Montant TTC", "currency": "Devise", "amount_chf": "Montant CHF", "quantity": "Quantite",
           "unit_price": "Prix unitaire", "station_name": "Station", "mileage": "Kilometrage", "product_type": "Produit"}


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def fingerprint():
    """Counts par (collection, tenant ≠ cible) + hash du contenu complet du tenant default (global + par collection).
    `default_sha256_stable` exclut les champs volatils de `vehicles` écrits par le job horaire Navixy (updated_at, navixy_*, kilometrage)."""
    fp = {}
    colls = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
    for c in colls:
        for row in db[c].aggregate([{"$match": {"tenant_id": {"$ne": TENANT}}}, {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}}]):
            fp[f"{c}|{row['_id']}"] = row["n"]
    h, hs = hashlib.sha256(), hashlib.sha256()
    for c in colls:
        hc = hashlib.sha256()
        for d in db[c].find({"tenant_id": "default"}, {"_id": 0}).sort("id", 1):
            raw = json.dumps(d, sort_keys=True, default=str).encode()
            h.update(raw)
            hc.update(raw)
            if c == "vehicles":
                d = {k: v for k, v in d.items() if k != "updated_at" and k != "kilometrage" and not k.startswith("navixy_")}
            hs.update(json.dumps(d, sort_keys=True, default=str).encode())
        if db[c].count_documents({"tenant_id": "default"}):
            fp[f"default_sha256|{c}"] = hc.hexdigest()[:16]
    fp["default_sha256"] = h.hexdigest()
    fp["default_sha256_stable"] = hs.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TENANT}}, {"_id": 0, "id": 1}))
    return fp


def csv_bytes(rows):
    return ("\ufeff" + "\n".join(";".join(r) for r in [HEADER] + rows) + "\n").encode("utf-8")


def xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relevé"
    ws.append(HEADER)
    for r in rows:
        ws.append([None if v == "" else v for v in r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rows_mai(v):
    """Import confirmé via API : transactions + anomalies visibles dès l'ouverture des pages Transactions / Anomalies."""
    return [
        ["M01", "04.05.2026 07:45", "1111", "", "", "92.25", "CHF", "", "45", "2.05", "Migrol Lausanne-Malley", "42350", "Diesel"],       # carte unique → 90 auto (v1)
        ["M02", "06.05.2026 12:10", "1111", "", "", "61.50", "CHF", "", "30", "2.05", "Migrol Renens", "42810", "Diesel"],                # idem, km cohérent
        ["M03", "11.05.2026 08:30", "4444", "", v["v1"], "41.00", "CHF", "", "20", "2.05", "Migrol Nyon", "", "Diesel"],                # carte expirée (31.03) → CARD_INACTIVE
        ["M04", "12.05.2026 09:00", "3333", "", v["v2"], "44.00", "CHF", "", "20", "2.20", "Migrol Morges", "", "Essence"],             # carte suspendue → CARD_INACTIVE
        ["M05", "13.05.2026 10:15", "9999", "", v["v1"], "82.00", "CHF", "", "40", "2.05", "Migrol Gland", "", "Diesel"],               # carte affectée à v2, tx sur v1 → CARD_VEHICLE_MISMATCH
        ["M06", "18.05.2026 17:40", "1111", "", "", "70.00", "EUR", "67.90", "35", "2.00", "Total Annemasse", "", "Diesel"],             # devise + CHF
        ["M07", "19.05.2026 18:00", "1111", "", "", "20.00", "EUR", "", "10", "2.00", "Total Annemasse", "", "Diesel"],                  # devise sans CHF → pending_fx
        ["M08", "25.05.2026 08:00", "1111", "", "", "200.00", "CHF", "", "40", "2.05", "Migrol Lausanne-Malley", "", "Diesel"],         # montant ≠ qté×prix → anomalie
        ["M09", "26.05.2026 08:10", "7777", "", v["v2"], "25.00", "CHF", "", "50", "0.50", "Ionity Bursins", "", "Électricité"],        # recharge électrique
    ]


def rows_juin(v, pl):
    """Réservé au parcours UI (upload → mapping → preview → confirm par le testing agent)."""
    return [
        ["J01", "01.06.2026 08:00", "**** 1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne-Malley", "43200", "Diesel"],  # A/C normale, carte unique → 90 auto
        ["J02", "01.06.2026 09:00", "2222", pl["v1"], "", "60.00", "CHF", "", "30", "2.00", "Shell Vevey", "", "Diesel"],                 # D carte ambiguë (2 cartes Shell 2222)
        ["J03", "01.06.2026 10:00", "0000", "", v["v2"], "55.00", "CHF", "", "25", "2.20", "Migrol Nyon", "", "Essence"],                 # E carte introuvable + direct id → 100
        ["J04", "02.06.2026 10:00", "3333", "", v["v2"], "44.00", "CHF", "", "20", "2.20", "Migrol Morges", "", "Essence"],               # F carte suspendue → CARD_INACTIVE
        ["J05", "02.06.2026 11:00", "4444", "", v["v1"], "41.00", "CHF", "", "20", "2.05", "Migrol Rolle", "", "Diesel"],                 # G carte expirée à la date → CARD_INACTIVE
        ["J06", "02.06.2026 12:00", "9999", "", v["v1"], "61.50", "CHF", "", "30", "2.05", "Migrol Gland", "", "Diesel"],                 # H CARD_VEHICLE_MISMATCH
        ["J07", "03.06.2026 08:00", "", pl["v3"], "", "41.00", "CHF", "", "20", "2.05", "Agrola Aigle", "", "Diesel"],                     # I plaque candidat unique → revue
        ["J08", "03.06.2026 09:00", "", pl["v4"], "", "41.00", "CHF", "", "20", "2.05", "Agrola Bex", "", "Diesel"],                       # S plaque candidat unique (bulk)
        ["J09", "03.06.2026 10:00", "", pl["v5"].replace(" ", "-"), "", "41.00", "CHF", "", "20", "2.05", "Agrola Monthey", "", "Diesel"], # S plaque normalisée (tirets) candidat unique (bulk)
        ["J10", "03.06.2026 11:00", "", pl["dup"], "", "44.00", "CHF", "", "20", "2.20", "Coop Pronto Sion", "", "Essence"],               # J plaque ambiguë (2 véhicules)
        ["J11", "03.06.2026 12:00", "", "ZH 999 999", "", "33.00", "CHF", "", "15", "2.20", "Coop Pronto Zurich", "", "Essence"],          # K véhicule introuvable
        ["J01", "01.06.2026 08:00", "**** 1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne-Malley", "43200", "Diesel"],  # L doublon intra-fichier
        ["M01", "04.05.2026 07:45", "1111", "", "", "92.25", "CHF", "", "45", "2.05", "Migrol Lausanne-Malley", "42350", "Diesel"],       # L doublon d'une transaction déjà importée (mai)
        ["J14", "04.06.2026 08:00", "1111", "", "", "50.00", "EUR", "48.50", "25", "2.00", "Total Annemasse", "", "Diesel"],              # N devise + CHF
        ["J15", "04.06.2026 09:00", "1111", "", "", "30.00", "EUR", "", "15", "2.00", "Total Annemasse", "", "Diesel"],                   # O devise sans CHF → pending_fx
        ["J16", "04.06.2026 10:00", "1111", "", "", "", "CHF", "", "10", "2.00", "Migrol Lausanne-Malley", "", "Diesel"],                 # P invalide (montant manquant)
        ["J17", "05.06.2026 08:00", "1111", "", "", "100.00", "CHF", "", "40", "2.05", "Migrol Lausanne-Malley", "", "Diesel"],           # montant incohérent → importé + anomalie
        ["J18", "05.06.2026 09:00", "7777", "", v["v2"], "25.00", "CHF", "", "50", "0.50", "Ionity Bursins", "", "Électricité"],          # recharge
    ]


def rows_juillet(v, pl):
    """Job laissé en preview (smoke screenshot + détail d'un job non confirmé)."""
    return [
        ["X01", "01.07.2026 08:00", "1111", "", "", "82.00", "CHF", "", "40", "2.05", "Migrol Lausanne-Malley", "44100", "Diesel"],
        ["X02", "01.07.2026 09:00", "2222", "", "", "60.00", "CHF", "", "30", "2.00", "Shell Vevey", "", "Diesel"],
        ["X03", "02.07.2026 10:00", "3333", "", v["v2"], "44.00", "CHF", "", "20", "2.20", "Migrol Morges", "", "Essence"],
        ["X04", "02.07.2026 11:00", "", pl["v3"], "", "41.00", "CHF", "", "20", "2.05", "Agrola Aigle", "", "Diesel"],
        ["X05", "02.07.2026 12:00", "", "ZH 999 999", "", "33.00", "CHF", "", "15", "2.20", "Coop Pronto Zurich", "", "Essence"],
        ["X06", "03.07.2026 08:00", "1111", "", "", "", "CHF", "", "10", "2.00", "Migrol Lausanne-Malley", "", "Diesel"],
        ["X07", "03.07.2026 09:00", "1111", "", "", "30.00", "EUR", "", "15", "2.00", "Total Annemasse", "", "Diesel"],
    ]


def seed():
    if not BASELINE.exists():
        BASELINE.write_text(json.dumps(fingerprint(), indent=1))
    sa = login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])
    pw_admin, pw_ro = "LotF-Admin-" + secrets.token_hex(3), "LotF-Ro-" + secrets.token_hex(3)
    r = requests.post(f"{BASE}/api/admin/tenants", json={"name": "Lot F UI test", "id": TENANT}, headers=sa, timeout=30)
    assert r.status_code in (200, 409), r.text
    for email, pw, role in ((ADMIN, pw_admin, "admin"), (RO, pw_ro, "read_only")):
        r = requests.post(f"{BASE}/api/admin/tenants/{TENANT}/users", json={"email": email, "password": pw, "role": role, "name": role}, headers=sa, timeout=30)
        assert r.status_code == 200, r.text
    h = login(ADMIN, pw_admin)
    post = lambda p, b: requests.post(f"{BASE}/api{p}", json=b, headers=h, timeout=60)  # noqa: E731
    pl = {"v1": "VD 600 001", "v2": "GE 600 002", "v3": "VS 600 003", "v4": "FR 600 004", "v5": "NE 600 005", "dup": "TI 600 009"}
    v = {}
    for k, body in (("v1", {"plaque": pl["v1"], "marque": "Skoda", "modele": "Octavia", "type_carburant": "Diesel", "capacite_reservoir_l": 50, "kilometrage": 42000}),
                    ("v2", {"plaque": pl["v2"], "marque": "VW", "modele": "ID.Buzz", "type_carburant": "Électrique", "kilometrage": 18000}),
                    ("v3", {"plaque": pl["v3"], "marque": "Ford", "modele": "Transit", "type_carburant": "Diesel", "kilometrage": 90000}),
                    ("v4", {"plaque": pl["v4"], "marque": "Renault", "modele": "Master", "type_carburant": "Diesel", "kilometrage": 61000}),
                    ("v5", {"plaque": pl["v5"], "marque": "Fiat", "modele": "Ducato", "type_carburant": "Diesel", "kilometrage": 30500}),
                    ("dupA", {"plaque": pl["dup"], "marque": "Toyota", "modele": "Proace", "kilometrage": 1000}),
                    ("dupB", {"plaque": pl["dup"].replace(" ", ""), "marque": "Toyota", "modele": "Proace City", "kilometrage": 2000})):
        r = post("/vehicles", body)
        assert r.status_code == 200, r.text
        v[k] = r.json()["id"]
    d1 = post("/drivers", {"nom": "Favre", "prenom": "Julien", "matricule_interne": "LF-01"}).json()["id"]
    assert post(f"/vehicles/{v['v3']}/driver-assignments", {"driver_id": d1, "valid_from": "2026-01-01"}).status_code == 200
    cards = {}

    def card(key, **b):
        r = post("/fuel-cards", {"type_affectation": "vehicule", "expire_le": "2030-12-31", **b})
        assert r.status_code == 200, r.text
        cards[key] = r.json()["id"]

    def assign(cid, **b):
        assert post(f"/fuel-cards/{cid}/assignments", {"type": "vehicule", "valid_from": "2026-01-01", **b}).status_code == 200
    card("migrol_1111", fournisseur="Migrol", last4="1111", external_card_id="MIG-1111"); assign(cards["migrol_1111"], vehicle_id=v["v1"])
    card("shell_2222_a", fournisseur="Shell", last4="2222", external_card_id="SH-A-2222"); assign(cards["shell_2222_a"], vehicle_id=v["v1"])
    card("shell_2222_b", fournisseur="Shell", last4="2222", external_card_id="SH-B-2222", collision_confirmed=True); assign(cards["shell_2222_b"], vehicle_id=v["v3"])
    card("migrol_3333_susp", fournisseur="Migrol", last4="3333"); assign(cards["migrol_3333_susp"], vehicle_id=v["v2"])
    assert post(f"/fuel-cards/{cards['migrol_3333_susp']}/status", {"statut": "suspendue", "motif": "Carte déclarée perdue"}).status_code == 200
    card("migrol_4444_exp", fournisseur="Migrol", last4="4444", expire_le="2026-03-31"); assign(cards["migrol_4444_exp"], vehicle_id=v["v1"])
    card("migrol_9999_v2", fournisseur="Migrol", last4="9999"); assign(cards["migrol_9999_v2"], vehicle_id=v["v2"])
    card("ionity_7777", fournisseur="Ionity", last4="7777"); assign(cards["ionity_7777"], vehicle_id=v["v2"])
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / "lotf_releve_mai.csv").write_bytes(csv_bytes(rows_mai(v)))
    (FIX / "lotf_releve_juin.csv").write_bytes(csv_bytes(rows_juin(v, pl)))
    (FIX / "lotf_releve_juin.xlsx").write_bytes(xlsx_bytes(rows_juin(v, pl)))
    (FIX / "lotf_releve_juillet.xlsx").write_bytes(xlsx_bytes(rows_juillet(v, pl)))
    up = lambda name, data: requests.post(f"{BASE}/api/fuel/imports", files={"file": (name, data)}, data={"fournisseur": "Migrol"}, headers=h, timeout=120)  # noqa: E731
    r = up("lotf_releve_mai.csv", (FIX / "lotf_releve_mai.csv").read_bytes()); assert r.status_code == 200, r.text
    job_mai = r.json()["id"]
    r = post(f"/fuel/imports/{job_mai}/mapping", {"mapping": MAPPING, "save_mapping": True}); assert r.status_code == 200, r.text
    r = post(f"/fuel/imports/{job_mai}/confirm", {}); assert r.status_code == 200, r.text
    confirm = r.json()
    r = up("lotf_releve_juillet.xlsx", (FIX / "lotf_releve_juillet.xlsx").read_bytes()); assert r.status_code == 200, r.text
    job_juillet = r.json()["id"]
    r = post(f"/fuel/imports/{job_juillet}/mapping", {"mapping": MAPPING}); assert r.status_code == 200, r.text
    an = requests.get(f"{BASE}/api/fuel/anomalies", params={"type": "incoherence_montant"}, headers=h, timeout=30).json()["items"]
    justified = None
    if an:
        r = post(f"/fuel/anomalies/{an[0]['id']}/decide", {"decision": "justify", "reason": "Facture fournisseur contrôlée : remise de fin de mois incluse dans le montant"})
        assert r.status_code == 200, r.text
        justified = an[0]["id"]
    print(json.dumps({"tenant": TENANT, "admin": ADMIN, "admin_password": pw_admin, "read_only": RO, "read_only_password": pw_ro, "vehicles": v, "plates": pl,
                      "driver": d1, "cards": cards, "job_mai_confirmed": job_mai, "confirm_mai": {k: confirm[k] for k in ("imported", "set_aside", "anomalies")},
                      "job_juillet_preview": job_juillet, "justified_anomaly": justified, "fixtures": sorted(p.name for p in FIX.iterdir())}, indent=1))
    inventory()


def inventory():
    out = {c: db[c].count_documents({"tenant_id": TENANT}) for c in sorted(db.list_collection_names())}
    out = {k: v for k, v in out.items() if v}
    out["tenants(id)"] = db.tenants.count_documents({"id": TENANT})
    out["login_attempts(identifier)"] = db.login_attempts.count_documents({"identifier": {"$regex": TENANT}}) if "login_attempts" in db.list_collection_names() else 0
    out["files/storage"] = {"files": db.files.count_documents({"tenant_id": TENANT}), "documents_with_storage_path": db.documents.count_documents({"tenant_id": TENANT, "storage_path": {"$nin": [None, ""]}})}
    out["fuel_transactions_card_id"] = {"with_card_id": db.fuel_transactions.count_documents({"tenant_id": TENANT, "card_id": {"$nin": [None, ""]}}),
                                         "without": db.fuel_transactions.count_documents({"tenant_id": TENANT, "card_id": None})}
    out["fuel_anomalies_by_status"] = {s["_id"]: s["n"] for s in db.fuel_anomalies.aggregate([{"$match": {"tenant_id": TENANT}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    out["fuel_import_jobs_by_status"] = {s["_id"]: s["n"] for s in db.fuel_import_jobs.aggregate([{"$match": {"tenant_id": TENANT}}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    print("INVENTORY", json.dumps(out, indent=1, ensure_ascii=False))
    return out


def verify():
    before = json.loads(BASELINE.read_text())
    after = fingerprint()
    diff = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k) and k != "tenants|None"}
    print("default / autres tenants inchangés depuis la baseline :", "OUI" if not diff else f"NON {json.dumps(diff, indent=1)}")
    print("Hash default avant/après :", before["default_sha256"][:16], after["default_sha256"][:16])
    if "default_sha256_stable" in before:
        print("Hash default STABLE (hors champs volatils Navixy de vehicles) avant/après :", before["default_sha256_stable"][:16], after["default_sha256_stable"][:16],
              "→", "IDENTIQUE" if before["default_sha256_stable"] == after["default_sha256_stable"] else "DIFFÉRENT")
    print("Tenants (hors cible) avant/après :", before["tenants_ids"] == after["tenants_ids"], "| `tenants|None` = nombre de documents tenants (dont la cible) : ignoré")
    print("Lot F dans default : card_id", db.fuel_transactions.count_documents({"tenant_id": "default", "card_id": {"$exists": True}}),
          "· matches", db.fuel_transaction_matches.count_documents({"tenant_id": "default"}), "· anomalies", db.fuel_anomalies.count_documents({"tenant_id": "default"}),
          "· jobs", db.fuel_import_jobs.count_documents({"tenant_id": "default"}), "· rows", db.fuel_import_rows.count_documents({"tenant_id": "default"}))
    print("Baselines default : Migrol 74.17 =", db.fuel_transactions.count_documents({"tenant_id": "default", "montant": 74.17}),
          "· facture 510.77 =", db.documents.count_documents({"tenant_id": "default", "montant": 510.77, "is_deleted": False}),
          "· amende 120 =", db.documents.count_documents({"tenant_id": "default", "montant": 120, "is_deleted": False}))
    return not diff


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    if cmd == "baseline":
        BASELINE.write_text(json.dumps(fingerprint(), indent=1))
        print("BASELINE écrite", BASELINE)
    else:
        {"seed": seed, "inventory": inventory, "verify": verify}[cmd]()
