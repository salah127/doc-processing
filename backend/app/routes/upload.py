import re
import os
import json
from fastapi import APIRouter, UploadFile, File

from backend.app.pipeline.ocr import extract_text
from backend.app.pipeline.extractor import extract_information
from backend.app.pipeline.classifier import classify_document
from backend.app.pipeline.validator import validate_document, check_inconsistencies

from backend.app.services.datalake import (
    generate_batch_id,
    generate_document_id,
    save_to_raw,
    save_to_clean,
    save_to_curated,
    create_document_entry,
    save_batch_anomalies
)

router = APIRouter()

@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    results = []
    batch_id = generate_batch_id()

    # ── RAW + CLEAN + CURATED ────────────────────────────────────────────────
    for file in files:
        filename = file.filename
        content  = await file.read()
        doc_id   = generate_document_id()

        # 1. Save to RAW (Bronze)
        raw_meta = save_to_raw(doc_id, filename, content, batch_id)
        
        # 2. Extract Document Type Early (for MongoDB entry)
        # We need text for classification
        result = {
            "document_id": doc_id,
            "filename": filename,
            "raw_path": raw_meta["file_path"],
            "status": "raw",
            "document_type": "unknown",
            "extracted_data": {},
            "validation": {},
        }

        ext = os.path.splitext(filename)[1].lower()

        if ext in [".jpg", ".jpeg", ".png", ".pdf", ".webp"]:
            try:
                # 3. OCR / Extraction -> CLEAN (Silver)
                text = extract_text(raw_meta["file_path"])
                doc_type = classify_document(text)
                extracted_data = extract_information(text)
                
                # Update early MongoDB entry
                create_document_entry(raw_meta, predicted_type=doc_type)

                clean_paths = save_to_clean(
                    doc_id, 
                    batch_id, 
                    ocr_text=text, 
                    extracted_data=extracted_data
                )

                # 4. Validation -> CURATED (Gold)
                temp_doc = {
                    "document_id": doc_id,
                    "filename": filename,
                    "document_type": doc_type,
                    "extracted_data": extracted_data,
                    "text": text,
                }
                validation_result = validate_document(temp_doc)

                curated_paths = save_to_curated(
                    batch_id=batch_id,
                    document_id=doc_id,
                    validated_record=temp_doc,
                    anomalies=validation_result.get("anomalies", [])
                )

                result.update({
                    "status": "curated",
                    "document_type": doc_type,
                    "extracted_data": extracted_data,
                    "ocr_text_preview": text[:200],
                    "clean_path": clean_paths.get("clean_path"),
                    "curated_path": curated_paths.get("curated_path"),
                    "validation": validation_result
                })

            except Exception as e:
                result["status"] = f"processing_failed: {str(e)}"
        else:
            create_document_entry(raw_meta)
            result["status"] = "raw_only"
            result["note"] = "File type not supported for full pipeline."

        results.append(result)

    # Validation inter-documents si plusieurs fichiers
    cross_document_alerts = []
    
    # Filter only successfully processed (curated) documents for cross-validation
    processed_list = []
    for r in results:
        if r and r.get("status") == "curated":
            processed_list.append({
                "document_id": r.get("document_id"),
                "filename": r.get("filename"),
                "document_type": r.get("document_type"),
                "extracted_data": r.get("extracted_data") or {},
            })

    if len(processed_list) >= 2:
        for i in range(len(processed_list)):
            for j in range(i + 1, len(processed_list)):
                doc1 = processed_list[i]
                doc2 = processed_list[j]
                
                alerts = check_inconsistencies(doc1, doc2)
                if alerts:
                    # Persist as BATCH_INCONSISTENCY in MongoDB
                    batch_anomalies = [{
                        "message": alert,
                        "document_ids": [doc1.get("document_id"), doc2.get("document_id")],
                        "severity": "high"
                    } for alert in alerts]
                    save_batch_anomalies(batch_id, batch_anomalies)

                    cross_document_alerts.append({
                        "doc1": doc1.get("filename"),
                        "doc2": doc2.get("filename"),
                        "alerts": alerts
                    })

    return {
        "batch_id": batch_id,
        "results": results,
        "cross_document_alerts": cross_document_alerts
    }
