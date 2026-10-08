"""Clôture technique Lot E — nettoyage vérifié du tenant isolé `lote-ui-test` UNIQUEMENT (tenant_id exact).
Garde-fou : les comptes attendus (rapport Lot E) doivent correspondre exactement, sinon STOP sans suppression.
Étapes : inventaire avant → empreinte (autres tenants + hash `default`) → suppression ordonnée → preuves 0 résidu,
`default` / autres tenants identiques, storage, login compte supprimé."""
import hashlib
import json
import sys

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET = "lote-ui-test"
EXPECTED = {"tenants(id)": 1, "users": 2, "vehicles": 2, "drivers": 2, "fuel_cards": 9, "fuel_card_assignments": 8, "audit_logs": 34}
EXPECTED_ZERO = ("alerts", "documents", "fuel_transactions", "files", "inspections", "driver_assignments")
ORDER = ("fuel_card_assignments", "fuel_cards", "audit_logs", "alerts", "documents", "files", "inspections", "fuel_transactions",
         "driver_assignments", "tenant_settings", "tenant_integrations", "legacy_vehicle_map", "legacy_tenant_map", "vehicles_archive",
         "document_transfers", "vehicle_field_meta", "fuel_snapshots", "drivers", "vehicles", "users")
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ALL = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
COLLS = [c for c in ALL if not c.startswith("astra_")]  # référentiel ASTRA : sans tenant_id (vérifié séparément)
DRY = "--apply" not in sys.argv


