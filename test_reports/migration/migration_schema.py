"""Phase 4C — Dry-run migration Journal → Documents : SCHÉMA d'export Journal (source unique de vérité).

Ce module décrit EXACTEMENT les fichiers et champs que l'export READ-ONLY côté Journal doit produire
(§4.11 / §4.14 de docs/PHASE4C_SPECIFICATION.md + modèles `Legacy*In` de server.py). Il sert à la fois :
- au validateur d'entrée du harness (refus si schéma invalide / legacy_id manquant / incohérences) ;
- à la génération de la spécification d'export (`migration_journal_export_spec.md` / `.json`) ;
- à la génération du script d'extraction READ-ONLY à exécuter ULTÉRIEUREMENT côté Journal.

AUCUNE donnée n'est extraite ou inventée ici : ce ne sont que des définitions de champs.
`legacy_source` = "journal". Clé d'idempotence cible : (tenant_id Documents, legacy_source, legacy_id).
"""

LEGACY_SOURCE = "journal"
TENANT_MATCH_KEY = "navixy_master_user_id"  # D3 : Journal.tenants.navixy_master_user_id ↔ Documents.tenant_integrations.master_user_id

# type ∈ {string, int, float, bool, date, datetime, object, array}
def F(name, typ, required=False, legacy_id=False, relation=None, enum=None, note="", do_not_migrate=False):
    return {"name": name, "type": typ, "required": required, "legacy_id": legacy_id,
            "relation": relation, "enum": enum, "note": note, "do_not_migrate": do_not_migrate}


FINE_STATUSES = ("recue", "a_analyser", "conducteur_a_identifier", "en_attente_conducteur", "contestee",
                 "a_payer", "payee", "refacturee", "cloturee", "annulee")
FINE_STATUS_ALIASES = {"received": "recue", "to_analyze": "a_analyser", "identify_driver": "conducteur_a_identifier",
                       "awaiting_driver": "en_attente_conducteur", "disputed": "contestee", "to_pay": "a_payer",
                       "paid": "payee", "recharged": "refacturee", "closed": "cloturee", "cancelled": "annulee"}
KNOWN_INFRACTION_TYPES = ("speeding", "parking", "red_light", "toll", "forbidden_zone", "phone", "seatbelt", "other")

