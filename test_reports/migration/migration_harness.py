"""Phase 4C — HARNESS de dry-run migration Journal → Documents (LECTURE SEULE, 0 écriture métier).

Résultat de cette étape = `MIGRATION HARNESS = READY` (le dry-run RÉEL n'a lieu qu'une fois l'export
Journal fourni — option A). Le harness :
- valide l'export d'entrée (refus si fichier obligatoire absent / schéma invalide / legacy_id manquant /
  tenant non identifiable / incohérences référentielles) ;
- mappe les tenants (D3), résout les véhicules (Lot A, resolver figé), les conducteurs (Lot C), les cartes
  (D2/Lot E), les transactions carburant (§4.11, D5 dates, D7 FX, D8 anomalies recalculées) et les amendes
  (Lot D, D4 quarantaine plaque, D9 annulée) ;
- classe chaque objet en EXACTEMENT une catégorie : READY / ALREADY_PRESENT / REVIEW_REQUIRED / BLOCKED /
  DUPLICATE / IGNORED (reason_code + reason_text + source_id + target_id) ;
- dédoublonne par clé stable (tenant_id Documents, legacy_source, legacy_id) ; idempotent (rejouer = même plan) ;
- capture l'empreinte Documents avant/après et prouve DOCUMENTS_UNCHANGED ;
- n'exécute AUCUN appel mutatif, aucun scheduler, aucun import, aucun endpoint ; DB en lecture seule stricte.

Usage :
  python3 migration_harness.py emit-spec          # spécification d'export Journal + script d'extraction READ-ONLY
  python3 migration_harness.py baseline           # empreinte Documents (preuve "avant")
  python3 migration_harness.py validate <dir>     # valide un export (refuse si invalide)
  python3 migration_harness.py dryrun <dir>       # dry-run réel sur un export fourni (option A)
  python3 migration_harness.py selftest           # auto-test du harness sur entrées vides/malformées (sans données Journal)
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from pymongo import MongoClient

HERE = Path(__file__).resolve().parent
REP = HERE.parent  # /app/test_reports
BACKEND = Path("/app/backend")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(HERE))
import legacy_identity as LI  # noqa: E402  (resolver + D3 + idempotence figés)
import migration_schema as SCHEMA  # noqa: E402

ENV = dotenv_values(str(BACKEND / ".env"))
LEGACY_SOURCE = SCHEMA.LEGACY_SOURCE
DEFAULT_INPUT = REP / "migration_input"
# collections cibles de migration (empreinte Documents)
TARGET_COLLECTIONS = ("documents", "fuel_transactions", "fuel_cards", "fuel_card_assignments", "drivers",
                      "driver_assignments", "fuel_transaction_matches", "fuel_anomalies", "fuel_reconciliations",
                      "vehicles", "tenant_integrations", "tenants", "legacy_vehicle_map", "legacy_tenant_map",
                      "vehicles_archive")
CATEGORIES = ("READY", "ALREADY_PRESENT", "REVIEW_REQUIRED", "BLOCKED", "DUPLICATE", "IGNORED")


# ---------------------------------------------------------------- lecture seule stricte
class ReadOnlyDB:
    """Enveloppe pymongo n'exposant QUE des opérations de lecture (toute mutation lève)."""
    _ALLOWED = {"find", "find_one", "count_documents", "distinct", "aggregate", "estimated_document_count"}

    def __init__(self, db):
        self._db = db

    def list_collection_names(self):
        return self._db.list_collection_names()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, name):
        coll = self._db[name]

        class _ROColl:
            def __getattr__(self, attr):
                if attr in ReadOnlyDB._ALLOWED:
                    return getattr(coll, attr)
                raise PermissionError(f"HARNESS READ-ONLY : opération '{attr}' interdite sur {name}")
        return _ROColl()


def connect_ro():
    return ReadOnlyDB(MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]])


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- empreinte Documents
VOLATILE = {"vehicles": ("updated_at", "kilometrage", "conso_moyenne_l_100km", "conso_source", "conso_updated_at")}


def fingerprint(db):
    fp = {"counts": {}, "hashes": {}}
    for c in TARGET_COLLECTIONS:
        if c not in db.list_collection_names():
            continue
        key = "id" if c == "tenants" else "tenant_id"
        for t in sorted(str(x) for x in db[c].distinct(key)):
            h, n = hashlib.sha256(), 0
            for d in db[c].find({key: t}, {"_id": 0}).sort("id", 1):
                n += 1
                d = {k: v for k, v in d.items() if k not in VOLATILE.get(c, ()) and not str(k).startswith("navixy_")}
                h.update(json.dumps(d, sort_keys=True, default=str).encode())
            fp["counts"][f"{c}|{t}"], fp["hashes"][f"{c}|{t}"] = n, h.hexdigest()
    return fp


def fp_diff(a, b):
    out = {}
    for sec in ("counts", "hashes"):
        keys = set(a[sec]) | set(b[sec])
        out[sec] = sorted(k for k in keys if a[sec].get(k) != b[sec].get(k))
    return out


# ---------------------------------------------------------------- validateur d'entrée
def load_json_list(path):
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path.name} : racine attendue = liste JSON")
    return data


