"""Lot D — tenant UI isolé `lotd-ui-test` : création via API superadmin (jamais `default`), jeu de données Amendes
couvrant les 10 statuts + pièces liées, puis inventaire exact par collection. Idempotent (409 ignorés)."""
import json
import secrets
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TENANT = "lotd-ui-test"
ADMIN = f"lotd-admin@{TENANT}.ch"
RO = f"lotd-ro@{TENANT}.ch"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 160
D = lambda n: (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def main(mode):
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    if mode == "inventory":
        return inventory(db)
    sa = login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])
    pw_admin, pw_ro = "LotD-Admin-" + secrets.token_hex(3), "LotD-Ro-" + secrets.token_hex(3)
    r = requests.post(f"{BASE}/api/admin/tenants", json={"name": "Lot D UI test", "id": TENANT}, headers=sa, timeout=30)
    assert r.status_code in (200, 409), r.text
    for email, pw, role in ((ADMIN, pw_admin, "admin"), (RO, pw_ro, "read_only")):
        r = requests.post(f"{BASE}/api/admin/tenants/{TENANT}/users", json={"email": email, "password": pw, "role": role, "name": role}, headers=sa, timeout=30)
        assert r.status_code == 200, r.text
    h = login(ADMIN, pw_admin)
    post = lambda p, b: requests.post(f"{BASE}/api{p}", json=b, headers=h, timeout=60)  # noqa: E731
    v1 = post("/vehicles", {"plaque": "VD 400 001", "marque": "Skoda", "modele": "Octavia", "kilometrage": 42000, "type_carburant": "Diesel"}).json()["id"]
    v2 = post("/vehicles", {"plaque": "GE 400 002", "marque": "VW", "modele": "Caddy", "kilometrage": 18000}).json()["id"]
    d1 = post("/drivers", {"nom": "Dupont", "prenom": "Marc", "matricule_interne": "LD-01"}).json()["id"]
    d2 = post("/drivers", {"nom": "Rey", "prenom": "Sofia", "matricule_interne": "LD-02"}).json()["id"]
    base = {"motif": "Courrier papier non scanné (jeu de test Lot D)", "devise": "CHF", "source": "manual"}
    fines = [
        (v1, {"autorite": "Police cantonale vaudoise", "numero_amende": "LOTD-001", "date_infraction": D(-20), "delai_paiement": D(15), "montant": 120.0,
              "type_infraction": "speeding", "driver_id": d1, "lieu_infraction": {"ville": "Lausanne", "canton": "VD"}, "montant_amende": 100.0, "frais_admin": 20.0}),
        (v1, {"autorite": "Ville de Genève", "numero_amende": "LOTD-002", "date_infraction": D(-45), "delai_paiement": D(-10), "montant": 250.0,
              "type_infraction": "parking", "driver_id": d2, "priorite": "high"}),
        (v2, {"autorite": "Police municipale Nyon", "numero_amende": "LOTD-003", "date_infraction": D(-30), "delai_paiement": D(20), "montant": 180.0,
              "type_infraction": "speeding", "fine_status": "contestee", "driver_id": d1}),
        (v2, {"autorite": "Police cantonale vaudoise", "numero_amende": "LOTD-004", "date_infraction": D(-60), "delai_paiement": D(-30), "montant": 90.0,
              "type_infraction": "parking", "driver_id": d2}),
        (v1, {"autorite": "Ville de Lausanne", "numero_amende": "LOTD-005", "date_infraction": D(-50), "delai_paiement": D(-20), "montant": 60.0,
              "type_infraction": "parking"}),
        (v2, {"autorite": "Police cantonale fribourgeoise", "numero_amende": "LOTD-006", "date_infraction": D(-15), "delai_paiement": D(25), "montant": 40.0,
              "type_infraction": "other", "fine_status": "conducteur_a_identifier"}),
        (v1, {"autorite": "Police cantonale bernoise", "numero_amende": "LOTD-007", "date_infraction": D(-70), "delai_paiement": D(-40), "montant": 300.0,
              "type_infraction": "speeding", "driver_id": d1}),
        (v2, {"autorite": "Ville de Genève", "numero_amende": "LOTD-008", "date_infraction": D(-3), "montant": 40.0, "type_infraction": "parking", "fine_status": "recue"}),
    ]
    ids = []
    for vid, body in fines:
        r = post(f"/vehicles/{vid}/fines", {**base, **body})
        assert r.status_code == 200, r.text
        ids.append(r.json()["document_id"])
    # états terminaux UNIQUEMENT via les actions métier dédiées (jamais à la création)
    r = post(f"/documents/{ids[3]}/paid", {"payee": True, "paid_on": D(-35), "payment_ref": "VIR-LOTD-004"})
    assert r.status_code == 200, r.text
    r = post(f"/documents/{ids[6]}/fine-status", {"fine_status": "refacturee", "paid_on": D(-42), "motif": "Refacturée au conducteur"})
    assert r.status_code == 200, r.text
    r = post(f"/documents/{ids[4]}/fine-status", {"fine_status": "annulee", "motif": "Amende retirée par l'autorité (doublon)"})
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/api/documents/{ids[0]}/attachments", data={"piece_type": "courrier", "titre": "Courrier de l'autorité", "date_piece": D(-18),
                      "note": "Original au classeur"}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/api/documents/{ids[3]}/attachments", data={"piece_type": "preuve_paiement", "titre": "Quittance e-banking"},
                      files={"file": ("quittance.png", PNG, "image/png")}, headers=h, timeout=60)
    assert r.status_code == 200, r.text
    print(json.dumps({"tenant": TENANT, "admin": ADMIN, "admin_password": pw_admin, "read_only": RO, "read_only_password": pw_ro,
                      "vehicles": [v1, v2], "drivers": [d1, d2], "fines": ids}, indent=1))
    inventory(db)


def inventory(db):
    out = {}
    for coll in sorted(db.list_collection_names()):
        n = db[coll].count_documents({"tenant_id": TENANT})
        if n:
            out[coll] = n
    out["tenants(id)"] = db.tenants.count_documents({"id": TENANT})
    docs = list(db.documents.find({"tenant_id": TENANT}, {"_id": 0, "id": 1, "numero": 1, "fine_status": 1, "parent_document_id": 1, "storage_path": 1, "label": 1}))
    out["documents_detail"] = [{k: v for k, v in d.items() if v is not None} for d in docs]
    out["storage_objects"] = [d["storage_path"] for d in docs if d.get("storage_path")]
    print("INVENTORY", json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "seed")
