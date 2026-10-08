"""Phase 4C — Lot F (6a) : import CSV/XLSX de transactions carburant — parsing, mapping, normalisation, dédup.

Pipeline (spec §6a) : upload → job `mapping` → mapping colonnes → preview (`fuel_import_rows` = espace de travail,
0 écriture métier finale) → confirm (documents sans fichier + fuel_transactions) / force ligne motivé.
Dédup propre à Documents (aucun secret Journal) : (tenant, fournisseur, external_transaction_id) → `dedup_key`
sha256 déterministe tenant-scopée → intra-fichier.
"""
import csv
import hashlib
import io
import re
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

MAX_BYTES = 30 * 1024 * 1024
MAX_ROWS = 20000
JOB_STATUSES = ("mapping", "preview", "confirmed")  # spec §6a.6 — pas d'autre taxonomie
ROW_STATUSES = ("pending", "ok", "invalid", "duplicate", "unknown_card", "amount_mismatch", "unknown_vehicle")
IMPORTABLE = ("ok", "amount_mismatch", "unknown_card")  # confirm importe ces statuts ; duplicate/invalid/unknown_vehicle mis de côté
ROW_LABELS = {"pending": "En attente", "ok": "Valide", "invalid": "Invalide", "duplicate": "Doublon", "unknown_card": "Carte non résolue",
              "amount_mismatch": "Montant incohérent", "unknown_vehicle": "Véhicule non résolu"}
AMOUNT_TOLERANCE = 0.05
REASON_MIN_LEN = 3

# Champs cibles Documents (mapping explicite colonne source → champ). `required` : tx_datetime (ou tx_date) + amount_total.
IMPORT_FIELDS = [
    {"key": "tx_datetime", "label": "Date / heure de transaction", "required": True, "group": "transaction",
     "hint": "ISO ou JJ.MM.AAAA HH:MM — sans fuseau = heure locale Europe/Zurich (D5)", "guess": ["datetime", "date heure", "date/heure", "zeit", "date transaction", "transaction date", "tx_date", "datum", "date"]},
    {"key": "tx_time", "label": "Heure (si colonne séparée)", "required": False, "group": "transaction", "guess": ["heure", "time", "uhrzeit"]},
    {"key": "external_transaction_id", "label": "Référence transaction fournisseur", "required": False, "group": "transaction",
     "guess": ["transaction id", "n transaction", "ref", "reference", "beleg", "receipt", "ticket", "id"]},
    {"key": "fournisseur", "label": "Fournisseur (si colonne)", "required": False, "group": "transaction", "guess": ["fournisseur", "provider", "lieferant", "reseau", "network"]},
    {"key": "card_last4", "label": "Carte — 4 derniers chiffres / n° masqué", "required": False, "group": "carte",
     "hint": "Seuls les 4 derniers chiffres sont conservés (jamais le n° complet)", "guess": ["last4", "carte", "card", "karte", "kartennummer", "numero de carte"]},
    {"key": "vehicle_id", "label": "Identifiant véhicule Documents (UUID)", "required": False, "group": "vehicule", "guess": ["vehicle_id", "vehicle id", "id vehicule"]},
    {"key": "vehicle_hint", "label": "Immatriculation (aide à la revue, jamais d'auto-rattachement)", "required": False, "group": "vehicule",
     "guess": ["immatriculation", "plaque", "plate", "kennzeichen", "license", "vehicule", "vehicle", "fahrzeug"]},
    {"key": "driver_hint", "label": "Conducteur (indicatif)", "required": False, "group": "vehicule", "guess": ["chauffeur", "conducteur", "driver", "fahrer"]},
    {"key": "amount_total", "label": "Montant TTC", "required": True, "group": "montant", "guess": ["montant ttc", "montant", "amount", "total", "betrag", "brutto", "prix total"]},
    {"key": "currency", "label": "Devise (défaut CHF)", "required": False, "group": "montant", "guess": ["devise", "currency", "währung", "waehrung", "monnaie"]},
    {"key": "amount_chf", "label": "Contre-valeur CHF (devise ≠ CHF)", "required": False, "group": "montant", "guess": ["montant chf", "amount chf", "chf"]},
    {"key": "quantity", "label": "Quantité (litres ou kWh)", "required": False, "group": "quantite", "guess": ["quantite", "quantité", "litres", "liter", "menge", "quantity", "volume", "kwh"]},
    {"key": "unit", "label": "Unité (L / kWh)", "required": False, "group": "quantite", "guess": ["unite", "unité", "unit", "einheit"]},
    {"key": "unit_price", "label": "Prix unitaire", "required": False, "group": "quantite", "guess": ["prix unitaire", "prix/l", "prix litre", "unit price", "preis", "einzelpreis", "prix"]},
    {"key": "product_type", "label": "Produit / carburant", "required": False, "group": "quantite", "guess": ["produit", "product", "carburant", "fuel", "kraftstoff", "treibstoff", "artikel"]},
    {"key": "station_name", "label": "Station / lieu", "required": False, "group": "lieu", "guess": ["station", "lieu", "site", "tankstelle", "location", "ort"]},
    {"key": "country", "label": "Pays (ISO2)", "required": False, "group": "lieu", "guess": ["pays", "country", "land"]},
    {"key": "mileage", "label": "Kilométrage", "required": False, "group": "vehicule", "guess": ["kilometrage", "kilométrage", "km", "odometer", "mileage", "kilometerstand"]},
    {"key": "invoice_ref", "label": "N° facture / relevé", "required": False, "group": "transaction", "guess": ["facture", "invoice", "rechnung", "releve"]},
    {"key": "comment", "label": "Commentaire", "required": False, "group": "transaction", "guess": ["commentaire", "comment", "remarque", "bemerkung", "note"]},
]
FIELD_KEYS = {f["key"] for f in IMPORT_FIELDS}
_PRODUCT_MAP = {"diesel": "Diesel", "gasoil": "Diesel", "gazole": "Diesel", "essence": "Essence", "benzin": "Essence", "bleifrei": "Essence",
                "sans plomb": "Essence", "sp95": "Essence", "sp98": "Essence", "petrol": "Essence", "gasoline": "Essence", "unleaded": "Essence",
                "adblue": "AdBlue", "electri": "Électricité", "elektr": "Électricité", "strom": "Électricité", "recharge": "Électricité", "kwh": "Électricité"}
