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
    "vignette": {"label": "Vignette autoroutière", "folder": "Vignette"},
    "facture": {"label": "Facture véhicule", "folder": "Factures"},
    "amende": {"label": "Amende", "folder": "Divers"},
    "autre": {"label": "Autre document", "folder": "Divers"},
}

# target: root (fiche véhicule) | carte_grise | assurance | leasing | controle_technique | document
FIELD_DEFS = {
    "permis_circulation": [
        {"key": "plaque", "label": "Immatriculation", "target": "root", "kind": "str"},
        {"key": "vin", "label": "VIN / N° de châssis", "target": "root", "kind": "str"},
        {"key": "numero_matricule", "label": "N° de matricule", "target": "carte_grise", "kind": "str"},
        {"key": "numero_homologation", "label": "Réception par type / N° d'homologation", "target": "root", "kind": "str"},
        {"key": "marque", "label": "Marque", "target": "root", "kind": "str"},
        {"key": "modele", "label": "Modèle", "target": "root", "kind": "str"},
        {"key": "variante", "label": "Variante / type", "target": "root", "kind": "str"},
        {"key": "categorie", "label": "Genre de véhicule / catégorie", "target": "root", "kind": "str"},
        {"key": "carrosserie", "label": "Carrosserie", "target": "carte_grise", "kind": "str"},
        {"key": "couleur", "label": "Couleur", "target": "carte_grise", "kind": "str"},
        {"key": "date_mise_circulation", "label": "1re mise en circulation", "target": "carte_grise", "kind": "date"},
        {"key": "type_carburant", "label": "Carburant", "target": "root", "kind": "str"},
        {"key": "cylindree_cm3", "label": "Cylindrée (cm³)", "target": "root", "kind": "int"},
        {"key": "puissance_kw", "label": "Puissance (kW)", "target": "root", "kind": "float"},
        {"key": "nombre_places", "label": "Nombre de places", "target": "carte_grise", "kind": "int"},
        {"key": "poids_vide", "label": "Poids à vide (kg)", "target": "root", "kind": "int"},
        {"key": "charge_utile", "label": "Charge utile (kg)", "target": "carte_grise", "kind": "int"},
        {"key": "poids_total", "label": "Poids total (kg)", "target": "carte_grise", "kind": "int"},
        {"key": "charge_remorquable", "label": "Charge remorquable (kg)", "target": "carte_grise", "kind": "int"},
        {"key": "charge_toit", "label": "Charge sur le toit (kg)", "target": "carte_grise", "kind": "int"},
        {"key": "code_emissions", "label": "Code d'émissions", "target": "carte_grise", "kind": "str"},
        {"key": "co2_g_km", "label": "CO₂ (g/km)", "target": "root", "kind": "float"},
        {"key": "detenteur", "label": "Détenteur", "target": "carte_grise", "kind": "str"},
        {"key": "adresse_detenteur", "label": "Adresse du détenteur", "target": "carte_grise", "kind": "str"},
        {"key": "date_emission", "label": "Date d'émission du permis", "target": "carte_grise", "kind": "date"},
        {"key": "lieu_emission", "label": "Lieu d'émission", "target": "carte_grise", "kind": "str"},
        {"key": "date_dernier", "label": "Dernière expertise (zone Prüfungen / Expertises)", "target": "controle_technique", "kind": "date"},
        {"key": "compagnie", "label": "Assureur", "target": "assurance", "kind": "str"},
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
    "vignette": [
        {"key": "annee", "label": "Année", "target": "document", "kind": "int"},
        {"key": "type_vignette", "label": "Type (e-vignette / autocollante)", "target": "document", "kind": "str"},
        {"key": "plaque", "label": "Immatriculation mentionnée", "target": "document", "kind": "str"},
        {"key": "date_achat", "label": "Date d'achat", "target": "document", "kind": "date"},
        {"key": "date_expiration", "label": "Date d'expiration", "target": "document", "kind": "date"},
        {"key": "prix_chf", "label": "Prix (CHF)", "target": "document", "kind": "float"},
        {"key": "statut", "label": "Statut", "target": "document", "kind": "str"},
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
        intro = (f'Type attendu : "{document_type}" ({DOC_TYPES[document_type]["label"]}). '
                 "Extrais les champs de ce type. Indique cependant dans \"document_type\" le type que TU "
                 "détectes réellement sur le document, choisi parmi : "
                 + ", ".join(f'"{k}" ({v["label"]})' for k, v in DOC_TYPES.items())
                 + " — même s'il diffère du type attendu.")
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
        '"fields": {"<champ>": {"value": <valeur>, "confidence": <0..1>, "status": "found|uncertain|missing"}}}\n'
        "Règles STRICTES :\n"
        "- N'INVENTE JAMAIS une valeur absente ou illisible : status \"missing\", value null, confidence 0.\n"
        "- status \"found\" si la valeur est clairement lisible, \"uncertain\" si la lecture est douteuse.\n"
        "- Dates au format YYYY-MM-DD. Nombres en numérique pur, sans unité ni séparateur de milliers.\n"
        "- confidence reflète honnêtement ta certitude de lecture (0 à 1), par champ.\n"
        "- Plaque suisse au format 'GE 123456'. Carburant en français (Diesel, Essence, Électrique, Hybride…).\n"
        "- VIN en MAJUSCULES, SANS espaces (17 caractères pour un VIN standard) — recopie exacte, "
        "n'essaie JAMAIS de corriger un caractère douteux (0/O, 1/I, 5/S, 8/B) : baisse la confidence.\n"
        "- N° de matricule suisse recopié tel qu'imprimé (p.ex. 123.456.789).\n"
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
        for v in fields.values():
            st = v.get("status")
            if st not in ("found", "uncertain", "missing"):
                conf = v.get("confidence")
                if v.get("value") in (None, ""):
                    st = "missing"
                elif isinstance(conf, (int, float)) and conf < 0.6:
                    st = "uncertain"
                else:
                    st = "found"
            v["status"] = st
        return {
            "document_type": parsed.get("document_type"),
            "type_confidence": parsed.get("type_confidence"),
            "fields": fields,
        }

    async def suggest_reservoir(self, vehicle: dict) -> dict:
        """Estimation IA de la capacité du réservoir carburant (donnée constructeur).
        Retourne value_l=None si aucune estimation fiable. JAMAIS écrit sans validation humaine."""
        if not self.api_key:
            raise RuntimeError("Aucune clé d'extraction configurée (ANTHROPIC_API_KEY ou EMERGENT_LLM_KEY)")
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        cg = vehicle.get("carte_grise") or {}
        desc = " · ".join(filter(None, [
            vehicle.get("marque"), vehicle.get("modele"), vehicle.get("variante"),
            f"{vehicle.get('cylindree_cm3')} cm³" if vehicle.get("cylindree_cm3") else None,
            f"{vehicle.get('puissance_kw')} kW" if vehicle.get("puissance_kw") else None,
            vehicle.get("type_carburant"),
            f"1re mise en circulation {cg.get('date_mise_circulation')}" if cg.get("date_mise_circulation") else None,
        ]))
        prompt = (
            "Quelle est la capacité du réservoir de carburant (en litres, donnée constructeur) de ce véhicule ?\n"
            f"Véhicule : {desc}\n\n"
            "Règles STRICTES :\n"
            "- Réponds UNIQUEMENT en JSON strict : {\"value_l\": <nombre|null>, \"confidence\": <0..1>, \"rationale\": \"<justification courte en français>\"}\n"
            "- value_l = capacité standard constructeur du réservoir carburant pour ce modèle/génération/motorisation.\n"
            "- Si plusieurs variantes existent, prends la capacité standard la plus courante et dis-le dans rationale.\n"
            "- Si tu n'es pas raisonnablement sûr, ou si le véhicule est 100% électrique : value_l = null.\n"
            "- N'invente JAMAIS une valeur farfelue ; plage plausible 20–200 L pour un véhicule routier."
        )
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"reservoir-{uuid.uuid4()}",
            system_message="Tu es un expert des fiches techniques constructeur automobile. Tu réponds uniquement en JSON strict.",
        ).with_model(self.llm_provider, self.model)
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        text = text.strip()
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        parsed = json.loads(text)
        value = parsed.get("value_l")
        try:
            value = round(float(value), 1) if value is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and not (10 <= value <= 500):
            value = None
        conf = parsed.get("confidence")
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            conf = None
        return {"value_l": value, "confidence": conf,
                "rationale": (parsed.get("rationale") or "").strip() or None}

    async def suggest_conso(self, vehicle: dict) -> dict:
        """Estimation IA de la consommation officielle combinée (homologation constructeur).
        Retourne value_l_100km=None si aucune estimation fiable. JAMAIS écrit sans validation humaine."""
        if not self.api_key:
            raise RuntimeError("Aucune clé d'extraction configurée (ANTHROPIC_API_KEY ou EMERGENT_LLM_KEY)")
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        cg = vehicle.get("carte_grise") or {}
        desc = " · ".join(filter(None, [
            vehicle.get("marque"), vehicle.get("modele"), vehicle.get("variante"),
            f"{vehicle.get('cylindree_cm3')} cm³" if vehicle.get("cylindree_cm3") else None,
            f"{vehicle.get('puissance_kw')} kW" if vehicle.get("puissance_kw") else None,
            vehicle.get("type_carburant"),
            f"1re mise en circulation {cg.get('date_mise_circulation')}" if cg.get("date_mise_circulation") else None,
        ]))
        prompt = (
            "Quelle est la consommation officielle combinée (homologation constructeur, en L/100 km) de ce véhicule ?\n"
            f"Véhicule : {desc}\n\n"
            "Règles STRICTES :\n"
            "- Réponds UNIQUEMENT en JSON strict : {\"value_l_100km\": <nombre|null>, \"norme\": \"WLTP\"|\"NEDC\"|null, "
            "\"confidence\": <0..1>, \"rationale\": \"<justification courte en français>\"}\n"
            "- value_l_100km = consommation combinée d'homologation pour ce modèle/génération/motorisation (WLTP de préférence, sinon NEDC — indique la norme).\n"
            "- Si plusieurs variantes existent, prends la valeur de la variante la plus courante et dis-le dans rationale.\n"
            "- Si tu n'es pas raisonnablement sûr, ou si le véhicule est 100% électrique : value_l_100km = null.\n"
            "- N'invente JAMAIS une valeur farfelue ; plage plausible 2–35 L/100 km pour un véhicule routier."
        )
        chat = LlmChat(
            api_key=self.api_key,
            session_id=f"conso-{uuid.uuid4()}",
            system_message="Tu es un expert des fiches techniques constructeur automobile. Tu réponds uniquement en JSON strict.",
        ).with_model(self.llm_provider, self.model)
        resp = await chat.send_message(UserMessage(text=prompt))
        text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
        text = text.strip()
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        parsed = json.loads(text)
        value = parsed.get("value_l_100km")
        try:
            value = round(float(value), 1) if value is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and not (1 <= value <= 40):
            value = None
        norme = (parsed.get("norme") or "").strip().upper() or None
        if norme not in ("WLTP", "NEDC"):
            norme = None
        conf = parsed.get("confidence")
        try:
            conf = max(0.0, min(1.0, float(conf)))
        except (TypeError, ValueError):
            conf = None
        return {"value_l_100km": value, "norme": norme, "confidence": conf,
                "rationale": (parsed.get("rationale") or "").strip() or None}


def check_image_quality(data: bytes) -> dict:
    """Contrôle qualité non-LLM (résolution + netteté). level: ok | warning | blocked.
    Bloque uniquement si l'image est réellement inexploitable."""
    from PIL import Image, ImageFilter, ImageStat, ImageOps
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception:
        return {"level": "blocked", "issues": ["image illisible"]}
    w, h = img.size
    if min(w, h) < 250:
        return {"level": "blocked", "issues": [f"résolution insuffisante ({w}×{h} px)"]}
    issues, level = [], "ok"
    if min(w, h) < 550:
        issues.append(f"résolution faible ({w}×{h} px)")
        level = "warning"
    g = img.convert("L")
    if max(g.size) > 1000:
        g.thumbnail((1000, 1000))
    edges = g.filter(ImageFilter.FIND_EDGES)
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    var = ImageStat.Stat(edges).var[0]
    if var < 5:
        return {"level": "blocked", "issues": issues + ["image extrêmement floue ou vide"]}
    if var < 40:
        issues.append("image floue")
        level = "warning"
    return {"level": level, "issues": issues}


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
