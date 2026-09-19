# Averis Hackathon — Context for Claude

Read this file first in any new conversation about this project. It explains the
challenge, the data, the tooling already built, and how to build/evaluate a solution.
Full spec: [`Shipping Document Verification Use Case.pdf`](Shipping%20Document%20Verification%20Use%20Case.pdf).

## 1. The challenge

**Shipping document verification: from email inbox to discrepancy report.**

A shipping operations team gets a mixed inbox (document-check requests, new SI
requests, invoice questions, general updates, spam). For a document-checking
request, they compare a **Shipping Instruction (SI)** — the source of truth for
intended shipment details — against a draft **Bill of Lading (BL)**, to catch
errors before the BL is finalized.

Three real problems the system should solve:
1. **Triage is slow** — staff must read every email and decide what it needs.
2. **Manual comparison is error-prone** — names, ports, quantities, weight checked
   by eye across two documents.
3. **Label synonymy** — the same field is worded differently across documents
   (e.g. "Port of Loading" vs "Load Port", "Consignee" vs "To the Order of",
   "Gross Weight (KG)" vs "Gross Wt (kgs)"). The system must recognize these as
   the same field.

### Required capabilities
| Capability | Meaning |
|---|---|
| **Classify** | Sort each email: `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`. Only `BL_COMPARISON` continues to extraction/comparison. |
| **Extract** | For comparison requests, read the SI and BL attachments and pull out the 7 shipment fields. |
| **Compare** | Diff SI vs BL field-by-field, surface mismatches side by side. |
| **Ask for help** | When it can't complete confidently, escalate to a human with context — never guess or fail silently. |

### The 7 comparison fields
`shipper, consignee, notify_party, port_of_loading, port_of_discharge, container_count, gross_weight_kg`

### Output expectations
- One clear result per email.
- If all 7 fields match → report **"No mismatch detected."**
- Otherwise flag exactly the mismatched fields, showing **SI value vs BL value** side by side.
  - Example: SI says 3 containers / 22,000 kg; BL says 4 containers / 22,000 kg → flag only
    container count, show `SI: 3 / BL: 4`.

### Advanced stage (optional, for standing out)
| Extension | What changes |
|---|---|
| PDF/Word attachments | Extract from tables and varied page layouts (not just plain text). |
| Scanned documents | Image-only PDFs — need OCR and/or a vision-capable LLM. |
| Messier inputs | Varied labels, misleading subjects, missing attachments — distinguish a real discrepancy from a reading/formatting issue. |
| Reliability & human review | When unreadable/missing/uncertain, escalate with source evidence + reason; allow retries; handle failures visibly. |

Accuracy = right requests + right discrepancies, no false alarms. Reliability =
knowing when *not* to guess.

## 2. Repo layout

```
Averis Hackathon/
├── Shipping Document Verification Use Case.pdf   ← official spec (source of truth)
├── HACKATHON_CONTEXT.md                          ← this file
├── sdoc-bundle/            ← unzipped STATIC participant bundle (no ground truth)
│   ├── inbox/              email_001.json … (JSON email records)
│   ├── attachments/        SI/BL files referenced by inbox emails (txt/xlsx/docx/pdf)
│   ├── loader.py           same Inbox() helper as below, points at local files or HTTP
│   ├── sample_submission.json
│   └── README.md
└── sdoc-docker/            ← organizer-side project: server + full dataset + generator
    ├── docker-compose.yml  docker compose up --build  → http://localhost:8080
    ├── data_v2/            THE FULL DATASET incl. ground_truth.json (don't ship this to participants)
    │   ├── inbox/           520 × email_XXX.json (500 main + 20 edge cases email_501–520)
    │   ├── attachments/     SI+BL pairs, txt/pdf/docx/xlsx
    │   ├── ground_truth.json   ← labels; PRIVATE, never served over HTTP by default
    │   ├── sample_submission.json
    │   ├── generate.py     deterministic generator (`python3 generate.py --seed 42 --n 500`)
    │   ├── pools.py         entity pools: carriers, ports, customers, label synonyms…
    │   ├── shipment.py      canonical shipment model + defect injection
    │   ├── render.py        attachment renderers (txt/pdf/docx/xlsx)
    │   ├── emails.py        subject/body generators per category
    │   ├── edgecases.py     generators for the 20 NEEDS_REVIEW edge cases
    │   └── README.md
    └── server/
        ├── app.py           FastAPI app: serves data + scores submissions
        ├── scoring.py       v2-aware scoring logic (shared by server + CLI)
        ├── score_cli.py     score a submission.json from the terminal (judges)
        ├── loader.py        participant one-import helper: `from loader import Inbox`
        ├── make_bundle.py   builds the participant static bundle (strips ground truth)
        ├── make_docker_bundle.py
        ├── requirements.txt fastapi + uvicorn
        ├── Dockerfile
        └── README.md        (delivery-kit doc — mirrors §3/§4 below)
```

