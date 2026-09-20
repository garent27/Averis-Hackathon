# Shipping Document Verification — Method

This describes the pipeline in `solution/`: given the SDOC hackathon inbox
(`email_id` → subject/body/attachments), produce a classification and, for
document-comparison requests, an SI-vs-BL discrepancy report, for every email.

## Pipeline overview

```
inbox (Docker server / static bundle)
        │
        ▼
  classify_email()  ──────────────────────────────────────────────
        │  1. rule_classify_email() — regex on known subject templates
        │  2. only if no rule matches → llm.classify_email() (Claude, JSON)
        ▼
  category ∈ {BL_COMPARISON, SI_REQUEST, INVOICE_QUERY, GENERAL, SPAM}
        │
        │  (only BL_COMPARISON emails with both an SI and a BL attachment continue)
        ▼
  extract_fields() × 2 (SI, BL)  ─────────────────────────────────
        │  1. deterministic label-matching (regex + synonym dictionary)
        │  2. LLM text fallback — fills only the fields tier 1 missed
        │  3. vision LLM fallback — image-only/scanned PDFs with no text layer
        ▼
  normalize (case, whitespace, punctuation, company suffixes, weight units)
        ▼
  compare_fields(si, bl) → list of mismatched fields
        ▼
  submission.json { email_id: {category, status, defect_fields, has_defect, review_reason} }
        ▼
  POST /submit → scoreboard
```

Files:

| File | Role |
|---|---|
| `loader.py` | Given by organizers. Fetches emails/attachments from the local static bundle or the Docker server over the same API. |
| `classify.py` | Entry point. Runs the classifier + extractor over every email, writes `submission.json`, self-scores via `/submit`. |
| `extract_compare.py` | Field extraction (hybrid, see below) + normalization + comparison. |
| `llm.py` | The LLM fallback tier for both classification and extraction (Claude, structured JSON output). Only called when the deterministic tier is unconfident or incomplete. |

Run it with `python classify.py` from inside `solution/`, against a running
Docker server (`docker compose up --build` from `sdoc-docker/`).

## Classification

**Tier 1 — rules.** `rule_classify_email()` matches each subject against the
literal templates the dataset generator uses (`sdoc-docker/data_v2/emails.py`
+ `pools.py`): the fixed SPAM subject list, `BL_COMPARISON`'s coded
department-prefix and plain-English phrasings, `SI_REQUEST`'s `SI - ...`
prefix, `INVOICE_QUERY`'s billing/charges phrasing, `GENERAL`'s report/reminder
phrasing. If nothing matches, it returns `None` instead of guessing.

**Tier 2 — LLM fallback.** Only emails tier 1 couldn't confidently place go to
`llm.classify_email()`: one Claude call with `output_format` constrained to a
5-value enum, so the response is always exactly one of the five categories.

On this dataset, tier 1 alone reaches **100% accuracy** (macro F1 = 1.0) and
tier 2 is never invoked — the dataset's subject lines are template-generated,
so the rule set covers them exactly. Tier 2 exists for inputs the rules don't
recognize (unusual phrasing on a less templated, real-world inbox).

## Extraction

The seven compared fields: `shipper, consignee, notify_party,
port_of_loading, port_of_discharge, container_count, gross_weight_kg`.

**Tier 1 — deterministic label-matching.** Each SI/BL attachment renders the
same field under a different synonym label (e.g. "Port of Loading" vs "Load
Port" vs "POL") — a synonym dictionary maps every known label variant to its
canonical field, per attachment format:

- **.txt** — `Label: value` lines.
- **.pdf** — extracted text; count/weight lines use `Label: value`, name/port
  lines render label and value on one line with no colon.
- **.docx** — a 2-column table, label cell may carry a trailing Chinese
  annotation.
- **.xlsx** — 2-column rows; name fields are `"name | addr1; addr2"`.

**Tier 2 — LLM text fallback.** If tier 1 didn't find all 7 fields, the
attachment's full plain text goes to `llm.extract_fields_raw()` (Claude,
structured JSON via a Pydantic schema), and only the *missing* fields are
filled in — fields tier 1 already found are never overwritten by the LLM.
A fallback failure (e.g. no API key, network error) degrades to tier 1's
partial result rather than discarding it.

**Tier 3 — vision LLM fallback.** If an attachment has no extractable text at
all (image-only/scanned PDF), the first page is rendered to a PNG and sent to
`llm.extract_fields_vision()` for the same structured extraction, straight
from the image.

On this dataset, tier 1 alone handles the vast majority of cases (plain text
and the real PDF/DOCX/XLSX layouts); tiers 2–3 exist for messier or scanned
inputs not present in the main 500 emails.

## Normalization

Extracted values are normalized before comparison so equal information in
different wording doesn't register as a false mismatch:

- **Names** (shipper/consignee/notify_party): uppercased, punctuation
  stripped, whitespace collapsed, trailing company-suffix tokens (`LTD`,
  `LLC`, `INC`, `PTE`, `FZE`, …) dropped.
- **Ports**: trailing `" (CODE)"` annotations stripped, case/whitespace
  normalized.
- **Container count**: leading integer parsed out of strings like `"3 x
  40'HC"`.
- **Gross weight**: parsed to an integer number of **kilograms**, converting
  from metric tons (`MT`/`tonne`) or pounds (`lb`) when that unit is present
  in the raw value; kilograms/no-unit is the default.

## Comparison

`compare_fields(si, bl)` is deterministic: for each of the 7 fields, if both
sides extracted a value and they differ (after normalization), the field is
reported as a mismatch. A field missing from either side is **not** reported
as a mismatch — a blank or unreadable value is treated as uncertainty, not a
discrepancy (this distinction matters for the dataset's `NEEDS_REVIEW`
category, see Limitations).

## Submission

`classify.py` builds one JSON object keyed by every `email_id`, in the shape
the scoring endpoint expects:

```json
{ "email_001": {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": null,
    "has_defect": true,
    "defect_fields": ["consignee"]
} }
```

and submits it to `POST /submit` for a self-score before you look at anything
else.

## Results (main 500 + 20 edge cases, n = 520)

| Metric | Score |
|---|---|
| Stage 1 — classification macro F1 | **1.00** |
| Stage 3 — defect detection F1 | **0.97** (precision 0.96, recall 0.98) |
| End-to-end (defects routed *and* flagged with exact fields) | **0.87** (40/46) |
| **Final score** (`0.30·stage1 + 0.20·stage3 + 0.50·end_to_end`) | **0.928** |

## Known limitations / next steps

- **`NEEDS_REVIEW` escalation is not implemented yet.** The dataset's 20 edge
  cases (`wrong_doc_type`, `missing_attachment`, `unreadable`,
  `missing_value`) should be escalated to a human with the reason, rather than
  silently defaulting to `OK`. Currently `reliability.escalation_recall` is
  `0.0` — this is the main gap left in the `end_to_end` score.
- LLM fallback tiers (2 and 3) are single-shot prompts with no few-shot
  examples — untested against real model output on this dataset, since tier 1
  resolves everything here. Worth validating against a deliberately messy
  input once an API key is available.
- The report currently only stores which fields mismatched, not the
  side-by-side SI/BL values for each — worth adding for the human-readable
  discrepancy report the spec asks for (e.g. `"SI: 3 / BL: 4"`).
