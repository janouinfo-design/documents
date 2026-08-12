"""Service d'extraction de documents véhicule — abstraction provider + GPT vision."""
import base64
import io
import json
import logging
import os
import re
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

DOC_TYPES = {
    "permis_circulation": {"label": "Permis de circulation", "folder": "Carte grise"},
    "assurance": {"label": "Assurance", "folder": "Assurance"},
    "leasing": {"label": "Contrat de leasing", "folder": "Leasing"},
    "controle_technique": {"label": "Expertise / Contrôle technique", "folder": "Contrôle technique"},
    "facture": {"label": "Facture véhicule", "folder": "Factures"},
    "amende": {"label": "Amende", "folder": "Divers"},
    "autre": {"label": "Autre document", "folder": "Divers"},
}

# target: root (fiche véhicule) | carte_grise | assurance | leasing | controle_technique | document
FIELD_DEFS = {
    "permis_circulation": [
        {"key": "plaque", "label": "Immatriculation", "target": "root", "kind": "str"},
        {"key": "vin", "label": "VIN / N° de châssis", "target": "root", "kind": "str"},
        {"key": "marque", "label": "Marque", "target": "root", "kind": "str"},
        {"key": "modele", "label": "Modèle", "target": "root", "kind": "str"},
        {"key": "variante", "label": "Variante / type", "target": "root", "kind": "str"},
        {"key": "numero_homologation", "label": "N° d'homologation", "target": "root", "kind": "str"},
        {"key": "date_mise_circulation", "label": "1re mise en circulation", "target": "carte_grise", "kind": "date"},
        {"key": "type_carburant", "label": "Carburant", "target": "root", "kind": "str"},
        {"key": "cylindree_cm3", "label": "Cylindrée (cm³)", "target": "root", "kind": "int"},
        {"key": "puissance_kw", "label": "Puissance (kW)", "target": "root", "kind": "float"},
        {"key": "poids_vide", "label": "Poids à vide (kg)", "target": "root", "kind": "int"},
        {"key": "poids_total", "label": "Poids total (kg)", "target": "carte_grise", "kind": "int"},
        {"key": "categorie", "label": "Catégorie", "target": "root", "kind": "str"},
        {"key": "nombre_places", "label": "Nombre de places", "target": "carte_grise", "kind": "int"},
        {"key": "co2_g_km", "label": "CO₂ (g/km)", "target": "root", "kind": "float"},
    ],
    "assurance": [
        {"key": "compagnie", "label": "Compagnie", "target": "assurance", "kind": "str"},
        {"key": "numero_police", "label": "N° de police", "target": "assurance", "kind": "str"},
        {"key": "plaque", "label": "Immatriculation", "target": "root", "kind": "str"},
        {"key": "vin", "label": "VIN", "target": "root", "kind": "str"},
        {"key": "type_couverture", "label": "Type de couverture", "target": "assurance", "kind": "str"},
        {"key": "prime_annuelle", "label": "Prime annuelle (CHF)", "target": "assurance", "kind": "float"},
        {"key": "date_debut", "label": "Date de début", "target": "assurance", "kind": "date"},
        {"key": "date_echeance", "label": "Date d'échéance", "target": "assurance", "kind": "date"},
    ],
    "leasing": [
        {"key": "societe", "label": "Organisme de leasing", "target": "leasing", "kind": "str"},
        {"key": "numero_contrat", "label": "N° de contrat", "target": "leasing", "kind": "str"},
        {"key": "plaque", "label": "Immatriculation", "target": "root", "kind": "str"},
        {"key": "vin", "label": "VIN", "target": "root", "kind": "str"},
        {"key": "date_debut", "label": "Date de début", "target": "leasing", "kind": "date"},
        {"key": "date_fin", "label": "Date de fin", "target": "leasing", "kind": "date"},
        {"key": "mensualite_chf", "label": "Mensualité (CHF)", "target": "leasing", "kind": "float"},
        {"key": "duree_mois", "label": "Durée (mois)", "target": "leasing", "kind": "int"},
        {"key": "km_contractuel", "label": "Kilométrage contractuel", "target": "leasing", "kind": "int"},
        {"key": "km_annuel", "label": "Kilométrage annuel", "target": "leasing", "kind": "int"},
        {"key": "valeur_residuelle", "label": "Valeur résiduelle (CHF)", "target": "leasing", "kind": "float"},
        {"key": "cout_total", "label": "Valeur du contrat (CHF)", "target": "leasing", "kind": "float"},
    ],
    "controle_technique": [
        {"key": "plaque", "label": "Immatriculation", "target": "root", "kind": "str"},
        {"key": "vin", "label": "VIN", "target": "root", "kind": "str"},
        {"key": "date_dernier", "label": "Date du contrôle", "target": "controle_technique", "kind": "date"},
        {"key": "date_prochain", "label": "Prochain contrôle", "target": "controle_technique", "kind": "date"},
        {"key": "centre", "label": "Centre / office", "target": "controle_technique", "kind": "str"},
        {"key": "resultat", "label": "Résultat", "target": "controle_technique", "kind": "str"},
    ],
    "facture": [
        {"key": "fournisseur", "label": "Fournisseur", "target": "document", "kind": "str"},
        {"key": "numero_facture", "label": "N° de facture", "target": "document", "kind": "str"},
        {"key": "date_facture", "label": "Date de facture", "target": "document", "kind": "date"},
        {"key": "montant_chf", "label": "Montant (CHF)", "target": "document", "kind": "float"},
        {"key": "plaque", "label": "Immatriculation mentionnée", "target": "document", "kind": "str"},
    ],
    "amende": [
        {"key": "autorite", "label": "Autorité", "target": "document", "kind": "str"},
        {"key": "numero_amende", "label": "N° de l'amende", "target": "document", "kind": "str"},
        {"key": "date_infraction", "label": "Date de l'infraction", "target": "document", "kind": "date"},
        {"key": "montant_chf", "label": "Montant (CHF)", "target": "document", "kind": "float"},
        {"key": "delai_paiement", "label": "Délai de paiement", "target": "document", "kind": "date"},
        {"key": "plaque", "label": "Immatriculation mentionnée", "target": "document", "kind": "str"},
    ],
    "autre": [
        {"key": "titre", "label": "Titre du document", "target": "document", "kind": "str"},
        {"key": "date_document", "label": "Date du document", "target": "document", "kind": "date"},
        {"key": "description", "label": "Description", "target": "document", "kind": "str"},
    ],
}