# Chaque fichier : filename, entity, required (fichier obligatoire au dry-run), records_key, target (collections Documents), fields.
FILES = [
    {"filename": "tenants.json", "entity": "tenant", "required": True,
     "target": ["(mapping) legacy_tenant_map → tenant_integrations"], "legacy_id_field": "legacy_tenant_id",
     "decision": "D3 — mapping par clé technique uniquement ; name jamais utilisé ; aucun fallback default.",
     "fields": [
         F("legacy_tenant_id", "string", required=True, legacy_id=True, note="UUID/clé tenant Journal — identifiant legacy"),
         F("navixy_master_user_id", "int", note="D3 : clé de correspondance → tenant_integrations.master_user_id ; absent = tenant NON migré"),
         F("name", "string", note="affichage seulement — JAMAIS utilisé pour la correspondance"),
     ]},
    {"filename": "vehicles.json", "entity": "vehicle", "required": True,
     "target": ["(mapping) legacy_vehicle_map → vehicles"], "legacy_id_field": "legacy_vehicle_id",
     "decision": "Lot A — resolver vin > navixy_vehicle_id > tracker(warning) > plate(manual_review) ; aucun match auto par plaque/nom/label.",
     "fields": [
         F("legacy_vehicle_id", "string", required=True, legacy_id=True, note="UUID véhicule Journal — identifiant legacy"),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id", note="tenant propriétaire (contexte de résolution)"),
         F("plate", "string", note="indice uniquement → manual_review ; jamais jointure automatique"),
         F("vin", "string", note="critère fort (resolver)"),
         F("navixy_vehicle_id", "int", note="critère fort (resolver)"),
         F("navixy_tracker_id", "int", note="critère évolutif → candidate_warning (tracker_join_no_assignment_history)"),
         F("navixy_tracker_id_archived", "int", note="historique tracker (contexte)"),
         F("model", "string", note="contexte"),
     ]},
    {"filename": "drivers.json", "entity": "driver", "required": False,
     "target": ["drivers"], "legacy_id_field": "legacy_driver_id",
     "decision": "Lot C — identité par id canonique UNIQUEMENT ; jamais le nom comme clé ; association insuffisante → REVIEW_REQUIRED.",
     "fields": [
         F("legacy_driver_id", "string", required=True, legacy_id=True, note="UUID conducteur Journal — identifiant legacy"),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("name", "string"), F("first_name", "string"), F("last_name", "string"),
         F("email", "string", note="contexte RH, non clé d'identité"),
         F("navixy_employee_id", "int"), F("internal_number", "string"),
         F("active", "bool", note="statut actif/inactif"),
     ]},
    {"filename": "vehicle_assignments.json", "entity": "vehicle_assignment", "required": False,
     "target": ["driver_assignments"], "legacy_id_field": "legacy_assignment_id",
     "decision": "Affectation datée — migrée seulement si relations résolues sans ambiguïté ; jamais inventée.",
     "fields": [
         F("legacy_assignment_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("legacy_vehicle_id", "string", required=True, relation="vehicles.legacy_vehicle_id"),
         F("legacy_driver_id", "string", required=True, relation="drivers.legacy_driver_id"),
         F("valid_from", "date", note="D5 — fuseau Europe/Zurich"),
         F("valid_to", "date", note="null = en cours"),
         F("principal", "bool"),
     ]},
    {"filename": "fuel_cards.json", "entity": "fuel_card", "required": False,
     "target": ["fuel_cards (résolution seule — D2 : aucune création auto)"], "legacy_id_field": "legacy_card_id",
     "decision": "D2/Lot E — identité (provider,last4) NON unique ; aucun HMAC Journal migré ; found/ambiguous/not_found.",
     "fields": [
         F("legacy_card_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("provider", "string", note="→ fournisseur"),
         F("last4", "string", note="4 derniers chiffres — (provider,last4) non unique"),
         F("external_card_id", "string"),
         F("status", "string"),
         F("expires_at", "date"),
     ]},
    {"filename": "fuel_card_assignments.json", "entity": "fuel_card_assignment", "required": False,
     "target": ["fuel_card_assignments"], "legacy_id_field": "legacy_card_assignment_id",
     "decision": "Lot E — affectation datée migrée seulement si déterminable sans ambiguïté.",
     "fields": [
         F("legacy_card_assignment_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("legacy_card_id", "string", required=True, relation="fuel_cards.legacy_card_id"),
         F("type", "string", enum=("vehicule", "conducteur"), note="type d'affectation"),
         F("legacy_vehicle_id", "string", relation="vehicles.legacy_vehicle_id"),
         F("legacy_driver_id", "string", relation="drivers.legacy_driver_id"),
         F("valid_from", "date"), F("valid_to", "date"),
     ]},
    {"filename": "fuel_transactions.json", "entity": "fuel_transaction", "required": True,
     "target": ["documents (ticket_carburant, sans fichier)", "fuel_transactions"], "legacy_id_field": "legacy_transaction_id",
     "decision": "§4.11 — document = source canonique du coût ; fuel_transaction JAMAIS resommé ; D5 dates ; D7 FX ; D8 anomalies recalculées.",
     "fields": [
         F("legacy_transaction_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("external_transaction_id", "string", note="→ tx.external_transaction_id · doc.numero ; unique partiel (tenant,fournisseur,ext_id)"),
         F("provider", "string", note="→ fournisseur ; 'manuel' → null + created_from=manual"),
         F("legacy_card_id", "string", relation="fuel_cards.legacy_card_id", note="→ tx.card_id via fuel_cards.legacy_id"),
         F("card_last4", "string", note="→ tx.carte_last4"),
         F("tx_datetime", "datetime", required=True, note="D5 : tz-aware→Europe/Zurich ; naïf→heure locale Europe/Zurich + date_heure_tz_assumed=true ; brut conservé dans date_heure_source"),
         F("accounting_date", "date", note="→ tx.date_comptable"),
         F("station_name", "string"), F("station_address", "string"), F("station_country", "string"),
         F("station_lat", "float", do_not_migrate=True, note="DO NOT MIGRATE"),
         F("station_lng", "float", do_not_migrate=True, note="DO NOT MIGRATE"),
         F("product_type", "string", enum=("diesel", "essence", "adblue", "electric", "other"),
           note="diesel→Diesel, essence→Essence, adblue→AdBlue (exclu conso), electric→Électricité(energie=electrique), other→Autre"),
         F("quantity", "float", note="→ litres(L) / energie_kwh(kWh) / quantite_unite(unit) ; jamais L+kWh additionnés"),
         F("unit", "string", enum=("L", "kWh", "unit")),
         F("unit_price", "float", note="→ prix_litre / prix_kwh"),
         F("amount_net", "float", note="→ doc.montant_ht"),
         F("vat_amount", "float", note="→ doc.tva_chf"), F("vat_rate", "float", note="→ doc.tva_taux"),
         F("amount_total", "float", required=True, note="→ doc.montant / tx.montant"),
         F("currency", "string", required=True, note="→ devise"),
         F("amount_chf", "float", note="D7 : utilisé seulement si devise≠CHF ; absent + devise≠CHF → fx_status=pending, exclu du total CHF"),
         F("fx_rate", "float"), F("fx_rate_date", "date"), F("fx_source", "string"),
         F("mileage", "int", note="→ tx.kilometrage ; JAMAIS écrit sur vehicle.kilometrage"),
         F("vehicle_hint", "string", note="contexte — jamais résolution auto"),
         F("driver_hint", "string", note="contexte — jamais résolution auto"),
         F("legacy_vehicle_id", "string", relation="vehicles.legacy_vehicle_id", note="→ vehicle_id via legacy_vehicle_map CONFIRMÉ ; non résolu → quarantaine (REVIEW_REQUIRED)"),
         F("legacy_driver_id", "string", relation="drivers.legacy_driver_id", note="→ driver_id via drivers.legacy_id"),
         F("trip_id", "string", do_not_migrate=True, note="DO NOT MIGRATE (pas de trajets)"),
         F("classification", "string", note="conservée, non exploitée"),
         F("match_status", "string", do_not_migrate=True, note="RECALCULATE (D8) — jamais migré tel quel"),
         F("match_score", "float", do_not_migrate=True, note="RECALCULATE (D8)"),
         F("anomaly_decision", "string", note="D8 : réimporté UNIQUEMENT si anomalie re-détectée (même tx, même type, donnée réelle)"),
         F("source", "string", enum=("manual", "import"), note="→ tx.created_from + doc.source=legacy_import"),
         F("commentaire", "string", note="D8 : issues[] NON migrées ; commentaire métier réel → tx.commentaire"),
     ]},
    {"filename": "fines.json", "entity": "fine", "required": True,
     "target": ["documents (amende)"], "legacy_id_field": "legacy_fine_id",
     "decision": "Lot D + D4 + D9 — vehicle_id obligatoire ; plaque seule → REVIEW_REQUIRED (quarantaine) ; annulee conservée hors coûts/délais ; 10 statuts ; type_infraction enum.",
     "fields": [
         F("legacy_fine_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("legacy_vehicle_id", "string", relation="vehicles.legacy_vehicle_id", note="D4 : via legacy_vehicle_map CONFIRMÉ ; absent → voir plaque_mentionnee"),
         F("plaque_mentionnee", "string", note="D4 : plaque seule → manual_review → REVIEW_REQUIRED (quarantaine), jamais jointure auto"),
         F("legacy_driver_id", "string", relation="drivers.legacy_driver_id"),
         F("numero_amende", "string", note="→ numero"),
         F("autorite", "string"),
         F("date_infraction", "date", required=True, note="D5 Europe/Zurich"),
         F("montant", "float", required=True), F("devise", "string", required=True, note="D7 identique aux pleins"),
         F("amount_chf", "float", note="D7"),
         F("delai_paiement", "date", note="échéance ; D9 : inactive si annulee/payee/refacturee/cloturee"),
         F("motif", "string"),
         F("type_infraction", "string", enum=KNOWN_INFRACTION_TYPES, note="enum 8 valeurs ; inconnu → REVIEW_REQUIRED"),
         F("fine_status", "string", enum=FINE_STATUSES, note="10 statuts (ou alias EN) ; absent → a_payer (lecture) ; annulee exclue coûts+délais (D9)"),
         F("lieu_infraction", "object", note="{lieu, ville, canton} — jamais texte brut"),
         F("notes_internes", "string", note="D6.3 : masquées read_only/driver (RBAC serveur) — conservées, jamais exposées au driver"),
         F("dossier_number", "string", note="→ dossier_interne (référence humaine, NON clé)"),
     ]},
    {"filename": "documents_costs.json", "entity": "document_cost", "required": False,
     "target": ["documents"], "legacy_id_field": "legacy_document_id",
     "decision": "Documents/coûts associés éventuels — document = source canonique du coût ; compté une fois.",
     "fields": [
         F("legacy_document_id", "string", required=True, legacy_id=True),
         F("legacy_tenant_id", "string", required=True, relation="tenants.legacy_tenant_id"),
         F("legacy_vehicle_id", "string", relation="vehicles.legacy_vehicle_id"),
         F("type", "string"), F("montant", "float"), F("devise", "string"), F("amount_chf", "float"),
         F("date", "date"), F("categorie", "string"),
     ]},
]

FILES_BY_NAME = {f["filename"]: f for f in FILES}
REQUIRED_FILES = [f["filename"] for f in FILES if f["required"]]


def export_projection(entity_file):
    """Projection READ-ONLY (champs à extraire côté Journal) pour un fichier."""
    return [fld["name"] for fld in entity_file["fields"] if not fld["do_not_migrate"]]
