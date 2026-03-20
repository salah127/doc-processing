"""
generate_invoices.py - v4.2
Corrections v4.2 :
  - Totaux TOUJOURS sur la même ligne que leur label dans PDF et image
    (élimine le CAS B OCR de l'extractor sur les fichiers propres)
  - ImageBuilder : espacement dynamique basé sur hauteur réelle des glyphes,
    polices recalibrées pour 1240×1754 px (~150 DPI A4)
  - Nouvelle anomalie EXPIRED_DATE : date > 1 an dans le passé, tous types
  - EXPIRED_ATTESTATION : attestation dont la validité est dépassée
  - 6 types d'anomalies au total
"""

import os
import random
import uuid
from datetime import datetime, timedelta

import cv2
import numpy as np
from faker import Faker
from PIL import Image, ImageDraw, ImageFont
from pymongo import MongoClient
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OUTPUT_DIR = "dataset/generator/generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)
fake = Faker("fr_FR")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/hackathon")
DB_NAME = "hackathon"
COLLECTION_NAME = "companies"

TVA_RATE = 0.20
DOC_TYPES = ["FACTURE", "DEVIS", "ATTESTATION_URSSAF", "KBIS"]

# Image A4 à ~150 DPI
IMG_W, IMG_H = 1240, 1754


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_companies():
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        db = client[DB_NAME]
        return list(db[COLLECTION_NAME].find())
    except Exception:
        return []


def fmt_money(amount: float) -> str:
    """Montant sans ambiguité pour l'OCR : 1234.56 (point décimal, pas d'espace)."""
    return f"{amount:.2f}"


def add_photo_effect(image: Image.Image, intensity: float = 0.4) -> Image.Image:
    img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    angle = random.uniform(-0.6, 0.6) * intensity
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, M, (w, h),
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    grain_max = max(1, int(5 * intensity))
    noise = np.random.randint(0, grain_max, (h, w, 3), dtype="uint8")
    img = cv2.add(img, noise)
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------------------
# Fonts — calibrées pour 1240×1754 px (~150 DPI)
# ---------------------------------------------------------------------------

def load_fonts() -> dict:
    spec = {
        "h1":      ("arialbd.ttf", 26),
        "h2":      ("arialbd.ttf", 20),
        "bold":    ("arialbd.ttf", 15),
        "regular": ("arial.ttf",   15),
        "small":   ("arial.ttf",   12),
        "mono":    ("cour.ttf",    14),
        "section": ("arialbd.ttf", 13),
    }
    fonts = {}
    for key, (fname, size) in spec.items():
        try:
            fonts[key] = ImageFont.truetype(fname, size)
        except OSError:
            fonts[key] = ImageFont.load_default()
    return fonts


# ---------------------------------------------------------------------------
# PDF Builder
# ---------------------------------------------------------------------------

