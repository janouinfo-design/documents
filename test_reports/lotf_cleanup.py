"""Clôture Lot F — nettoyage contrôlé du tenant isolé `lotf-ui-test` UNIQUEMENT (tenant_id exact), modèle Lot E.
DRY-RUN par défaut (0 suppression, 0 modification) : inventaire, empreinte des autres tenants + hash `default`, manifeste exact
des éléments qui seraient supprimés (`lotf_cleanup_dryrun_manifest.json`), contrôle d'isolation. `--apply` = suppression ordonnée
puis preuves 0 résidu (collections, identifiants, texte, login_attempts, storage) et `default` / autres tenants identiques. `--verify` = relecture seule.
Garde-fou : les comptes doivent correspondre exactement au rapport Lot F, sinon STOP sans suppression."""
import hashlib
import json
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
TARGET = "lotf-ui-test"
MANIFEST = Path("/app/test_reports/lotf_cleanup_dryrun_manifest.json")
MANIFEST_PRIOR = MANIFEST
EXPECTED = {"tenants(id)": 1, "users": 2, "vehicles": 7, "drivers": 1, "driver_assignments": 1, "fuel_cards": 7, "fuel_card_assignments": 7,
            "fuel_import_jobs": 5, "fuel_import_rows": 70, "fuel_import_mappings": 1, "documents": 22, "fuel_transactions": 22,
            "fuel_transaction_matches": 22, "fuel_anomalies": 12, "audit_logs": 93, "vehicle_field_meta": 1}
EXPECTED_ZERO = ("alerts", "files", "inspections", "login_attempts(identifier)", "tenant_settings", "tenant_integrations")
ORDER = ("fuel_anomalies", "fuel_transaction_matches", "fuel_import_rows", "fuel_import_jobs", "fuel_import_mappings", "fuel_transactions",
         "documents", "fuel_card_assignments", "fuel_cards", "driver_assignments", "drivers", "audit_logs", "alerts", "files", "inspections",
         "vehicle_field_meta", "tenant_settings", "tenant_integrations", "legacy_vehicle_map", "legacy_tenant_map", "vehicles_archive",
         "document_transfers", "fuel_snapshots", "vehicles", "users")
db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ALL = sorted(c for c in db.list_collection_names() if not c.startswith("system."))
COLLS = [c for c in ALL if not c.startswith("astra_")]  # référentiel ASTRA : sans tenant_id (vérifié séparément)
DRY = "--apply" not in sys.argv
VOLATILE_VEHICLE = ("updated_at", "kilometrage")  # écrits par le job horaire Navixy (+ navixy_*)


