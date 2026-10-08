"""Clôture Lot G — nettoyage contrôlé du tenant isolé `lotg-ui-test` UNIQUEMENT (tenant_id exact), modèle Lot F.
DRY-RUN par défaut (0 suppression) : garde-fou comptes attendus (inventaire post-it.47), inventaire storage, manifeste exact
(`lotg_cleanup_dryrun_manifest.json`), preuve d'isolation (0 clé étrangère croisée), empreinte default/autres tenants (même
fingerprint stable que `lotg_seed.py` → comparable à `lotg_baseline_before_seed.json`). `--apply` = STOP si les ids diffèrent du
manifeste DRY-RUN, suppression ordonnée enfants → parents, preuves 0 résidu. `--verify` = relecture seule."""
import importlib.util
import json
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET = "lotg-ui-test"
REP = Path("/app/test_reports")
MANIFEST = REP / "lotg_cleanup_dryrun_manifest.json"
BASELINE = REP / "lotg_baseline_before_seed.json"
FP_OUT = REP / "lotg_cleanup_fingerprints.json"
EXPECTED = {"tenants(id)": 1, "users": 2, "vehicles": 5, "vehicle_field_meta": 3, "tenant_settings": 1, "fuel_snapshots": 7, "fuel_cards": 5,
            "fuel_card_assignments": 5, "fuel_import_jobs": 4, "fuel_import_rows": 7, "documents": 21, "fuel_transactions": 20,
            "fuel_transaction_matches": 20, "fuel_anomalies": 3, "fuel_reconciliations": 2, "fuel_statements": 6, "fuel_statement_lines": 20, "audit_logs": 127}
EXPECTED_ZERO = ("alerts", "files", "inspections", "drivers", "driver_assignments", "fuel_import_mappings", "tenant_integrations", "vehicles_archive")
ORDER = ("fuel_statement_lines", "fuel_statements", "fuel_reconciliations", "fuel_anomalies", "fuel_transaction_matches", "fuel_import_rows",
         "fuel_import_jobs", "fuel_import_mappings", "fuel_transactions", "documents", "fuel_card_assignments", "fuel_cards", "fuel_snapshots",
         "driver_assignments", "drivers", "audit_logs", "alerts", "files", "inspections", "vehicle_field_meta", "tenant_settings", "tenant_integrations",
         "legacy_vehicle_map", "legacy_tenant_map", "vehicles_archive", "document_transfers", "vehicles", "users")
FK = ("id", "card_id", "vehicle_id", "transaction_id", "job_id", "document_id", "source_document_id", "driver_id", "import_job_id", "user_id",
      "statement_id", "parent_statement_id", "forced_duplicate_of", "anomaly_id", "row_id")
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ALL = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
COLLS = [c for c in ALL if not c.startswith("astra_") and c != "login_attempts"]
DRY = "--apply" not in sys.argv