class PDFBuilder:
    W, H = A4  # 595 × 842 pt

    def __init__(self, path: str):
        self.path = path
        self.c = canvas.Canvas(path, pagesize=A4)
        self._y = self.H - 1.5 * cm

    def _nl(self, step_cm: float = 0.52):
        self._y -= step_cm * cm

    def _line_h(self, lw: float = 0.5, color=(0, 0, 0)):
        self.c.setLineWidth(lw)
        self.c.setStrokeColorRGB(*color)
        self.c.line(1 * cm, self._y, self.W - 1 * cm, self._y)
        self._nl(0.22)

    def _label_value(self, label: str, value: str,
                     label_w_cm: float = 5.5, bold_value: bool = False, size: int = 9):
        """
        Écrit LABEL: valeur sur UNE SEULE LIGNE.
        Le label et la valeur sont garantis sur la même ligne → CAS A dans l'extractor.
        """
        self.c.setFont("Helvetica-Bold", size)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.drawString(1 * cm, self._y, f"{label}:")
        self.c.setFont("Helvetica-Bold" if bold_value else "Helvetica", size)
        self.c.drawString((1 + label_w_cm) * cm, self._y, value)
        self._nl()

    def _section_title(self, title: str):
        self._nl(0.25)
        self._line_h(lw=0.8, color=(0.2, 0.2, 0.2))
        self.c.setFont("Helvetica-Bold", 8)
        self.c.setFillColorRGB(0.2, 0.2, 0.2)
        self.c.drawString(1 * cm, self._y, f"[ {title} ]")
        self._nl()
        self._nl(0.08)

    def header_company(self, company: dict, doc_type: str, ref: str, date_str: str):
        self.c.setFont("Helvetica-Bold", 13)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.drawString(1 * cm, self._y, company["name"].upper()[:60])
        self._nl(0.7)
        self._label_value("EMETTEUR",    company["name"])
        self._label_value("SIRET",       company["siret"])
        self._label_value("SIREN",       company["siret"][:9] if company["siret"] else "")
        self._label_value("ADRESSE",     company["address"])
        self._label_value("CODE POSTAL", company.get("postal_code", fake.postcode()))
        self._label_value("VILLE",       company.get("city", fake.city()))
        self._nl(0.25)
        self._line_h(lw=1.2)
        self._nl(0.25)
        self.c.setFont("Helvetica-Bold", 16)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.drawCentredString(self.W / 2, self._y, doc_type)
        self._nl(0.85)
        self._line_h(lw=0.5)
        self._label_value("REFERENCE",     ref)
        self._label_value("DATE",          date_str)
        self._label_value("TYPE DOCUMENT", doc_type)

    def client_block(self, client_name: str, client_id: str, client_address: str):
        self._section_title("DESTINATAIRE")
        self._label_value("CLIENT",         client_name)
        self._label_value("ID CLIENT",      client_id)
        self._label_value("ADRESSE CLIENT", client_address[:60])

    def items_table(self, items: list) -> float:
        self._section_title("DETAIL DES PRESTATIONS")
        col_x = [1, 9, 12.5, 16]
        self.c.setFont("Helvetica-Bold", 8)
        self.c.setFillColorRGB(0, 0, 0)
        for hdr, x in zip(["DESIGNATION", "QTE", "PU HT EUR", "MONTANT HT EUR"], col_x):
            self.c.drawString(x * cm, self._y, hdr)
        self._nl(0.35)
        self._line_h(lw=0.3)
        total_ht = 0.0
        for item in items:
            mt = round(item["qty"] * item["unit_price"], 2)
            total_ht += mt
            self.c.setFont("Helvetica", 8)
            self.c.drawString(col_x[0] * cm, self._y, item["desc"][:42])
            self.c.drawString(col_x[1] * cm, self._y, str(item["qty"]))
            self.c.drawString(col_x[2] * cm, self._y, fmt_money(item["unit_price"]))
            self.c.drawString(col_x[3] * cm, self._y, fmt_money(mt))
            self._nl()
        return total_ht

    def totals_block(self, total_ht: float, tva_override=None, ttc_override=None):
        """
        Chaque total sur une seule ligne : LABEL: VALEUR EUR
        Garantit le CAS A dans l'extractor (pas de split label/valeur).
        """
        tva = tva_override if tva_override is not None else round(total_ht * TVA_RATE, 2)
        ttc = ttc_override if ttc_override is not None else round(total_ht + tva, 2)
        self._section_title("RECAPITULATIF FINANCIER")
        # Valeur directement après le label sur la même ligne
        self._label_value("TOTAL HT",  fmt_money(total_ht) + " EUR", bold_value=True)
        self._label_value("TVA (20%)", fmt_money(tva) + " EUR")
        self._label_value("TOTAL TTC", fmt_money(ttc) + " EUR",  bold_value=True, size=10)

    def attestation_block(self, company: dict, date_str: str, validity_days: int):
        self._section_title("CONTENU DE L'ATTESTATION")
        lines = [
            "La presente attestation certifie que l'entreprise",
            "est en regle vis-a-vis de ses obligations legales.",
            "",
            f"RAISON SOCIALE:  {company['name']}",
            f"SIRET:           {company['siret']}",
            f"DATE DELIVRANCE: {date_str}",
            f"VALIDITE:        {validity_days} jours",
            "",
            "Ce document est delivre a titre informatif.",
        ]
        for line in lines:
            self.c.setFont("Helvetica", 9)
            self.c.setFillColorRGB(0, 0, 0)
            self.c.drawString(1.5 * cm, self._y, line)
            self._nl()

    def footer(self, company: dict):
        self._nl(0.4)
        self._line_h(lw=0.4, color=(0.5, 0.5, 0.5))
        self.c.setFont("Helvetica", 7)
        self.c.setFillColorRGB(0.4, 0.4, 0.4)
        txt = f"{company['name']} | SIRET: {company['siret']} | {company['address']}"
        self.c.drawCentredString(self.W / 2, self._y, txt[:110])

    def save(self):
        self.c.save()


