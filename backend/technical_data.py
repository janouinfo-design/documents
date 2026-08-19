"""Fournisseur de données techniques véhicules suisses (données officielles OFROU/ASTRA).
Implémentation SwissCarInfo API v3 — active uniquement si SWISSCARINFO_API_KEY est renseignée.
Stratégie : plaque (registre IVI, véhicule exact) en priorité, n° d'homologation (TG) en secours."""
import logging
import os
import re
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

TECH_FIELD_DEFS = [
    {"key": "type_carburant", "label": "Carburant", "target": "root", "kind": "str"},
    {"key": "cylindree_cm3", "label": "Cylindrée (cm³)", "target": "root", "kind": "int"},
    {"key": "puissance_kw", "label": "Puissance (kW)", "target": "root", "kind": "float"},
    {"key": "conso_officielle_l_100km", "label": "Consommation officielle (L/100 km)", "target": "root", "kind": "float"},
    {"key": "conso_officielle_kwh_100km", "label": "Consommation officielle (kWh/100 km)", "target": "root", "kind": "float"},
    {"key": "conso_officielle_norme", "label": "Norme consommation", "target": "root", "kind": "str"},
    {"key": "co2_g_km", "label": "CO₂ officiel (g/km)", "target": "root", "kind": "float"},
    {"key": "co2_norme", "label": "Norme CO₂", "target": "root", "kind": "str"},
    {"key": "poids_vide", "label": "Poids à vide (kg)", "target": "root", "kind": "int"},
    {"key": "poids_total", "label": "Poids total (kg)", "target": "carte_grise", "kind": "int"},
    {"key": "nombre_places", "label": "Nombre de places", "target": "carte_grise", "kind": "int"},
    {"key": "date_prochain", "label": "Prochain contrôle technique", "target": "controle_technique", "kind": "date"},
]

CANTONS = {"AG", "AI", "AR", "BE", "BL", "BS", "FR", "GE", "GL", "GR", "JU", "LU",
           "NE", "NW", "OW", "SG", "SH", "SO", "SZ", "TG", "TI", "UR", "VD", "VS", "ZG", "ZH"}


class TechnicalLookupError(Exception):
    pass


class VehicleTechnicalDataProvider:
    """Interface — permet de brancher un autre fournisseur licencié sans toucher au métier."""

    def lookup(self, vin=None, homologation_number=None, make=None, model=None,
               variant=None, plate=None) -> dict:
        raise NotImplementedError


def _num(x):
    try:
        n = float(str(x).replace(",", "."))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _num0(x):
    """Comme _num mais accepte 0 (CO₂ légitime à 0 pour un véhicule électrique)."""
    try:
        n = float(str(x).replace(",", "."))
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def _conso_from_row(row):
    if not row:
        return None, None, None, None
    conso_w, conso_n = _num(row.get("primaryFuelConsumptionWltp")), _num(row.get("primaryFuelConsumption"))
    co2_w, co2_n = _num0(row.get("primaryEmissionCo2Wltp")), _num0(row.get("primaryEmissionCo2"))
    conso, cnorme = (conso_w, "WLTP") if conso_w else (conso_n, "NEDC") if conso_n else (None, None)
    if co2_w is not None:
        co2, co2norme = co2_w, "WLTP"
    elif co2_n is not None:
        co2, co2norme = co2_n, "NEDC"
    else:
        co2, co2norme = None, None
    return conso, cnorme, co2, co2norme


def _variant_fields(row):
    conso, cnorme, co2, co2n = _conso_from_row(row)
    return {"conso_officielle_l_100km": conso,
            "conso_officielle_norme": cnorme if conso else None,
            "co2_g_km": co2,
            "co2_norme": co2n if co2 is not None else None}


def _pick_emission_row(rows, gearbox_code=None):
    """Retourne (row, resolved). resolved=False si plusieurs variantes divergent
    sans correspondance de boîte — l'utilisateur devra alors choisir."""
    if not rows:
        return None, True
    if len(rows) == 1:
        return rows[0], True
    if gearbox_code:
        pref = str(gearbox_code)[:1].lower()
        for r in rows:
            if str(r.get("chGearboxType") or "")[:1].lower() == pref:
                return r, True
    vals = [_variant_fields(r) for r in rows]
    if all(v == vals[0] for v in vals[1:]):
        return rows[0], True
    return None, False


def _variantes(rows):
    return [{"label": r.get("chGearboxType_label") or r.get("chGearboxType") or "Variante",
             "fields": _variant_fields(r)} for r in rows]