def validate_export(input_dir):
    """Refuse de démarrer si : fichier obligatoire absent · schéma invalide · legacy_id manquant ·
    tenant non identifiable · incohérence référentielle. Retourne (ok, errors, loaded)."""
    errors, loaded = [], {}
    d = Path(input_dir)
    if not d.exists():
        return False, [f"dossier d'entrée absent : {d}"], {}
    for fname in SCHEMA.REQUIRED_FILES:
        if not (d / fname).exists():
            errors.append(f"FICHIER OBLIGATOIRE ABSENT : {fname}")
    for f in SCHEMA.FILES:
        p = d / f["filename"]
        if not p.exists():
            if f["required"]:
                continue  # déjà signalé
            loaded[f["filename"]] = []
            continue
        try:
            rows = load_json_list(p)
        except Exception as e:  # schéma invalide
            errors.append(f"SCHÉMA INVALIDE : {f['filename']} — {e}")
            continue
        loaded[f["filename"]] = rows
        lid = f["legacy_id_field"]
        required_fields = [fl["name"] for fl in f["fields"] if fl["required"]]
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                errors.append(f"SCHÉMA INVALIDE : {f['filename']}[{i}] n'est pas un objet")
                continue
            if not r.get(lid):
                errors.append(f"LEGACY_ID MANQUANT : {f['filename']}[{i}] ({lid})")
            for rf in required_fields:
                if r.get(rf) in (None, ""):
                    errors.append(f"CHAMP OBLIGATOIRE MANQUANT : {f['filename']}[{i}].{rf}")
    if errors:
        return False, errors, loaded
    # cohérence référentielle (seulement si fichiers chargés)
    tenant_ids = {r.get("legacy_tenant_id") for r in loaded.get("tenants.json", [])}
    vehicle_ids = {r.get("legacy_vehicle_id") for r in loaded.get("vehicles.json", [])}
    for fname in ("vehicles.json", "drivers.json", "fuel_transactions.json", "fines.json",
                  "vehicle_assignments.json", "fuel_cards.json", "fuel_card_assignments.json", "documents_costs.json"):
        for i, r in enumerate(loaded.get(fname, [])):
            lt = r.get("legacy_tenant_id")
            if lt is not None and lt not in tenant_ids:
                errors.append(f"TENANT NON IDENTIFIABLE : {fname}[{i}] legacy_tenant_id={lt} absent de tenants.json")
    for fname in ("fuel_transactions.json", "vehicle_assignments.json"):
        for i, r in enumerate(loaded.get(fname, [])):
            lv = r.get("legacy_vehicle_id")
            if lv is not None and lv != "" and lv not in vehicle_ids:
                errors.append(f"INCOHÉRENCE SOURCE : {fname}[{i}] legacy_vehicle_id={lv} absent de vehicles.json")
    return (not errors), errors, loaded


# ---------------------------------------------------------------- moteur de dry-run
def line(category, entity, source_id, reason_code, reason_text, target_id=None, extra=None):
    assert category in CATEGORIES
    return {"category": category, "entity": entity, "source_id": source_id, "target_id": target_id,
            "reason_code": reason_code, "reason_text": reason_text, **(extra or {})}


def build_documents_context(db):
    integrations = list(db.tenant_integrations.find({}, {"_id": 0, "tenant_id": 1, "master_user_id": 1}))
    tenants_by_id = {t["id"]: t for t in db.tenants.find({}, {"_id": 0, "id": 1, "name": 1})}
    vehicles_by_tenant = {}
    for v in db.vehicles.find({}, {"_id": 0, "id": 1, "tenant_id": 1, "vin": 1, "plaque": 1, "marque": 1,
                                    "modele": 1, "annee": 1, "navixy_tracker_id": 1, "navixy_vehicle_id": 1}):
        vehicles_by_tenant.setdefault(v.get("tenant_id"), []).append(v)
    vmap_confirmed = {}
    for m in db.legacy_vehicle_map.find({"status": "confirmed"}, {"_id": 0, "tenant_id": 1, "legacy_source": 1,
                                                                   "legacy_vehicle_id": 1, "vehicle_id": 1}):
        vmap_confirmed[(m["tenant_id"], m.get("legacy_source"), m["legacy_vehicle_id"])] = m.get("vehicle_id")
    return integrations, tenants_by_id, vehicles_by_tenant, vmap_confirmed


def existing_legacy(db, collection, tenant_id, legacy_id, extra_match=None):
    q = {"tenant_id": tenant_id, "legacy_source": LEGACY_SOURCE, "legacy_id": str(legacy_id)}
    if extra_match:
        q.update(extra_match)
    return db[collection].find_one(q, {"_id": 0, "id": 1, "legacy_payload_sha256": 1})


def map_tenants(loaded, integrations, tenants_by_id):
    rows = loaded.get("tenants.json", [])
    out, resolved = [], {}  # legacy_tenant_id -> documents tenant_id (si MATCHED)
    doc_target = {}
    for r in rows:
        cand = LI.tenant_candidates(integrations, tenants_by_id, {"legacy_tenant_id": r.get("legacy_tenant_id"),
                                                                  SCHEMA.TENANT_MATCH_KEY: r.get(SCHEMA.TENANT_MATCH_KEY)})
        st = cand["status"]
        status = {"found": "MATCHED", "ambiguous": "AMBIGUOUS", "not_found": "UNMAPPED",
                  "no_technical_key": "UNMAPPED"}[st]
        tid = cand["candidates"][0]["tenant_id"] if status == "MATCHED" else None
        out.append({"legacy_tenant_id": r.get("legacy_tenant_id"), "match_key": SCHEMA.TENANT_MATCH_KEY,
                    "match_value": cand.get("match_value"), "status": status,
                    "documents_tenant_id": tid, "candidates": cand["candidates"],
                    "reason": "clé technique absente → non migré" if st == "no_technical_key" else st})
        if status == "MATCHED":
            doc_target.setdefault(tid, []).append(r.get("legacy_tenant_id"))
            resolved[r.get("legacy_tenant_id")] = tid
    # CONFLICT : plusieurs tenants Journal → même tenant Documents
    for tid, legacies in doc_target.items():
        if len(legacies) > 1:
            for o in out:
                if o["documents_tenant_id"] == tid:
                    o["status"] = "CONFLICT"
                    o["reason"] = f"collision : {len(legacies)} tenants Journal → même tenant Documents {tid}"
            for lt in legacies:
                resolved.pop(lt, None)
    return out, resolved


