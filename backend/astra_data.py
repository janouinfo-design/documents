"""Données officielles ASTRA/OFROU (opendata.astra.admin.ch/ivzod) — copie locale.
Source principale du resolver technique : aucune clé ni fournisseur externe requis."""
import asyncio
import csv
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

import requests
from pymongo import ReplaceOne

from technical_data import TechnicalLookupError

logger = logging.getLogger(__name__)

ASTRA_BASE = "https://opendata.astra.admin.ch/ivzod"

DATASETS = {
    "tas": {
        "label": "TAS — homologations automobiles",
        "url": f"{ASTRA_BASE}/4000-Typengenehmigungen_TAS/4300-Datensaetze/TAS_Automobil.csv",
        "filename": "TAS_Automobil.csv",
        "collection": "astra_tas",
        "multi": False,
    },
    "tas_emission": {
        "label": "TAS — consommation & émissions (WLTP/NEDC)",
        "url": f"{ASTRA_BASE}/4000-Typengenehmigungen_TAS/4300-Datensaetze/TAS_Emission.csv",
        "filename": "TAS_Emission.csv",
        "collection": "astra_tas_emissions",
        "multi": True,
    },
    "tg": {
        "label": "TG/TARGA — homologations historiques (dès 1995)",
        "url": f"{ASTRA_BASE}/2000-Typengenehmigungen_TG_TARGA/2200-Basisdaten_TG_ab_1995/TG-Automobil.txt",
        "filename": "TG-Automobil.txt",
        "collection": "astra_tg",
        "multi": False,
    },
    "tg_verbrauch": {
        "label": "TG/TARGA — consommation & CO₂ (dès 1995)",
        "url": f"{ASTRA_BASE}/2000-Typengenehmigungen_TG_TARGA/2200-Basisdaten_TG_ab_1995/verbrauch.txt",
        "filename": "verbrauch.txt",
        "collection": "astra_tg_verbrauch",
        "multi": True,
    },
}

# Codes carburant suisses (documentation officielle TARGA/ASTRA)
FUEL_LABELS = {
    "B": "Essence", "C": "Essence / Électrique (hybride)", "D": "Diesel",
    "E": "Électrique", "F": "Diesel / Électrique (hybride)",
    "J": "Éthanol", "K": "Essence / Éthanol", "L": "GPL", "M": "Méthanol",
    "N": "Gaz naturel (CNG)", "P": "Essence",
    "R": "Électrique (prolongateur d'autonomie)", "W": "Hydrogène",
    "X": "Hydrogène / Électrique", "Y": "Gaz naturel (CNG) / Essence",
    "Z": "GPL / Essence",
}
# CO₂ = 0 légitime uniquement pour ces motorisations
ELECTRIC_FUELS = {"E", "W", "X"}

GEARBOX_KINDS = {"m": "manuelle", "a": "automatique", "s": "semi-automatique",
                 "v": "CVT", "d": "double embrayage", "e": "électrique (rapport fixe)"}


class AstraLookupError(TechnicalLookupError):
    def __init__(self, message, code="lookup_failed", http_status=502):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def data_dir() -> str:
    return os.environ.get("ASTRA_DATA_DIR") or os.path.join(os.path.dirname(__file__), "astra_data")


def sync_enabled() -> bool:
    return (os.environ.get("ASTRA_SYNC_ENABLED") or "true").strip().lower() != "false"


def normalize_approval(s):
    if not s:
        return None
    key = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return key or None


def gearbox_label(code):
    c = (code or "").strip()
    m = re.match(r"^([A-Za-z])(\d+)?$", c)
    if not m:
        return c or "Variante"
    kind = GEARBOX_KINDS.get(m.group(1).lower())
    if not kind:
        return f"Boîte {c}"
    return f"Boîte {kind}" + (f" ({m.group(2)} rapports)" if m.group(2) else "")


