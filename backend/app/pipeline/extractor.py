"""
extractor.py - v2.1
Corrections v2.1:
  BUG 1 — TVA tronquée (ex: 1763.87 → 763.87)
    Cause: le séparateur [:\|;1] incluait le chiffre "1", qui était confondu
           avec le premier chiffre du montant (ex: "1" dans "1763.87").
    Fix:   séparateur réduit à [:\|;] (jamais de chiffre), et pattern TVA
           utilise [ \t]* pour ne PAS traverser les sauts de ligne.

  BUG 2 — TOTAL HT = "20" au lieu de la vraie valeur
    Cause: quand l'OCR sépare label et valeur sur des lignes différentes
           (TOTAL HT:\n\nTVA (20%):\n\n29498.41\n...), le pattern \s*
           traversait les newlines et capturait la mauvaise valeur, ou
           le fallback prenait la première ligne non-vide (qui était le
           label suivant, contenant "20" dans "TVA (20%)").
    Fix:   extract_financial_block() gère explicitement deux cas :
           - CAS A : label + valeur sur la même ligne ([ \t]* interdit le newline)
           - CAS B : labels groupés puis valeurs groupées — parsing positionnel
                     dans l'ordre des labels du bloc RECAPITULATIF.
"""

import re


# ---------------------------------------------------------------------------
# Helpers génériques
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Strip + suppression des lignes vides multiples."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _extract_field(text: str, *labels: str) -> str | None:
    """
    Cherche LABEL: valeur sur une seule ligne.
    Séparateur: : | ; uniquement — jamais de chiffre pour éviter la confusion
    avec le premier caractère du montant.
    [ \t]* après le séparateur : ne traverse pas les sauts de ligne.
    """
    for label in labels:
        pattern = rf"(?i)^{re.escape(label)}\s*[:\|;][ \t]*(.+)$"
        m = re.search(pattern, text, re.MULTILINE)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return None


def _norm_float(raw: str | None) -> str | None:
    """Normalise une chaîne monétaire en float string ('1 234,56 EUR' → '1234.56')."""
    if not raw:
        return None
    v = re.sub(r"[^\d,\.]", "", str(raw))
    if "," in v and "." not in v:
        v = v.replace(",", ".")
    elif "," in v and "." in v:
        # Format 1.234,56 → retirer le point millier, garder la virgule
        v = v.replace(".", "").replace(",", ".")
    nums = re.findall(r"\d+\.\d+|\d+", v)
    return nums[0] if nums else None


# ---------------------------------------------------------------------------
# Extraction du bloc financier (logique centrale corrigée)
# ---------------------------------------------------------------------------

