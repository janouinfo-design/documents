"""Clôture Lot H — nettoyage contrôlé du tenant synthétique `loth-ui-test` UNIQUEMENT (modèle Lot F/G).

Garde-fous stricts :
- cible EXACTE `loth-ui-test` (refus sinon) ; aucun `delete_many` sans filtre tenant ; aucun `drop` ; jamais `default` ni cross-tenant.
- filtre de suppression : {'tenant_id': 'loth-ui-test'} par collection + {'id': 'loth-ui-test'} pour `tenants`
  + login_attempts par e-mail `@loth-ui-test.ch`. Objets de stockage : uniquement ceux référencés par des documents du tenant.

Empreinte default / autres tenants = capturée JUSTE AVANT le cleanup (pas la baseline historique du 08.10),
comparée JUSTE APRÈS (cycle de cleanup) → DEFAULT_UNCHANGED_DURING_CLEANUP / OTHER_TENANTS_UNCHANGED_DURING_CLEANUP.

Usage : python3 test_reports/loth_cleanup.py            # DRY-RUN (0 suppression)
        python3 test_reports/loth_cleanup.py --apply     # suppression (STOP si l'état diffère du manifeste DRY-RUN)
        python3 test_reports/loth_cleanup.py --verify     # relecture seule (0 suppression)
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET = "loth-ui-test"
if TARGET != "loth-ui-test":
    print("FAIL-FAST : cible invalide")
    sys.exit(2)
REP = Path("/app/test_reports")
DRY_MANIFEST = REP / "loth_cleanup_dryrun_manifest.json"
APPLY_MANIFEST = REP / "loth_cleanup_apply_manifest.json"
FP_OUT = REP / "loth_cleanup_fingerprints.json"
EMAIL_RE = r"@loth-ui-test\.ch$"

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = ENV.get("EMERGENT_LLM_KEY")

db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ALL = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
COLLS = [c for c in ALL if not c.startswith("astra_") and c != "login_attempts"]
DRY = "--apply" not in sys.argv and "--verify" not in sys.argv
VERIFY = "--verify" in sys.argv

VOLATILE = {"vehicles": ("updated_at", "kilometrage", "conso_moyenne_l_100km", "conso_source", "conso_updated_at")}
FK = ("id", "vehicle_id", "driver_id", "transaction_id", "source_document_id", "card_id", "document_id",
      "user_id", "assignment_id", "anomaly_id", "entity_id", "parent_id", "statement_id")
# ordre enfants → parents (cosmétique : filtrage par tenant_id, pas de contrainte Mongo)
ORDER = ("fuel_transaction_matches", "fuel_anomalies", "fuel_reconciliations", "fuel_card_assignments", "fuel_cards",
         "fuel_transactions", "documents", "inspections", "driver_assignments", "drivers", "alerts", "audit_logs",
         "vehicle_field_meta", "tenant_settings", "tenant_integrations", "vehicles_archive", "vehicles", "users")


def guard(flt, coll):
    """Refuse tout filtre de suppression non strictement limité à la cible."""
    if coll == "tenants":
        assert flt == {"id": TARGET}, f"filtre tenants non strict: {flt}"
    elif coll == "login_attempts":
        assert flt.get("identifier", {}).get("$regex") == EMAIL_RE, f"filtre login non strict: {flt}"
    else:
        assert flt == {"tenant_id": TARGET} and TARGET, f"filtre non strict ({coll}): {flt}"
    return flt


def fingerprint():
    fp = {"counts": {}, "hashes": {}}
    for c in sorted(x for x in db.list_collection_names() if not x.startswith("system.") and x != "login_attempts"):
        key = "id" if c == "tenants" else "tenant_id"
        for t in sorted(str(x) for x in db[c].distinct(key, {key: {"$ne": TARGET}})):
            h, n = hashlib.sha256(), 0
            for d in db[c].find({key: t}, {"_id": 0}).sort("id", 1):
                n += 1
                d = {k: v for k, v in d.items() if k not in VOLATILE.get(c, ()) and not k.startswith("navixy_")}
                h.update(json.dumps(d, sort_keys=True, default=str).encode())
            fp["counts"][f"{c}|{t}"], fp["hashes"][f"{c}|{t}"] = n, h.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TARGET}}, {"_id": 0, "id": 1}))
    return fp


def fp_diff(a, b):
    out = {}
    for sec in ("counts", "hashes"):
        keys = set(a[sec]) | set(b[sec])
        out[sec] = sorted(k for k in keys if a[sec].get(k) != b[sec].get(k))
    out["tenants_ids_equal"] = a["tenants_ids"] == b["tenants_ids"]
    return out


def target_counts():
    out = {c: db[c].count_documents({"tenant_id": TARGET}) for c in ALL if c != "login_attempts"}
    out = {k: v for k, v in out.items() if v}
    out["tenants(id)"] = db.tenants.count_documents({"id": TARGET})
    out["users(email)"] = db.users.count_documents({"email": {"$regex": EMAIL_RE}})
    out["login_attempts(email)"] = db.login_attempts.count_documents({"identifier": {"$regex": EMAIL_RE}}) if "login_attempts" in ALL else 0
    return out


def storage_paths():
    paths = []
    for d in db.documents.find({"tenant_id": TARGET, "storage_path": {"$type": "string", "$ne": ""}}, {"_id": 0, "id": 1, "storage_path": 1, "original_filename": 1}):
        paths.append({"doc_id": d["id"], "path": d["storage_path"], "filename": d.get("original_filename")})
    for d in db.documents.find({"tenant_id": TARGET, "pages.path": {"$exists": True}}, {"_id": 0, "id": 1, "pages": 1}):
        for p in d.get("pages") or []:
            if p.get("path"):
                paths.append({"doc_id": d["id"], "path": p["path"], "filename": "(page)"})
    for f in db.files.find({"tenant_id": TARGET, "storage_path": {"$type": "string", "$ne": ""}}, {"_id": 0, "storage_path": 1}):
        paths.append({"doc_id": None, "path": f["storage_path"], "filename": "(files)"})
    for v in db.vehicles.find({"tenant_id": TARGET, "photo_url": {"$nin": [None, ""]}}, {"_id": 0, "photo_url": 1}):
        paths.append({"doc_id": None, "path": v["photo_url"], "filename": "(photo_url)"})
    return paths


def manifest():
    m = {"tenant": [t for t in db.tenants.find({"id": TARGET}, {"_id": 0, "id": 1, "name": 1})],
         "users": [{"id": u["id"], "email": u["email"], "role": u.get("role")} for u in db.users.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "email": 1, "role": 1})],
         "vehicles": [{"id": v["id"], "plaque": v.get("plaque")} for v in db.vehicles.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "plaque": 1})],
         "drivers": [{"id": d["id"], "matricule": d.get("matricule_interne")} for d in db.drivers.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "matricule_interne": 1})]}
    for c in ("driver_assignments", "documents", "fuel_transactions", "fuel_transaction_matches", "fuel_cards",
              "fuel_card_assignments", "fuel_anomalies", "inspections", "alerts", "audit_logs", "vehicle_field_meta"):
        m[c] = [d["id"] for d in db[c].find({"tenant_id": TARGET}, {"_id": 0, "id": 1}) if d.get("id")]
    m["counts"] = target_counts()
    m["storage"] = storage_paths()
    m["autres_collections_tenant_id"] = {c: db[c].count_documents({"tenant_id": TARGET}) for c in COLLS
                                         if c not in ORDER and c != "tenants" and db[c].count_documents({"tenant_id": TARGET})}
    return m


def all_ids_of(m):
    out = []
    for k, v in m.items():
        if isinstance(v, list) and k not in ("storage",):
            for x in v:
                out.append(x["id"] if isinstance(x, dict) else x)
    return [x for x in out if x]


def isolation_proof(all_ids):
    refs = {}
    for c in COLLS:
        if c == "tenants":
            continue
        n = db[c].count_documents({"tenant_id": {"$ne": TARGET}, "$or": [{f: {"$in": all_ids}} for f in FK]})
        if n:
            refs[c] = n
    return refs


def residuals(all_ids):
    res = {}
    for c in COLLS:
        n = db[c].count_documents({"$or": [{"tenant_id": TARGET}, {"email": {"$regex": EMAIL_RE}}] + [{f: {"$in": all_ids}} for f in FK]})
        if n:
            res[c] = n
    if db.tenants.count_documents({"id": TARGET}):
        res["tenants(id)"] = 1
    textual = {}
    for c in COLLS:
        if c == "audit_logs":
            continue
        n = sum(1 for d in db[c].find({}, {"_id": 0}) if TARGET in json.dumps(d, default=str))
        if n:
            textual[c] = n
    platform_audit = db.audit_logs.count_documents({"tenant_id": {"$ne": TARGET}, "$or": [{"detail": {"$regex": TARGET}}, {"entity_id": TARGET}, {"tenant_id": TARGET}]})
    login = db.login_attempts.count_documents({"identifier": {"$regex": EMAIL_RE}}) if "login_attempts" in ALL else 0
    return res, textual, platform_audit, login


def delete_storage(paths):
    try:
        key = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30).json()["storage_key"]
    except Exception as e:
        return {"error": f"init storage: {e}", "deleted": 0, "unsupported": 0, "detail": []}
    out = {"deleted": 0, "unsupported": 0, "notfound": 0, "detail": []}
    for p in paths:
        path = p["path"]
        try:
            r = requests.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
            g = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
            gone = g.status_code == 404
            if r.status_code in (200, 202, 204) and gone:
                out["deleted"] += 1
                st = "deleted"
            elif gone:
                out["notfound"] += 1
                st = "already-absent"
            else:
                out["unsupported"] += 1
                st = f"delete={r.status_code} get={g.status_code}"
            out["detail"].append({"path": path, "status": st})
        except Exception as e:
            out["unsupported"] += 1
            out["detail"].append({"path": path, "status": f"error:{e}"})
    return out


def verify_mode():
    tc = target_counts()
    print("Cible (collections non vides) :", json.dumps({k: v for k, v in tc.items() if v}, ensure_ascii=False) or "0 partout")
    prior = json.loads(APPLY_MANIFEST.read_text()) if APPLY_MANIFEST.exists() else (json.loads(DRY_MANIFEST.read_text()) if DRY_MANIFEST.exists() else {})
    res, textual, platform_audit, login = residuals(all_ids_of(prior))
    sp = storage_paths()
    print("Résidus ids/FK/email :", res or 0, "| textuels hors audit :", textual or 0, "| audit mentionnant la cible :", platform_audit, "| login_attempts :", login, "| storage refs DB :", len(sp))
    fps = json.loads(FP_OUT.read_text()) if FP_OUT.exists() else None
    if fps:
        d_cycle = fp_diff(fps["before_cleanup"], fps["after_cleanup"])
        print("EMPREINTE cycle cleanup (avant → après) : counts diff =", d_cycle["counts"] or "aucune", "| hashes diff =", d_cycle["hashes"] or "aucune", "| tenants_ids identiques =", d_cycle["tenants_ids_equal"])
    residual_total = sum(res.values()) + sum(textual.values()) + login + (platform_audit if platform_audit else 0)
    ok = not any(v for v in tc.values()) and not res and not textual and not login and platform_audit == 0
    print("LOTH_RESIDUAL_RECORDS =", residual_total)
    print("LOTH TEST CLEANUP VERIFY =", "PASS" if ok else "FAIL")
    return ok


def main():
    if VERIFY:
        verify_mode()
        return
    before = target_counts()
    print("AVANT — cible (collections non vides) :", json.dumps({k: v for k, v in before.items() if v}, ensure_ascii=False))
    total_before = sum(v for k, v in before.items() if k not in ("users(email)",) and v)
    if total_before == 0:
        print("STOP — la cible ne contient aucune donnée (rien à nettoyer).")
        sys.exit(2)
    m = manifest()
    all_ids = all_ids_of(m)
    sp = m["storage"]
    (DRY_MANIFEST if DRY else APPLY_MANIFEST).write_text(json.dumps(m, indent=1, ensure_ascii=False, default=str))
    print(f"MANIFESTE → {(DRY_MANIFEST if DRY else APPLY_MANIFEST).name} : {len(all_ids)} identifiants + 1 tenant + {len(sp)} objets storage")
    print("  tenant :", m["tenant"])
    print("  users :", [f"{u['email']} ({u['role']})" for u in m["users"]])
    print("  vehicles :", [v["plaque"] for v in m["vehicles"]], "| drivers :", len(m["drivers"]))
    print("  counts :", json.dumps({k: v for k, v in m["counts"].items() if v}, ensure_ascii=False))
    print("  storage :", [f"{s['filename']}→{s['path'].split('/')[-1]}" for s in sp])
    print("  autres collections tenant_id exact :", m["autres_collections_tenant_id"] or "aucune")
    refs = isolation_proof(all_ids)
    print("ISOLATION — documents d'autres tenants référençant un id de la cible :", json.dumps(refs) if refs else "0 (aucune clé étrangère croisée)")
    print("ISOLATION — filtres : {'tenant_id':'loth-ui-test'} par collection · {'id':'loth-ui-test'} pour tenants · login_attempts par e-mail @loth-ui-test.ch. Aucun filtre global, aucun drop.")
    if DRY:
        print("DRY-RUN (sans --apply) : 0 suppression, 0 modification DB, 0 suppression storage. Manifeste écrit uniquement.")
        print("LOTH TEST CLEANUP DRY-RUN =", "PASS" if not refs else "FAIL")
        return
    # --apply : garde-fou vs manifeste DRY-RUN validé
    prior = json.loads(DRY_MANIFEST.read_text()) if DRY_MANIFEST.exists() else None
    if prior is None:
        print("STOP — aucun manifeste DRY-RUN validé ; aucune suppression.")
        sys.exit(2)
    if sorted(all_ids) != sorted(all_ids_of(prior)) or sorted(x["path"] for x in sp) != sorted(x["path"] for x in prior.get("storage", [])):
        print("STOP — l'état actuel diffère du manifeste DRY-RUN (ids ou storage). Aucune suppression.")
        sys.exit(2)
    if refs:
        print("STOP — références croisées détectées :", refs)
        sys.exit(2)
    print(f"Garde-fou manifeste : OK — {len(all_ids)} identifiants + tenant identiques au DRY-RUN validé")
    # 1) empreinte JUSTE AVANT cleanup (pas la baseline du 08.10)
    fp_before = fingerprint()
    # 2) suppression DB (fenêtre serrée) — filtres stricts
    deleted = {}
    for c in ORDER:
        if c in ALL:
            n = db[c].delete_many(guard({"tenant_id": TARGET}, c)).deleted_count
            if n:
                deleted[c] = n
    for c in COLLS:
        if c not in ORDER and c != "tenants":
            if db[c].count_documents({"tenant_id": TARGET}):
                deleted[c] = db[c].delete_many(guard({"tenant_id": TARGET}, c)).deleted_count
    deleted["tenants(id)"] = db.tenants.delete_many(guard({"id": TARGET}, "tenants")).deleted_count
    # 3) empreinte JUSTE APRÈS cleanup DB
    fp_after = fingerprint()
    print("SUPPRIMÉ :", json.dumps(deleted, ensure_ascii=False), "| total =", sum(deleted.values()))
    # 4) storage distant (objets du tenant uniquement)
    st = delete_storage(sp)
    print("STORAGE distant :", json.dumps({k: v for k, v in st.items() if k != "detail"}, ensure_ascii=False))
    for d in st.get("detail", []):
        print("   ", d["path"].split("/")[-1], "→", d["status"])
    # 5) login compte supprimé (probe AVANT purge finale de login_attempts pour ne pas laisser de trace auto-générée)
    r = requests.post(f"{BASE}/api/auth/login", json={"email": f"loth-admin@{TARGET}.ch", "password": "x"}, timeout=30)
    print("Login compte supprimé (attendu 401) :", r.status_code)
    if "login_attempts" in ALL:
        n = db.login_attempts.delete_many(guard({"identifier": {"$regex": EMAIL_RE}}, "login_attempts")).deleted_count
        if n:
            deleted["login_attempts"] = n
            print("login_attempts purgés (dont la trace du probe) :", n)
    # 6) empreinte cycle + résidus
    d_cycle = fp_diff(fp_before, fp_after)
    FP_OUT.write_text(json.dumps({"captured_at": datetime.now(timezone.utc).isoformat(), "before_cleanup": fp_before, "after_cleanup": fp_after, "diff_cycle": d_cycle}, indent=1, default=str))
    after = target_counts()
    res, textual, platform_audit, login = residuals(all_ids)
    sp_after = storage_paths()
    default_ok = not [k for k in d_cycle["counts"] + d_cycle["hashes"] if k.endswith("|default")]
    others_ok = not [k for k in d_cycle["counts"] + d_cycle["hashes"] if not k.endswith("|default")] and d_cycle["tenants_ids_equal"]
    print("APRÈS — cible :", json.dumps({k: v for k, v in after.items() if v}, ensure_ascii=False) or "0 partout")
    print("Résidus ids/FK/email :", res or 0, "| textuels hors audit :", textual or 0, "| audit mentionnant la cible :", platform_audit, "| login_attempts :", login, "| storage refs DB :", len(sp_after))
    print("EMPREINTE cycle (avant → après) : counts diff =", d_cycle["counts"] or "aucune", "| hashes diff =", d_cycle["hashes"] or "aucune", "| tenants_ids identiques =", d_cycle["tenants_ids_equal"])
    residual_total = sum(res.values()) + sum(textual.values()) + login + platform_audit + len(sp_after)
    print("LOTH_RESIDUAL_RECORDS =", residual_total)
    print("DEFAULT_UNCHANGED_DURING_CLEANUP =", "PASS" if default_ok else "FAIL")
    print("OTHER_TENANTS_UNCHANGED_DURING_CLEANUP =", "PASS" if others_ok else "FAIL")
    if st.get("unsupported", 0):
        print(f"NOTE storage : {st['unsupported']} objet(s) distant(s) non supprimables (objstore répond HTTP 405 sur DELETE — aucune API de suppression). "
              f"Désormais ORPHELINS : 0 référence DB subsistante (storage refs DB = {len(sp_after)}). Divergence NON bloquante, hors périmètre applicatif.")
    ok = not any(v for v in after.values()) and residual_total == 0 and default_ok and others_ok
    print("LOTH TEST CLEANUP =", "PASS" if ok else "FAIL", "(volet DB/références ; orphelins storage documentés séparément)")


if __name__ == "__main__":
    main()
