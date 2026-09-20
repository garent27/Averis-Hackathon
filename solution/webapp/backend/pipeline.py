#!/usr/bin/env python3
"""
pipeline.py — builds the report data the app serves, by reusing the existing
solution/ modules (loader, classify, extract_compare) instead of duplicating
their logic.

Unlike classify.py's build_result() (which only records category/status/
defect_fields for the submission.json format), process_email() here also
keeps the actual SI/BL field VALUES so the frontend can show them side by
side, plus enough error/reason detail to drive the Review Queue and Retry
button.
"""
import sys
from pathlib import Path

# solution/ (parent of webapp/) holds loader.py, classify.py, extract_compare.py, llm.py
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from loader import Inbox  # noqa: E402
from extract_compare import extract_fields, compare_fields, COMPARE_FIELDS, _finalize  # noqa: E402
import classify as classify_module  # noqa: E402

SERVER = "http://localhost:8080"


def _find_attachment(attachments, marker):
    return next((p for p in attachments if marker in p), None)


def normalize_values(values: dict) -> dict:
    """Run user-edited (or re-submitted) field values through the same
    normalizer extraction uses, so a saved review compares like-for-like."""
    return _finalize(values or {})


def process_email(email: dict, inbox: Inbox) -> dict:
    """Classify + (if applicable) extract/compare one email. Returns a row
    with everything the Report and Review Queue views need."""
    email_id = email["email_id"]
    category = classify_module.classify_email(email)

    row = {
        "email_id": email_id,
        "subject": email.get("subject", ""),
        "from": email.get("from", ""),
        "attachments": email.get("attachments", []),
        "category": category,
        "status": "OK",
        "has_defect": False,
        "defect_fields": [],
        "review_reason": None,
        "error": None,
        "si_values": None,
        "bl_values": None,
        "reviewed": False,
        "note": None,
    }

    if category != "BL_COMPARISON" or not email.get("attachments"):
        return row

    si_path = _find_attachment(email["attachments"], "_SI.")
    bl_path = _find_attachment(email["attachments"], "_BL.")
    if not si_path or not bl_path:
        row["status"] = "NEEDS_REVIEW"
        row["review_reason"] = "missing_attachment"
        return row

    try:
        si_bytes = inbox.read_bytes(si_path)
        bl_bytes = inbox.read_bytes(bl_path)
    except Exception as e:
        row["status"] = "FAILED"
        row["error"] = f"could not fetch attachment: {e}"
        return row

    si_fields, bl_fields = {}, {}
    errors = []
    try:
        si_fields = extract_fields(si_bytes, si_path)
    except Exception as e:
        errors.append(f"SI extraction failed: {e}")
    try:
        bl_fields = extract_fields(bl_bytes, bl_path)
    except Exception as e:
        errors.append(f"BL extraction failed: {e}")

    row["si_values"] = si_fields
    row["bl_values"] = bl_fields

    if errors:
        row["status"] = "FAILED"
        row["error"] = " / ".join(errors)
        return row

    missing = [f for f in COMPARE_FIELDS if f not in si_fields or f not in bl_fields]
    if missing:
        row["status"] = "NEEDS_REVIEW"
        row["review_reason"] = "missing_value"
        return row

    defect_fields = compare_fields(si_fields, bl_fields)
    if defect_fields:
        row["status"] = "MISMATCH"
        row["has_defect"] = True
        row["defect_fields"] = defect_fields

    return row


def build_all(server: str = SERVER) -> dict:
    """Process every email in the inbox. Returns {email_id: row}."""
    inbox = Inbox(server)
    emails = inbox.emails()
    return {email["email_id"]: process_email(email, inbox) for email in emails}


def retry_one(email_id: str, server: str = SERVER) -> dict:
    """Re-run the pipeline for a single email (the Retry button)."""
    inbox = Inbox(server)
    email = inbox.get(email_id)
    return process_email(email, inbox)