_DT_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
               "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y",
               "%d.%m.%y %H:%M", "%d.%m.%y", "%Y%m%d %H%M", "%Y%m%d")
_TIME_RE = re.compile(r"^(\d{1,2})[:h.](\d{2})(?::\d{2})?$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class MappingPayload(BaseModel):
    mapping: dict  # champ Documents → colonne source
    fournisseur: Optional[str] = None
    save_mapping: bool = False


class ReasonPayload(BaseModel):
    reason: str


class RowResolvePayload(BaseModel):
    vehicle_id: Optional[str] = None
    card_id: Optional[str] = None
    reason: str


class BulkAcceptPayload(BaseModel):
    row_ids: List[str]
    reason: str


def clean(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def norm_key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").casefold())


def num(v) -> Optional[float]:
    """Nombre tolérant : apostrophes/espaces milliers, virgule décimale, devise accolée. None si vide/invalide."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9,.\-]", "", str(v).replace("'", "").replace("’", "").replace(" ", "").replace("\u00a0", ""))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def last4(v) -> Optional[str]:
    digits = re.sub(r"\D", "", str(v or ""))
    return digits[-4:] if len(digits) >= 4 else None


def parse_datetime(v, time_v=None):
    """→ (date 'AAAA-MM-JJ', heure 'HH:MM' | None) ou (None, None). Fuseau ignoré (D5 : heure locale Zurich)."""
    if isinstance(v, datetime):
        d, h = v.strftime("%Y-%m-%d"), v.strftime("%H:%M")
    elif isinstance(v, date):
        d, h = v.isoformat(), None
    else:
        s = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", str(v or "").strip())
        d = h = None
        for fmt in _DT_FORMATS:
            try:
                dt = datetime.strptime(s, fmt)
            except ValueError:
                continue
            d = dt.strftime("%Y-%m-%d")
            h = dt.strftime("%H:%M") if any(x in fmt for x in ("%H",)) else None
            break
        if d is None:
            return None, None
    if time_v not in (None, ""):
        if isinstance(time_v, datetime):
            h = time_v.strftime("%H:%M")
        else:
            m = _TIME_RE.match(str(time_v).strip())
            if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
                h = f"{int(m.group(1)):02d}:{m.group(2)}"
    return d, h


def product_label(v) -> Optional[str]:
    s = (clean(v) or "").casefold()
    if not s:
        return None
    for k, label in _PRODUCT_MAP.items():
        if k in s:
            return label
    return clean(v)


def suggest_mapping(columns: list) -> dict:
    """Auto-suggestion par mots-clés FR/DE/EN — proposition uniquement, l'admin confirme chaque colonne."""
    out, used = {}, set()
    for f in sorted(IMPORT_FIELDS, key=lambda f: (not f["required"], -max(len(g) for g in f["guess"]))):
        for col in columns:
            if col in used:
                continue
            nk = norm_key(col)
            if any(norm_key(g) == nk for g in f["guess"]) or any(len(norm_key(g)) >= 4 and norm_key(g) in nk for g in f["guess"]):
                out[f["key"]] = col
                used.add(col)
                break
    return out


def parse_file(filename: str, data: bytes):
    """→ (columns, rows[dict], meta). CSV : encodage utf-8-sig/utf-8/latin-1 + délimiteur ; , tab |. XLSX : 1re feuille (read_only)."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"fichier > {MAX_BYTES // (1024 * 1024)} MB")
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = None
        for r in it:
            if r and any(c not in (None, "") for c in r):
                header = [clean(c) or f"col_{i + 1}" for i, c in enumerate(r)]
                break
        if not header:
            raise ValueError("feuille vide")
        rows = []
        for r in it:
            if r is None or not any(c not in (None, "") for c in r):
                continue
            rows.append({header[i]: (c if isinstance(c, (datetime, date, int, float)) else clean(c)) for i, c in enumerate(r) if i < len(header)})
            if len(rows) > MAX_ROWS:
                raise ValueError(f"plus de {MAX_ROWS} lignes")
        wb.close()
        return header, rows, {"format": "xlsx", "sheet": ws.title}
    if not name.endswith((".csv", ".txt")):
        raise ValueError("format non supporté : CSV ou XLSX")
    text, encoding = None, None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text, encoding = data.decode(enc), enc
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delimiter = max(";,\t|", key=lambda d: sample.count(d))
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    header = None
    rows = []
    for r in reader:
        if not r or not any(clean(c) for c in r):
            continue
        if header is None:
            header = [clean(c) or f"col_{i + 1}" for i, c in enumerate(r)]
            continue
        rows.append({header[i]: clean(c) for i, c in enumerate(r) if i < len(header)})
        if len(rows) > MAX_ROWS:
            raise ValueError(f"plus de {MAX_ROWS} lignes")
    if header is None:
        raise ValueError("fichier vide")
    return header, rows, {"format": "csv", "encoding": encoding, "delimiter": delimiter}


def mapping_errors(mapping: dict, columns: list) -> list:
    errors = []
    for k, col in mapping.items():
        if k not in FIELD_KEYS:
            errors.append(f"champ inconnu : {k}")
        elif col not in columns:
            errors.append(f"colonne absente du fichier : {col} ({k})")
    if not mapping.get("tx_datetime"):
        errors.append("tx_datetime (date de transaction) obligatoire")
    if not mapping.get("amount_total"):
        errors.append("amount_total (montant TTC) obligatoire")
    return errors


def normalize_row(raw: dict, mapping: dict, job_fournisseur: Optional[str]):
    """Colonne source → champ Documents. Aucune valeur inventée : champ non mappé = None. → (normalized, errors)."""
    g = lambda k: raw.get(mapping[k]) if mapping.get(k) else None  # noqa: E731
    errors = []
    d, h = parse_datetime(g("tx_datetime"), g("tx_time"))
    if not d:
        errors.append("date de transaction manquante ou invalide")
    montant = num(g("amount_total"))
    if montant is None:
        errors.append("montant TTC manquant ou invalide")
    elif montant < 0:
        errors.append("montant TTC négatif")
    devise = (clean(g("currency")) or "CHF").upper()
    if not _CURRENCY_RE.match(devise):
        errors.append(f"devise invalide : {devise}")
    montant_chf = num(g("amount_chf"))
    if devise == "CHF":
        montant_chf = None  # D7 : contre-valeur sans objet en CHF
    qty = num(g("quantity"))
    if qty is not None and qty < 0:
        errors.append("quantité négative")
    unit_raw = (clean(g("unit")) or "").casefold()
    product = product_label(g("product_type"))
    electric = "kwh" in unit_raw or (product == "Électricité")
    prix_unitaire = num(g("unit_price"))
    km = num(g("mileage"))
    fournisseur = clean(g("fournisseur")) or clean(job_fournisseur)
    norm = {
        "external_transaction_id": clean(g("external_transaction_id")), "fournisseur": fournisseur,
        "card_last4": last4(g("card_last4")), "date": d, "heure": h, "date_heure": f"{d}T{h}:00" if d and h else d,
        "station": clean(g("station_name")), "pays": (clean(g("country")) or "")[:2].upper() or None,
        "type_carburant": product, "energie": "electrique" if electric else "thermique",
        "litres": None if electric else (round(qty, 2) if qty is not None else None),
        "energie_kwh": round(qty, 2) if electric and qty is not None else None,
        "prix_litre": None if electric else prix_unitaire, "prix_kwh": prix_unitaire if electric else None,
        "montant": round(montant, 2) if montant is not None else None, "devise": devise,
        "montant_chf": round(montant_chf, 2) if montant_chf is not None else None,
        "kilometrage": int(round(km)) if km is not None else None,
        "vehicle_id_hint": clean(g("vehicle_id")), "plaque_hint": clean(g("vehicle_hint")), "driver_hint": clean(g("driver_hint")),
        "invoice_ref": clean(g("invoice_ref")), "commentaire": clean(g("comment")),
    }
    return norm, errors


def amount_mismatch(norm: dict) -> Optional[str]:
    """qté × prix unitaire ≠ montant (± 5 %, min 0.10) → explication ; None si cohérent ou non calculable."""
    qty = norm.get("energie_kwh") if norm.get("energie") == "electrique" else norm.get("litres")
    price = norm.get("prix_kwh") if norm.get("energie") == "electrique" else norm.get("prix_litre")
    m = norm.get("montant")
    if not (qty and price and m):
        return None
    calc = qty * price
    if abs(calc - m) > max(0.10, AMOUNT_TOLERANCE * m):
        return f"{qty} × {price} = {calc:.2f} ≠ montant {m:.2f} {norm.get('devise')}"
    return None


def dedup_key(tenant_id: str, norm: dict) -> str:
    """Clé déterministe propre à Documents (aucun secret) : tenant|fournisseur|date_heure|last4|station|litres/kwh|montant|devise."""
    qty = norm.get("energie_kwh") if norm.get("energie") == "electrique" else norm.get("litres")
    parts = [tenant_id, norm_key(norm.get("fournisseur")), norm.get("date_heure") or "", norm.get("card_last4") or "",
             norm_key(norm.get("station")), f"{qty:.2f}" if qty is not None else "", f"{norm.get('montant'):.2f}" if norm.get("montant") is not None else "",
             norm.get("devise") or ""]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def status_priority(flags: dict) -> str:
    """invalid > duplicate > unknown_vehicle > unknown_card > amount_mismatch > ok."""
    for s in ("invalid", "duplicate", "unknown_vehicle", "unknown_card", "amount_mismatch"):
        if flags.get(s):
            return s
    return "ok"


def counts_for(rows: list) -> dict:
    c = {s: 0 for s in ROW_STATUSES}
    for r in rows:
        c[r.get("status", "pending")] = c.get(r.get("status", "pending"), 0) + 1
    c["total"] = len(rows)
    c["imported"] = sum(1 for r in rows if r.get("imported"))
    return c


def example_values(rows: list, columns: list, n: int = 3) -> dict:
    out = {}
    for col in columns:
        vals = []
        for r in rows:
            v = r.get(col)
            if v not in (None, "") and str(v) not in vals:
                vals.append(str(v) if not isinstance(v, (datetime, date)) else v.isoformat())
            if len(vals) >= n:
                break
        out[col] = vals
    return out
