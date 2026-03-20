"""
Data Lake service — Medallion architecture (Raw → Clean → Curated).

Structure:
    data/raw/       raw uploaded files
    data/clean/     OCR text files  (.txt)
    data/curated/   validated JSON  (.json)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.app.db.mongodb import get_db

# ---------------------------------------------------------------------------
RAW    = "data/raw"
CLEAN  = "data/clean"
CURATED = "data/curated"


def init_datalake() -> None:
    """Create the 3 Data Lake directories if they do not already exist."""
    for path in (RAW, CLEAN, CURATED):
        os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def generate_document_id() -> str:
    return str(uuid.uuid4())


def generate_batch_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Raw layer — raw uploaded file
# ---------------------------------------------------------------------------

def save_to_raw(
    document_id: str,
    filename: str,
    file_bytes: bytes,
    batch_id: str,
) -> dict:
    """
    Save the raw uploaded file directly into data/raw/.
    Metadata is stored in MongoDB only (no sidecar file).

    Returns the metadata dict.
    """
    init_datalake()

    raw_path = os.path.join(RAW, f"{document_id}_{filename}")
    with open(raw_path, "wb") as fh:
        fh.write(file_bytes)

    return {
        "document_id": document_id,
        "filename":    filename,
        "file_path":   raw_path,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "batch_id":    batch_id,
        "status":      "raw",
    }


def create_document_entry(metadata: dict, predicted_type: str = "unknown") -> None:
    """Insert one record into the MongoDB ``documents`` collection."""
    db = get_db()
    db["documents"].insert_one(
        {
            "document_id":    metadata["document_id"],
            "batch_id":       metadata["batch_id"],
            "filename":       metadata["filename"],
            "raw_path":       metadata["file_path"],
            "uploaded_at":    metadata["uploaded_at"],
            "status":         metadata["status"],
            "predicted_type": predicted_type,
        }
    )


# ---------------------------------------------------------------------------
# Clean layer — OCR text file
# ---------------------------------------------------------------------------

def save_to_clean(
    document_id: str,
    batch_id: str,
    ocr_text: Optional[str] = None,
    extracted_data: Optional[dict] = None,
    normalized_data: Optional[dict] = None,
) -> dict:
    """
    Save the OCR text into data/clean/{document_id}.txt.
    Extracted and normalized data are stored in MongoDB only.

    Returns a dict with the clean_path key.
    """
    init_datalake()

    paths: dict = {}
    now = datetime.now(timezone.utc).isoformat()

    if ocr_text is not None:
        clean_path = os.path.join(CLEAN, f"{document_id}.txt")
        with open(clean_path, "w", encoding="utf-8") as fh:
            fh.write(ocr_text)
        paths["clean_path"] = clean_path

    db = get_db()
    db["extracted_data"].update_one(
        {"document_id": document_id},
        {
            "$set": {
                "document_id":     document_id,
                "batch_id":        batch_id,
                "clean_path":      paths.get("clean_path", ""),
                "extracted_data":  extracted_data  or {},
                "normalized_data": normalized_data or {},
                "extracted_at":    now,
            }
        },
        upsert=True,
    )

    db["documents"].update_one(
        {"document_id": document_id},
        {"$set": {"status": "clean"}},
    )

    return paths


# ---------------------------------------------------------------------------
# Curated layer — validated JSON file
# ---------------------------------------------------------------------------

def save_to_curated(
    batch_id: str,
    document_id: Optional[str] = None,
    validated_record: Optional[dict] = None,
    anomalies: Optional[list] = None,
) -> dict:
    """
    Save one validated record as data/curated/{document_id}.json.
    Anomalies are stored in MongoDB only.

    Returns a dict with the curated_path key.
    """
    init_datalake()

    paths: dict = {}
    now = datetime.now(timezone.utc).isoformat()
    db  = get_db()

    if validated_record is not None and document_id is not None:
        p = os.path.join(CURATED, f"{document_id}.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(validated_record, fh, indent=2, ensure_ascii=False)
        paths["curated_path"] = p

        db["validated_records"].update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "document_id":   document_id,
                    "batch_id":      batch_id,
                    "supplier_name": validated_record.get("supplier_name", ""),
                    "siren":         validated_record.get("siren", ""),
                    "siret":         validated_record.get("siret", ""),
                    "doc_type":      validated_record.get("doc_type", ""),
                    "montants":      validated_record.get("montants", []),
                    "status":        "curated",
                    "validated_at":  now,
                }
            },
            upsert=True,
        )

    if anomalies:
        for anomaly in anomalies:
            db["anomalies"].insert_one(
                {
                    "anomaly_id":   str(uuid.uuid4()),
                    "batch_id":     batch_id,
                    "rule_code":    anomaly.get("rule_code", "UNKNOWN"),
                    "message":      anomaly.get("message", ""),
                    "severity":     anomaly.get("severity", "medium"),
                    "document_ids": anomaly.get("document_ids", []),
                    "detected_at":  now,
                }
            )

    if document_id:
        db["documents"].update_one(
            {"document_id": document_id},
            {"$set": {"status": "curated"}},
        )

def save_batch_anomalies(batch_id: str, anomalies: list) -> None:
    """Save anomalies that concern multiple documents or the batch as a whole."""
    if not anomalies:
        return

    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    for anomaly in anomalies:
        db["anomalies"].insert_one(
            {
                "anomaly_id":   str(uuid.uuid4()),
                "batch_id":     batch_id,
                "rule_code":    anomaly.get("rule_code", "BATCH_INCONSISTENCY"),
                "message":      anomaly.get("message", ""),
                "severity":     anomaly.get("severity", "high"),
                "document_ids": anomaly.get("document_ids", []),
                "detected_at":  now,
            }
        )