_DATE_PATTERNS = [
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})"), lambda m: (m.group(1), m.group(2), m.group(3))),
    (re.compile(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})"), lambda m: (m.group(3), m.group(2), m.group(1))),
]


def _norm_date(value):
    s = str(value).strip()
    for pat, order in _DATE_PATTERNS:
        m = pat.match(s)
        if m:
            y, mo, d = order(m)
            try:
                out = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                datetime.strptime(out, "%Y-%m-%d")
                return out
            except ValueError:
                return None
    return None


def _norm_number(value):
    txt = re.sub(r"[^\d.,\-]", "", str(value)).replace(",", ".")
    if txt.count(".") > 1:
        parts = txt.split(".")
        txt = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(txt)
    except ValueError:
        return None


def normalize_value(value, kind: str):
    """Coerce une valeur extraite/saisie vers le type attendu. None si inexploitable."""
    if value is None:
        return None
    if kind == "date":
        return _norm_date(value)
    if kind in ("int", "float"):
        n = float(value) if isinstance(value, (int, float)) else _norm_number(value)
        if n is None:
            return None
        return int(round(n)) if kind == "int" else round(n, 2)
    s = str(value).strip()
    return s or None


def prepare_image_b64(data: bytes, max_side: int = 1800) -> str:
    """Redresse (EXIF), réduit et ré-encode une image en JPEG base64."""
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def pdf_to_images_b64(data: bytes, max_pages: int = 5, dpi: int = 150) -> list:
    """Convertit les pages d'un PDF en images JPEG base64."""
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    out = []
    for page in doc:
        if len(out) >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi)
        out.append(prepare_image_b64(pix.tobytes("png")))
    doc.close()
    return out


def _schema_lines(dtype: str) -> str:
    return "\n".join(f'- "{d["key"]}" ({d["kind"]}) : {d["label"]}' for d in FIELD_DEFS[dtype])


