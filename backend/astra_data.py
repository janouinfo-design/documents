"""Données officielles ASTRA/OFROU (opendata.astra.admin.ch/ivzod) — copie locale.
Source principale du resolver technique : aucune clé ni fournisseur externe requis."""
import asyncio
import csv
import hashlib
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from pymongo import ReplaceOne
from pymongo.errors import DuplicateKeyError

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
    "edatenblatt": {
        "label": "eDatenblatt — fiches COC par VIN",
        "url": f"{ASTRA_BASE}/3000-eDatenblatt/eDatenblatt.csv",
        "filename": "eDatenblatt.csv",
        "collection": "astra_edatenblatt",
        "multi": False,
        "dedupe_sig": True,
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

# Codes carburant numériques eDatenblatt (table officielle "Codes")
EDB_FUEL_LABELS = {
    "10": "Essence", "11": "Essence E5", "12": "Essence E10", "13": "Essence E15",
    "14": "Essence E25", "15": "Éthanol", "16": "Éthanol E85", "18": "Éthanol E75",
    "19": "Mélange", "20": "Diesel", "21": "Biodiesel", "22": "ED95",
    "23": "GTL (Diesel)", "24": "BTL (Diesel)", "25": "CTL (Diesel)", "26": "HVO (Diesel)",
    "27": "XTL", "30": "GPL", "40": "Gaz naturel (CNG)", "44": "Biométhane",
    "50": "Hydrogène", "60": "GNL", "81": "Diesel B5", "82": "Diesel B7",
    "90": "Autres", "91": "Air comprimé",
}

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


def normalize_vin(s):
    if not s:
        return None
    v = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return v or None


def gearbox_label(code):
    c = (code or "").strip()
    m = re.match(r"^([A-Za-z])(\d+)?", c)
    if not m:
        return c or "Variante"
    kind = GEARBOX_KINDS.get(m.group(1).lower())
    if not kind:
        return f"Boîte {c}"
    label = f"Boîte {kind}" + (f" ({m.group(2)} rapports)" if m.group(2) else "")
    if len(c) > len(m.group(0)):
        label += f" — {c}"
    return label


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


def parse_edatenblatt(path):
    _TRUE = {"1", "true", "yes", "x", "ja", "oui"}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        idx = {c.strip(): i for i, c in enumerate(header)}
        for row in reader:
            vin = normalize_vin(_g(row, idx, "0.10. VehicleIdentificationNumber"))
            if not vin:
                continue
            yield {
                "_key": vin[:10],
                "approval_eu": _g(row, idx, "0.2. TypeApprovalNumber") or None,
                "make": _g(row, idx, "0.1. Make") or None,
                "commercial_name": _g(row, idx, "0.2.1. CommercialName") or None,
                "type": _g(row, idx, "0.2. Type") or None,
                "variant": _g(row, idx, "0.2. Variant") or None,
                "version": _g(row, idx, "0.2. Version") or None,
                "fuel_code": _g(row, idx, "26. FuelCode") or None,
                "hybrid_class": _g(row, idx, "23.1. ClassOfHybridVehicleCode") or None,
                "is_electric": _g(row, idx, "23. PureElectricVehIndicator").lower() in _TRUE,
                "engine_capacity": _to_int(_g(row, idx, "25. EngineCapacity")),
                "power_kw": _to_float(_g(row, idx, "27.1. MaximumNetPower")),
                "curb_weight": _to_int(_g(row, idx, "13. MassOfTheVehicleInRunningOrder")),
                "gross_weight": _to_int(_g(row, idx, "16.1. TechnPermMaxLadenMass")),
                "seats": _to_int(_g(row, idx, "42. NrOfSeatingPositions")),
                "conso_nedc": _to_float(_g(row, idx, "49. CombinedFuelConsumption")),
                "co2_nedc": _to_float0(_g(row, idx, "49. CombinedCO2")),
                "conso_wltp": _to_float(_g(row, idx, "49. WLTPCombinedFuelCons")),
                "co2_wltp": _to_float0(_g(row, idx, "49. WLTPCombinedCO2")),
                "conso_wltp_weighted": _to_float(_g(row, idx, "49. WLTPWeightedCombinedFuelCons")),
                "co2_wltp_weighted": _to_float0(_g(row, idx, "49. WLTPWeightedCombinedCO2")),
            }


PARSERS = {"tas": parse_tas, "tas_emission": parse_tas_emission,
           "tg": parse_tg, "tg_verbrauch": parse_tg_verbrauch,
           "edatenblatt": parse_edatenblatt}


# ---------------------------------------------------------------------------
# Téléchargement + import (batch/upserts, reprise via run mensuel)
# ---------------------------------------------------------------------------
_IMPORT_RUNNING = False


def import_running() -> bool:
    return _IMPORT_RUNNING


async def _acquire_lock(db) -> bool:
    """Verrou atomique en base — empêche deux imports concurrents (multi-process/hot-reload)."""
    now = datetime.now(timezone.utc)
    until = (now + timedelta(minutes=30)).isoformat()
    res = await db.astra_locks.update_one(
        {"_id": "import", "locked_until": {"$lt": now.isoformat()}},
        {"$set": {"locked_until": until}})
    if res.modified_count:
        return True
    try:
        await db.astra_locks.insert_one({"_id": "import", "locked_until": until})
        return True
    except DuplicateKeyError:
        return False


async def _release_lock(db):
    await db.astra_locks.update_one(
        {"_id": "import"},
        {"$set": {"locked_until": datetime.now(timezone.utc).isoformat()}})


async def import_active(db) -> bool:
    if _IMPORT_RUNNING:
        return True
    doc = await db.astra_locks.find_one({"_id": "import"})
    return bool(doc and doc.get("locked_until", "") > datetime.now(timezone.utc).isoformat())


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
            if ds.get("dedupe_sig"):
                sig = hashlib.md5(repr(sorted(doc.items())).encode()).hexdigest()[:16]
                doc["sig"] = sig
                filt = {"_key": doc["_key"], "sig": sig}
            elif ds["multi"]:
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
    if _IMPORT_RUNNING or not await _acquire_lock(db):
        logger.info("ASTRA: import déjà en cours — nouvelle demande ignorée")
        return [{"status": "already_running"}]
    _IMPORT_RUNNING = True
    try:
        names = datasets or list(DATASETS)
        return [await import_dataset(db, n, download, force_download) for n in names]
    finally:
        _IMPORT_RUNNING = False
        await _release_lock(db)


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
           "import_running": await import_active(db), "datasets": {}}
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
# Resolver — priorité : ASTRA TAS local → ASTRA TG local → eDatenblatt (VIN) → manuel.
# Plaque seule : indisponible sans fournisseur externe.
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
    out = {"conso_officielle_l_100km": None, "conso_officielle_kwh_100km": None,
           "co2_g_km": co2, "co2_norme": co2n}
    if fuel_code == "E":
        out["conso_officielle_kwh_100km"] = conso
    elif fuel_code in ELECTRIC_FUELS:
        conso = None  # hydrogène/autre : unité non garantie — aucune valeur supposée
    else:
        out["conso_officielle_l_100km"] = conso
    out["conso_officielle_norme"] = norme if conso else None
    return out


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


