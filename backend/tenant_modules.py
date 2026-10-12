"""Modules fonctionnels activables par client (console Super Admin).
Désactivé = accès bloqué (403 MODULE_DISABLED), jamais de suppression de données.
Clé absente dans `tenant.modules` = module ACTIVÉ (zéro régression pour les clients existants)."""
import re
from typing import Optional

MODULES = [
    ("vehicles", "Véhicules"),
    ("documents", "Documents"),
    ("deadlines", "Échéances"),
    ("costs", "Coûts"),
    ("energy", "Énergie"),
    ("drivers", "Conducteurs"),
    ("fines", "Amendes"),
    ("ai", "Assistant IA"),
    ("alerts", "Alertes"),
    ("integrity", "Intégrité"),
]
MODULE_KEYS = [k for k, _ in MODULES]
MODULE_LABELS = dict(MODULES)
CORE_MODULE = "vehicles"

_V = r"/api/vehicles/[^/]+"
# Toutes les règles qui matchent s'appliquent : une sous-ressource véhicule est bloquée si SON module OU le socle est OFF.
_RULES = [
    ("documents", rf"^(/api/documents|/api/document-types|/api/doc-requirements|/api/doc-categories|/api/business-categories"
                  rf"|/api/upload|{_V}/documents|{_V}/conformite-documents|/api/vehicles-archive/[^/]+/documents|/api/reports/conformite)"),
    ("deadlines", r"^(/api/deadlines|/api/timeline)"),
    ("costs", rf"^(/api/costs|{_V}/costs|/api/reports/couts)"),
    ("energy", rf"^(/api/fuel|/api/energy|/api/tenant-settings/fuel|/api/astra|{_V}/fuel-transactions|{_V}/energy"
               rf"|/api/fleet/consumption-ranking|/api/me/fuel-transactions)"),
    ("drivers", rf"^(/api/drivers|/api/driver-assignments|{_V}/driver-assignments|{_V}/driver-at)"),
    ("fines", rf"^(/api/fines|{_V}/fines|/api/me/fines)"),
    ("ai", r"^/api/ai(/|$)"),
    ("alerts", r"^/api/alerts(/|$)"),
    ("integrity", r"^/api/fleet/integrity"),
    ("vehicles", r"^(/api/vehicles|/api/inspections|/api/technical-data|/api/navixy|/api/integrations|/api/me/vehicles)"),
]
_COMPILED = [(k, re.compile(rx)) for k, rx in _RULES]


def resolve_modules(tenant: Optional[dict]) -> dict:
    raw = (tenant or {}).get("modules") or {}
    return {k: raw.get(k) is not False for k in MODULE_KEYS}


def disabled_module_for(tenant: Optional[dict], path: str) -> Optional[str]:
    mods = resolve_modules(tenant)
    for key, rx in _COMPILED:
        if rx.match(path) and not mods[key]:
            return key
    return None


def disabled_detail(key: str) -> dict:
    return {"code": "MODULE_DISABLED", "module": key,
            "message": f"Module {MODULE_LABELS.get(key, key)} désactivé pour ce compte"}


def deadline_module(item: dict) -> Optional[str]:
    """Module propriétaire d'une échéance du moteur central (None = échéance véhicule socle)."""
    if item.get("is_fine"):
        return "fines"
    if item.get("type") == "carte_carburant":
        return "energy"
    if item.get("source") == "document":
        return "documents"
    return None