_spec = importlib.util.spec_from_file_location("lotg_seed", REP / "lotg_seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)
fingerprint = _seed.fingerprint  # counts + sha256 stable (hors champs volatils Navixy) + raw + tenants_ids, par (collection | tenant ≠ cible)

NAVIXY_KEYS = {"vehicles|default", "tenant_integrations|default"}  # collections écrites par le job horaire Navixy (hors Lot G)


def fp_diff(a, b):
    out = {}
    for sec in ("counts", "hashes", "hashes_raw"):
        keys = set(a[sec]) | set(b[sec])
        out[sec] = sorted(k for k in keys if a[sec].get(k) != b[sec].get(k))
    out["tenants_ids_equal"] = a["tenants_ids"] == b["tenants_ids"]
    return out


def target_counts():
    out = {c: db[c].count_documents({"tenant_id": TARGET}) for c in ALL if c != "login_attempts"}
    out["tenants(id)"] = db.tenants.count_documents({"id": TARGET})
    out["users(email)"] = db.users.count_documents({"email": {"$regex": f"@{TARGET}\\.ch$"}})
    out["login_attempts(identifier)"] = db.login_attempts.count_documents({"identifier": {"$regex": TARGET}}) if "login_attempts" in ALL else 0
    return out


def show(title, counts):
    nz = {k: v for k, v in counts.items() if v}
    print(f"{title}: {json.dumps(nz, ensure_ascii=False) if nz else '0 partout'}")


def ids(coll, field="id"):
    return [d[field] for d in db[coll].find({"tenant_id": TARGET}, {"_id": 0, field: 1}) if d.get(field)]


def manifest():
    m = {"tenant": [t for t in db.tenants.find({"id": TARGET}, {"_id": 0, "id": 1, "name": 1})]}
    m["users"] = [{"id": u["id"], "email": u["email"], "role": u["role"]} for u in db.users.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "email": 1, "role": 1})]
    m["vehicles"] = [{"id": v["id"], "plaque": v.get("plaque")} for v in db.vehicles.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "plaque": 1})]
    m["fuel_cards"] = [{"id": c["id"], "carte": f"{c.get('fournisseur')} ••••{c.get('last4')}", "statut": c.get("statut")} for c in db.fuel_cards.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "fournisseur": 1, "last4": 1, "statut": 1})]
    m["fuel_card_assignments"] = ids("fuel_card_assignments")
    m["fuel_snapshots"] = [f"{s['vehicle_id']}|{s['day']}" for s in db.fuel_snapshots.find({"tenant_id": TARGET}, {"_id": 0, "vehicle_id": 1, "day": 1})]  # pas de champ id : clé (véhicule, jour)
    m["fuel_import_jobs"] = [{"id": j["id"], "filename": j.get("filename"), "status": j.get("status"), "rows": j.get("row_count")} for j in db.fuel_import_jobs.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "filename": 1, "status": 1, "row_count": 1})]
    m["fuel_import_rows"] = ids("fuel_import_rows")
    m["fuel_import_mappings"] = ids("fuel_import_mappings")
    m["documents"] = ids("documents")
    m["fuel_transactions"] = [{"id": t["id"], "locked": bool(t.get("locked")), "statement_number": t.get("statement_number")} for t in db.fuel_transactions.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "locked": 1, "statement_number": 1})]
    m["fuel_transaction_matches"] = ids("fuel_transaction_matches")
    m["fuel_anomalies"] = [{"id": a["id"], "type": a.get("type"), "status": a.get("status")} for a in db.fuel_anomalies.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "type": 1, "status": 1})]
    m["fuel_reconciliations"] = [{"id": r["id"], "period_month": r.get("period_month"), "vehicle_id": r.get("vehicle_id")} for r in db.fuel_reconciliations.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "period_month": 1, "vehicle_id": 1})]
    m["fuel_statements"] = [{"id": s["id"], "number": s.get("number"), "type": s.get("type"), "status": s.get("status"), "close_exception": bool(s.get("close_exception"))} for s in db.fuel_statements.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "number": 1, "type": 1, "status": 1, "close_exception": 1})]
    m["fuel_statement_lines"] = ids("fuel_statement_lines")
    m["audit_logs"] = ids("audit_logs")
    m["vehicle_field_meta"] = db.vehicle_field_meta.count_documents({"tenant_id": TARGET})
    m["tenant_settings"] = db.tenant_settings.count_documents({"tenant_id": TARGET})
    m["login_attempts(identifier)"] = [d["identifier"] for d in db.login_attempts.find({"identifier": {"$regex": TARGET}}, {"_id": 0, "identifier": 1})] if "login_attempts" in ALL else []
    m["autres_collections_avec_tenant_id"] = {c: db[c].count_documents({"tenant_id": TARGET}) for c in COLLS if c not in ORDER and c != "tenants" and db[c].count_documents({"tenant_id": TARGET})}
    return m


def all_ids_of(m):
    return [x["id"] if isinstance(x, dict) else x for k, v in m.items() if isinstance(v, list) and k not in ("login_attempts(identifier)", "fuel_snapshots") for x in v if (x.get("id") if isinstance(x, dict) else x)]


def isolation_proof(all_ids):
    refs = {}
    for c in COLLS:
        if c == "tenants":
            continue
        n = db[c].count_documents({"tenant_id": {"$ne": TARGET}, "$or": [{f: {"$in": all_ids}} for f in FK]})
        if n:
            refs[c] = n
    return refs