# ---------------------------------------------------------------------------
# Recherche par VIN (eDatenblatt — VIN anonymisés aux 10 premiers caractères)
# ---------------------------------------------------------------------------
def edb_fuel_label(doc):
    if doc.get("is_electric"):
        return "Électrique"
    base = EDB_FUEL_LABELS.get(doc.get("fuel_code") or "", doc.get("fuel_code") or None)
    if base and doc.get("hybrid_class"):
        return f"{base} / Électrique (hybride)"
    return base


def _edb_fields(doc):
    conso, norme = None, None
    for v, n in ((doc.get("conso_wltp"), "WLTP"), (doc.get("conso_wltp_weighted"), "WLTP"),
                 (doc.get("conso_nedc"), "NEDC")):
        if v:
            conso, norme = v, n
            break
    co2, co2n = None, None
    for v, n in ((doc.get("co2_wltp"), "WLTP"), (doc.get("co2_wltp_weighted"), "WLTP"),
                 (doc.get("co2_nedc"), "NEDC")):
        if v is not None and (v > 0 or doc.get("is_electric")):
            co2, co2n = v, n
            break
    return {
        "type_carburant": edb_fuel_label(doc),
        "cylindree_cm3": doc.get("engine_capacity"),
        "puissance_kw": doc.get("power_kw"),
        "poids_vide": doc.get("curb_weight"),
        "poids_total": doc.get("gross_weight"),
        "nombre_places": doc.get("seats"),
        "conso_officielle_l_100km": None if doc.get("is_electric") else conso,
        "conso_officielle_kwh_100km": conso if doc.get("is_electric") else None,
        "conso_officielle_norme": norme if conso else None,
        "co2_g_km": co2,
        "co2_norme": co2n,
    }


