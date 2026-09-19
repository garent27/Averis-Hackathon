#!/usr/bin/env python3
"""
classify.py — baseline pipeline: fetch every email from the running Docker
server, classify it, write submission.json, and self-score it.

Right now classify_email() is a stub that defaults everything to GENERAL/OK.
The point of running this first is to prove the plumbing works end-to-end
(fetch -> build submission -> submit -> get a score) BEFORE writing real
classification logic. Once this runs cleanly, replace classify_email() with
real rules/model and re-run.

Usage:
    python classify.py
"""
import json

from loader import Inbox

SERVER = "http://localhost:8080"
OUTPUT_PATH = "submission.json"


SPAM_KEYWORDS = [
    "YOU HAVE WON", "CLAIM YOUR PRIZE", "LOTTERY", "PARCEL FEE",
    "MAILBOX FULL", "VERIFY YOUR ACCOUNT", "CONGRATULATIONS", "INHERITANCE",
]

BL_COMPARISON_KEYWORDS = [
    "TO CONFIRM DOCS", "REQUEST BL DRAFT", "DRAFT BL", "AMEND BL", "BL DRAFT",
]

SI_REQUEST_KEYWORDS = [
    "REQUEST SI", "SI NEEDED", "CUST SI", "SI -",
]

INVOICE_QUERY_KEYWORDS = [
    "MISSING GR", "CANCEL INVOICE", "LOCAL CHARGES", "D & D CHARGES",
    "TOTAL FREIGHT", "BILLING", "INVOICE",
]


def classify_email(email: dict) -> str:
    """Return one of: BL_COMPARISON, SI_REQUEST, INVOICE_QUERY, GENERAL, SPAM.

    Very basic keyword matching on the subject line, using the real-inbox
    signal words documented in data_v2/README.md. Checked in order from most
    distinctive/risky (SPAM) to the catch-all default (GENERAL).
    """
    subject = email["subject"].upper()

    if any(kw in subject for kw in SPAM_KEYWORDS):
        return "SPAM"
    if any(kw in subject for kw in BL_COMPARISON_KEYWORDS):
        return "BL_COMPARISON"
    if any(kw in subject for kw in SI_REQUEST_KEYWORDS):
        return "SI_REQUEST"
    if any(kw in subject for kw in INVOICE_QUERY_KEYWORDS):
        return "INVOICE_QUERY"
    return "GENERAL"


def build_result(email: dict) -> dict:
    """Build the per-email result in the shape score_cli.py / /submit expects.

    Only BL_COMPARISON emails ever get real status/defect_fields — everything
    else defaults to OK / no defects (see HACKATHON_CONTEXT.md section 5).
    """
    category = classify_email(email)

    result = {
        "category": category,
        "status": "OK",
        "review_reason": None,
        "defect_fields": [],
        "has_defect": False,
    }

    # TODO once classify_email() is real: for BL_COMPARISON emails with
    # attachments, extract the 7 fields from SI + BL, compare them, and set
    # status/has_defect/defect_fields/review_reason based on the result.

    return result


def main():
    inbox = Inbox(SERVER)
    emails = inbox.emails()
    print(f"fetched {len(emails)} emails from {SERVER}")


    submission = {email["email_id"]: build_result(email) for email in emails}

    with open(OUTPUT_PATH, "w") as f:
        json.dump(submission, f, indent=2)
    print(f"wrote {OUTPUT_PATH} ({len(submission)} entries)")

    print("submitting for self-score...")
    scoreboard = inbox.submit(submission)
    print(json.dumps(scoreboard, indent=2))


if __name__ == "__main__":
    main()
