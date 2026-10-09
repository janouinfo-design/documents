"""EXTRACTION READ-ONLY côté JOURNAL — À EXÉCUTER ULTÉRIEUREMENT SUR LE SYSTÈME JOURNAL.

NE PAS exécuter dans l'espace Documents : aucune base Journal n'y est présente.
Ce script LIT la base Journal (JOURNAL_MONGO_URL / JOURNAL_DB_NAME, READ-ONLY) et écrit des fichiers JSON
au schéma attendu par le harness de dry-run. Il n'écrit JAMAIS dans Journal (find() uniquement).

Adapter COLLECTION_MAP / FIELD_MAP aux noms réels des collections/champs Journal AVANT exécution
(les noms ci-dessous reprennent les champs cibles de la spec ; si le Journal nomme différemment,
mapper ici — sans inventer de valeur). Puis :

    JOURNAL_MONGO_URL=... JOURNAL_DB_NAME=... python3 journal_export_readonly.py /chemin/sortie
"""
import json, os, sys
from pymongo import MongoClient

OUT = sys.argv[1] if len(sys.argv) > 1 else "./migration_input"
os.makedirs(OUT, exist_ok=True)
URL = os.environ["JOURNAL_MONGO_URL"]          # fourni côté Journal, READ-ONLY
DBN = os.environ["JOURNAL_DB_NAME"]
db = MongoClient(URL, readPreference="secondaryPreferred")[DBN]

# fichier de sortie -> (collection Journal, projection de champs attendus)
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

# Si le Journal nomme un champ différemment du champ cible, déclarer ici : {"champ_cible": "champ_journal"}
FIELD_MAP = {
    # exemple : "legacy_tenant_id": "id", "navixy_master_user_id": "navixy_master_user_id",
    # "legacy_vehicle_id": "id", "legacy_transaction_id": "id", "legacy_fine_id": "id",
}

def extract(filename, collection, fields):
    src_fields = [FIELD_MAP.get(f, f) for f in fields]
    rows = []
    for d in db[collection].find({}, {"_id": 0, **{s: 1 for s in src_fields}}):
        rows.append({f: d.get(FIELD_MAP.get(f, f)) for f in fields})
    with open(os.path.join(OUT, filename), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=1, default=str)
    print(f"{filename}: {len(rows)} enregistrements")

if __name__ == "__main__":
    for filename, collection in COLLECTION_MAP.items():
        extract(filename, collection, PROJECTION[filename])
    print("EXTRACTION READ-ONLY terminée →", OUT)
