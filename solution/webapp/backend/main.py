#!/usr/bin/env python3
"""
main.py — FastAPI backend for the review app.

Endpoints:
  GET  /api/report          all rows (Report view)
  GET  /api/review          rows needing review, not yet resolved (Review Queue view)
  POST /api/review/{id}     save edited SI/BL values + note -> re-run comparator, mark reviewed
  POST /api/retry/{id}      re-run extraction for one email (Retry button)
  POST /api/rebuild         re-run the pipeline for every email (fresh start)

Run with: uvicorn main:app --reload --port 8001
"""
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import pipeline
import store

app = FastAPI(title="SDOC Review App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    if not store.load():
        state = pipeline.build_all()
        store.save(state)


@app.get("/api/report")
def get_report():
    return list(store.load().values())


@app.get("/api/review")
def get_review_queue():
    state = store.load()
    return [row for row in state.values() if row["status"] in ("NEEDS_REVIEW", "FAILED") and not row["reviewed"]]


class ReviewSave(BaseModel):
    si_values: Dict[str, Optional[str]] = {}
    bl_values: Dict[str, Optional[str]] = {}
    note: Optional[str] = None


@app.post("/api/review/{email_id}")
def save_review(email_id: str, body: ReviewSave):
    state = store.load()
    row = state.get(email_id)
    if row is None:
        raise HTTPException(404, f"unknown email_id: {email_id}")

    si_norm = pipeline.normalize_values(body.si_values)
    bl_norm = pipeline.normalize_values(body.bl_values)
    row["si_values"] = si_norm
    row["bl_values"] = bl_norm
    row["note"] = body.note
    row["error"] = None

    missing = [f for f in pipeline.COMPARE_FIELDS if f not in si_norm or f not in bl_norm]
    if missing:
        row["status"] = "NEEDS_REVIEW"
        row["review_reason"] = "missing_value"
        row["has_defect"] = False
        row["defect_fields"] = []
    else:
        defect_fields = pipeline.compare_fields(si_norm, bl_norm)
        row["review_reason"] = None
        if defect_fields:
            row["status"] = "MISMATCH"
            row["has_defect"] = True
            row["defect_fields"] = defect_fields
        else:
            row["status"] = "OK"
            row["has_defect"] = False
            row["defect_fields"] = []

    row["reviewed"] = True
    state[email_id] = row
    store.save(state)
    return row


@app.post("/api/retry/{email_id}")
def retry(email_id: str):
    state = store.load()
    if email_id not in state:
        raise HTTPException(404, f"unknown email_id: {email_id}")
    try:
        row = pipeline.retry_one(email_id)
    except Exception as e:
        raise HTTPException(500, f"retry failed: {e}")
    row["reviewed"] = False
    state[email_id] = row
    store.save(state)
    return row


@app.post("/api/rebuild")
def rebuild():
    state = pipeline.build_all()
    store.save(state)
    return {"count": len(state)}