def resolve_vehicle(legacy_vehicle, tenant_doc_id, vehicles_by_tenant, vmap_confirmed):
    """Retourne (status, vehicle_id|None, detail). status ∈ CONFIRMED/REVIEW_REQUIRED/CONFLICT/UNMATCHED."""
    key = (tenant_doc_id, LEGACY_SOURCE, legacy_vehicle.get("legacy_vehicle_id"))
    if key in vmap_confirmed:
        return "CONFIRMED", vmap_confirmed[key], {"method": "legacy_vehicle_map(confirmed)"}
    cand = LI.vehicle_candidates(vehicles_by_tenant.get(tenant_doc_id, []), {
        "legacy_vehicle_id": legacy_vehicle.get("legacy_vehicle_id"), "plate": legacy_vehicle.get("plate"),
        "vin": legacy_vehicle.get("vin"), "navixy_vehicle_id": legacy_vehicle.get("navixy_vehicle_id"),
        "navixy_tracker_id": legacy_vehicle.get("navixy_tracker_id"), "model": legacy_vehicle.get("model")})
    st = cand["status"]
    if st in ("strong_candidate", "candidate_warning", "manual_review"):
        return "REVIEW_REQUIRED", None, {"method": cand["method_suggested"], "candidates": cand["candidates"], "warnings": cand["warnings"]}
    if st == "ambiguous":
        return "CONFLICT", None, {"candidates": cand["candidates"]}
    return "UNMATCHED", None, {}