def storage_refs():
    return {"documents.storage_path": [d["storage_path"] for d in db.documents.find({"tenant_id": TARGET, "storage_path": {"$type": "string", "$ne": ""}}, {"_id": 0, "storage_path": 1})],
            "documents.pages.path": [p.get("path") for d in db.documents.find({"tenant_id": TARGET, "pages.path": {"$exists": True}}, {"_id": 0, "pages": 1}) for p in d.get("pages") or []],
            "files.storage_path": [f.get("storage_path") for f in db.files.find({"tenant_id": TARGET}, {"_id": 0, "storage_path": 1})],
            "fuel_import_jobs.storage_path": [j.get("storage_path") for j in db.fuel_import_jobs.find({"tenant_id": TARGET, "storage_path": {"$nin": [None, ""]}}, {"_id": 0, "storage_path": 1})],
            "vehicles.photo_url": [v["photo_url"] for v in db.vehicles.find({"tenant_id": TARGET, "photo_url": {"$nin": [None, ""]}}, {"_id": 0, "photo_url": 1})]}


def residuals(all_ids):
    res = {}
    for c in COLLS:
        n = db[c].count_documents({"$or": [{"tenant_id": TARGET}, {"email": {"$regex": TARGET}}] + [{f: {"$in": all_ids}} for f in FK]})
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
    platform_audit = db.audit_logs.count_documents({"tenant_id": {"$ne": TARGET}, "$or": [{"detail": {"$regex": TARGET}}, {"entity_id": TARGET}]})
    login = db.login_attempts.count_documents({"identifier": {"$regex": TARGET}}) if "login_attempts" in ALL else 0
    return res, textual, platform_audit, login


def compare_to_baseline(fp_now, label):
    base = json.loads(BASELINE.read_text())
    d = fp_diff(base, fp_now)
    non_navixy_hash = [k for k in d["hashes"] if k not in NAVIXY_KEYS]
    print(f"BASELINE ({BASELINE.name}) vs {label} : counts diff={d['counts'] or 'aucune'} · hashes stables diff={d['hashes'] or 'aucune'}"
          f" · tenants_ids identiques={d['tenants_ids_equal']}" + (f" · hors job Navixy : {non_navixy_hash or 'aucune'}" if d["hashes"] else ""))
    return d, non_navixy_hash


