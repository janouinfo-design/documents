"""Lot E — tenant UI isolé `lote-ui-test` : création via API superadmin (jamais `default`), jeu de données cartes carburant
(statuts, expirations, collision last4 confirmée, affectations véhicule/conducteur, archivée), puis inventaire exact.
Usage : python lote_seed.py seed | inventory | cleanup"""
import hashlib
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TENANT = "lote-ui-test"
ADMIN, RO = f"lote-admin@{TENANT}.ch", f"lote-ro@{TENANT}.ch"
D = lambda n: (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def seed():
    sa = login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])
    pw_admin, pw_ro = "LotE-Admin-" + secrets.token_hex(3), "LotE-Ro-" + secrets.token_hex(3)
    r = requests.post(f"{BASE}/api/admin/tenants", json={"name": "Lot E UI test", "id": TENANT}, headers=sa, timeout=30)
    assert r.status_code in (200, 409), r.text
    for email, pw, role in ((ADMIN, pw_admin, "admin"), (RO, pw_ro, "read_only")):
        r = requests.post(f"{BASE}/api/admin/tenants/{TENANT}/users", json={"email": email, "password": pw, "role": role, "name": role}, headers=sa, timeout=30)
        assert r.status_code == 200, r.text
    h = login(ADMIN, pw_admin)
    post = lambda p, b: requests.post(f"{BASE}/api{p}", json=b, headers=h, timeout=60)  # noqa: E731
    v1 = post("/vehicles", {"plaque": "VD 500 001", "marque": "Skoda", "modele": "Octavia", "kilometrage": 42000}).json()["id"]
    v2 = post("/vehicles", {"plaque": "GE 500 002", "marque": "VW", "modele": "Caddy", "kilometrage": 18000}).json()["id"]
    d1 = post("/drivers", {"nom": "Dupont", "prenom": "Marc", "matricule_interne": "LE-01"}).json()["id"]
    d2 = post("/drivers", {"nom": "Rey", "prenom": "Sofia", "matricule_interne": "LE-02"}).json()["id"]
    cards = {}
    def card(key, **b):
        r = post("/fuel-cards", b)
        assert r.status_code == 200, r.text
        cards[key] = r.json()["id"]
    card("migrol_1234", fournisseur="Migrol", last4="1234", external_card_id="MIG-A-1234", type_affectation="vehicule", expire_le=D(400), activee_le=D(-200),
         produits_autorises=["diesel", "adblue"], pays_autorises=["CH"], plafond_tx=200)
    card("migrol_1234_bis", fournisseur="Migrol", last4="1234", external_card_id="MIG-B-1234", type_affectation="conducteur", expire_le=D(300), collision_confirmed=True)
    card("shell_5678", fournisseur="Shell", last4="5678", type_affectation="vehicule", expire_le=D(-15))          # expirée par date, statut active
    card("avia_9012", fournisseur="AVIA", last4="9012", type_affectation="vehicule", expire_le=D(20))            # expire bientôt (urgent)
    card("shell_3456", fournisseur="Shell", last4="3456", type_affectation="pool", expire_le=None)               # sans date, sans affectation
    card("migrol_7777", fournisseur="Migrol", last4="7777", type_affectation="vehicule", expire_le=D(500))       # sera suspendue
    card("avia_8888", fournisseur="AVIA", last4="8888", type_affectation="vehicule", expire_le=D(100))           # sera archivée
    r = post(f"/fuel-cards/{cards['migrol_7777']}/status", {"statut": "suspendue", "motif": "Carte déclarée perdue le " + D(-3)})
    assert r.status_code == 200, r.text
    r = post(f"/fuel-cards/{cards['avia_8888']}/archive", {"motif": "Contrat résilié"})
    assert r.status_code == 200, r.text
    asg = {}
    def assign(key, cid, **b):
        r = post(f"/fuel-cards/{cid}/assignments", b)
        assert r.status_code == 200, r.text
        asg[key] = r.json()["id"]
    assign("a1", cards["migrol_1234"], type="vehicule", vehicle_id=v1, valid_from=D(-120), motif="Mise en service")
    assign("a2", cards["migrol_1234"], type="conducteur", driver_id=d1, valid_from=D(-60), motif="Conducteur principal")
    assign("a3", cards["migrol_1234_bis"], type="conducteur", driver_id=d2, valid_from=D(-30))
    assign("a4", cards["shell_5678"], type="vehicule", vehicle_id=v2, valid_from=D(-300), motif="Historique")
    assign("a5", cards["avia_9012"], type="vehicule", vehicle_id=v1, valid_from=D(-200), valid_to=D(-121), motif="Ancienne carte du véhicule")
    print(json.dumps({"tenant": TENANT, "admin": ADMIN, "admin_password": pw_admin, "read_only": RO, "read_only_password": pw_ro,
                      "vehicles": {"VD 500 001": v1, "GE 500 002": v2}, "drivers": {"Marc Dupont": d1, "Sofia Rey": d2}, "cards": cards, "assignments": asg}, indent=1))
    inventory()


def inventory():
    out = {c: db[c].count_documents({"tenant_id": TENANT}) for c in sorted(db.list_collection_names())}
    out = {k: v for k, v in out.items() if v}
    out["tenants(id)"] = db.tenants.count_documents({"id": TENANT})
    out["fuel_cards_detail"] = [{k: v for k, v in c.items() if v is not None} for c in
                                db.fuel_cards.find({"tenant_id": TENANT}, {"_id": 0, "id": 1, "fournisseur": 1, "last4": 1, "statut": 1, "is_deleted": 1, "expire_le": 1})]
    out["storage_objects"] = []  # Lot E : aucun fichier
    print("INVENTORY", json.dumps(out, indent=1, ensure_ascii=False))


def fingerprint():
    fp = {}
    colls = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
    for c in colls:
        for row in db[c].aggregate([{"$match": {"tenant_id": {"$ne": TENANT}}}, {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}}]):
            fp[f"{c}|{row['_id']}"] = row["n"]
    h = hashlib.sha256()
    for c in colls:
        for d in db[c].find({"tenant_id": "default"}, {"_id": 0}).sort("id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
    fp["default_sha256"] = h.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TENANT}}, {"_id": 0, "id": 1}))
    return fp


def cleanup():
    before = fingerprint()
    inventory()
    deleted = {}
    for c in sorted(db.list_collection_names()):
        n = db[c].delete_many({"tenant_id": TENANT}).deleted_count
        if n:
            deleted[c] = n
    deleted["tenants(id)"] = db.tenants.delete_many({"id": TENANT}).deleted_count
    if "login_attempts" in db.list_collection_names():
        deleted["login_attempts(identifier)"] = db.login_attempts.delete_many({"identifier": {"$regex": TENANT}}).deleted_count
    print("SUPPRIMÉ:", json.dumps(deleted), "total =", sum(deleted.values()))
    residual = sum(db[c].count_documents({"$or": [{"tenant_id": TENANT}, {"email": {"$regex": TENANT}}]}) for c in db.list_collection_names())
    after = fingerprint()
    diff = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}
    print("Résidu cible:", residual, "| tenant doc:", db.tenants.count_documents({"id": TENANT}))
    print("default / autres tenants inchangés:", "OUI" if not diff else f"NON {diff}")
    print("Hash default avant/après:", before["default_sha256"][:16], after["default_sha256"][:16])
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ADMIN, "password": "x"}, timeout=30)
    print("Login compte supprimé:", r.status_code)


if __name__ == "__main__":
    {"seed": seed, "inventory": inventory, "cleanup": cleanup}[sys.argv[1] if len(sys.argv) > 1 else "inventory"]()
