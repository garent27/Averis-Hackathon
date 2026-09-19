#!/usr/bin/env python3
"""
extract_compare.py — extract the 7 shipment fields from plain-text SI/BL
attachments and compare them.

Field labels/synonyms are copied from sdoc-docker/data_v2/pools.py LABELS —
the SI and BL each pick a random label variant for the same field, so
extraction must recognise all variants and map them to one canonical name
(the "same information looks different" challenge from the spec).

Scope for now: .txt attachments only (render.py's si_txt/bl_txt layout).
PDF/DOCX/XLSX extraction is a separate follow-up (different parsing per
format); when an attachment isn't .txt, extract_fields() below returns {}
for it and the caller should treat that as "couldn't extract" rather than
guessing a comparison result.
"""
import re

# Canonical field -> label variants actually used by data_v2/render.py.
FIELD_LABELS = {
    "shipper": ["Shipper", "Shipper/Exporter", "Shipper (Principal or Seller)", "SHIPPER"],
    "consignee": ["Consignee", "Consignee (Non-Negotiable)", "CONSIGNEE", "To the Order of"],
    "notify_party": ["Notify Party", "Notify", "Notify Party/Intermediate Consignee", "NOTIFY PARTY"],
    "port_of_loading": ["Port of Loading", "Port of Loading (POL)", "Load Port", "POL", "PORT OF LOADING"],
    "port_of_discharge": ["Port of Discharge", "Port of Discharge (POD)", "Discharge Port", "POD", "PORT OF DISCHARGE"],
    "container_count": ["No. of Containers", "Total Containers", "No. of Containers or Packages", "Container Count"],
    "gross_weight_kg": ["Gross Weight (KG)", "Gross Wt (kgs)", "Gross Weight毛重(KGS)", "GROSS WEIGHT"],
}

COMPARE_FIELDS = list(FIELD_LABELS.keys())

# label text (uppercased) -> canonical field, for O(1) lookup while parsing.
_LABEL_TO_FIELD = {
    variant.upper(): field
    for field, variants in FIELD_LABELS.items()
    for variant in variants
}


def _parse_labelled_lines(text: str) -> dict:
    """Scan every 'Label: value' line and map recognised labels to raw values.
    Lines whose label doesn't match a known variant (e.g. address continuation
    lines, headers) are ignored rather than guessed at."""
    raw = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        field = _LABEL_TO_FIELD.get(label.strip().upper())
        if field is None:
            continue
        raw[field] = value.strip()
    return raw


def _normalize_port(value: str) -> str:
    # render.py's txt layout appends " (CODE)" to the port name; the
    # ground-truth port value never includes the code, so strip it.
    return re.sub(r"\s*\([A-Z0-9]+\)\s*$", "", value).strip()


def _normalize_container_count(value: str):
    # txt layout is "{count} x {size}", e.g. "3 x 40'HC".
    m = re.match(r"\s*(\d+)", value)
    return int(m.group(1)) if m else None


def _normalize_gross_weight(value: str):
    # txt layout is "{weight:,} KG", e.g. "22,000 KG".
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else None


def extract_fields(text: str) -> dict:
    """Extract+normalise the 7 comparison fields from SI/BL .txt content.
    Missing fields are simply absent from the returned dict — the caller
    decides what to do about an incomplete extraction."""
    raw = _parse_labelled_lines(text)
    out = {}
    for field, value in raw.items():
        if field == "port_of_loading" or field == "port_of_discharge":
            out[field] = _normalize_port(value)
        elif field == "container_count":
            out[field] = _normalize_container_count(value)
        elif field == "gross_weight_kg":
            out[field] = _normalize_gross_weight(value)
        else:
            out[field] = value
    return out


def compare_fields(si_fields: dict, bl_fields: dict) -> list:
    """Return the sorted list of the 7 fields whose SI and BL values differ.
    A field missing from either side is NOT reported as a mismatch -- a
    blank/unreadable value is uncertainty, not a discrepancy (see
    HACKATHON_CONTEXT.md: NEEDS_REVIEW is a separate axis from MISMATCH)."""
    mismatches = []
    for field in COMPARE_FIELDS:
        si_val = si_fields.get(field)
        bl_val = bl_fields.get(field)
        if si_val is None or bl_val is None:
            continue
        if si_val != bl_val:
            mismatches.append(field)
    return sorted(mismatches)
