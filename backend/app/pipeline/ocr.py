import os
import cv2
import pytesseract
import numpy as np
import pypdfium2 as pdfium


def _preprocess_image(img: np.ndarray) -> np.ndarray:
    if img is None:
        raise ValueError("Image vide ou illisible.")

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Check if we should threshold - for very clean docs, adaptive thresholding can be harmful
    # If the variance is low (mostly white/black), maybe just use binary
    # For now, let's just use simple thresholding if it looks high contrast
    _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return thresh


def extract_text_from_image(image_path: str) -> str:
    img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"Impossible de lire le fichier image : {image_path}")

    # Try raw first if it's very clean, or just use the processed one
    processed = _preprocess_image(img)
    text = pytesseract.image_to_string(processed, lang="fra+eng")
    
    # If empty, try without preprocessing
    if not text.strip():
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray, lang="fra+eng")
        
    return text.strip()


def extract_text_from_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        raise ValueError(f"PDF introuvable : {pdf_path}")

    pdf = pdfium.PdfDocument(pdf_path)
    all_text = []

    for i in range(len(pdf)):
        page = pdf[i]
        # Increase scale to 3 for higher DPI (approx 216 DPI)
        bitmap = page.render(scale=3)
        pil_image = bitmap.to_pil()
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Same strategy: try processed then raw
        processed = _preprocess_image(img)
        page_text = pytesseract.image_to_string(processed, lang="fra+eng")
        
        if not page_text.strip():
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            page_text = pytesseract.image_to_string(gray, lang="fra+eng")
            
        all_text.append(page_text.strip())

    return "\n".join(all_text).strip()


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()

    if ext in [".jpg", ".jpeg", ".png"]:
        return extract_text_from_image(file_path)

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)

    raise ValueError(f"Type de fichier non supporté pour OCR : {ext}")