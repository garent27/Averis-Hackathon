#!/usr/bin/env python3
"""
llm.py — LLM classifier and extractor, used as the FALLBACK tier in the
hybrid pipeline (classify.py / extract_compare.py do rules/regex first and
only call into here when the deterministic pass is unconfident or incomplete):
  - classify_email(): one call, structured JSON output -> one of 5 categories.
    Called only when no classification rule matched.
  - extract_fields_raw(): one call per attachment's plain text, structured
    JSON output -> the 7 shipment fields as RAW strings (unit conversion /
    cleanup stays a separate deterministic Normalizer step, so this only ever
    fills in fields the regex extractor couldn't find).
  - extract_fields_vision(): same, but for a page IMAGE -- used when there's
    no text layer at all (image-only/scanned PDF), so plain-text extraction
    has nothing to work with.

Uses Google Gemini (free tier via Google AI Studio) instead of a paid API --
good enough for a basic fallback tier to iterate on: better prompts, few-shot
examples for edge cases, confidence/uncertainty signals for NEEDS_REVIEW
routing, etc.

Requires GOOGLE_API_KEY -- read from a local .env file (see .env in this
folder; keep it out of git, already covered by .gitignore) or the environment.
Being the fallback tier (not the primary path) keeps call volume low -- most
emails/attachments in this dataset are resolved by rules/regex for free and
never reach this module at all.
"""
import os
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()  # reads GOOGLE_API_KEY from .env next to this file

MODEL = "gemini-2.5-flash"

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
class Category(str, Enum):
    BL_COMPARISON = "BL_COMPARISON"
    SI_REQUEST = "SI_REQUEST"
    INVOICE_QUERY = "INVOICE_QUERY"
    GENERAL = "GENERAL"
    SPAM = "SPAM"


class ClassificationResult(BaseModel):
    category: Category


CLASSIFY_PROMPT = """Classify this shipping-operations inbox email into exactly one category.

- BL_COMPARISON: asks to check/compare a draft Bill of Lading against a Shipping Instruction (SI), or to prepare/amend a draft BL for that purpose.
- SI_REQUEST: asks to prepare, send, or confirm a Shipping Instruction for a new shipment.
- INVOICE_QUERY: about invoices, billing, freight/local charges, GR, D&D charges.
- GENERAL: internal operational updates, reports, reminders, HR/admin notices -- not a document request.
- SPAM: unsolicited marketing, phishing, prize/lottery scams, or anything unrelated to shipping operations.

From: {from_}
Subject: {subject}

Body:
{body}
"""


def classify_email(email: dict) -> str:
    """Classify one email via an LLM call with structured JSON output."""
    prompt = CLASSIFY_PROMPT.format(
        from_=email.get("from", ""),
        subject=email.get("subject", ""),
        body=email.get("body", ""),
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ClassificationResult,
        ),
    )
    return response.parsed.category.value


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class ShipmentFields(BaseModel):
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    container_count: Optional[str] = None  # raw, e.g. "3 x 40'HC" -- normalized later
    gross_weight_kg: Optional[str] = None  # raw, e.g. "22,000 KG" or "22 MT" -- normalized later


EXTRACT_PROMPT = """Extract these 7 shipment fields from the SI/BL document text below.
Return each value exactly as it appears in the document -- do not convert units
or reformat, that happens in a separate normalization step. If a field is not
present in the document, omit it rather than guessing.

Fields:
- shipper
- consignee
- notify_party
- port_of_loading
- port_of_discharge
- container_count (e.g. "3 x 40'HC")
- gross_weight_kg (the weight value with whatever unit is shown, e.g. "22,000 KG" or "22 MT")

Document text:
{text}
"""


def extract_fields_raw(document_text: str) -> dict:
    """Extract the 7 shipment fields from raw document text via an LLM call
    with structured JSON output. Returns RAW (un-normalized) string values --
    pass them through extract_compare.py's normalizer before comparing."""
    if not document_text.strip():
        return {}
    response = client.models.generate_content(
        model=MODEL,
        contents=EXTRACT_PROMPT.format(text=document_text),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ShipmentFields,
        ),
    )
    return {k: v for k, v in response.parsed.model_dump().items() if v is not None}


VISION_EXTRACT_PROMPT = """This is a page from a scanned/image-only shipping document (SI or BL) --
there is no text layer, so read the fields directly from the image.
Return each value exactly as it appears -- do not convert units or reformat,
that happens in a separate normalization step. If a field is not visible or
legible, omit it rather than guessing.

Fields:
- shipper
- consignee
- notify_party
- port_of_loading
- port_of_discharge
- container_count (e.g. "3 x 40'HC")
- gross_weight_kg (the weight value with whatever unit is shown, e.g. "22,000 KG" or "22 MT")
"""


def extract_fields_vision(image_bytes: bytes, media_type: str = "image/png") -> dict:
    """Extract the 7 shipment fields from a page IMAGE (no text layer) via a
    vision LLM call with structured JSON output. Used only when plain-text
    extraction found no usable text at all (image-only/scanned PDF) -- the
    "Scanned documents" advanced-stage case from the spec."""
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=media_type),
            VISION_EXTRACT_PROMPT,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ShipmentFields,
        ),
    )
    return {k: v for k, v in response.parsed.model_dump().items() if v is not None}
