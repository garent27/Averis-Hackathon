# SDOC Review App

A minimal React + FastAPI app on top of the `solution/` pipeline
(`loader.py`, `classify.py`, `extract_compare.py`, `llm.py`): it runs the
classifier/extractor over the inbox, shows the results, and lets a human
review and fix the cases the pipeline couldn't resolve on its own.

No styling, no auth, no routing library — just enough to exercise the
pipeline through a UI instead of `submission.json`.

## Prerequisites

- The SDOC Docker inbox server running at `http://localhost:8080`
  (`docker compose up --build` from `sdoc-docker/`).
- Python deps from `solution/` already installed (`anthropic`/`google-genai`
  not required to *run* the app, only to exercise the LLM fallback tier).
- Node.js + npm.

## Running it

**Backend** (from `solution/webapp/backend/`):

```bash
python -m uvicorn main:app --reload --port 8001
```

On first startup (empty `data/state.json`), it automatically runs the full
pipeline over every email in the inbox and saves the result — this can take
a little while and will print `LLM text/vision fallback failed` lines to the
console if the Gemini free-tier rate limit is hit; those are non-fatal, the
affected rows just fall back to whatever the deterministic tier found (see
`solution/extract_compare.py`).

**Frontend** (from `solution/webapp/frontend/`):

```bash
npm install   # first time only
npm run dev
```

Then open **http://localhost:5173**. The frontend talks to the backend at
`http://localhost:8001` (hardcoded in `src/api.js`).

## What the backend does

`solution/webapp/backend/`:

| File | Role |
|---|---|
| `pipeline.py` | Imports `loader.py`/`classify.py`/`extract_compare.py` from `solution/` directly (no duplicated logic). `process_email()` classifies one email and, for `BL_COMPARISON` emails with attachments, extracts and compares SI vs BL — keeping the actual field *values*, not just which fields mismatched, so the UI can show them side by side. |
| `store.py` | Persists the full per-email result set as one JSON blob (`data/state.json`), so review decisions and retries survive a server restart. |
| `main.py` | The FastAPI app. |

**Endpoints:**

| Method | Path | What it does |
|---|---|---|
| GET | `/api/report` | All 520 rows, for the Report view. |
| GET | `/api/review` | Only rows with `status` = `NEEDS_REVIEW` or `FAILED` that haven't been resolved yet — the Review Queue. |
| POST | `/api/review/{email_id}` | Save human-edited SI/BL field values (+ an optional note). Re-runs the normalizer + comparator on the edited values, updates `status`/`has_defect`/`defect_fields` accordingly, and marks the row `reviewed`. |
| POST | `/api/retry/{email_id}` | Re-runs classification + extraction for one email from scratch (fresh fetch + fresh LLM fallback call if needed) — for transient failures like a rate-limited API call. |
| POST | `/api/rebuild` | Re-runs the pipeline for *every* email and overwrites the saved state — a hard reset. |

A row's possible `status` values: `OK` (compared clean), `MISMATCH` (≥1
field differs), `NEEDS_REVIEW` (missing attachment or missing field value —
couldn't compare confidently), `FAILED` (an exception during fetch/extract,
e.g. a corrupt attachment).

## What the frontend shows

`solution/webapp/frontend/src/`:

- **`ReportView.jsx`** — one table row per email: `email_id`, `category`,
  `status`, `has_defect`, and (when there's a mismatch) the flagged fields
  with their SI and BL values side by side. Rows with `status = FAILED` get
  a **Retry** button inline.
- **`ReviewQueue.jsx`** — one card per email that needs a human: the reason
  (`review_reason` or the extraction `error`), the subject/sender and
  attachment filenames as evidence, and an **editable table** of all 7
  fields for SI and BL. **Save** submits the edited values to
  `POST /api/review/{id}` (which re-runs the comparator); **Retry
  extraction** calls `POST /api/retry/{id}` instead, for when the fix is
  "just try again" rather than "a human needs to type in the value."
- **`App.jsx`** — two buttons switch between the two views above; no router.

## Persistence

Everything lives in `solution/webapp/backend/data/state.json` — a single
JSON object keyed by `email_id`. It's gitignored (generated/mutable data,
like a local dev database) and gets created automatically on first run.
Delete it and restart the backend to force a full rebuild, or call
`POST /api/rebuild` without deleting anything.