def main():
    if "--verify" in sys.argv:
        show("Cible (toutes collections)", target_counts())
        fp = fingerprint()
        d, non_nav = compare_to_baseline(fp, "maintenant")
        prior = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        res, textual, platform_audit, login = residuals(all_ids_of(prior))
        print("Résidus ids/FK/email:", res or 0, "| textuels hors audit:", textual or 0, "| audit autres tenants mentionnant la cible:", platform_audit, "| login_attempts:", login)
        for c in ("fuel_statements", "fuel_statement_lines", "fuel_reconciliations", "fuel_snapshots"):
            print(f"  {c} total base: {db[c].count_documents({})} (default: {db[c].count_documents({'tenant_id': 'default'})})")
        fps = json.loads(FP_OUT.read_text()) if FP_OUT.exists() else None
        if fps:
            d_cycle = fp_diff(fps["before_cleanup"], fp)
            print("EMPREINTE avant-cleanup → maintenant : counts diff =", d_cycle["counts"] or "aucune", "| hashes stables diff =", d_cycle["hashes"] or "aucune", "| tenants_ids identiques =", d_cycle["tenants_ids_equal"])
        base_counts = json.loads(BASELINE.read_text())["counts"]
        print("DRIFT vs baseline initiale (counts) :", {k: (base_counts.get(k), fp["counts"].get(k)) for k in d["counts"]} or "identiques", "| hashes stables :", d["hashes"] or "identiques")
        ok = not any(target_counts().values()) and not res and not textual and not login and d["tenants_ids_equal"] and (not fps or (not d_cycle["counts"] and not d_cycle["hashes"]))
        print("LOTG TEST CLEANUP VERIFY =", "PASS" if ok else "FAIL")
        return
    before = target_counts()
    show("AVANT — cible (collections non vides)", before)
    mismatch = {k: (before.get(k), v) for k, v in EXPECTED.items() if before.get(k) != v}
    mismatch.update({k: (before.get(k), 0) for k in EXPECTED_ZERO if before.get(k)})
    unexpected = {k: v for k, v in before.items() if v and k not in EXPECTED and k not in EXPECTED_ZERO and k not in ("users(email)", "login_attempts(identifier)")}
    if mismatch or unexpected:
        print("STOP — comptes différents de l'inventaire post-it.47 (observé, attendu):", json.dumps(mismatch), "| collections inattendues:", json.dumps(unexpected))
        sys.exit(2)
    print("Garde-fou comptes attendus : OK (inventaire post-it.47 : 1 tenant · 2 users · 5 vehicles · 3 vehicle_field_meta · 1 tenant_settings · 7 snapshots · 5 cards · 5 assignments · 4 jobs · 7 rows · 21 documents · 20 tx · 20 matches · 3 anomalies · 2 reconciliations · 6 statements · 20 lines · 127 audit)")
    sr = storage_refs()
    print("STORAGE — objets référencés par la cible:", json.dumps(sr), "→ total", sum(len(v) for v in sr.values()))
    m = manifest()
    (MANIFEST if DRY else REP / "lotg_cleanup_apply_manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False, default=str))
    all_ids = all_ids_of(m)
    print(f"MANIFESTE exact → {MANIFEST if DRY else 'lotg_cleanup_apply_manifest.json'} ({len(all_ids)} identifiants + 1 tenant + {len(m['login_attempts(identifier)'])} login_attempts)")
    print("  tenant:", m["tenant"])
    print("  users:", [u["email"] + " (" + u["role"] + ")" for u in m["users"]])
    print("  vehicles:", [v["plaque"] for v in m["vehicles"]])
    print("  fuel_cards:", [f"{c['carte']} [{c['statut']}]" for c in m["fuel_cards"]], "| assignments:", len(m["fuel_card_assignments"]), "| snapshots:", len(m["fuel_snapshots"]))
    print("  fuel_import_jobs:", [f"{j['filename']} [{j['status']}, {j['rows']} lignes]" for j in m["fuel_import_jobs"]], "| rows:", len(m["fuel_import_rows"]))
    print("  fuel_statements:", [f"{s['number']} [{s['type']}, {s['status']}{', exception' if s['close_exception'] else ''}]" for s in m["fuel_statements"]], "| lines:", len(m["fuel_statement_lines"]))
    print("  fuel_transactions:", len(m["fuel_transactions"]), "dont locked:", sum(1 for t in m["fuel_transactions"] if t["locked"]), "| matches:", len(m["fuel_transaction_matches"]), "| documents:", len(m["documents"]))
    print("  fuel_anomalies:", [f"{a['type']}/{a['status']}" for a in m["fuel_anomalies"]], "| reconciliations:", [(r["period_month"], r["vehicle_id"][:8]) for r in m["fuel_reconciliations"]])
    print("  audit_logs:", len(m["audit_logs"]), "| vehicle_field_meta:", m["vehicle_field_meta"], "| tenant_settings:", m["tenant_settings"], "| login_attempts:", m["login_attempts(identifier)"])
    print("  autres collections portant le tenant_id exact :", m["autres_collections_avec_tenant_id"] or "aucune")
    fp_before = fingerprint()
    compare_to_baseline(fp_before, "avant cleanup")
    refs = isolation_proof(all_ids)
    print("ISOLATION — documents d'autres tenants référençant un identifiant de la cible :", json.dumps(refs) if refs else "0 (aucune clé étrangère croisée)")
    print("ISOLATION — filtre de suppression : {'tenant_id': '%s'} exact par collection + {'id': '%s'} pour `tenants` + login_attempts par identifiant e-mail du tenant ; aucun filtre global." % (TARGET, TARGET))
    if DRY:
        print("DRY-RUN (sans --apply) : 0 suppression, 0 modification. Fichier écrit : manifeste uniquement.")
        print("LOTG TEST CLEANUP DRY-RUN =", "PASS" if not refs and not any(len(v) for v in sr.values()) else "FAIL")
        return
    prior = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
    if prior is None:
        print("STOP — aucun manifeste DRY-RUN validé ; aucune suppression.")
        sys.exit(2)
    norm = lambda v: sorted(x["id"] if isinstance(x, dict) else x for x in v) if isinstance(v, list) else v  # noqa: E731
    delta = {k: (len(prior.get(k) or []) if isinstance(prior.get(k), list) else prior.get(k), len(m.get(k) or []) if isinstance(m.get(k), list) else m.get(k))
             for k in set(prior) | set(m) if k != "login_attempts(identifier)" and norm(prior.get(k)) != norm(m.get(k))}
    if delta or refs or any(len(v) for v in sr.values()):
        print("STOP — l'état actuel diffère du manifeste DRY-RUN validé (clé: avant, maintenant) :", json.dumps(delta, default=str), "| refs croisées:", refs, "| storage:", sr)
        sys.exit(2)
    print(f"Garde-fou manifeste : OK — {len(all_ids)} identifiants identiques au DRY-RUN validé + tenant {TARGET}")
    deleted = {}
    for c in ORDER:
        if c in ALL:
            n = db[c].delete_many({"tenant_id": TARGET}).deleted_count
            if n:
                deleted[c] = n
    for c in COLLS:
        if c not in ORDER and c != "tenants":
            n = db[c].delete_many({"tenant_id": TARGET}).deleted_count
            if n:
                deleted[c] = n
    deleted["tenants(id)"] = db.tenants.delete_many({"id": TARGET}).deleted_count
    r = requests.post(f"{BASE}/api/auth/login", json={"email": f"lotg-admin@{TARGET}.ch", "password": "x"}, timeout=30)
    print("Login compte supprimé (attendu 401):", r.status_code)
    n = db.login_attempts.delete_many({"identifier": {"$regex": f"@{TARGET}\\.ch$"}}).deleted_count
    if n:
        deleted["login_attempts(identifier)"] = n
    print("SUPPRIMÉ (lines → statements → reconciliations → anomalies → matches → rows → jobs → tx → documents → affectations → cartes → snapshots → audit → meta → settings → vehicles → users → tenant → login_attempts):",
          json.dumps(deleted, ensure_ascii=False), "total =", sum(deleted.values()))
    after = target_counts()
    show("APRÈS — cible", after)
    fp_after = fingerprint()
    d_cycle = fp_diff(fp_before, fp_after)
    print("EMPREINTE avant/après cleanup (default + autres tenants) : counts diff =", d_cycle["counts"] or "aucune", "| hashes stables diff =", d_cycle["hashes"] or "aucune",
          "| hashes bruts diff =", d_cycle["hashes_raw"] or "aucune", "| tenants_ids identiques =", d_cycle["tenants_ids_equal"])
    d_base, non_nav = compare_to_baseline(fp_after, "après cleanup")
    FP_OUT.write_text(json.dumps({"before_cleanup": fp_before, "after_cleanup": fp_after, "diff_cycle": d_cycle, "diff_vs_baseline": d_base}, indent=1, default=str))
    res, textual, platform_audit, login = residuals(all_ids)
    print("Résidus par identifiants (tous ids du manifeste, clés étrangères, email):", json.dumps(res) if res else "0")
    print(f"Résidus textuels « {TARGET} » hors audit_logs:", json.dumps(textual) if textual else "0")
    print("Audit autres tenants mentionnant la cible :", platform_audit, "| login_attempts restants :", login)
    for c in ("fuel_statements", "fuel_statement_lines", "fuel_reconciliations", "fuel_snapshots", "fuel_cards", "fuel_import_jobs", "fuel_anomalies"):
        print(f"  {c} total base: {db[c].count_documents({})} (default: {db[c].count_documents({'tenant_id': 'default'})})")
    ok = not any(after.values()) and not res and not textual and not login and not d_cycle["counts"] and not d_cycle["hashes"] and d_cycle["tenants_ids_equal"]
    drift = sorted(set(d_base["counts"] + d_base["hashes"]))
    print("DEFAULT_UNCHANGED (cycle cleanup : empreinte avant → après, counts + hashes stables + bruts) =", "PASS" if not [k for k in d_cycle["hashes"] + d_cycle["hashes_raw"] + d_cycle["counts"] if k.endswith("|default")] else "FAIL")
    print("OTHER_TENANTS_UNCHANGED (cycle cleanup) =", "PASS" if not [k for k in d_cycle["hashes"] + d_cycle["hashes_raw"] + d_cycle["counts"] if not k.endswith("|default")] and d_cycle["tenants_ids_equal"] else "FAIL")
    print("DRIFT vs baseline initiale (hors cycle cleanup, à attribuer explicitement dans le rapport) :", drift or "aucun",
          "| counts :", {k: (json.loads(BASELINE.read_text())["counts"].get(k), fp_after["counts"].get(k)) for k in d_base["counts"]} or "identiques")
    print("LOTG TEST CLEANUP =", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