def run_dryrun(input_dir, emit=True):
    db = connect_ro()
    fp_before = fingerprint(db)
    ok, errors, loaded = validate_export(input_dir)
    if not ok:
        return {"validated": False, "errors": errors}
    integrations, tenants_by_id, vehicles_by_tenant, vmap_confirmed = build_documents_context(db)

    tenant_mapping, tenant_resolved = map_tenants(loaded, integrations, tenants_by_id)

    # --- véhicules (Lot A)
    vehicle_mapping, veh_resolved = [], {}  # legacy_vehicle_id -> (status, vehicle_id)
    for r in loaded.get("vehicles.json", []):
        tdoc = tenant_resolved.get(r.get("legacy_tenant_id"))
        if not tdoc:
            vehicle_mapping.append({"legacy_vehicle_id": r.get("legacy_vehicle_id"), "status": "UNMATCHED",
                                    "method": None, "confidence": "none", "reason": "tenant non mappé (D3)"})
            veh_resolved[r.get("legacy_vehicle_id")] = ("UNMATCHED", None)
            continue
        st, vid, detail = resolve_vehicle(r, tdoc, vehicles_by_tenant, vmap_confirmed)
        conf = {"CONFIRMED": "confirmed", "REVIEW_REQUIRED": "to_review", "CONFLICT": "conflict", "UNMATCHED": "none"}[st]
        vehicle_mapping.append({"legacy_vehicle_id": r.get("legacy_vehicle_id"), "documents_tenant_id": tdoc,
                                "status": st, "method": detail.get("method"), "confidence": conf,
                                "candidates": detail.get("candidates", []), "warnings": detail.get("warnings", [])})
        veh_resolved[r.get("legacy_vehicle_id")] = (st, vid)

    plan = []  # toutes les lignes classées
    seen = {}  # (entity, legacy_id) -> dédoublonnage intra-source

    def dedup(entity, legacy_id):
        k = (entity, legacy_id)
        if k in seen:
            return True
        seen[k] = True
        return False

    def classify_with_vehicle(entity, r, legacy_id, tdoc, coll, vehicle_required, plate_field=None):
        if dedup(entity, legacy_id):
            return line("DUPLICATE", entity, legacy_id, "DUPLICATE_LEGACY_ID", "legacy_id déjà vu dans l'export")
        if existing_legacy(db, coll, tdoc, legacy_id):
            return line("ALREADY_PRESENT", entity, legacy_id, "LEGACY_KEY_PRESENT",
                        "déjà présent dans Documents (tenant,legacy_source,legacy_id)")
        lv = r.get("legacy_vehicle_id")
        vst, vid = veh_resolved.get(lv, ("UNMATCHED", None)) if lv else ("NONE", None)
        if lv and vst == "CONFIRMED":
            return line("READY", entity, legacy_id, "OK", "tenant mappé + véhicule confirmé", target_id=vid,
                        extra={"documents_tenant_id": tdoc, "vehicle_id": vid})
        if lv and vst in ("REVIEW_REQUIRED", "UNMATCHED"):
            return line("REVIEW_REQUIRED", entity, legacy_id, "VEHICLE_NOT_CONFIRMED",
                        "véhicule non confirmé (quarantaine Lot A/D4)", extra={"documents_tenant_id": tdoc})
        if lv and vst == "CONFLICT":
            return line("REVIEW_REQUIRED", entity, legacy_id, "VEHICLE_AMBIGUOUS",
                        "plusieurs véhicules candidats (ambigu)", extra={"documents_tenant_id": tdoc})
        # pas de legacy_vehicle_id
        if plate_field and r.get(plate_field):
            return line("REVIEW_REQUIRED", entity, legacy_id, "PLATE_ONLY",
                        "plaque seule → quarantaine (D4), jamais jointure auto", extra={"documents_tenant_id": tdoc})
        if vehicle_required:
            return line("BLOCKED", entity, legacy_id, "VEHICLE_MISSING",
                        "vehicle_id obligatoire et aucun indice exploitable", extra={"documents_tenant_id": tdoc})
        return line("READY", entity, legacy_id, "OK", "tenant mappé (sans véhicule requis)", extra={"documents_tenant_id": tdoc})

    def tenant_doc(r):
        return tenant_resolved.get(r.get("legacy_tenant_id"))

    def blocked_if_no_tenant(entity, legacy_id, r):
        tdoc = tenant_doc(r)
        if not tdoc:
            return line("BLOCKED", entity, legacy_id, "TENANT_UNMAPPED",
                        "tenant Journal non mappé (D3) — aucun fallback"), None
        return None, tdoc

    # --- conducteurs (Lot C)
    for r in loaded.get("drivers.json", []):
        lid = r.get("legacy_driver_id")
        b, tdoc = blocked_if_no_tenant("driver", lid, r)
        if b:
            plan.append(b); continue
        if dedup("driver", lid):
            plan.append(line("DUPLICATE", "driver", lid, "DUPLICATE_LEGACY_ID", "legacy_id déjà vu")); continue
        if existing_legacy(db, "drivers", tdoc, lid):
            plan.append(line("ALREADY_PRESENT", "driver", lid, "LEGACY_KEY_PRESENT", "déjà présent")); continue
        if not (r.get("name") or r.get("last_name")):
            plan.append(line("REVIEW_REQUIRED", "driver", lid, "INSUFFICIENT_IDENTITY",
                             "identité conducteur insuffisante (jamais le nom comme clé)", extra={"documents_tenant_id": tdoc})); continue
        plan.append(line("READY", "driver", lid, "OK", "conducteur mappé par id canonique", extra={"documents_tenant_id": tdoc}))

    # --- cartes carburant (D2/Lot E : résolution seule, aucune création auto)
    for r in loaded.get("fuel_cards.json", []):
        lid = r.get("legacy_card_id")
        b, tdoc = blocked_if_no_tenant("fuel_card", lid, r)
        if b:
            plan.append(b); continue
        if dedup("fuel_card", lid):
            plan.append(line("DUPLICATE", "fuel_card", lid, "DUPLICATE_LEGACY_ID", "legacy_id déjà vu")); continue
        matches = list(db.fuel_cards.find({"tenant_id": tdoc, "fournisseur": r.get("provider"), "last4": r.get("last4")},
                                          {"_id": 0, "id": 1}))
        if existing_legacy(db, "fuel_cards", tdoc, lid):
            plan.append(line("ALREADY_PRESENT", "fuel_card", lid, "LEGACY_KEY_PRESENT", "déjà présent")); continue
        if len(matches) == 1:
            plan.append(line("ALREADY_PRESENT", "fuel_card", lid, "CARD_RESOLVED",
                             "carte Documents résolue par (fournisseur,last4) — aucune création (D2)", target_id=matches[0]["id"])); continue
        if len(matches) > 1:
            plan.append(line("REVIEW_REQUIRED", "fuel_card", lid, "CARD_AMBIGUOUS",
                             "(fournisseur,last4) non unique → désambiguïsation manuelle (D2)", extra={"documents_tenant_id": tdoc})); continue
        plan.append(line("REVIEW_REQUIRED", "fuel_card", lid, "CARD_NOT_FOUND",
                         "carte introuvable dans Documents — aucune création auto (D2)", extra={"documents_tenant_id": tdoc}))

    # --- affectations de cartes (Lot E)
    for r in loaded.get("fuel_card_assignments.json", []):
        lid = r.get("legacy_card_assignment_id")
        b, tdoc = blocked_if_no_tenant("fuel_card_assignment", lid, r)
        if b:
            plan.append(b); continue
        if dedup("fuel_card_assignment", lid):
            plan.append(line("DUPLICATE", "fuel_card_assignment", lid, "DUPLICATE_LEGACY_ID", "legacy_id déjà vu")); continue
        plan.append(line("REVIEW_REQUIRED", "fuel_card_assignment", lid, "ASSIGNMENT_NEEDS_RESOLUTION",
                         "affectation datée migrée seulement si carte+cible déterminables sans ambiguïté", extra={"documents_tenant_id": tdoc}))

    # --- affectations véhicule↔conducteur
    for r in loaded.get("vehicle_assignments.json", []):
        lid = r.get("legacy_assignment_id")
        b, tdoc = blocked_if_no_tenant("vehicle_assignment", lid, r)
        if b:
            plan.append(b); continue
        if dedup("vehicle_assignment", lid):
            plan.append(line("DUPLICATE", "vehicle_assignment", lid, "DUPLICATE_LEGACY_ID", "legacy_id déjà vu")); continue
        vst, vid = veh_resolved.get(r.get("legacy_vehicle_id"), ("UNMATCHED", None))
        drv = existing_legacy(db, "drivers", tdoc, r.get("legacy_driver_id")) if r.get("legacy_driver_id") else None
        if vst == "CONFIRMED" and drv:
            plan.append(line("READY", "vehicle_assignment", lid, "OK", "véhicule confirmé + conducteur présent",
                             extra={"documents_tenant_id": tdoc, "vehicle_id": vid})); continue
        plan.append(line("REVIEW_REQUIRED", "vehicle_assignment", lid, "RELATION_UNRESOLVED",
                         "véhicule non confirmé et/ou conducteur non résolu — jamais d'affectation inventée", extra={"documents_tenant_id": tdoc}))

    # --- transactions carburant (§4.11 ; D5 ; D7 ; D8)
    pending_fx = []
    for r in loaded.get("fuel_transactions.json", []):
        lid = r.get("legacy_transaction_id")
        b, tdoc = blocked_if_no_tenant("fuel_transaction", lid, r)
        if b:
            plan.append(b); continue
        res = classify_with_vehicle("fuel_transaction", r, lid, tdoc, "fuel_transactions", vehicle_required=False, plate_field=None)
        # D7 FX : devise≠CHF sans montant_chf → pending (ligne migrée mais exclue du total CHF)
        devise = (r.get("currency") or "").upper()
        if devise and devise != "CHF" and r.get("amount_chf") in (None, ""):
            res["fx_status"] = "pending"
            pending_fx.append({"legacy_id": lid, "devise": devise, "montant": r.get("amount_total")})
        else:
            res["fx_status"] = "ok"
        res["anomalies"] = "RECALCULATE_ON_APPLY (D8)"
        plan.append(res)

    # --- amendes (Lot D, D4, D9)
    for r in loaded.get("fines.json", []):
        lid = r.get("legacy_fine_id")
        b, tdoc = blocked_if_no_tenant("fine", lid, r)
        if b:
            plan.append(b); continue
        res = classify_with_vehicle("fine", r, lid, tdoc, "documents", vehicle_required=True, plate_field="plaque_mentionnee")
        # enrichissements non bloquants : statut + type
        raw_status = r.get("fine_status")
        norm_status = SCHEMA.FINE_STATUS_ALIASES.get(raw_status, raw_status) if raw_status else "a_payer"
        if raw_status and norm_status not in SCHEMA.FINE_STATUSES and res["category"] == "READY":
            res = line("REVIEW_REQUIRED", "fine", lid, "UNKNOWN_FINE_STATUS",
                       f"statut inconnu « {raw_status} »", extra={"documents_tenant_id": tdoc})
        typ = r.get("type_infraction")
        if typ and typ not in SCHEMA.KNOWN_INFRACTION_TYPES and res["category"] == "READY":
            res = line("REVIEW_REQUIRED", "fine", lid, "UNKNOWN_INFRACTION_TYPE",
                       f"type_infraction inconnu « {typ} »", extra={"documents_tenant_id": tdoc})
        res["fine_status"] = norm_status
        res["cost_excluded"] = (norm_status == "annulee")  # D9
        plan.append(res)

    # --- documents/coûts éventuels
    for r in loaded.get("documents_costs.json", []):
        lid = r.get("legacy_document_id")
        b, tdoc = blocked_if_no_tenant("document_cost", lid, r)
        if b:
            plan.append(b); continue
        plan.append(classify_with_vehicle("document_cost", r, lid, tdoc, "documents", vehicle_required=False))

    fp_after = fingerprint(db)
    diff = fp_diff(fp_before, fp_after)
    documents_unchanged = not diff["counts"] and not diff["hashes"]

    # agrégats
    by_cat = {c: 0 for c in CATEGORIES}
    by_type = {}
    for p in plan:
        by_cat[p["category"]] += 1
        t = by_type.setdefault(p["entity"], {c: 0 for c in CATEGORIES})
        t[p["category"]] += 1

    result = {
        "generated_at": now_iso(), "legacy_source": LEGACY_SOURCE, "input_dir": str(input_dir),
        "validated": True, "documents_unchanged": documents_unchanged, "fp_diff": diff,
        "totals": by_cat, "by_type": by_type, "pending_fx": pending_fx,
        "tenant_mapping": tenant_mapping, "vehicle_mapping": vehicle_mapping, "plan": plan,
    }
    if emit:
        emit_deliverables(result, fp_before, fp_after)
    return result