def fingerprint():
    fp = {}
    for c in COLLS:
        if c == "tenants":
            fp["tenants|count_hors_cible"] = db.tenants.count_documents({"id": {"$ne": TARGET}})
            continue
        for row in db[c].aggregate([{"$match": {"tenant_id": {"$ne": TARGET}}}, {"$group": {"_id": "$tenant_id", "n": {"$sum": 1}}}]):
            fp[f"{c}|{row['_id']}"] = row["n"]
    fp["tenants|ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": TARGET}}, {"_id": 0, "id": 1}))
    h, hs = hashlib.sha256(), hashlib.sha256()
    for c in COLLS:
        for d in db[c].find({"tenant_id": "default"}, {"_id": 0}).sort("id", 1):
            h.update(json.dumps(d, sort_keys=True, default=str).encode())
            if c == "vehicles":
                d = {k: v for k, v in d.items() if k not in VOLATILE_VEHICLE and not k.startswith("navixy_")}
            hs.update(json.dumps(d, sort_keys=True, default=str).encode())
    fp["default|sha256"] = h.hexdigest()
    fp["default|sha256_stable"] = hs.hexdigest()
    fp["default|baselines"] = {
        "fuel_cards": db.fuel_cards.count_documents({"tenant_id": "default"}),
        "fuel_card_assignments": db.fuel_card_assignments.count_documents({"tenant_id": "default"}),
        "fuel_import_jobs": db.fuel_import_jobs.count_documents({"tenant_id": "default"}),
        "fuel_anomalies": db.fuel_anomalies.count_documents({"tenant_id": "default"}),
        "fuel_transaction_matches": db.fuel_transaction_matches.count_documents({"tenant_id": "default"}),
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
    out["login_attempts(identifier)"] = db.login_attempts.count_documents({"identifier": {"$regex": TARGET}}) if "login_attempts" in ALL else 0
    return out


def show(title, counts):
    nz = {k: v for k, v in counts.items() if v}
    print(f"{title}: {json.dumps(nz, ensure_ascii=False) if nz else '0 partout'}")


def ids(coll, field="id"):
    return [d[field] for d in db[coll].find({"tenant_id": TARGET}, {"_id": 0, field: 1}) if d.get(field)]


def manifest():
    """Liste exacte, par collection, des éléments qui seraient supprimés (identifiants + libellés lisibles)."""
    m = {"tenant": [t for t in db.tenants.find({"id": TARGET}, {"_id": 0, "id": 1, "name": 1})]}
    m["users"] = [{"id": u["id"], "email": u["email"], "role": u["role"]} for u in db.users.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "email": 1, "role": 1})]
    m["vehicles"] = [{"id": v["id"], "plaque": v.get("plaque")} for v in db.vehicles.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "plaque": 1})]
    m["drivers"] = [{"id": d["id"], "nom": f"{d.get('prenom', '')} {d.get('nom', '')}".strip()} for d in db.drivers.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "nom": 1, "prenom": 1})]
    m["driver_assignments"] = ids("driver_assignments")
    m["fuel_cards"] = [{"id": c["id"], "carte": f"{c.get('fournisseur')} ••••{c.get('last4')}", "statut": c.get("statut")} for c in db.fuel_cards.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "fournisseur": 1, "last4": 1, "statut": 1})]
    m["fuel_card_assignments"] = ids("fuel_card_assignments")
    m["fuel_import_jobs"] = [{"id": j["id"], "filename": j.get("filename"), "status": j.get("status"), "rows": j.get("row_count")} for j in db.fuel_import_jobs.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "filename": 1, "status": 1, "row_count": 1})]
    m["fuel_import_rows"] = ids("fuel_import_rows")
    m["fuel_import_mappings"] = ids("fuel_import_mappings")
    m["documents"] = ids("documents")
    m["fuel_transactions"] = ids("fuel_transactions")
    m["fuel_transaction_matches"] = ids("fuel_transaction_matches")
    m["fuel_anomalies"] = [{"id": a["id"], "type": a.get("type"), "status": a.get("status")} for a in db.fuel_anomalies.find({"tenant_id": TARGET}, {"_id": 0, "id": 1, "type": 1, "status": 1})]
    m["audit_logs"] = ids("audit_logs")
    m["vehicle_field_meta"] = db.vehicle_field_meta.count_documents({"tenant_id": TARGET})
    m["autres_collections_avec_tenant_id"] = {c: db[c].count_documents({"tenant_id": TARGET}) for c in COLLS if c not in ORDER and c != "tenants" and db[c].count_documents({"tenant_id": TARGET})}
    return m


