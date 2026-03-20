def classify_document(text: str) -> str:
    text = text.lower()
    
    # Pre-clean for header check (handles "FACTU R E", "D E V I S")
    text_clean = text.replace(" ", "")

    scores = {
        "facture": 0,
        "devis": 0,
        "attestation": 0,
        "rib": 0,
    }

    # weighted_keywords
    weighted_keywords = {
        "facture": {
            "facture": 5,
            "net à payer": 4,
            "montant ttc": 2,
            "fac-": 3,
            "tva (20%)": 1,
        },
        "devis": {
            "devis": 5,
            "proposition": 2,
            "validité": 3,
            "ref: dev": 4,
            "n° : dev": 4,
        },
        "attestation": {
            "attestation": 6,
            "urssaf": 5,
            "vigilance": 5,
            "certifie": 2,
            "déclare": 2,
        },
        "rib": {
            "iban": 5,
            "bic": 4,
            "rib": 4,
            "compte bancaire": 3,
        },
    }

    for doc_type, keywords in weighted_keywords.items():
        for word, weight in keywords.items():
            if word in text:
                scores[doc_type] += weight

    # Priority Title Check (Header)
    # Using text_clean to catch "F A C T U R E" or "FACTU R E"
    if "facture" in text_clean[:200]:
        scores["facture"] += 15
    if "devis" in text_clean[:200]:
        scores["devis"] += 15
    if "attestation" in text_clean[:200] or "vigilance" in text_clean[:200]:
        scores["attestation"] += 15
    if "relevéd'identitébancaire" in text_clean[:200]:
        scores["rib"] += 15

    best_type = max(scores, key=scores.get)

    if scores[best_type] == 0:
        return "unknown"

    return best_type