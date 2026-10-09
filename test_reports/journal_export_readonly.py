"""EXTRACTION READ-ONLY côté JOURNAL — À EXÉCUTER UNIQUEMENT SUR LE SYSTÈME JOURNAL.

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

COLLECTION_MAP = {
    "tenants.json": "tenants",
    "vehicles.json": "vehicles",
    "drivers.json": "drivers",
    "vehicle_assignments.json": "vehicle_assignments",
    "fuel_cards.json": "fuel_cards",
    "fuel_card_assignments.json": "fuel_card_assignments",
    "fuel_transactions.json": "fuel_transactions",
    "fines.json": "fines",
    "documents_costs.json": "documents"
}
PROJECTION = {
    "tenants.json": [
        "legacy_tenant_id",
        "navixy_master_user_id",
        "name"
    ],
    "vehicles.json": [
        "legacy_vehicle_id",
        "legacy_tenant_id",
        "plate",
        "vin",
        "navixy_vehicle_id",
        "navixy_tracker_id",
        "navixy_tracker_id_archived",
        "model"
    ],
    "drivers.json": [
        "legacy_driver_id",
        "legacy_tenant_id",
        "name",
        "first_name",
        "last_name",
        "email",
        "navixy_employee_id",
        "internal_number",
        "active"
    ],
    "vehicle_assignments.json": [
        "legacy_assignment_id",
        "legacy_tenant_id",
        "legacy_vehicle_id",
        "legacy_driver_id",
        "valid_from",
        "valid_to",
        "principal"
    ],
    "fuel_cards.json": [
        "legacy_card_id",
        "legacy_tenant_id",
        "provider",
        "last4",
        "external_card_id",
        "status",
        "expires_at"
    ],
    "fuel_card_assignments.json": [
        "legacy_card_assignment_id",
        "legacy_tenant_id",
        "legacy_card_id",
        "type",
        "legacy_vehicle_id",
        "legacy_driver_id",
        "valid_from",
        "valid_to"
    ],
    "fuel_transactions.json": [
        "legacy_transaction_id",
        "legacy_tenant_id",
        "external_transaction_id",
        "provider",
        "legacy_card_id",
        "card_last4",
        "tx_datetime",
        "accounting_date",
        "station_name",
        "station_address",
        "station_country",
        "product_type",
        "quantity",
        "unit",
        "unit_price",
        "amount_net",
        "vat_amount",
        "vat_rate",
        "amount_total",
        "currency",
        "amount_chf",
        "fx_rate",
        "fx_rate_date",
        "fx_source",
        "mileage",
        "vehicle_hint",
        "driver_hint",
        "legacy_vehicle_id",
        "legacy_driver_id",
        "classification",
        "anomaly_decision",
        "source",
        "commentaire"
    ],
    "fines.json": [
        "legacy_fine_id",
        "legacy_tenant_id",
        "legacy_vehicle_id",
        "plaque_mentionnee",
        "legacy_driver_id",
        "numero_amende",
        "autorite",
        "date_infraction",
        "montant",
        "devise",
        "amount_chf",
        "delai_paiement",
        "motif",
        "type_infraction",
        "fine_status",
        "lieu_infraction",
        "notes_internes",
        "dossier_number"
    ],
    "documents_costs.json": [
        "legacy_document_id",
        "legacy_tenant_id",
        "legacy_vehicle_id",
        "type",
        "montant",
        "devise",
        "amount_chf",
        "date",
        "categorie"
    ]
}
ENTITY = {
    "tenants.json": "tenant",
    "vehicles.json": "vehicle",
    "drivers.json": "driver",
    "vehicle_assignments.json": "vehicle_assignment",
    "fuel_cards.json": "fuel_card",
    "fuel_card_assignments.json": "fuel_card_assignment",
    "fuel_transactions.json": "fuel_transaction",
    "fines.json": "fine",
    "documents_costs.json": "document_cost"
}
REQUIRED = ["tenants.json", "vehicles.json", "fuel_transactions.json", "fines.json"]

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
    joined = "\n".join(f"{fn}:{shas[fn]}" for fn in sorted(shas))
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
        fh.write("\n".join(lines))
    verdict = "FAIL" if req_missing else "PASS"
    print(f"JOURNAL EXPORT READ-ONLY = {verdict} | EXPORT_SET_SHA256 = {export_set}")

if __name__ == "__main__":
    main()
