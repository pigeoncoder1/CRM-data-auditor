# CRM Data Health Auditor

A small FastAPI backend that audits `messy_crm_dataset.csv` for missing,
invalid and inconsistently formatted contact data.

## Run it

```bash
pip install -r requirements.txt
uvicorn crm_auditor.main:app --reload
```

Then open http://127.0.0.1:8000/audit (or http://127.0.0.1:8000/docs).

To audit a different file, set `CRM_CSV_PATH=/path/to/file.csv`.

Sanity check against the real dataset (no server needed):

```bash
python test_audit.py
```

## Layout

| File | Responsibility |
|---|---|
| `crm_auditor/loader.py` | Reads the CSV into dicts. Empty cells become `null`; nothing else is changed. |
| `crm_auditor/validation.py` | Per-field rules (missing / invalid / format), date and phone normalization. |
| `crm_auditor/scoring.py` | Per-record completeness, per-field summary, overall score. |
| `crm_auditor/main.py` | FastAPI app; `audit_contacts()` ties the steps together. |

Dataset-level checks such as duplicate detection (step 3) should go in a new
module, called from the marked spot in `audit_contacts()`.

## What `GET /audit` returns

```jsonc
{
  "record_count": 70,
  "records_with_issues": 68,
  "overall_score": 93.0,           // mean of per-record completeness scores
  "field_summary": {
    "industry": { "missing": 19, "invalid": 0, "missing_or_invalid": 19, "pct_missing_or_invalid": 27.1 },
    // ... email, phone, job_title, date_added
  },
  "records": [
    {
      // original CSV fields, unchanged ...
      "date_added": "8-03-2024",
      "date_added_normalized": "2024-03-08",   // ISO, or null if unparseable
      "date_added_format": "DD-MM-YYYY",       // which known format was detected
      "phone_normalized": "+44710033092",      // E.164, or null if missing/invalid
      "issues": ["inconsistent_phone_format", "missing_job_title", "inconsistent_date_format"],
      "completeness_score": 90.0
    }
  ]
}
```

### Issue codes

- `missing_<field>`: the field is empty (full_name, email, phone, company, job_title, date_added, industry)
- `invalid_email_format`: the email doesn't have the structure of a valid address
- `invalid_phone_format`: the phone doesn't match a known format or has an implausible length
- `unparseable_date`: the date doesn't match any of the 4 known formats, or isn't a real date (e.g. `02/30/2024`)
- `inconsistent_date_format`: a valid date that isn't in the canonical `YYYY-MM-DD` format
- `inconsistent_phone_format`: a valid phone that isn't in the canonical `+44 ...` international format

### Scoring

- **Record `completeness_score`**: the weighted % of expected fields that are
  present *and* valid. Required fields (full_name, email, company) have
  weight 2; optional fields (phone, job_title, industry, date_added) have
  weight 1. Format inconsistencies are listed in `issues` but don't lower
  the score.
- **`overall_score`**: the mean of the record scores. The reasoning is in
  `scoring.py`.