def extract_financial_block(text: str) -> dict:
    """
    Extrait TOTAL HT, TVA et TOTAL TTC en gérant deux mises en page OCR :

    CAS A — label et valeur sur la même ligne (PDF propre ou OCR parfait) :
        TOTAL HT: 1234.56 EUR
        TVA (20%) 246.91 EUR
        TOTAL TTC: 1481.47 EUR

    CAS B — labels groupés puis valeurs groupées (OCR qui casse les colonnes) :
        TOTAL HT:
        TVA (20%):
        TOTAL TTC:
        1234.56 EUR
        246.91 EUR
        1481.47 EUR

    Dans les deux cas, [ \t]* est utilisé après le séparateur pour ne jamais
    traverser un saut de ligne en CAS A, ce qui évitait la capture croisée.
    """
    results = {"total_ht": None, "tva": None, "total_ttc": None}

    # --- CAS A : même ligne ([ \t]* = pas de newline autorisé) ---

    for label in ("TOTAL HT", "MONTANT HT", "NET HT"):
        m = re.search(
            rf"(?i)^{re.escape(label)}\s*[:\|;][ \t]*(\d[\d ]*[.,]\d+)",
            text, re.MULTILINE
        )
        if m:
            results["total_ht"] = m.group(1).replace(" ", "").replace(",", ".")
            break

    for label in ("TOTAL TTC", "MONTANT TTC", "NET A PAYER"):
        m = re.search(
            rf"(?i)^{re.escape(label)}\s*[:\|;][ \t]*(\d[\d ]*[.,]\d+)",
            text, re.MULTILINE
        )
        if m:
            results["total_ttc"] = m.group(1).replace(" ", "").replace(",", ".")
            break

    # TVA : pattern dédié pour "TVA (XX%) [:]? montant" sur une seule ligne.
    # [ \t]* interdit le saut de ligne → pas de capture croisée avec la ligne suivante.
    m_tva = re.search(
        r"(?i)TVA\s*\([^)]*\)[ \t]*:?[ \t]*(\d[\d ]*[.,]\d+)", text
    )
    if m_tva:
        results["tva"] = m_tva.group(1).replace(" ", "").replace(",", ".")

    # --- CAS B : fallback positionnel si des champs manquent ---
    if any(v is None for v in results.values()):
        # Isole le bloc récapitulatif
        bloc_m = re.search(
            r"(?i)\[?\s*RECAPITULATIF[^\n]*\]?\n([\s\S]+?)(?=\n\[|\Z)", text
        )
        bloc = bloc_m.group(1) if bloc_m else text

        # Collecte les montants des lignes qui NE contiennent PAS un label connu,
        # dans l'ordre d'apparition.
        amounts = []
        for line in bloc.splitlines():
            if not re.search(r"(?i)TOTAL HT|TVA|TOTAL TTC|MONTANT|NET A", line):
                for num in re.findall(r"\d+[.,]\d+", line):
                    amounts.append(num.replace(",", "."))

        # Reconstruit l'ordre des clés tel qu'elles apparaissent dans le bloc
        order_map = []
        for pattern_re, key in (
            (r"TOTAL HT",  "total_ht"),
            (r"TVA",       "tva"),
            (r"TOTAL TTC", "total_ttc"),
        ):
            if re.search(rf"(?i){pattern_re}", bloc):
                order_map.append(key)

        # Assigne chaque montant au champ encore null, dans l'ordre
        amt_idx = 0
        for key in order_map:
            if results[key] is None and amt_idx < len(amounts):
                results[key] = amounts[amt_idx]
                amt_idx += 1

    return results


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def extract_information(text: str) -> dict:
    """
    Extrait les champs clés d'un document administratif français.
    Entrée  : texte brut sorti de l'OCR.
    Sortie  : dict compatible avec le pipeline de validation.
    """
    t = _clean(text)

    # 1. SIRET — label d'abord, fallback 14 chiffres consécutifs
    siret_raw = _extract_field(t, "SIRET", "SIRET EMETTEUR")
    if siret_raw:
        siret_raw = re.sub(r"\D", "", siret_raw)   # garde uniquement les chiffres
        if not siret_raw:
            siret_raw = None
    else:
        no_space = re.sub(r"\s+", "", t)
        m14 = re.findall(r"(?<!\d)\d{14}(?!\d)", no_space)
        siret_raw = m14[0] if m14 else None

    # 2. Date — label d'abord, fallback pattern dd/mm/yyyy
    date_raw = _extract_field(t, "DATE", "DATE DELIVRANCE", "DATE DOCUMENT")
    if date_raw:
        dm = re.search(r"(\d{2})\s*/\s*(\d{2})\s*/\s*(\d{4})", date_raw)
        date_val = f"{dm.group(1)}/{dm.group(2)}/{dm.group(3)}" if dm else date_raw
    else:
        dm = re.search(r"(\d{2})\s*/\s*(\d{2})\s*/\s*(\d{4})", t)
        date_val = f"{dm.group(1)}/{dm.group(2)}/{dm.group(3)}" if dm else None

    # 3. Nom de l'entreprise
    company = _extract_field(t, "EMETTEUR", "COMPANY", "SOCIETE", "RAISON SOCIALE") or "Inconnu"

    # 4. Champs financiers (logique robuste CAS A / CAS B)
    financials = extract_financial_block(t)

    # 5. Métadonnées
    doc_type  = _extract_field(t, "TYPE DOCUMENT", "TYPE DOC")
    reference = _extract_field(t, "REFERENCE", "REF")

    return {
        # Champs attendus par le pipeline
        "company_name": company,
        "siret":        [siret_raw] if siret_raw else [],
        "dates":        [date_val]  if date_val  else [],
        "total_ht":     financials["total_ht"],
        "tva_amount":   financials["tva"],
        "total_ttc":    financials["total_ttc"],
        # Champs bonus
        "document_type": doc_type,
        "reference":     reference,
    }