"""
uvicorn crm_auditor.main:app --reload
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .loader import Row, load_contacts
from .scoring import completeness_score, field_summary, overall_score
from .validation import FieldCheck, validate_record

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "messy_crm_dataset.csv"
CSV_PATH = Path(os.environ.get("CRM_CSV_PATH", DEFAULT_CSV))

app = FastAPI(title="CRM Data Health Auditor")


def build_record(row: Row, checks: dict[str, FieldCheck]) -> dict:
    return {
        **row,
        "date_added_normalized": checks["date_added"].normalized,
        "date_added_format": checks["date_added"].detail,
        "phone_normalized": checks["phone"].normalized,
        "issues": [issue for check in checks.values() for issue in check.issues],
        "completeness_score": completeness_score(checks),
    }


def audit_contacts(rows: list[Row]) -> dict:
    all_checks = [validate_record(row) for row in rows]
    records = [build_record(row, checks) for row, checks in zip(rows, all_checks)]
    return {
        "record_count": len(records),
        "records_with_issues": sum(1 for r in records if r["issues"]),
        "overall_score": overall_score([r["completeness_score"] for r in records]),
        "field_summary": field_summary(all_checks),
        "records": records,
    }


@app.get("/audit")
def audit() -> dict:
    try:
        rows = load_contacts(CSV_PATH)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"CSV not found: {CSV_PATH}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return audit_contacts(rows)