Note: `sdoc-bundle/` is effectively a snapshot of `sdoc-docker/data_v2/` minus
`ground_truth.json` and the generator scripts — i.e. it's what participants
actually receive.

## 3. The dataset (`data_v2`, "realistic" v2)

Grounded in real APRIL SDOC samples (Outlook `.msg` emails + SI/BL PDF/DOCX/XLSX
pairs): real carriers, ports, customers, coded subject lines, forwarded threads,
signatures, multi-format attachments.

**Email record schema** (`inbox/email_XXX.json`):
```json
{
  "email_id": "email_004",
  "from": "docs@vitalsolutions.sg",
  "subject": "REQUEST BL DRAFT _ PO 26067_ COATED IVORY BOARD__138MT",
  "body": "Hi Mitchelle, ...",
  "attachments": ["attachments/email_004_SI.txt", "attachments/email_004_BL.txt"]
}
```
No labels in the inbox record — labels live only in `ground_truth.json`.

**Ground-truth schema** (`data_v2/ground_truth.json`, private):
```json
{
  "category": "BL_COMPARISON",
  "status": "MISMATCH",          // OK | MISMATCH | NEEDS_REVIEW
  "review_reason": null,         // null, or a review reason (see below)
  "defect_fields": ["consignee"],
  "has_defect": true
}
```
`status` is orthogonal to `has_defect`:

| status | meaning | has_defect | defect_fields | review_reason |
|---|---|---|---|---|
| `OK` | compared cleanly, everything matches | false | `[]` | null |
| `MISMATCH` | compared cleanly, ≥1 field differs | true | the fields | null |
| `NEEDS_REVIEW` | could not be compared confidently → escalate | false | `[]` | one of below |

A blank field or unreadable scan is **not** a mismatch — it's genuine
uncertainty, tracked on a separate axis from false alarms.

### Categories & mix (main set, n = 500)
| Category | Count | Real-inbox signals |
|---|---|---|
| `BL_COMPARISON` | 200 | `TO CONFIRM DOCS`, `REQUEST BL DRAFT`, coded `AIE-POD-CARRIER(BL#)-OC-INV-CUSTOMER-TERM`, `Draft BL … amend` |
| `SI_REQUEST` | 125 | `SI - <bl> - DIRECT(<carrier>) - <OC> - <POD> - <BLtype>`, `CUST SI`, `REQUEST SI`, `SI NEEDED` |
| `INVOICE_QUERY` | 75 | `BILLING … MISSING GR`, `CANCEL INVOICE`, `LOCAL CHARGES`, `D & D charges`, `Total Freight` |
| `GENERAL` | 60 | `UPDATE SUMMARY`, `Berthing Report`, SLA reminders, `_RPA_` bot notices, HR/holiday |
| `SPAM` | 40 | prize/parcel-fee/mailbox-full/phishing |