# ---------------------------------------------------------------- livrables
def emit_deliverables(result, fp_before, fp_after):
    (REP / "migration_dryrun_manifest.json").write_text(json.dumps(result, indent=1, ensure_ascii=False, default=str))
    (REP / "migration_tenant_mapping.json").write_text(json.dumps(result["tenant_mapping"], indent=1, ensure_ascii=False, default=str))
    (REP / "migration_vehicle_mapping.json").write_text(json.dumps(result["vehicle_mapping"], indent=1, ensure_ascii=False, default=str))
    (REP / "migration_review_required.json").write_text(json.dumps([p for p in result["plan"] if p["category"] == "REVIEW_REQUIRED"], indent=1, ensure_ascii=False, default=str))
    (REP / "migration_blocked.json").write_text(json.dumps([p for p in result["plan"] if p["category"] == "BLOCKED"], indent=1, ensure_ascii=False, default=str))
    (REP / "migration_fingerprints.json").write_text(json.dumps({"before": fp_before, "after": fp_after, "diff": result["fp_diff"], "documents_unchanged": result["documents_unchanged"]}, indent=1, default=str))
    _emit_summary(result)


def _emit_summary(result):
    t = result["totals"]
    lines = ["# Dry-run migration Journal → Documents — SYNTHÈSE", "",
             f"- Généré : {result['generated_at']} · `legacy_source = {result['legacy_source']}`",
             f"- Entrée : `{result['input_dir']}`",
             f"- DOCUMENTS_UNCHANGED : {'PASS' if result['documents_unchanged'] else 'FAIL'}",
             "", "## Totaux par catégorie", "",
             "| " + " | ".join(CATEGORIES) + " |", "|" + "---|" * len(CATEGORIES),
             "| " + " | ".join(str(t[c]) for c in CATEGORIES) + " |", "",
             "## Par type", "", "| Type | " + " | ".join(CATEGORIES) + " |", "|---|" + "---|" * len(CATEGORIES)]
    for typ, c in sorted(result["by_type"].items()):
        lines.append(f"| {typ} | " + " | ".join(str(c[k]) for k in CATEGORIES) + " |")
    lines += ["", f"- pending_fx (devise≠CHF sans montant_chf, exclues du total CHF) : {len(result['pending_fx'])}",
              f"- tenants : {sum(1 for x in result['tenant_mapping'] if x['status']=='MATCHED')} MATCHED / "
              f"{sum(1 for x in result['tenant_mapping'] if x['status']=='AMBIGUOUS')} AMBIGUOUS / "
              f"{sum(1 for x in result['tenant_mapping'] if x['status']=='UNMAPPED')} UNMAPPED / "
              f"{sum(1 for x in result['tenant_mapping'] if x['status']=='CONFLICT')} CONFLICT",
              f"- véhicules : {sum(1 for x in result['vehicle_mapping'] if x['status']=='CONFIRMED')} CONFIRMED / "
              f"{sum(1 for x in result['vehicle_mapping'] if x['status']=='REVIEW_REQUIRED')} REVIEW / "
              f"{sum(1 for x in result['vehicle_mapping'] if x['status']=='UNMATCHED')} UNMATCHED / "
              f"{sum(1 for x in result['vehicle_mapping'] if x['status']=='CONFLICT')} CONFLICT", "",
              "> Rappel : un dry-run PASS ne signifie PAS que toutes les lignes sont READY. "
              "REVIEW_REQUIRED / BLOCKED sont attendus et listés dans les manifests dédiés."]
    (REP / "migration_dryrun_summary.md").write_text("\n".join(lines))