def build_prompt(document_type: str = None) -> str:
    if document_type and document_type in FIELD_DEFS:
        intro = (f'Ce document est de type "{document_type}" ({DOC_TYPES[document_type]["label"]}). '
                 "Extrais uniquement les champs de ce type.")
        schemas = f"Champs à extraire :\n{_schema_lines(document_type)}"
    else:
        intro = ("Détermine d'abord le type du document parmi : "
                 + ", ".join(f'"{k}" ({v["label"]})' for k, v in DOC_TYPES.items())
                 + ". Puis extrais les champs correspondant au type détecté.")
        schemas = "\n\n".join(f'Champs du type "{k}" :\n{_schema_lines(k)}' for k in FIELD_DEFS)
    return (
        "Tu analyses un document administratif de véhicule suisse "
        "(possiblement en français, allemand ou italien, photo ou scan, une ou plusieurs pages). "
        + intro + "\n\n" + schemas + "\n\n"
        "Réponds UNIQUEMENT avec un objet JSON strict de la forme :\n"
        '{"document_type": "<type>", "type_confidence": <0..1>, '
        '"fields": {"<champ>": {"value": <valeur>, "confidence": <0..1>}}}\n'
        "Règles STRICTES :\n"
        "- N'INVENTE JAMAIS une valeur absente ou illisible : omets le champ ou mets value à null.\n"
        "- Dates au format YYYY-MM-DD. Nombres en numérique pur, sans unité ni séparateur de milliers.\n"
        "- confidence reflète honnêtement ta certitude de lecture (0 à 1), par champ.\n"
        "- Plaque suisse au format 'GE 123456'. Carburant en français (Diesel, Essence, Électrique, Hybride…).\n"
        "- Aucun texte hors JSON, aucune balise de code."
    )


class DocumentExtractionProvider:
    """Interface d'extraction — permet de brancher Azure Document Intelligence,
    Google Document AI, AWS Textract, etc. sans réécrire la logique métier."""

    async def analyze(self, images_b64: list, document_type: str = None) -> dict:
        raise NotImplementedError


class LlmVisionProvider(DocumentExtractionProvider):
    """Extraction vision via LLM — Claude (clé Anthropic directe) ou GPT (clé Emergent)."""

    def __init__(self, api_key: str, llm_provider: str = "openai", model: str = "gpt-5.4"):
        self.api_key = api_key
        self.llm_provider = llm_provider
        self.model = model

    async def analyze(self, images_b64: list, document_type: str = None) -> dict:
        if not self.api_key:
            raise RuntimeError("Aucune clé d'extraction configurée (ANTHROPIC_API_KEY ou EMERGENT_LLM_KEY)")
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"docscan-{uuid.uuid4()}",
            system_message=("Tu es un expert en extraction structurée de documents administratifs "
                            "de véhicules suisses (FR/DE/IT). Tu réponds uniquement en JSON strict."),
        ).with_model(self.llm_provider, self.model)
        msg = UserMessage(
            text=build_prompt(document_type),
            file_contents=[ImageContent(image_base64=b) for b in images_b64],
        )
        resp = await chat.send_message(msg)
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        text = text.strip()
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        parsed = json.loads(text)
        fields = parsed.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        fields = {k: (v if isinstance(v, dict) else {"value": v, "confidence": None})
                  for k, v in fields.items()}
        return {
            "document_type": parsed.get("document_type"),
            "type_confidence": parsed.get("type_confidence"),
            "fields": fields,
        }


def enhance_and_pdf(images_bytes: list):
    """Améliore la lisibilité des photos (EXIF + autocontraste) et assemble un PDF unique.
    Retourne (pdf_bytes, jpeg_pages)."""
    from PIL import Image, ImageOps
    if not images_bytes:
        raise ValueError("Aucune image à assembler")
    pil_pages, jpegs = [], []
    for data in images_bytes:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageOps.autocontrast(img, cutoff=1)
        if max(img.size) > 2200:
            img.thumbnail((2200, 2200))
        pil_pages.append(img)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        jpegs.append(buf.getvalue())
    out = io.BytesIO()
    pil_pages[0].save(out, "PDF", save_all=True, append_images=pil_pages[1:], resolution=150)
    return out.getvalue(), jpegs


def get_provider(emergent_key: str = None, anthropic_key: str = None) -> DocumentExtractionProvider:
    """Sélection automatique : Claude si ANTHROPIC_API_KEY présente, sinon GPT via clé Emergent."""
    override = (os.environ.get("DOC_EXTRACTION_PROVIDER") or "").lower()
    if override == "gpt_vision":
        return LlmVisionProvider(emergent_key, "openai", os.environ.get("DOC_EXTRACTION_MODEL") or "gpt-5.4")
    if override == "claude" or anthropic_key:
        return LlmVisionProvider(anthropic_key, "anthropic",
                                 os.environ.get("DOC_EXTRACTION_MODEL") or "claude-sonnet-4-6")
    return LlmVisionProvider(emergent_key, "openai", os.environ.get("DOC_EXTRACTION_MODEL") or "gpt-5.4")


class VehicleTechnicalDataProvider:
    """Voir technical_data.py — abstraction et implémentation SwissCarInfo y résident."""