### Attachments
- Only `BL_COMPARISON` emails carry attachments, and only ~55% of them
  (`BL_WITH_ATTACH`) — rest are "please send the draft BL" with nothing to
  compare yet (classify-but-can't-compare case).
- ~109 SI+BL pairs total. ~22% are real binary formats; rest are `.txt`:
  - `pdf + pdf` — mirrors real sample `5680009008` (BDP/MSC layout, container table)
  - `xlsx + docx` — mirrors `3751010806` (excel SI, bilingual word BL)
  - `xlsx + xlsx` — mirrors `3751011338`
- **Label synonymy is deliberate** across SI/BL renderings (see §1).

### Defects
The generator builds one canonical shipment (truth), renders the SI from it,
then renders the BL either faithfully or with 1–2 injected field mismatches —
so ground truth can never drift from the documents.
- ~50% of attachment-bearing pairs have ≥1 defect (`DEFECT_RATE`).
- Injected values are plausible (a real other port, ±1 container, ±500–2000 kg).
- Non-comparison categories / no-attachment emails: always `defect_fields: []`,
  `has_defect: false`, `status: OK`.

### Edge cases (20, `email_501`–`email_520`)
Appended after the main 500 (doesn't skew the base distribution). All classify
as `BL_COMPARISON` but should resolve `NEEDS_REVIEW`. Five of each reason:

| review_reason | what's wrong | how it's built |
|---|---|---|
| `wrong_doc_type` | "BL" is actually a Commercial Invoice / Packing List / Certificate of Origin | SI normal; 2nd attachment is a different doc type |
| `missing_attachment` | 0 attachments (3 cases) or SI-only (2 cases) | no BL to compare against |
| `unreadable` | image-only scanned PDF (no text layer), 0-byte empty file, or truncated/garbled PDF | `write_image_only_pdf` / `write_empty_file` / `write_garbled_pdf` |
| `missing_value` | SI has blank required fields (`???`, `_______`, `TBA`) vs a complete BL | a blank is uncertainty, not a discrepancy |

These implement the spec's "Messier inputs" and "Reliability and human review"
extensions.

### Regenerating the dataset
```bash
cd sdoc-docker/data_v2
pip3 install openpyxl python-docx reportlab
python3 generate.py --seed 42 --n 500 --out .
```
Deterministic per seed.

## 4. Accessing the data

### Option A — static bundle (`sdoc-bundle/`, already unzipped here)
No service needed — read `inbox/*.json` and `attachments/*` directly, or use
`loader.py`.

### Option B — Docker server (`sdoc-docker/`)
```bash
cd sdoc-docker
docker compose up --build      # serves on http://localhost:8080
```
`data_v2/` mounted read-only at `/data`; `ground_truth.json` mounted
**separately and privately** at `/secrets` — never in the served tree, never
returned by any public endpoint.

**Endpoints:**
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + email count |
| GET | `/emails` | all email records (no labels) |
| GET | `/emails/{id}` | one email |
| GET | `/attachments/{path}` | download an SI/BL file |
| GET | `/sample_submission` | required output shape |
| POST | `/submit` | score a submission → scoreboard JSON |
| GET | `/ground_truth` | 404 unless `REVEAL_GT=1` (judge-only, `X-Judge-Token` header) |

Change port by editing `ports:` in `docker-compose.yml` (default `8080:8000`).

### The loader (same interface for both options)
```python
from loader import Inbox
inbox = Inbox("data")                      # or Inbox("http://localhost:8080")
for email in inbox: ...                    # each email record
inbox.read_text(path)                      # text of an SI/BL attachment
inbox.submit(submission_dict)              # POST /submit via the loader
```
Start with one email + its two attachments to see how records connect.

## 5. Submission format & scoring

**Submission** = one JSON object keyed by `email_id`, covering **every** email
in the dataset:
```json
{ "email_001": {
    "category": "BL_COMPARISON",
    "status": "MISMATCH",
    "review_reason": null,
    "has_defect": true,
    "defect_fields": ["consignee"]
} }
```
Shape mirrors `sample_submission.json` / the ground-truth schema.

**Scoring model:**
```
final_score = 0.30 · stage1_macroF1 (classification)
            + 0.20 · stage3_defectF1 (defect detection)
            + 0.50 · end_to_end (defects routed AND flagged with exact fields — the headline metric)
```
The 20 `NEEDS_REVIEW` edge cases are graded on a **separate** diagnostic axis
(escalation precision/recall) so they don't distort the core leaderboard unless
you choose to weight them in.

**Scoring tools:**
```bash
# offline, against the private data_v2/ground_truth.json
python3 sdoc-docker/server/score_cli.py path/to/submission.json
python3 sdoc-docker/server/score_cli.py submission.json --json   # machine-readable

# online, via the running docker server (no labels ever returned)
curl -s -X POST localhost:8080/submit \
  -H 'Content-Type: application/json' \
  --data-binary @submission.json | python3 -m json.tool
```

**Using the scoreboard while building:**
- It's a diagnostic, not the final assessment — doesn't judge whether human
  review was invoked at the right time or with useful context.
- Check where classification was wrong or a mismatch was missed.
- Review incomplete/uncertain cases separately from accuracy.
- If your result differs from the reference, check the source documents before
  "fixing" your answer — a reasonable disagreement is fine if you record why.

## 6. Practical build notes / gotchas

- Only `BL_COMPARISON` emails ever need extraction + comparison; every other
  category just needs correct classification.
- ~45% of `BL_COMPARISON` emails have **no attachments at all** — still needs
  correct classification, but nothing to compare (`has_defect: false`,
  `status: OK`, empty `defect_fields`).
- Field label synonymy is intentional test material — build a
  canonical-field-name mapping (aliases → canonical), don't hardcode exact
  label strings.
- `NEEDS_REVIEW` is a distinct outcome from both `OK` and `MISMATCH` — a blank
  field or unreadable doc must **not** be reported as a mismatch; escalate with
  a `review_reason` instead. Guessing on unreadable/missing input actively hurts
  the end-to-end score and the reliability axis.
- Real binary attachments (`pdf+pdf`, `xlsx+docx`, `xlsx+xlsx`) require actual
  table/layout-aware extraction (`pdftotext`, `python-docx`, `openpyxl`), not
  naive text reads — this is the "advanced stage" hook.
- Ground truth (`data_v2/ground_truth.json`) is never to be shipped to
  participants or peeked at while building "honestly" — use `score_cli.py` /
  `POST /submit` instead, mirroring how a real participant would validate.