# ---------------------------------------------------------------- spécification d'export + extraction
def emit_spec():
    spec = {"legacy_source": LEGACY_SOURCE, "tenant_match_key": SCHEMA.TENANT_MATCH_KEY,
            "idempotence_key": ["tenant_id(Documents)", "legacy_source", "legacy_id"],
            "files": [{"filename": f["filename"], "entity": f["entity"], "required": f["required"],
                       "legacy_id_field": f["legacy_id_field"], "decision": f["decision"],
                       "fields": f["fields"], "projection_readonly": SCHEMA.export_projection(f)} for f in SCHEMA.FILES]}
    (REP / "migration_journal_export_schema.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    _emit_spec_md()
    _emit_extraction_script()


def _emit_spec_md():
    L = ["# Spécification d'export Journal (READ-ONLY) pour le dry-run de migration", "",
         f"- `legacy_source = \"{LEGACY_SOURCE}\"` · clé de correspondance tenant (D3) : `{SCHEMA.TENANT_MATCH_KEY}` ↔ Documents `tenant_integrations.master_user_id`",
         "- Clé d'idempotence cible : `(tenant_id Documents, legacy_source, legacy_id)`",
         "- Format : un fichier JSON par entité (racine = tableau d'objets), encodage UTF-8, dates ISO-8601.",
         "- **Ne rien inventer** : un champ absent est omis (ou `null`) ; aucune valeur par défaut fabriquée.",
         "- Fichiers OBLIGATOIRES : " + ", ".join(f"`{x}`" for x in SCHEMA.REQUIRED_FILES) + ".", ""]
    for f in SCHEMA.FILES:
        L += [f"## `{f['filename']}` — {f['entity']} {'(OBLIGATOIRE)' if f['required'] else '(optionnel)'}",
              f"- Identifiant legacy : `{f['legacy_id_field']}` · Décision figée : {f['decision']}", "",
              "| Champ | Type | Obligatoire | Relation | Enum | Note |", "|---|---|---|---|---|---|"]
        for fld in f["fields"]:
            L.append(f"| `{fld['name']}`{' 🔑' if fld['legacy_id'] else ''}{' ⛔DO NOT MIGRATE' if fld['do_not_migrate'] else ''} "
                     f"| {fld['type']} | {'oui' if fld['required'] else ''} | {fld['relation'] or ''} "
                     f"| {', '.join(fld['enum']) if fld['enum'] else ''} | {fld['note']} |")
        L.append("")
    L += ["## Relations entre fichiers", "",
          "- `tenants.legacy_tenant_id` ← référencé par tous les autres fichiers (`legacy_tenant_id`).",
          "- `vehicles.legacy_vehicle_id` ← `fuel_transactions`, `fines`, `vehicle_assignments`, `fuel_card_assignments`.",
          "- `drivers.legacy_driver_id` ← `fuel_transactions`, `fines`, `vehicle_assignments`, `fuel_card_assignments`.",
          "- `fuel_cards.legacy_card_id` ← `fuel_card_assignments`, `fuel_transactions`.", "",
          "## Dépôt attendu", "", f"Déposer les fichiers dans `{DEFAULT_INPUT}` puis lancer `migration_harness.py dryrun <dir>`."]
    (REP / "migration_journal_export_spec.md").write_text("\n".join(L))


def _emit_extraction_script():
    projections = {f["filename"]: SCHEMA.export_projection(f) for f in SCHEMA.FILES}
    coll_by_file = {"tenants.json": "tenants", "vehicles.json": "vehicles", "drivers.json": "drivers",
                    "vehicle_assignments.json": "vehicle_assignments", "fuel_cards.json": "fuel_cards",
                    "fuel_card_assignments.json": "fuel_card_assignments", "fuel_transactions.json": "fuel_transactions",
                    "fines.json": "fines", "documents_costs.json": "documents"}
    entity_by_file = {f["filename"]: f["entity"] for f in SCHEMA.FILES}
    script = '''"""EXTRACTION READ-ONLY côté JOURNAL — À EXÉCUTER UNIQUEMENT SUR LE SYSTÈME JOURNAL.

NE PAS exécuter dans l'espace Documents : aucune base Journal n'y est raccordée (par décision, option A).
Ce script LIT la base Journal (JOURNAL_MONGO_URL / JOURNAL_DB_NAME, READ-ONLY) et produit, dans le dossier
de sortie : les fichiers JSON par entité + journal_export_manifest.json + journal_export_report.md +
EXPORT_SET_SHA256. Il n'écrit JAMAIS dans Journal (find() uniquement) et n'inscrit aucun secret/URI.

AVANT exécution : auditer les vrais noms de collections/champs Journal, adapter COLLECTION_MAP / FIELD_MAP ;
ne mapper un champ que si sa sémantique est CERTAINE ; sinon le laisser absent et le documenter.

    JOURNAL_MONGO_URL=... JOURNAL_DB_NAME=... python3 journal_export_readonly.py /chemin/sortie
"""
import hashlib, json, os, sys
from datetime import datetime, timezone
from pymongo import MongoClient

OUT = sys.argv[1] if len(sys.argv) > 1 else "./migration_input"
os.makedirs(OUT, exist_ok=True)
URL = os.environ["JOURNAL_MONGO_URL"]          # fourni côté Journal, READ-ONLY (jamais écrit dans les rapports)
DBN = os.environ["JOURNAL_DB_NAME"]
db = MongoClient(URL, readPreference="secondaryPreferred")[DBN]

COLLECTION_MAP = ''' + json.dumps(coll_by_file, indent=4, ensure_ascii=False) + '''
PROJECTION = ''' + json.dumps(projections, indent=4, ensure_ascii=False) + '''
ENTITY = ''' + json.dumps(entity_by_file, indent=4, ensure_ascii=False) + '''
REQUIRED = ''' + json.dumps(SCHEMA.REQUIRED_FILES, ensure_ascii=False) + '''

# Si le Journal nomme un champ différemment du champ cible : {"champ_cible": "champ_journal_reel"}.
# Ne RIEN mettre si incertain (le champ sortira à null et sera documenté comme manquant).
FIELD_MAP = {
    # exemple : "legacy_tenant_id": "id", "legacy_vehicle_id": "id", "legacy_transaction_id": "id", "legacy_fine_id": "id",
}

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def extract(filename, collection, fields):
    """Retourne une entrée de manifeste. N'écrit le fichier que si la collection existe réellement."""
    ts = datetime.now(timezone.utc).isoformat()
    base = {"filename": filename, "entity": ENTITY[filename], "required": filename in REQUIRED,
            "source_collection": collection, "projection": fields, "extraction_timestamp": ts}
    if collection not in db.list_collection_names():
        base.update({"row_count": None, "sha256": None, "size_bytes": None,
                     "status": "NOT_PRESENT" if filename not in REQUIRED else "ERROR_REQUIRED_ABSENT"})
        return base, None
    src_fields = [FIELD_MAP.get(f, f) for f in fields]
    rows = [{f: d.get(FIELD_MAP.get(f, f)) for f in fields}
            for d in db[collection].find({}, {"_id": 0, **{s: 1 for s in src_fields}})]
    path = os.path.join(OUT, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
    sha = sha256_file(path)
    base.update({"row_count": len(rows), "sha256": sha, "size_bytes": os.path.getsize(path), "status": "OK"})
    print(f"{filename}: {len(rows)} enregistrements (sha256 {sha[:12]}…)")
    return base, sha

def main():
    manifest, shas, missing_fields = [], {}, {}
    for filename, collection in COLLECTION_MAP.items():
        entry, sha = extract(filename, collection, PROJECTION[filename])
        manifest.append(entry)
        if sha:
            shas[filename] = sha
    # EXPORT_SET_SHA256 déterministe : sha256 des "filename:sha256" triés (fichiers réellement produits)
    joined = "\\n".join(f"{fn}:{shas[fn]}" for fn in sorted(shas))
    export_set = hashlib.sha256(joined.encode()).hexdigest()
    out_manifest = {"extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                    "journal_db_name": DBN, "read_only": True, "files": manifest,
                    "EXPORT_SET_SHA256": export_set}
    with open(os.path.join(OUT, "journal_export_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(out_manifest, fh, ensure_ascii=False, indent=1, default=str)
    # rapport (aucun secret/URI)
    found = [m["source_collection"] for m in manifest if m["status"] == "OK"]
    absent = [m["source_collection"] for m in manifest if m["status"] != "OK"]
    req_missing = [m["filename"] for m in manifest if m["required"] and m["status"] != "OK"]
    lines = ["# Rapport d'extraction Journal (READ-ONLY)", "",
             f"- base Journal (nom) : {DBN}  (URI non affichée)", f"- read_only : find() uniquement, 0 mutation",
             f"- collections trouvées : {found or 'aucune'}", f"- collections absentes : {absent or 'aucune'}",
             f"- fichiers obligatoires manquants : {req_missing or 'aucun'}", "",
             "| Fichier | Collection | Lignes | SHA256 | Statut |", "|---|---|---|---|---|"]
    for m in manifest:
        lines.append(f"| {m['filename']} | {m['source_collection']} | {m['row_count'] if m['row_count'] is not None else 'NOT_AVAILABLE'} "
                     f"| {(m['sha256'][:16]+'…') if m['sha256'] else 'NOT_AVAILABLE'} | {m['status']} |")
    lines += ["", f"EXPORT_SET_SHA256 = {export_set}", "",
              "> FIELD_MAP appliqué : documenter ici tout champ Journal au nom différent, et tout champ laissé à null faute de certitude.",
              "> Transférer ensuite TOUS les fichiers produits vers /app/test_reports/migration_input/ côté Documents."]
    with open(os.path.join(OUT, "journal_export_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\\n".join(lines))
    verdict = "FAIL" if req_missing else "PASS"
    print(f"JOURNAL EXPORT READ-ONLY = {verdict} | EXPORT_SET_SHA256 = {export_set}")

if __name__ == "__main__":
    main()
'''
    (REP / "journal_export_readonly.py").write_text(script)


# ---------------------------------------------------------------- CLI
def cmd_baseline():
    db = connect_ro()
    fp = fingerprint(db)
    (REP / "migration_fingerprints.json").write_text(json.dumps({"baseline": fp, "captured_at": now_iso()}, indent=1, default=str))
    total = sum(fp["counts"].values())
    print(f"BASELINE Documents capturée → migration_fingerprints.json · {len(fp['counts'])} (collection|tenant), {total} enregistrements")


def cmd_selftest():
    print("=== SELFTEST 1 : validate() refuse une entrée incomplète ===")
    with tempfile.TemporaryDirectory() as d:
        ok, errors, _ = validate_export(d)
        assert not ok and any("OBLIGATOIRE ABSENT" in e for e in errors), "validate() aurait dû refuser"
        print("  refus correct :", errors[:3])
    print("=== SELFTEST 2 : validate() refuse un legacy_id manquant ===")
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        (dd / "tenants.json").write_text(json.dumps([{"navixy_master_user_id": 1}]))  # legacy_tenant_id manquant
        (dd / "vehicles.json").write_text("[]")
        (dd / "fuel_transactions.json").write_text("[]")
        (dd / "fines.json").write_text("[]")
        ok, errors, _ = validate_export(d)
        assert not ok and any("LEGACY_ID MANQUANT" in e for e in errors), "validate() aurait dû refuser legacy_id"
        print("  refus correct :", [e for e in errors if "LEGACY_ID" in e][:2])
    print("=== SELFTEST 3 : dry-run sur entrée VIDE bien formée (0 donnée Journal inventée) ===")
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        for fn in SCHEMA.REQUIRED_FILES:
            (dd / fn).write_text("[]")
        res = run_dryrun(d, emit=True)
        assert res["validated"] and res["documents_unchanged"], "dry-run vide devrait valider + Documents inchangé"
        assert sum(res["totals"].values()) == 0, "0 ligne attendue sur entrée vide"
        print("  validated:", res["validated"], "| DOCUMENTS_UNCHANGED:", res["documents_unchanged"], "| lignes:", sum(res["totals"].values()))
    print("=== SELFTEST 4 : lecture seule stricte (toute écriture lève) ===")
    db = connect_ro()
    for op in ("insert_one", "update_one", "delete_many", "drop"):
        try:
            getattr(db["documents"], op)
            raise AssertionError(f"{op} aurait dû être interdit")
        except PermissionError:
            pass
    print("  insert/update/delete/drop correctement interdits")
    print("\nMIGRATION HARNESS SELFTEST = PASS")


def cmd_verify_export(input_dir):
    """Côté Documents (point 8) : vérifier SHA256 reçus vs manifeste + recalculer EXPORT_SET_SHA256 + valider le schéma.
    Lecture seule, ne touche pas Documents."""
    d = Path(input_dir)
    man_path = d / "journal_export_manifest.json"
    print(f"VERIFY-EXPORT sur {d}")
    if not man_path.exists():
        print("  journal_export_manifest.json ABSENT → impossible de vérifier les SHA256 transmis.")
    recomputed, shas = {}, {}
    for f in SCHEMA.FILES:
        p = d / f["filename"]
        if p.exists():
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            recomputed[f["filename"]] = sha
            shas[f["filename"]] = sha
    sha_ok = True
    if man_path.exists():
        man = json.loads(man_path.read_text())
        by_name = {m["filename"]: m.get("sha256") for m in man.get("files", [])}
        for fn, sha in recomputed.items():
            exp = by_name.get(fn)
            match = (exp == sha)
            sha_ok = sha_ok and match
            print(f"  {fn}: sha256 {'OK' if match else 'MISMATCH'} (reçu {str(exp)[:12]}… / recalculé {sha[:12]}…)")
        joined = "\n".join(f"{fn}:{shas[fn]}" for fn in sorted(shas))
        recomputed_set = hashlib.sha256(joined.encode()).hexdigest()
        exp_set = man.get("EXPORT_SET_SHA256")
        set_ok = (recomputed_set == exp_set)
        sha_ok = sha_ok and set_ok
        print(f"  EXPORT_SET_SHA256: {'OK' if set_ok else 'MISMATCH'} (reçu {str(exp_set)[:16]}… / recalculé {recomputed_set[:16]}…)")
    ok, errors, _ = validate_export(input_dir)
    print("  SCHÉMA:", "PASS" if ok else "FAIL")
    for e in errors[:20]:
        print("    -", e)
    verdict = "PASS" if (ok and sha_ok) else "FAIL"
    print("JOURNAL EXPORT VERIFY =", verdict)
    sys.exit(0 if verdict == "PASS" else 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["emit-spec", "baseline", "validate", "verify-export", "dryrun", "selftest"])
    ap.add_argument("input_dir", nargs="?", default=str(DEFAULT_INPUT))
    a = ap.parse_args()
    if a.command == "emit-spec":
        emit_spec()
        print("SPÉCIFICATION + script d'extraction écrits → migration_journal_export_spec.md / .json / journal_export_readonly.py")
    elif a.command == "baseline":
        cmd_baseline()
    elif a.command == "validate":
        ok, errors, _ = validate_export(a.input_dir)
        print("VALIDATE =", "PASS" if ok else "FAIL")
        for e in errors:
            print("  -", e)
        sys.exit(0 if ok else 2)
    elif a.command == "verify-export":
        cmd_verify_export(a.input_dir)
    elif a.command == "dryrun":
        res = run_dryrun(a.input_dir, emit=True)
        if not res.get("validated"):
            print("DRY-RUN REFUSÉ (validation) :")
            for e in res["errors"]:
                print("  -", e)
            sys.exit(2)
        print("DRY-RUN généré. Totaux:", res["totals"], "| DOCUMENTS_UNCHANGED:", res["documents_unchanged"])
    elif a.command == "selftest":
        cmd_selftest()


if __name__ == "__main__":
    main()
