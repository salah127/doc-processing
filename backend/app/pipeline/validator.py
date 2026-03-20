import re
from datetime import datetime
from backend.app.db.mongodb import get_db

def _to_float(value):
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    # Strong clean
    v = str(value).replace("€", "").replace("EUR", "").replace(" ", "").replace(",", ".").replace("\xa0", "").strip()
    try:
        # If there are multiple groups of numbers (e.g. Rate + Amount), take the last one
        matches = re.findall(r"\d+\.\d+|\d+", v)
        if matches:
            return float(matches[-1])
        return None
    except:
        return None

def _parse_date(date_str):
    if not date_str: return None
    # Normalize: remove spaces and normalize separators
    d = date_str.replace(" ", "").replace(".", "/").replace("-", "/")
    # Try common formats
    for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(d, fmt)
        except:
            continue
    return None

def validate_document(doc: dict) -> dict:
    issues = []
    anomalies = []
    doc_id = doc.get("document_id")
    document_type = doc.get("document_type") or "unknown"
    extracted = doc.get("extracted_data") or {}
    
    siret_list = extracted.get("siret") or []
    dates = extracted.get("dates") or []
    total_ht = _to_float(extracted.get("total_ht"))
    tva_amount = _to_float(extracted.get("tva_amount"))
    total_ttc = _to_float(extracted.get("total_ttc"))

    # 1. SIRET Checks
    if not siret_list or not siret_list[0]:
        issues.append("SIRET manquant")
        anomalies.append({"rule_code": "MISSING_SIRET", "severity": "high", "message": "Aucun numéro SIRET n'a été détecté.", "document_ids": [doc_id]})
    else:
        siret = siret_list[0]
        # Check Format (14 digits)
        if not re.fullmatch(r"\d{14}", siret):
            issues.append(f"Format SIRET invalide : {siret}")
            anomalies.append({"rule_code": "INVALID_SIRET_FORMAT", "severity": "high", "message": f"SIRET format incorrect : {siret}", "document_ids": [doc_id]})
        else:
            # Check DB (SIRENE)
            db = get_db()
            company = db["companies"].find_one({"siren": siret[:9]})
            if not company:
                issues.append(f"SIRET inconnu : {siret[:9]}")
                anomalies.append({"rule_code": "SIRET_NOT_FOUND_IN_DB", "severity": "high", "message": f"Le SIREN {siret[:9]} n'existe pas en base SIRENE.", "document_ids": [doc_id]})

    # 2. Date & Expiration
    if not dates:
        issues.append("Date manquante")
        anomalies.append({"rule_code": "MISSING_DATE", "severity": "medium", "message": "Aucune date trouvée.", "document_ids": [doc_id]})
    else:
        if "vigilance" in document_type.lower() or "attestation" in document_type.lower():
            p_date = _parse_date(dates[0])
            if p_date and p_date.date() < datetime.now().date():
                msg = f"Document expiré le {p_date.strftime('%d/%m/%Y')}"
                issues.append(msg)
                anomalies.append({"rule_code": "EXPIRED_DOC", "severity": "critical", "message": msg, "document_ids": [doc_id]})

    # 3. Financial Consistency
    if document_type in ["devis", "facture"]:
        if total_ht is None or total_ttc is None:
            msg = "Champs financiers (HT/TTC) manquants."
            issues.append(msg)
            anomalies.append({"rule_code": "MISSING_FINANCIALS", "severity": "high", "message": msg, "document_ids": [doc_id]})
        else:
            # Check Math (TVA = 20%)
            calc_tva = round(total_ht * 0.20, 2)
            calc_ttc = round(total_ht + calc_tva, 2)
            
            # Check TVA amount if extracted
            if tva_amount is not None:
                if abs(tva_amount - calc_tva) > 5.0: # Allow small buffer for rounding or OCR
                    msg = f"TVA incohérente : {tva_amount} (lu) vs {calc_tva} (attendu)"
                    issues.append(msg)
                    anomalies.append({"rule_code": "TVA_INCONSISTENCY", "severity": "medium", "message": msg, "document_ids": [doc_id]})
            
            # Check Total TTC
            if abs(total_ttc - calc_ttc) > 5.0:
                msg = f"Erreur de calcul : HT({total_ht}) + TVA(20%) should be {calc_ttc} vs TTC({total_ttc}) lu."
                issues.append(msg)
                anomalies.append({"rule_code": "MATH_INCONSISTENCY", "severity": "high", "message": msg, "document_ids": [doc_id]})

    # Score calculation
    score = 100
    for a in anomalies:
        if a["severity"] == "critical": score -= 50
        elif a["severity"] == "high": score -= 30
        else: score -= 10
    
    return {
        "is_valid": len(anomalies) == 0,
        "issues": issues,
        "anomalies": anomalies,
        "score": max(0, score)
    }

def check_inconsistencies(doc1: dict, doc2: dict) -> list:
    alerts = []
    return alerts # Simplified for now to focus on doc-level