class SwissCarInfoProvider(VehicleTechnicalDataProvider):
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.swisscarinfo.ch").rstrip("/")

    def _get(self, path: str, params: dict) -> dict:
        try:
            r = requests.get(f"{self.base_url}{path}", params=params,
                             headers={"X-API-Key": self.api_key}, timeout=20)
        except requests.RequestException:
            raise TechnicalLookupError("Base technique injoignable — réessayez plus tard.")
        if r.status_code == 300:
            raise TechnicalLookupError("Plaque ambiguë (plaque interchangeable ?) — la recherche continue via le n° d'homologation.")
        if r.status_code in (401, 403):
            raise TechnicalLookupError("Clé API SwissCarInfo invalide ou non autorisée.")
        if r.status_code == 404:
            raise TechnicalLookupError("Véhicule introuvable dans la base technique.")
        if r.status_code == 429:
            raise TechnicalLookupError("Quota SwissCarInfo atteint — réessayez plus tard ou augmentez le plan.")
        if r.status_code >= 400:
            raise TechnicalLookupError(f"Erreur base technique (HTTP {r.status_code}).")
        try:
            return r.json()
        except ValueError:
            raise TechnicalLookupError("Réponse invalide de la base technique.")

    def lookup(self, vin=None, homologation_number=None, make=None, model=None,
               variant=None, plate=None) -> dict:
        if plate:
            m = re.match(r"^\s*([A-Za-z]{2})\s*[- ]?\s*(\d{1,7})\s*$", str(plate))
            if m and m.group(1).upper() in CANTONS:
                try:
                    data = self._get("/v3/plate", {"canton": m.group(1).upper(),
                                                   "number": m.group(2), "lang": "fr", "labels": 1})
                    parsed = self._parse_plate(data)
                    if parsed:
                        return parsed
                except TechnicalLookupError as e:
                    logger.info("Recherche par plaque sans résultat (%s) — repli homologation", e)
        if homologation_number:
            data = self._get("/v3/search", {"q": str(homologation_number).strip().upper(),
                                            "type": "variant", "lang": "fr", "labels": 1})
            parsed = self._parse_variant(data)
            if parsed:
                return parsed
        raise TechnicalLookupError(
            "Aucun résultat — vérifiez la plaque et le n° d'homologation (case 24 du permis de circulation).")

    def _result(self, matched_by: str, fields: dict, variantes: list) -> dict:
        return {"provider": "swisscarinfo", "matched_by": matched_by,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "fields": {k: v for k, v in fields.items() if v not in (None, "")},
                "variantes": variantes}

    def _parse_plate(self, data: dict):
        vehicles = data.get("vehicles") or []
        if not vehicles:
            return None
        v = vehicles[0]
        enriched = v.get("enriched") or {}
        tas = enriched.get("tas_data") or {}
        rows = enriched.get("tas_emissions") or []
        row, resolved = _pick_emission_row(rows, v.get("gearbox"))
        conso, cnorme, co2_row, co2_row_norme = _conso_from_row(row)
        co2_w, co2_n = _num0(v.get("co2_wltp")), _num0(v.get("co2_nedc"))
        if co2_w is not None:
            co2, co2n = co2_w, "WLTP"
        elif co2_n is not None:
            co2, co2n = co2_n, "NEDC"
        else:
            co2, co2n = co2_row, co2_row_norme
        fields = {
            "cylindree_cm3": v.get("displacement") or tas.get("engineCapacity"),
            "puissance_kw": _num(v.get("power_kw")) or _num(tas.get("maximumNetPower")),
            "type_carburant": v.get("fuel_label") or tas.get("chFuelType_label"),
            "conso_officielle_l_100km": conso,
            "conso_officielle_norme": cnorme if conso else None,
            "co2_g_km": co2,
            "co2_norme": co2n if co2 else None,
            "poids_vide": v.get("curb_weight"),
            "poids_total": v.get("gross_weight"),
            "nombre_places": v.get("seats"),
            "date_prochain": v.get("next_inspection"),
        }
        return self._result("plate", fields, [] if resolved else _variantes(rows))

    def _parse_variant(self, data: dict):
        recs = data.get("data") or []
        rec = next((r for r in recs if r.get("tas_data")), recs[0] if recs else None)
        if not rec:
            return None
        tas = rec.get("tas_data") or {}
        rows = rec.get("tas_emissions") or []
        row, resolved = _pick_emission_row(rows)
        conso, cnorme, co2, co2n = _conso_from_row(row)
        fields = {
            "cylindree_cm3": tas.get("engineCapacity") or rec.get("mhubr"),
            "puissance_kw": _num(tas.get("maximumNetPower")) or _num(rec.get("mleist")),
            "type_carburant": tas.get("chFuelType_label"),
            "conso_officielle_l_100km": conso,
            "conso_officielle_norme": cnorme if conso else None,
            "co2_g_km": co2,
            "co2_norme": co2n if co2 else None,
            "poids_vide": tas.get("chMassOfTheVehicleInRunningOrderMinimum") or _num(rec.get("lgew1")),
            "poids_total": tas.get("technicallyPermissibleMaximumLadenMassMinimum") or _num(rec.get("ggew1")),
            "nombre_places": tas.get("chNrOfSeatingPositionsMinimum") or _num(rec.get("plt1")),
        }
        return self._result("homologation", fields, [] if resolved else _variantes(rows))


def get_technical_provider():
    """SwissCarInfoProvider si la clé est configurée, sinon None (enrichissement désactivé)."""
    key = os.environ.get("SWISSCARINFO_API_KEY")
    if key:
        return SwissCarInfoProvider(key, os.environ.get("SWISSCARINFO_BASE_URL"))
    return None