def summary(m):
    agg = {
        "documents": {"n": len(m["documents"]), "source_import": db.documents.count_documents({"tenant_id": TARGET, "source": "import"}), "avec_fichier": db.documents.count_documents({"tenant_id": TARGET, "storage_path": {"$nin": [None, ""]}})},
        "fuel_transactions": {"n": len(m["fuel_transactions"]), "card_id_renseigne": db.fuel_transactions.count_documents({"tenant_id": TARGET, "card_id": {"$nin": [None, ""]}}),
                              "somme_montant": round(sum(t.get("montant") or 0 for t in db.fuel_transactions.find({"tenant_id": TARGET}, {"_id": 0, "montant": 1})), 2)},
        "fuel_anomalies_par_type_statut": {f"{a['type']}/{a['status']}": sum(1 for b in m["fuel_anomalies"] if b["type"] == a["type"] and b["status"] == a["status"]) for a in m["fuel_anomalies"]},
        "fuel_import_jobs_par_statut": {j["status"]: sum(1 for k in m["fuel_import_jobs"] if k["status"] == j["status"]) for j in m["fuel_import_jobs"]},
        "audit_logs_par_action": {r["_id"]: r["n"] for r in db.audit_logs.aggregate([{"$match": {"tenant_id": TARGET}}, {"$group": {"_id": {"$concat": ["$entity", "/", "$action"]}, "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}])},
    }
    return agg


def isolation_proof(all_ids):
    """Aucun document d'un autre tenant ne référence un identifiant de la cible (clé étrangère) ; aucun id de la cible ailleurs."""
    refs = {}
    for c in COLLS:
        if c == "tenants":
            continue
        q = {"tenant_id": {"$ne": TARGET}, "$or": [{"id": {"$in": all_ids}}, {"card_id": {"$in": all_ids}}, {"vehicle_id": {"$in": all_ids}}, {"transaction_id": {"$in": all_ids}},
                                                   {"job_id": {"$in": all_ids}}, {"document_id": {"$in": all_ids}}, {"source_document_id": {"$in": all_ids}}, {"driver_id": {"$in": all_ids}},
                                                   {"import_job_id": {"$in": all_ids}}, {"user_id": {"$in": all_ids}}]}
        n = db[c].count_documents(q)
        if n:
            refs[c] = n
    return refs


def main():
    if "--verify" in sys.argv:
        show("Cible (toutes collections)", target_counts())
        fp = fingerprint()
        print("default sha256:", fp["default|sha256"][:16], "| stable:", fp["default|sha256_stable"][:16], "| baselines:", json.dumps(fp["default|baselines"]))
        print("tenants hors cible:", fp["tenants|count_hors_cible"], fp["tenants|ids"])
        for c in ("fuel_cards", "fuel_card_assignments", "fuel_import_jobs", "fuel_import_rows", "fuel_import_mappings", "fuel_anomalies", "fuel_transaction_matches"):
            print(f"  {c} total base: {db[c].count_documents({})}")
        return
    before = target_counts()
    show("AVANT — cible (collections non vides)", before)
    mismatch = {k: (before.get(k), v) for k, v in EXPECTED.items() if before.get(k) != v}
    mismatch.update({k: (before.get(k), 0) for k in EXPECTED_ZERO if before.get(k)})
    unexpected = {k: v for k, v in before.items() if v and k not in EXPECTED and k not in EXPECTED_ZERO and k != "users(email)"}
    if mismatch or unexpected:
        print("STOP — comptes différents du rapport Lot F (observé, attendu):", json.dumps(mismatch), "| collections inattendues:", json.dumps(unexpected))
        sys.exit(2)
    print("Garde-fou comptes attendus : OK (rapport Lot F : 1 tenant · 2 users · 7 vehicles · 1 driver · 1 driver_assignment · 7 cards · 7 assignments · 5 jobs · 70 rows · 1 mapping · 22 documents · 22 tx · 22 matches · 12 anomalies · 93 audit · 1 vehicle_field_meta · 0 alerts/files/inspections/login_attempts)")
    storage_refs = {
        "documents.storage_path": [d["storage_path"] for d in db.documents.find({"tenant_id": TARGET, "storage_path": {"$type": "string"}}, {"_id": 0, "storage_path": 1})],
        "documents.pages.path": [p.get("path") for d in db.documents.find({"tenant_id": TARGET, "pages.path": {"$exists": True}}, {"_id": 0, "pages": 1}) for p in d.get("pages") or []],
        "files.storage_path": [f["storage_path"] for f in db.files.find({"tenant_id": TARGET}, {"_id": 0, "storage_path": 1})],
        "fuel_import_jobs.storage": [j.get("storage_path") for j in db.fuel_import_jobs.find({"tenant_id": TARGET, "storage_path": {"$exists": True}}, {"_id": 0, "storage_path": 1})],
        "vehicles.photo_url": [v["photo_url"] for v in db.vehicles.find({"tenant_id": TARGET, "photo_url": {"$nin": [None, ""]}}, {"_id": 0, "photo_url": 1})]}
    print("STORAGE — objets référencés par la cible:", json.dumps(storage_refs), "→ total", sum(len(v) for v in storage_refs.values()), "(les fichiers importés ne sont pas conservés : seul le sha256 est stocké dans le job)")
    m = manifest()
    if DRY:
        MANIFEST.write_text(json.dumps(m, indent=1, ensure_ascii=False, default=str))
    else:
        Path(str(MANIFEST).replace("dryrun", "apply")).write_text(json.dumps(m, indent=1, ensure_ascii=False, default=str))
    all_ids = [x["id"] if isinstance(x, dict) else x for k, v in m.items() if isinstance(v, list) for x in v if (x.get("id") if isinstance(x, dict) else x)]
    print(f"MANIFESTE exact des éléments qui seraient supprimés → {MANIFEST} ({len(all_ids)} identifiants + 1 tenant)")
    print("  users:", [u["email"] + " (" + u["role"] + ")" for u in m["users"]])
    print("  vehicles:", [v["plaque"] for v in m["vehicles"]])
    print("  drivers:", [d["nom"] for d in m["drivers"]], "| driver_assignments:", len(m["driver_assignments"]))
    print("  fuel_cards:", [f"{c['carte']} [{c['statut']}]" for c in m["fuel_cards"]], "| assignments:", len(m["fuel_card_assignments"]))
    print("  fuel_import_jobs:", [f"{j['filename']} [{j['status']}, {j['rows']} lignes]" for j in m["fuel_import_jobs"]], "| rows:", len(m["fuel_import_rows"]), "| mappings:", len(m["fuel_import_mappings"]))
    print("  agrégats:", json.dumps(summary(m), ensure_ascii=False))
    print("  autres collections portant le tenant_id exact :", m["autres_collections_avec_tenant_id"] or "aucune")
    fp_before = fingerprint()
    print("EMPREINTE avant — default sha256:", fp_before["default|sha256"][:16], "| stable:", fp_before["default|sha256_stable"][:16], "| baselines:", json.dumps(fp_before["default|baselines"]))
    print("  tenants hors cible:", fp_before["tenants|count_hors_cible"], fp_before["tenants|ids"])
    print("  collections ASTRA (référentiel sans tenant_id, non touchées) :", {k: v for k, v in fp_before.items() if k.endswith("tenant_id_present")})
    refs = isolation_proof(all_ids)
    print("ISOLATION — documents d'autres tenants référençant un identifiant de la cible :", json.dumps(refs) if refs else "0 (aucune clé étrangère croisée)")
    print("ISOLATION — filtre de suppression : {'tenant_id': '%s'} exact par collection + {'id': '%s'} pour `tenants` ; aucun `$regex`, aucun filtre global." % (TARGET, TARGET))
    if DRY:
        print("DRY-RUN (sans --apply) : 0 suppression, 0 modification. Fichiers écrits : manifeste uniquement.")
        print("LOTF TEST CLEANUP DRY-RUN =", "PASS" if not refs and not any(len(v) for v in storage_refs.values()) else "FAIL")
        return
    # Garde-fou --apply : les identifiants actuels doivent être EXACTEMENT ceux du manifeste validé au DRY-RUN (sinon STOP avant tout DELETE)
    prior = json.loads(MANIFEST_PRIOR.read_text()) if MANIFEST_PRIOR.exists() else None
    if prior is None:
        print("STOP — aucun manifeste DRY-RUN validé (lotf_cleanup_dryrun_manifest.json absent) ; aucune suppression.")
        sys.exit(2)
    norm = lambda v: sorted(x["id"] if isinstance(x, dict) else x for x in v) if isinstance(v, list) else v  # noqa: E731
    delta = {k: (len(prior.get(k) or []) if isinstance(prior.get(k), list) else prior.get(k), len(m.get(k) or []) if isinstance(m.get(k), list) else m.get(k))
             for k in set(prior) | set(m) if norm(prior.get(k)) != norm(m.get(k))}
    if delta or refs or any(len(v) for v in storage_refs.values()):
        print("STOP — l'état actuel diffère du manifeste DRY-RUN validé (clé: avant, maintenant) :", json.dumps(delta, default=str), "| refs croisées:", refs, "| storage:", storage_refs)
        sys.exit(2)
    print(f"Garde-fou manifeste : OK — {len(all_ids)} identifiants identiques au DRY-RUN validé ({MANIFEST_PRIOR.name}) + tenant {TARGET}")
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
    r = requests.post(f"{BASE}/api/auth/login", json={"email": f"lotf-admin@{TARGET}.ch", "password": "x"}, timeout=30)
    print("Login compte supprimé (attendu 401):", r.status_code)
    n = db.login_attempts.delete_many({"identifier": {"$regex": f"\\|[^|]+@{TARGET}\\.ch$"}}).deleted_count  # trace créée par le contrôle ci-dessus
    if n:
        deleted["login_attempts(identifier)"] = n
    print("SUPPRIMÉ (anomalies → matches → rows → jobs → mappings → tx → documents → affectations → cartes → conducteurs → audit → … → vehicles → users → tenant):",
          json.dumps(deleted, ensure_ascii=False), "total =", sum(deleted.values()))
    after = target_counts()
    show("APRÈS — cible", after)
    fp_after = fingerprint()
    diff = {k: (fp_before.get(k), fp_after.get(k)) for k in set(fp_before) | set(fp_after) if fp_before.get(k) != fp_after.get(k)}
    stable_ok = fp_before["default|sha256_stable"] == fp_after["default|sha256_stable"]
    counts_ok = not {k: v for k, v in diff.items() if not k.startswith("default|sha256")}
    print("default + autres tenants inchangés:", "OUI" if not diff else ("OUI (hash default stable identique ; seul le hash brut varie = champs volatils Navixy de vehicles)" if stable_ok and counts_ok else f"NON {json.dumps(diff, default=str)}"))
    print("Hash default avant/après:", fp_before["default|sha256"][:16], fp_after["default|sha256"][:16], "| stable:", fp_before["default|sha256_stable"][:16], fp_after["default|sha256_stable"][:16])
    print("Baselines default après:", json.dumps(fp_after["default|baselines"]))
    print("Tenants restants:", fp_after["tenants|ids"])
    residual = {}
    for c in COLLS:
        q = {"$or": [{"tenant_id": TARGET}, {"id": {"$in": all_ids}}, {"card_id": {"$in": all_ids}}, {"vehicle_id": {"$in": all_ids}}, {"transaction_id": {"$in": all_ids}},
                     {"job_id": {"$in": all_ids}}, {"document_id": {"$in": all_ids}}, {"source_document_id": {"$in": all_ids}}, {"email": {"$regex": TARGET}}]}
        n = db[c].count_documents(q)
        if n:
            residual[c] = n
    textual = {}
    for c in COLLS:
        if c == "audit_logs":
            continue
        n = sum(1 for d in db[c].find({}, {"_id": 0}) if TARGET in json.dumps(d, default=str))
        if n:
            textual[c] = n
    print("Résidus par identifiants (tous ids du manifeste, clés étrangères, email):", json.dumps(residual) if residual else "0")
    print("Résidus textuels « lotf-ui-test » hors audit_logs:", json.dumps(textual) if textual else "0")
    print("Audit plateforme (autres tenants) mentionnant la cible :", db.audit_logs.count_documents({"tenant_id": {"$ne": TARGET}, "detail": {"$regex": TARGET}}))
    for c in ("fuel_cards", "fuel_card_assignments", "fuel_import_jobs", "fuel_import_rows", "fuel_anomalies", "fuel_transaction_matches"):
        print(f"  {c} total base: {db[c].count_documents({})}")
    print("LOTF TEST CLEANUP =", "PASS" if not any(after.values()) and not residual and not textual and stable_ok and counts_ok else "FAIL")


if __name__ == "__main__":
    main()
