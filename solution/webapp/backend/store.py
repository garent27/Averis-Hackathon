#!/usr/bin/env python3
"""
store.py — persist the report/review state to a JSON file so review
decisions survive a restart. Basic file-based store (no SQLite) since a
single JSON blob is plenty for a hackathon-sized dataset (520 rows).
"""
import json
import threading
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "state.json"
_lock = threading.Lock()


def load() -> dict:
    if not DATA_PATH.exists():
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save(state: dict) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
