"""Génération de rapports PDF (fpdf2) — rapport de conformité flotte."""
from datetime import datetime, timezone

from fpdf import FPDF

LEVELS_FR = {"ok": "Conforme", "warning": "Avertissement", "critical": "Critique",
             "expired": "Expiré", "unknown": "Incomplet"}

_REPL = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u00a0": " ", "\u202f": " ",
         "\u2026": "...", "\u20ac": "EUR"}


def _tx(s):
    s = "" if s is None else str(s)
    for a, b in _REPL.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


def _date_fr(iso):
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso)


def _due(iso, days):
    if not iso:
        return "-"
    txt = _date_fr(iso)
    if days is None:
        return txt
    return f"{txt} (échu)" if days < 0 else f"{txt} ({days} j)"


def _chf(x):
    try:
        n = float(x or 0)
    except (TypeError, ValueError):
        n = 0
    if not n:
        return "-"
    return f"{n:,.0f}".replace(",", "'") + " CHF"


class _Report(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(130)
        self.cell(0, 8, _tx(f"LogiTrak Documents — Rapport de conformité — page {self.page_no()}"), align="C")
        self.set_text_color(0)


def _section(pdf, title):
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, _tx(title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def build_conformity_pdf(vehicles: list) -> bytes:
    pdf = _Report(orientation="L", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 9, _tx("Rapport de conformité — Flotte"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(100)
    pdf.cell(0, 5, _tx(f"Généré le {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC · "
                       f"{len(vehicles)} véhicule(s) · Échéances leasing / assurance / contrôle technique et coûts"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)

    counts = {"ok": 0, "warning": 0, "critical": 0, "expired": 0, "unknown": 0}
    for v in vehicles:
        overall = (v.get("metrics") or {}).get("overall") or "unknown"
        counts[overall if overall in counts else "unknown"] += 1
    _section(pdf, "Synthèse")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, _tx(f"Conformes : {counts['ok']}   ·   Avertissements : {counts['warning']}   ·   "
                       f"Critiques : {counts['critical']}   ·   Expirés : {counts['expired']}   ·   "
                       f"Données incomplètes : {counts['unknown']}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    _section(pdf, "Échéances & conformité")
    pdf.set_font("helvetica", "", 8.5)
    with pdf.table(col_widths=(20, 34, 26, 26, 26, 18), text_align=("LEFT", "LEFT", "LEFT", "LEFT", "LEFT", "CENTER"),
                   line_height=6, padding=1.2) as table:
        head = table.row()
        for h in ("Plaque", "Véhicule", "Fin de leasing", "Échéance assurance", "Prochain contrôle", "Statut"):
            head.cell(_tx(h))
        for v in vehicles:
            m = v.get("metrics") or {}
            leasing, assurance, controle = v.get("leasing") or {}, v.get("assurance") or {}, v.get("controle_technique") or {}
            row = table.row()
            row.cell(_tx(v.get("plaque") or "-"))
            row.cell(_tx(" ".join(x for x in (v.get("marque"), v.get("modele")) if x) or "-"))
            row.cell(_tx(_due(leasing.get("date_fin"), (m.get("leasing") or {}).get("days_remaining"))))
            row.cell(_tx(_due(assurance.get("date_echeance"), (m.get("assurance") or {}).get("days_remaining"))))
            row.cell(_tx(_due(controle.get("date_prochain"), (m.get("controle") or {}).get("days_remaining"))))
            row.cell(_tx(LEVELS_FR.get(m.get("overall"), "-")))
    pdf.ln(6)

    _section(pdf, "Coûts leasing & assurance")
    pdf.set_font("helvetica", "", 8.5)
    tot_mens, tot_rest, tot_prime = 0.0, 0.0, 0.0
    with pdf.table(col_widths=(20, 34, 24, 20, 26, 26), text_align=("LEFT", "LEFT", "RIGHT", "CENTER", "RIGHT", "RIGHT"),
                   line_height=6, padding=1.2) as table:
        head = table.row()
        for h in ("Plaque", "Véhicule", "Mensualité leasing", "Mois restants", "Coût restant leasing", "Prime assurance / an"):
            head.cell(_tx(h))
        for v in vehicles:
            m = v.get("metrics") or {}
            ml = m.get("leasing") or {}
            leasing, assurance = v.get("leasing") or {}, v.get("assurance") or {}
            mens = leasing.get("mensualite_chf") or leasing.get("cout_mensuel") or 0
            rest = ml.get("cost_remaining") or 0
            prime = assurance.get("prime_annuelle") or 0
            tot_mens += float(mens or 0)
            tot_rest += float(rest or 0)
            tot_prime += float(prime or 0)
            row = table.row()
            row.cell(_tx(v.get("plaque") or "-"))
            row.cell(_tx(" ".join(x for x in (v.get("marque"), v.get("modele")) if x) or "-"))
            row.cell(_tx(_chf(mens)))
            row.cell(_tx(ml.get("months_remaining") if ml.get("months_remaining") is not None else "-"))
            row.cell(_tx(_chf(rest)))
            row.cell(_tx(_chf(prime)))
        total = table.row()
        pdf.set_font("helvetica", "B", 8.5)
        total.cell(_tx("TOTAL"))
        total.cell(_tx(f"{len(vehicles)} véhicule(s)"))
        total.cell(_tx(_chf(tot_mens)))
        total.cell("-")
        total.cell(_tx(_chf(tot_rest)))
        total.cell(_tx(_chf(tot_prime)))
    pdf.ln(4)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(110)
    pdf.cell(0, 5, _tx("Coût restant leasing = mois restants × mensualité. Les montants proviennent des contrats "
                       "saisis dans les fiches véhicules ; les lignes sans contrat affichent « - »."),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)

    return bytes(pdf.output())
