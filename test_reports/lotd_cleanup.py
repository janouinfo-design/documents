"""Clôture Lot D — nettoyage vérifié du tenant isolé `lotd-ui-test` UNIQUEMENT.
Étapes : empreinte avant (toutes collections, tous tenants ≠ cible) → suppression ciblée tenant_id exact → objets storage
(DELETE si supporté, sinon neutralisation 0 octet) → preuves : 0 résidu, `default` et autres tenants identiques, chemins inaccessibles."""
import hashlib
import json
import sys

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET = "lotd-ui-test"
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
COLLS = sorted(c for c in db.list_collection_names() if not c.startswith("system."))


def fingerprint():
    """Compte par (collection, tenant) hors cible + hash du contenu des collections du tenant default (hors _id)."""
    fp = {}
    for c in COLLS:
        for row in db[c].aggregate([{"$match": {"tenant_id": {"$ne": TARGET}}}, {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}}]):
            fp[f"{c}|{row['_id']}"] = row["n"]
        fp[f"{c}|__total_sans_cible__"] = db[c].count_documents({"tenant_id": {"$ne": TARGET}}) if c != "tenants" else db[c].count_documents({"id": {"$ne": TARGET}})
    h = hashlib.sha256()
    for c in COLLS:
        for d in db[c].find({"tenant_id": "default"}, {"_id": 0}).sort("id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
    fp["default_sha256"] = h.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({}, {"_id": 0, "id": 1}))
    return fp


def target_counts():
    out = {c: db[c].count_documents({"tenant_id": TARGET}) for c in COLLS}
    out["tenants(id)"] = db.tenants.count_documents({"id": TARGET})
    out["users(email)"] = db.users.count_documents({"email": {"$regex": f"@{TARGET}\\.ch$"}})
    out["login_attempts(identifier)"] = db.login_attempts.count_documents({"identifier": {"$regex": TARGET}}) if "login_attempts" in COLLS else 0
    return {k: v for k, v in out.items() if v}


def storage_neutralize(paths):
    from pathlib import Path
    sys.path.insert(0, "/app/backend")
    import storage  # noqa: E402  (même configuration que le backend : STORAGE_URL / clé)
    key = storage._init_remote()
    res = {}
    for p in paths:
        r = requests.delete(f"{storage.STORAGE_URL}/objects/{p}", headers={"X-Storage-Key": key}, timeout=60)
        if r.status_code in (200, 204, 404):
            res[p] = {"delete": r.status_code}
            continue
        r2 = requests.put(f"{storage.STORAGE_URL}/objects/{p}", headers={"X-Storage-Key": key, "Content-Type": "application/octet-stream"}, data=b"", timeout=60)
        g = requests.get(f"{storage.STORAGE_URL}/objects/{p}", headers={"X-Storage-Key": key}, timeout=60)
        res[p] = {"delete": r.status_code, "neutralize_put": r2.status_code, "size_after": len(g.content) if g.status_code == 200 else f"http {g.status_code}"}
    return res


def main():
    before_target = target_counts()
    paths = [d["storage_path"] for d in db.documents.find({"tenant_id": TARGET, "storage_path": {"$type": "string"}}, {"_id": 0, "storage_path": 1})]
    user_ids = [u["id"] for u in db.users.find({"tenant_id": TARGET}, {"_id": 0, "id": 1})]
    fp_before = fingerprint()
    print("AVANT cible:", json.dumps(before_target, ensure_ascii=False))
    print("Objets storage référencés:", paths)
    deleted = {}
    for c in COLLS:
        n = db[c].delete_many({"tenant_id": TARGET}).deleted_count
        if n:
            deleted[c] = n
    deleted["tenants(id)"] = db.tenants.delete_many({"id": TARGET}).deleted_count
    if "login_attempts" in COLLS:
        deleted["login_attempts(identifier)"] = db.login_attempts.delete_many({"identifier": {"$regex": TARGET}}).deleted_count
    print("SUPPRIMÉ:", json.dumps(deleted, ensure_ascii=False), "total =", sum(deleted.values()))
    print("STORAGE:", json.dumps(storage_neutralize(paths), ensure_ascii=False))
    after_target = target_counts()
    fp_after = fingerprint()
    diff = {k: (fp_before.get(k), fp_after.get(k)) for k in set(fp_before) | set(fp_after) if fp_before.get(k) != fp_after.get(k)}
    print("APRÈS cible (doit être vide):", json.dumps(after_target, ensure_ascii=False))
    print("Autres tenants / default inchangés:", "OUI" if not diff else f"NON {diff}")
    print("Hash default avant/après:", fp_before["default_sha256"][:16], fp_after["default_sha256"][:16])
    print("Tenants restants:", fp_after["tenants_ids"])
    # résidus textuels éventuels (hors audit plateforme du superadmin)
    residual = {}
    for c in COLLS:
        if c == "audit_logs":
            continue
        n = db[c].count_documents({"$or": [{"tenant_id": TARGET}, {"email": {"$regex": TARGET}}, {"id": {"$in": user_ids}}]})
        if n:
            residual[c] = n
    print("Résidus hors audit plateforme:", json.dumps(residual) if residual else "0")
    print("Audit plateforme mentionnant la cible (traçabilité superadmin, conservé):",
          db.audit_logs.count_documents({"tenant_id": {"$ne": TARGET}, "detail": {"$regex": TARGET}}))
    # accès aux chemins : jeton admin default → jamais 200
    r = requests.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}, timeout=30)
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    print("Accès /api/files par le tenant default:", {p.split('/')[-1]: requests.get(f"{BASE}/api/files/{p}", headers=h, timeout=30).status_code for p in paths})
    r = requests.post(f"{BASE}/api/auth/login", json={"email": f"lotd-admin@{TARGET}.ch", "password": "x"}, timeout=30)
    print("Login compte supprimé:", r.status_code)


if __name__ == "__main__":
    main()