def fingerprint():
    fp = {}
    for c in COLLS:
        if c == "tenants":  # documents tenant : clé `id` (pas de tenant_id) → le tenant cible est exclu par `id`
            fp["tenants|count_hors_cible"] = db.tenants.count_documents({"id": {"$ne": TARGET}})
            continue
        for row in db[c].aggregate([{"$match": {"tenant_id": {"$ne": TARGET}}}, {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}}]):
            fp[f"{c}|{row['_id']}"] = row["n"]
    fp["tenants|ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TARGET}}, {"_id": 0, "id": 1}))
    h = hashlib.sha256()
    for c in COLLS:
        for d in db[c].find({"tenant_id": "default"}, {"_id": 0}).sort("id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
    fp["default|sha256"] = h.hexdigest()
    fp["default|baselines"] = {
        "fuel_cards": db.fuel_cards.count_documents({"tenant_id": "default"}),
        "fuel_card_assignments": db.fuel_card_assignments.count_documents({"tenant_id": "default"}),
        "migrol_74.17": db.fuel_transactions.count_documents({"tenant_id": "default", "montant": 74.17, "card_id": {"$exists": False}}),
        "facture_510.77": db.documents.count_documents({"tenant_id": "default", "montant": 510.77, "is_deleted": False}),
        "amende_120": db.documents.count_documents({"tenant_id": "default", "montant": 120, "is_deleted": False}),
        "alerts": db.alerts.count_documents({"tenant_id": "default"}),
        "audit_logs": db.audit_logs.count_documents({"tenant_id": "default"})}
    for c in ALL:
        if c.startswith("astra_"):
            fp[f"{c}|tenant_id_present"] = db[c].count_documents({"tenant_id": {"$exists": True}})
    return fp


def target_counts():
    out = {c: db[c].count_documents({"tenant_id": TARGET}) for c in ALL}
    out["tenants(id)"] = db.tenants.count_documents({"id": TARGET})
    out["users(email)"] = db.users.count_documents({"email": {"$regex": f"@{TARGET}\\.ch$"}})
    out["login_attempts(identifier)"] = db.login_attempts.count_documents({"identifier": {"$regex": TARGET}})
    return out


def show(title, counts):
    nz = {k: v for k, v in counts.items() if v}
    print(f"{title}: {json.dumps(nz, ensure_ascii=False) if nz else '0 partout'}")


def main():
    if "--verify" in sys.argv:  # re-contrôle indépendant de l'état après nettoyage (lecture seule)
        show("Cible (toutes collections)", target_counts())
        fp = fingerprint()
        print("default sha256:", fp["default|sha256"][:16], "baselines:", json.dumps(fp["default|baselines"]))
        print("tenants hors cible:", fp["tenants|count_hors_cible"], fp["tenants|ids"])
        print("fuel_cards total base:", db.fuel_cards.count_documents({}), "· fuel_card_assignments total base:", db.fuel_card_assignments.count_documents({}))
        return
    before = target_counts()
    show("AVANT cible (collections non vides)", before)
    mismatch = {k: (before.get(k), v) for k, v in EXPECTED.items() if before.get(k) != v}
    mismatch.update({k: (before.get(k), 0) for k in EXPECTED_ZERO if before.get(k)})
    if mismatch:
        print("STOP — comptes différents du rapport Lot E (observé, attendu):", json.dumps(mismatch))
        sys.exit(2)
    print("Garde-fou comptes attendus : OK (9 cartes · 8 affectations · 2 users · 2 vehicles · 2 drivers · 34 audit · 0 alerts/documents/files/tx)")
    storage_refs = {
        "documents.storage_path": [d["storage_path"] for d in db.documents.find({"tenant_id": TARGET, "storage_path": {"$type": "string"}}, {"_id": 0, "storage_path": 1})],
        "documents.pages.path": [p.get("path") for d in db.documents.find({"tenant_id": TARGET, "pages.path": {"$exists": True}}, {"_id": 0, "pages": 1}) for p in d.get("pages") or []],
        "files.storage_path": [f["storage_path"] for f in db.files.find({"tenant_id": TARGET}, {"_id": 0, "storage_path": 1})],
        "inspections.photos.path": [p.get("path") for i in db.inspections.find({"tenant_id": TARGET}, {"_id": 0, "photos": 1}) for p in i.get("photos") or []],
        "vehicles.photo_url": [v["photo_url"] for v in db.vehicles.find({"tenant_id": TARGET, "photo_url": {"$nin": [None, ""]}}, {"_id": 0, "photo_url": 1})]}
    print("STORAGE — objets référencés par le tenant cible:", json.dumps(storage_refs), "→ total", sum(len(v) for v in storage_refs.values()))
    user_ids = [u["id"] for u in db.users.find({"tenant_id": TARGET}, {"_id": 0, "id": 1})]
    card_ids = [c["id"] for c in db.fuel_cards.find({"tenant_id": TARGET}, {"_id": 0, "id": 1})]
    fp_before = fingerprint()
    print("Empreinte avant — default sha256:", fp_before["default|sha256"][:16], "baselines:", json.dumps(fp_before["default|baselines"]))
    if DRY:
        print("DRY-RUN (sans --apply) : aucune suppression effectuée.")
        return
    deleted = {}
    for c in ORDER:
        n = db[c].delete_many({"tenant_id": TARGET}).deleted_count
        if n:
            deleted[c] = n
    for c in ALL:  # toute autre collection portant le tenant_id exact
        if c not in ORDER and not c.startswith("astra_"):
            n = db[c].delete_many({"tenant_id": TARGET}).deleted_count
            if n:
                deleted[c] = n
    deleted["tenants(id)"] = db.tenants.delete_many({"id": TARGET}).deleted_count
    r = requests.post(f"{BASE}/api/auth/login", json={"email": f"lote-admin@{TARGET}.ch", "password": "x"}, timeout=30)
    print("Login compte supprimé (attendu 401):", r.status_code)
    # le contrôle de login ci-dessus incrémente le compteur anti-force-brute → purge APRÈS, par identifiant exact du tenant cible
    n = db.login_attempts.delete_many({"identifier": {"$regex": f"\\|[^|]+@{TARGET}\\.ch$"}}).deleted_count
    if n:
        deleted["login_attempts(identifier)"] = n
    print("SUPPRIMÉ (ordre : affectations → cartes → audit/alertes/enfants → drivers → vehicles → users → tenant):",
          json.dumps(deleted, ensure_ascii=False), "total =", sum(deleted.values()))
    after = target_counts()
    show("APRÈS cible", after)
    fp_after = fingerprint()
    diff = {k: (fp_before.get(k), fp_after.get(k)) for k in set(fp_before) | set(fp_after) if fp_before.get(k) != fp_after.get(k)}
    print("default + autres tenants inchangés:", "OUI" if not diff else f"NON {json.dumps(diff, default=str)}")
    print("Hash default avant/après:", fp_before["default|sha256"][:16], fp_after["default|sha256"][:16])
    print("Baselines default après:", json.dumps(fp_after["default|baselines"]))
    print("Tenants restants:", fp_after["tenants|ids"])
    # Résidus par identifiant (ids users/cartes) et résidus textuels hors audit plateforme
    residual = {}
    for c in COLLS:
        q = [{"tenant_id": TARGET}, {"id": {"$in": user_ids + card_ids}}, {"card_id": {"$in": card_ids}}, {"email": {"$regex": TARGET}}]
        n = db[c].count_documents({"$or": q})
        if n:
            residual[c] = n
    textual = {}
    for c in COLLS:
        if c == "audit_logs":
            continue
        n = sum(1 for d in db[c].find({}, {"_id": 0}) if TARGET in json.dumps(d, default=str))
        if n:
            textual[c] = n
    print("Résidus par identifiants (users/cartes/email):", json.dumps(residual) if residual else "0")
    print("Résidus textuels « lote-ui-test » hors audit_logs:", json.dumps(textual) if textual else "0")
    print("Audit plateforme (autres tenants) mentionnant la cible :", db.audit_logs.count_documents({"tenant_id": {"$ne": TARGET}, "detail": {"$regex": TARGET}}))
    print("fuel_cards total base:", db.fuel_cards.count_documents({}), "· fuel_card_assignments total base:", db.fuel_card_assignments.count_documents({}))
    print("LOTE TEST CLEANUP =", "PASS" if not any(after.values()) and not residual and not textual and not diff else "FAIL")


if __name__ == "__main__":
    main()