# ---------------------------------------------------------------------------
# Parsers (streaming, jamais de fichier complet en mémoire)
# ---------------------------------------------------------------------------
def _g(row, idx, col):
    i = idx.get(col)
    if i is None or i >= len(row):
        return ""
    return (row[i] or "").strip()


def _to_int(x):
    try:
        n = int(float(str(x).replace(",", ".").strip()))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _to_float(x):
    try:
        n = float(str(x).replace(",", ".").strip())
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _to_float0(x):
    try:
        s = str(x).replace(",", ".").strip()
        if s == "":
            return None
        n = float(s)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def parse_tas(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        idx = {c.strip(): i for i, c in enumerate(header)}
        for row in reader:
            key = normalize_approval(_g(row, idx, "chTypeApprovalNumber"))
            if not key:
                continue
            gearboxes = [_g(row, idx, f"gearboxEmissions{i}.chGearboxType") for i in range(1, 5)]
            yield {
                "_key": key,
                "approval_no": _g(row, idx, "chTypeApprovalNumber"),
                "version_no": _to_int(_g(row, idx, "versionNo")),
                "make": _g(row, idx, "makeName") or None,
                "commercial_name": _g(row, idx, "commercialName") or None,
                "type": _g(row, idx, "type") or None,
                "variant": _g(row, idx, "variant") or None,
                "vin_prefix": _g(row, idx, "chVinPrefix") or None,
                "category": _g(row, idx, "vehicleCategoryCode") or None,
                "fuel_code": _g(row, idx, "chFuelType") or None,
                "engine_capacity": _to_int(_g(row, idx, "engineCapacity")),
                "power_kw": _to_float(_g(row, idx, "maximumNetPower")),
                "seats": _to_int(_g(row, idx, "chNrOfSeatingPositionsMinimum")),
                "curb_weight": _to_int(_g(row, idx, "chMassOfTheVehicleInRunningOrderMinimum")),
                "gross_weight": _to_int(_g(row, idx, "technicallyPermissibleMaximumLadenMassMinimum")),
                "gearboxes": [g for g in gearboxes if g],
                "date_of_approval": _g(row, idx, "dateOfApproval") or None,
                "cancelation_date": _g(row, idx, "cancelationDate") or None,
            }


def parse_tas_emission(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        idx = {c.strip(): i for i, c in enumerate(header)}
        for row in reader:
            key = normalize_approval(_g(row, idx, "chTypeApprovalNumber"))
            if not key:
                continue
            yield {
                "_key": key,
                "gearbox": _g(row, idx, "chGearboxType") or None,
                "conso_nedc": _to_float(_g(row, idx, "primaryFuelConsumption")),
                "co2_nedc": _to_float0(_g(row, idx, "primaryEmissionCo2")),
                "conso_wltp": _to_float(_g(row, idx, "primaryFuelConsumptionWltp")),
                "co2_wltp": _to_float0(_g(row, idx, "primaryEmissionCo2Wltp")),
                "el_conso_wltp": _to_float(_g(row, idx, "electricEnergyConsumptionWltp")),
            }


def parse_tg(path):
    with open(path, encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        idx = {}
        for i, c in enumerate(header):
            c = c.strip()
            if c and c not in idx:
                idx[c] = i
        for row in reader:
            key = normalize_approval(_g(row, idx, "Typengenehmigungsnummer"))
            if not key:
                continue
            gearboxes = [_g(row, idx, f"18 Getriebe {i}") for i in range(1, 5)]
            yield {
                "_key": key,
                "approval_no": _g(row, idx, "Typengenehmigungsnummer"),
                "make": _g(row, idx, "04 Marke") or None,
                "type": _g(row, idx, "04 Typ") or None,
                "variant": _g(row, idx, "05 Typ; Variante/Version") or None,
                "vin_prefix": _g(row, idx, "12 Fahrgestellnummer") or None,
                "category": _g(row, idx, "03 Fahrzeugklasse") or None,
                "vehicle_kind": _g(row, idx, "01 Fahrzeugart") or None,
                "fuel_code": _g(row, idx, "26 Bauart Treibstoff") or None,
                "engine_capacity": _to_int(_g(row, idx, "27 Hubraum")),
                "power_kw": _to_float(_g(row, idx, "28 Leistung kW")),
                "seats": _to_int(_g(row, idx, "37 Anzahl Plätze Total von")),
                "curb_weight": _to_int(_g(row, idx, "52 Leergewicht von")),
                "gross_weight": _to_int(_g(row, idx, "53 Garantiegewicht von")),
                "gearboxes": [g for g in gearboxes if g],
                "date_of_approval": _g(row, idx, "Typengenehmigung erteilt") or None,
            }


def parse_tg_verbrauch(path):
    with open(path, encoding="latin-1", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader)
        idx = {c.strip(): i for i, c in enumerate(header)}
        for row in reader:
            key = normalize_approval(_g(row, idx, "TG-Code"))
            if not key:
                continue
            yield {
                "_key": key,
                "gearbox": _g(row, idx, "Getriebe") or None,
                "fuel_code": _g(row, idx, "Treibstoff") or None,
                "energy_class": _g(row, idx, "Energieeffizienzkategorie") or None,
                "conso_nedc": _to_float(_g(row, idx, "ET_Verbrauch")),
                "co2_nedc": _to_float0(_g(row, idx, "ET_CO2")),
                "conso_wltp": _to_float(_g(row, idx, "ET_Verbrauch_WLTP")),
                "co2_wltp": _to_float0(_g(row, idx, "ET_CO2_WLTP")),
                "el_conso": _to_float(_g(row, idx, "EL_Verbrauch")),
                "el_conso_wltp": _to_float(_g(row, idx, "EL_Verbrauch_WLTP")),
            }


PARSERS = {"tas": parse_tas, "tas_emission": parse_tas_emission,
           "tg": parse_tg, "tg_verbrauch": parse_tg_verbrauch}


# ---------------------------------------------------------------------------
# Téléchargement + import (batch/upserts, reprise via run mensuel)
# ---------------------------------------------------------------------------
_IMPORT_RUNNING = False


def import_running() -> bool:
    return _IMPORT_RUNNING


def download_file(url, path, force=False):
    if os.path.exists(path) and not force:
        age_days = (time.time() - os.path.getmtime(path)) / 86400
        if age_days < 25:
            logger.info("ASTRA: %s récent (%.1f j) — téléchargement ignoré", os.path.basename(path), age_days)
            return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with requests.get(url, stream=True, timeout=(30, 900)) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(512 * 1024):
                if chunk:
                    f.write(chunk)
    os.replace(tmp, path)
    logger.info("ASTRA: %s téléchargé (%.1f Mo)", os.path.basename(path), os.path.getsize(path) / 1e6)
    return True


async def import_dataset(db, name, download=False, force_download=False):
    ds = DATASETS[name]
    run_id = str(uuid.uuid4())
    await db.astra_import_runs.insert_one({
        "id": run_id, "dataset": name, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "rows_read": 0, "rows_upserted": 0, "source_url": ds["url"],
    })
    path = os.path.join(data_dir(), ds["filename"])
    coll = db[ds["collection"]]
    t0 = time.perf_counter()
    try:
        if download or not os.path.exists(path):
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, download_file, ds["url"], path, force_download)
        batch, read, upserted = [], 0, 0
        seq_key, seq_n = None, -1
        for doc in PARSERS[name](path):
            read += 1
            if ds["multi"]:
                if doc["_key"] == seq_key:
                    seq_n += 1
                else:
                    seq_key, seq_n = doc["_key"], 0
                doc["seq"] = seq_n
                filt = {"_key": doc["_key"], "seq": seq_n}
            else:
                filt = {"_key": doc["_key"]}
            doc["run_id"] = run_id
            batch.append(ReplaceOne(filt, doc, upsert=True))
            if len(batch) >= 1000:
                await coll.bulk_write(batch, ordered=False)
                upserted += len(batch)
                batch = []
                if read % 50000 == 0:
                    await db.astra_import_runs.update_one({"id": run_id}, {"$set": {"rows_read": read}})
        if batch:
            await coll.bulk_write(batch, ordered=False)
            upserted += len(batch)
        removed = (await coll.delete_many({"run_id": {"$ne": run_id}})).deleted_count
        await db.astra_import_runs.update_one({"id": run_id}, {"$set": {
            "status": "done", "finished_at": datetime.now(timezone.utc).isoformat(),
            "rows_read": read, "rows_upserted": upserted, "stale_removed": removed,
            "file_size": os.path.getsize(path), "duration_s": round(time.perf_counter() - t0, 1),
        }})
        logger.info("ASTRA import %s: %d lignes en %.1f s", name, read, time.perf_counter() - t0)
        return {"dataset": name, "status": "done", "rows": read}
    except Exception as e:
        logger.exception("ASTRA import %s échoué", name)
        await db.astra_import_runs.update_one({"id": run_id}, {"$set": {
            "status": "error", "finished_at": datetime.now(timezone.utc).isoformat(), "error": str(e)}})
        return {"dataset": name, "status": "error", "error": str(e)}


async def run_import(db, datasets=None, download=True, force_download=False):
    global _IMPORT_RUNNING
    if _IMPORT_RUNNING:
        return [{"status": "already_running"}]
    _IMPORT_RUNNING = True
    try:
        names = datasets or list(DATASETS)
        return [await import_dataset(db, n, download, force_download) for n in names]
    finally:
        _IMPORT_RUNNING = False


async def pending_datasets(db):
    out = []
    for name, ds in DATASETS.items():
        if await db[ds["collection"]].estimated_document_count() == 0:
            out.append(name)
    return out


async def is_imported(db) -> bool:
    if await db.astra_tas.estimated_document_count() > 0:
        return True
    return await db.astra_tg.estimated_document_count() > 0


async def astra_status(db):
    out = {"data_dir": data_dir(), "sync_enabled": sync_enabled(),
           "import_running": import_running(), "datasets": {}}
    for name, ds in DATASETS.items():
        path = os.path.join(data_dir(), ds["filename"])
        file_info = {"present": os.path.exists(path)}
        if file_info["present"]:
            file_info["size"] = os.path.getsize(path)
            file_info["modified"] = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc).isoformat()
        last_run = await db.astra_import_runs.find_one(
            {"dataset": name}, {"_id": 0}, sort=[("started_at", -1)])
        out["datasets"][name] = {
            "label": ds["label"], "collection": ds["collection"],
            "documents": await db[ds["collection"]].estimated_document_count(),
            "file": file_info, "last_run": last_run,
        }
    out["imported"] = await is_imported(db)
    return out


# ---------------------------------------------------------------------------
# Resolver — priorité : ASTRA TAS local → ASTRA TG local → saisie manuelle.
# Plaque seule : indisponible sans fournisseur externe. VIN : phase 3 (eDatenblatt).
# AutoRef / NHTSA vPIC : crochets réservés, désactivés (aucun appel implémenté).
# ---------------------------------------------------------------------------
def _base_fields(doc):
    return {
        "type_carburant": FUEL_LABELS.get(doc.get("fuel_code"), doc.get("fuel_code") or None),
        "cylindree_cm3": doc.get("engine_capacity"),
        "puissance_kw": doc.get("power_kw"),
        "poids_vide": doc.get("curb_weight"),
        "poids_total": doc.get("gross_weight"),
        "nombre_places": doc.get("seats"),
    }


def _tas_emission_fields(row, fuel_code):
    conso, norme = (None, None)
    if row.get("conso_wltp"):
        conso, norme = row["conso_wltp"], "WLTP"
    elif row.get("conso_nedc"):
        conso, norme = row["conso_nedc"], "NEDC"
    co2, co2n = None, None
    for val, n in ((row.get("co2_wltp"), "WLTP"), (row.get("co2_nedc"), "NEDC")):
        if val is not None and (val > 0 or fuel_code in ELECTRIC_FUELS):
            co2, co2n = val, n
            break
    return {"conso_officielle_l_100km": conso,
            "conso_officielle_norme": norme if conso else None,
            "co2_g_km": co2, "co2_norme": co2n}


def _row_has_data(r, fuel_code):
    if r.get("conso_wltp") or r.get("conso_nedc"):
        return True
    for k in ("co2_wltp", "co2_nedc"):
        v = r.get(k)
        if v is not None and (v > 0 or fuel_code in ELECTRIC_FUELS):
            return True
    return False


def _build_result(provider, doc, rows):
    fuel = doc.get("fuel_code") or ""
    useful = [r for r in rows if _row_has_data(r, fuel)]
    seen, uniq = set(), []
    for r in useful:
        sig = tuple(sorted(_tas_emission_fields(r, fuel).items(), key=lambda kv: kv[0]))
        if sig not in seen:
            seen.add(sig)
            uniq.append(r)
    row, resolved = (uniq[0] if uniq else None), len(uniq) <= 1
    if not resolved:
        boxes = [b for b in (doc.get("gearboxes") or []) if b]
        if len(set(boxes)) == 1:
            match = [r for r in uniq if (r.get("gearbox") or "").lower() == boxes[0].lower()]
            if len(match) == 1:
                row, resolved = match[0], True
    fields = dict(_base_fields(doc))
    variantes = []
    if resolved:
        if row:
            fields.update(_tas_emission_fields(row, fuel))
    else:
        variantes = [{"label": gearbox_label(r.get("gearbox")),
                      "fields": {k: v for k, v in _tas_emission_fields(r, fuel).items() if v is not None}}
                     for r in uniq]
    return {
        "provider": provider,
        "matched_by": "homologation",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "fields": {k: v for k, v in fields.items() if v is not None and v != ""},
        "variantes": variantes,
        "match": {"approval_no": doc.get("approval_no"), "make": doc.get("make"),
                  "model": doc.get("commercial_name") or doc.get("type"),
                  "category": doc.get("category"),
                  "dataset": "TAS" if provider == "astra_tas" else "TG (historique)"},
    }


async def lookup_homologation(db, key):
    doc = await db.astra_tas.find_one({"_key": key}, {"_id": 0})
    if doc:
        rows = await db.astra_tas_emissions.find({"_key": key}, {"_id": 0}).sort("seq", 1).to_list(100)
        return _build_result("astra_tas", doc, rows)
    doc = await db.astra_tg.find_one({"_key": key}, {"_id": 0})
    if doc:
        rows = await db.astra_tg_verbrauch.find({"_key": key}, {"_id": 0}).sort("seq", 1).to_list(100)
        return _build_result("astra_tg", doc, rows)
    return None


async def resolve_vehicle_data(db, vehicle):
    t0 = time.perf_counter()
    if not await is_imported(db):
        raise AstraLookupError(
            "Base technique ASTRA non importée sur ce serveur — l'import des données officielles "
            "se lance automatiquement au démarrage (ASTRA_SYNC_ENABLED=true) ou manuellement "
            "via POST /api/astra/import.", "not_imported", 503)
    key = normalize_approval(vehicle.get("numero_homologation"))
    if not key:
        raise AstraLookupError(
            "Aucun n° d'homologation renseigné (case 24 du permis de circulation). "
            "La recherche par plaque seule n'est pas disponible sans fournisseur externe payant, "
            "et la recherche par VIN (eDatenblatt) arrivera en phase 3. "
            "Scannez la carte grise ou saisissez le n° d'homologation, puis relancez.",
            "missing_homologation", 422)
    result = await lookup_homologation(db, key)
    if not result:
        raise AstraLookupError(
            f"Homologation « {vehicle.get('numero_homologation')} » introuvable dans les données "
            "officielles ASTRA locales (registres TAS et TG). Vérifiez la case 24 du permis de circulation.",
            "not_found", 404)
    result["lookup_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result