# ---------------------------------------------------------------------------
# Image Builder — espacement dynamique, polices calibrées
# ---------------------------------------------------------------------------

class ImageBuilder:
    """
    Image JPEG simulant une photo d'un document A4 à ~150 DPI.
    Règle : _advance(font) mesure la hauteur RÉELLE du texte rendu par Pillow
    et avance le curseur en conséquence → zéro superposition.
    Les totaux sont écrits sur UNE SEULE LIGNE (label + valeur) comme dans le PDF.
    """

    MARGIN_X = 55
    PAD_LINE  = 5
    PAD_SECT  = 12

    def __init__(self):
        self.img = Image.new("RGB", (IMG_W, IMG_H), color=(255, 255, 255))
        self.d   = ImageDraw.Draw(self.img)
        self.f   = load_fonts()
        self._y  = self.MARGIN_X

    # ---- Mesure -------------------------------------------------------------

    def _h(self, font) -> int:
        try:
            bb = font.getbbox("Hy")
            return bb[3] - bb[1]
        except AttributeError:
            return font.getsize("Hy")[1]

    def _w(self, text: str, font) -> int:
        try:
            bb = font.getbbox(text)
            return bb[2] - bb[0]
        except AttributeError:
            return font.getsize(text)[0]

    # ---- Primitives ---------------------------------------------------------

    def _put(self, x: int, text: str, font, color=(0, 0, 0)):
        self.d.text((x, self._y), text, fill=color, font=font)

    def _advance(self, font, extra: int = 0):
        self._y += self._h(font) + self.PAD_LINE + extra

    def _hline(self, thickness: int = 1, color=(0, 0, 0), gap: int = 5):
        self.d.line(
            [(self.MARGIN_X, self._y), (IMG_W - self.MARGIN_X, self._y)],
            fill=color, width=thickness,
        )
        self._y += gap

    def _label_value(self, label: str, value: str,
                     label_col: int = 240, bold_val: bool = False):
        """
        LABEL: valeur sur une seule ligne.
        label_col : largeur réservée en px pour la colonne label.
        """
        self._put(self.MARGIN_X,              f"{label}:", self.f["bold"])
        self._put(self.MARGIN_X + label_col,  value,
                  self.f["bold"] if bold_val else self.f["regular"])
        self._advance(self.f["regular"])

    def _section_title(self, title: str):
        self._y += self.PAD_SECT
        self._hline(thickness=1, color=(80, 80, 80), gap=4)
        self._put(self.MARGIN_X, f"[ {title} ]", self.f["section"], color=(50, 50, 50))
        self._advance(self.f["section"], extra=4)

    # ---- Blocs document -----------------------------------------------------

    def header_company(self, company: dict, doc_type: str, ref: str, date_str: str):
        self._put(self.MARGIN_X, company["name"].upper()[:55], self.f["h1"])
        self._advance(self.f["h1"], extra=8)
        self._label_value("EMETTEUR",    company["name"][:55])
        self._label_value("SIRET",       company["siret"])
        self._label_value("SIREN",       company["siret"][:9] if company["siret"] else "")
        self._label_value("ADRESSE",     company["address"][:55])
        self._label_value("CODE POSTAL", company.get("postal_code", fake.postcode()))
        self._label_value("VILLE",       company.get("city", fake.city()))
        self._y += 8
        self._hline(thickness=2, gap=8)
        tw = self._w(doc_type, self.f["h2"])
        self._put((IMG_W - tw) // 2, doc_type, self.f["h2"])
        self._advance(self.f["h2"], extra=8)
        self._hline(thickness=1, gap=6)
        self._label_value("REFERENCE",     ref)
        self._label_value("DATE",          date_str)
        self._label_value("TYPE DOCUMENT", doc_type)

    def client_block(self, client_name: str, client_id: str, client_addr: str):
        self._section_title("DESTINATAIRE")
        self._label_value("CLIENT",         client_name[:55])
        self._label_value("ID CLIENT",      client_id)
        self._label_value("ADRESSE CLIENT", client_addr[:55])

    def items_table(self, items: list) -> float:
        self._section_title("DETAIL DES PRESTATIONS")
        cx = [self.MARGIN_X, 580, 760, 980]
        for hdr, x in zip(["DESIGNATION", "QTE", "PU HT EUR", "MONTANT HT EUR"], cx):
            self._put(x, hdr, self.f["section"])
        self._advance(self.f["section"], extra=2)
        self._hline(thickness=1, gap=4)
        total_ht = 0.0
        for item in items:
            mt = round(item["qty"] * item["unit_price"], 2)
            total_ht += mt
            self._put(cx[0], item["desc"][:36],           self.f["regular"])
            self._put(cx[1], str(item["qty"]),             self.f["mono"])
            self._put(cx[2], fmt_money(item["unit_price"]), self.f["mono"])
            self._put(cx[3], fmt_money(mt),                self.f["mono"])
            self._advance(self.f["regular"])
        return total_ht

    def totals_block(self, total_ht: float, tva_override=None, ttc_override=None):
        """
        Totaux sur UNE SEULE LIGNE chacun — garantit le CAS A dans l'extractor.
        TOTAL HT: 1234.56 EUR   (tout sur la même ligne)
        TVA (20%): 246.91 EUR
        TOTAL TTC: 1481.47 EUR
        """
        tva = tva_override if tva_override is not None else round(total_ht * TVA_RATE, 2)
        ttc = ttc_override if ttc_override is not None else round(total_ht + tva, 2)
        self._section_title("RECAPITULATIF FINANCIER")
        self._label_value("TOTAL HT",  fmt_money(total_ht) + " EUR", bold_val=True)
        self._label_value("TVA (20%)", fmt_money(tva) + " EUR")
        self._label_value("TOTAL TTC", fmt_money(ttc) + " EUR",  bold_val=True)

    def attestation_block(self, company: dict, date_str: str, validity_days: int):
        self._section_title("CONTENU DE L'ATTESTATION")
        lines = [
            "La presente attestation certifie que l'entreprise",
            "est en regle vis-a-vis de ses obligations legales.",
            "",
            f"RAISON SOCIALE:  {company['name'][:45]}",
            f"SIRET:           {company['siret']}",
            f"DATE DELIVRANCE: {date_str}",
            f"VALIDITE:        {validity_days} jours",
            "",
            "Ce document est delivre a titre informatif.",
        ]
        for line in lines:
            if line:
                self._put(self.MARGIN_X + 20, line, self.f["regular"])
            self._advance(self.f["regular"])

    def footer(self, company: dict):
        self._y += 10
        self._hline(thickness=1, color=(160, 160, 160), gap=4)
        txt = f"{company['name']} | SIRET: {company['siret']} | {company['address']}"
        self._put(self.MARGIN_X, txt[:85], self.f["small"], color=(100, 100, 100))

    def save(self, path: str, intensity: float = 0.4):
        photo = add_photo_effect(self.img, intensity=intensity)
        photo.save(path, "JPEG", quality=93)


# ---------------------------------------------------------------------------
# Dataset Generator
# ---------------------------------------------------------------------------

class DatasetGenerator:

    ANOMALY_TYPES = [
        "MATH_ERROR",           # TTC délibérément fausse (+150 EUR)
        "SIRET_MISSING",        # SIRET vide
        "SIRET_DB_MISSING",     # SIRET inconnu en base SIRENE
        "EXPIRED_ATTESTATION",  # Attestation dont la période de validité est dépassée
        "TVA_WRONG",            # TVA incorrecte (TTC inchangé → incohérence)
        "EXPIRED_DATE",         # Date du document > 1 an dans le passé — tous types
    ]

    SERVICES = [
        "Prestation conseil",      "Developpement logiciel",
        "Maintenance corrective",  "Audit technique",
        "Formation professionnelle", "Ingenierie systeme",
        "Conception graphique",    "Integration continue",
        "Support technique",       "Analyse de donnees",
    ]

    def __init__(self, output_dir: str, companies: list):
        self.output_dir = output_dir
        self.companies  = companies

    def _get_company(self) -> dict:
        if self.companies:
            c = random.choice(self.companies)
            return {
                "name":        c.get("name",    fake.company()),
                "siren":       c.get("siren",   ""),
                "siret":       c.get("siret",   c.get("siren", "12345678900012")),
                "address":     c.get("address", fake.street_address()),
                "postal_code": c.get("postal_code", fake.postcode()),
                "city":        c.get("city",    fake.city()),
            }
        siren = "".join([str(random.randint(0, 9)) for _ in range(9)])
        return {
            "name":        fake.company(),
            "siren":       siren,
            "siret":       siren + "00012",
            "address":     fake.street_address(),
            "postal_code": fake.postcode(),
            "city":        fake.city(),
        }

    def _get_items(self, count: int = None) -> list:
        count = count or random.randint(1, 4)
        return [
            {
                "desc":       random.choice(self.SERVICES),
                "qty":        random.randint(1, 20),
                "unit_price": round(random.uniform(80, 800), 2),
            }
            for _ in range(count)
        ]

    # ---- Builders ----------------------------------------------------------

    def _build_facture_devis(self, pdf_path, jpg_path, doc_type, company,
                             date, tva_override, ttc_override, siret_override):
        co = dict(company)
        if siret_override is not None:
            co["siret"] = siret_override

        ref         = f"{doc_type[:3]}-{date.strftime('%Y%m')}-{random.randint(1000,9999)}"
        date_str    = date.strftime("%d/%m/%Y")
        items       = self._get_items()
        client_name = fake.company()
        client_id   = str(random.randint(10000, 99999))
        client_addr = fake.address().replace("\n", ", ")

        pdf = PDFBuilder(pdf_path)
        pdf.header_company(co, doc_type, ref, date_str)
        pdf.client_block(client_name, client_id, client_addr)
        total_ht = pdf.items_table(items)
        pdf.totals_block(total_ht, tva_override=tva_override, ttc_override=ttc_override)
        pdf.footer(co)
        pdf.save()

        img = ImageBuilder()
        img.header_company(co, doc_type, ref, date_str)
        img.client_block(client_name, client_id, client_addr)
        total_ht2 = img.items_table(items)
        img.totals_block(total_ht2, tva_override=tva_override, ttc_override=ttc_override)
        img.footer(co)
        img.save(jpg_path)

    def _build_attestation(self, pdf_path, jpg_path, doc_type, company,
                           date, validity_days, siret_override):
        co = dict(company)
        if siret_override is not None:
            co["siret"] = siret_override

        ref       = f"ATT-{date.strftime('%Y%m')}-{random.randint(1000,9999)}"
        date_str  = date.strftime("%d/%m/%Y")
        organisme = "URSSAF" if "URSSAF" in doc_type else "GREFFE DU TRIBUNAL"

        pdf = PDFBuilder(pdf_path)
        pdf.header_company(co, doc_type, ref, date_str)
        pdf._label_value("ORGANISME", organisme)
        pdf.attestation_block(co, date_str, validity_days)
        pdf.footer(co)
        pdf.save()

        img = ImageBuilder()
        img.header_company(co, doc_type, ref, date_str)
        img._label_value("ORGANISME", organisme)
        img.attestation_block(co, date_str, validity_days)
        img.footer(co)
        img.save(jpg_path)

    # ---- Batch -------------------------------------------------------------

    def generate_batch(self, batch_id: str, has_anomaly: bool = False):
        company      = self._get_company()
        anomaly_type = "CLEAN"

        if has_anomaly:
            anomaly_type = random.choice(self.ANOMALY_TYPES)

        print(f"[{batch_id}] {company['name'][:40]:<40} | {company['siret']} | {anomaly_type}")

        for doc_type in DOC_TYPES:
            uid      = uuid.uuid4().hex[:6]
            date     = datetime.now()
            tva_ov   = None
            ttc_ov   = None
            siret_ov = None
            validity = 180
            label    = "CLEAN"

            # Pré-calcul des montants (nécessaire pour construire les anomalies financières)
            items    = self._get_items()
            total_ht = round(sum(i["qty"] * i["unit_price"] for i in items), 2)
            tva_real = round(total_ht * TVA_RATE, 2)
            ttc_real = round(total_ht + tva_real, 2)

            if has_anomaly:

                if anomaly_type == "MATH_ERROR" and doc_type in ("FACTURE", "DEVIS"):
                    ttc_ov = round(ttc_real + 150.00, 2)   # TTC gonflé
                    tva_ov = tva_real                       # TVA correcte
                    label  = "MATH_ERROR"

                elif anomaly_type == "TVA_WRONG" and doc_type in ("FACTURE", "DEVIS"):
                    tva_ov = round(tva_real + 80.00, 2)    # TVA gonflée
                    ttc_ov = ttc_real                       # TTC inchangé → incohérence
                    label  = "TVA_WRONG"

                elif anomaly_type == "SIRET_MISSING":
                    siret_ov = ""
                    label    = "SIRET_MISSING"

                elif anomaly_type == "SIRET_DB_MISSING":
                    siret_ov = "99988877700012"
                    label    = "SIRET_DB_MISSING"

                elif anomaly_type == "EXPIRED_ATTESTATION" \
                        and doc_type in ("ATTESTATION_URSSAF", "KBIS"):
                    date     = datetime.now() - timedelta(days=random.randint(190, 500))
                    validity = 180
                    label    = "EXPIRED_ATTESTATION"

                elif anomaly_type == "EXPIRED_DATE":
                    # Date du document antérieure de plus d'un an — tous types
                    date  = datetime.now() - timedelta(days=random.randint(370, 900))
                    label = "EXPIRED_DATE"

            # Nom de fichier générique pour plus de réalisme
            fname    = f"{doc_type.lower()}_{uid}"
            pdf_path = os.path.join(self.output_dir, f"{fname}.pdf")
            jpg_path = os.path.join(self.output_dir, f"{fname}_photo.jpg")

            if doc_type in ("FACTURE", "DEVIS"):
                self._build_facture_devis(
                    pdf_path, jpg_path, doc_type, company, date,
                    tva_override=tva_ov,
                    ttc_override=ttc_ov,
                    siret_override=siret_ov,
                )
            else:
                self._build_attestation(
                    pdf_path, jpg_path, doc_type, company, date,
                    validity_days=validity,
                    siret_override=siret_ov,
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    companies = get_companies()
    gen = DatasetGenerator(OUTPUT_DIR, companies)

    for f in os.listdir(OUTPUT_DIR):
        if f.endswith((".pdf", ".jpg")):
            os.remove(os.path.join(OUTPUT_DIR, f))

    print(f"=== ScanDocs Dataset Generator v4.2 => {OUTPUT_DIR} ===\n")

    N_CLEAN  = 5
    N_ERRORS = 12

    for i in range(N_CLEAN):
        gen.generate_batch(f"B{i:02d}", has_anomaly=False)
    for i in range(N_ERRORS):
        gen.generate_batch(f"B{i+N_CLEAN:02d}", has_anomaly=True)

    total = (N_CLEAN + N_ERRORS) * len(DOC_TYPES) * 2
    print(f"\n✓ {total} fichiers generes dans '{OUTPUT_DIR}'.")