async def lookup_vin(db, vin):
    v = normalize_vin(vin)
    if not v or len(v) < 10:
        return None
    prefix = v[:10]
    rows = await db.astra_edatenblatt.find({"_key": prefix}, {"_id": 0}).to_list(300)
    if not rows:
        return None
    groups, seen = [], set()
    for r in rows:
        f = {k: val for k, val in _edb_fields(r).items() if val is not None}
        sig = tuple(sorted(f.items()))
        if sig in seen:
            continue
        seen.add(sig)
        groups.append((r, f))
    first = groups[0][0]
    base = {
        "provider": "astra_edatenblatt", "matched_by": "vin",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "match": {"approval_no": first.get("approval_eu"), "make": first.get("make"),
                  "model": first.get("commercial_name") or first.get("type"),
                  "vin_prefix": prefix, "dataset": "eDatenblatt",
                  "candidates": len(groups)},
    }
    if len(groups) == 1:
        return {**base, "fields": groups[0][1], "variantes": []}
    if len(groups) > 12:
        raise AstraLookupError(
            f"VIN trop ambigu — {len(groups)} configurations possibles pour le préfixe {prefix}. "
            "Renseignez le n° d'homologation (case 24 du permis de circulation) pour une correspondance exacte.",
            "ambiguous_vin", 409)
    common = {k: v2 for k, v2 in groups[0][1].items()
              if all(g[1].get(k) == v2 for g in groups[1:])}
    variantes = []
    for r, f in groups:
        diff = {k: v2 for k, v2 in f.items() if k not in common}
        parts = [r.get("commercial_name") or r.get("type"), r.get("version") or r.get("variant")]
        if r.get("power_kw"):
            parts.append(f"{r['power_kw']:g} kW")
        variantes.append({"label": " · ".join(str(x) for x in parts if x) or "Variante",
                          "fields": diff})
    return {**base, "fields": common, "variantes": variantes}


async def resolve_vehicle_data(db, vehicle):
    t0 = time.perf_counter()
    if not await is_imported(db):
        raise AstraLookupError(
            "Base technique ASTRA non importée sur ce serveur — l'import des données officielles "
            "se lance automatiquement au démarrage (ASTRA_SYNC_ENABLED=true) ou manuellement "
            "via POST /api/astra/import.", "not_imported", 503)
    key = normalize_approval(vehicle.get("numero_homologation"))
    vin = (vehicle.get("vin") or "").strip()
    result = None
    if key:
        result = await lookup_homologation(db, key)
    if result is None and vin:
        result = await lookup_vin(db, vin)
    if result is None:
        if key:
            raise AstraLookupError(
                f"Homologation « {vehicle.get('numero_homologation')} » introuvable dans les données "
                "officielles ASTRA locales (registres TAS et TG"
                + (", VIN sans correspondance eDatenblatt" if vin else "")
                + "). Vérifiez la case 24 du permis de circulation.",
                "not_found", 404)
        if vin:
            if await db.astra_edatenblatt.estimated_document_count() == 0:
                raise AstraLookupError(
                    "Recherche par VIN indisponible — le dataset eDatenblatt n'est pas encore importé "
                    "(POST /api/astra/import?datasets=edatenblatt).", "not_imported", 503)
            raise AstraLookupError(
                f"VIN « {vin} » introuvable dans les fiches eDatenblatt (véhicules importés dès ~2023). "
                "Renseignez le n° d'homologation (case 24 du permis de circulation).",
                "not_found", 404)
        raise AstraLookupError(
            "Aucun n° d'homologation (case 24) ni VIN renseigné. "
            "La recherche par plaque seule n'est pas disponible sans fournisseur externe payant. "
            "Scannez la carte grise ou saisissez le n° d'homologation ou le VIN, puis relancez.",
            "missing_homologation", 422)
    result["lookup_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return result

