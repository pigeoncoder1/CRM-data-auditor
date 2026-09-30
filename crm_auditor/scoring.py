from statistics import mean

from .validation import INVALID, MISSING, FieldCheck


REQUIRED_FIELDS = ("full_name", "email", "company")
OPTIONAL_FIELDS = ("phone", "job_title", "industry", "date_added")
REQUIRED_WEIGHT = 2
OPTIONAL_WEIGHT = 1

FIELD_WEIGHTS = {
    **{f: REQUIRED_WEIGHT for f in REQUIRED_FIELDS},
    **{f: OPTIONAL_WEIGHT for f in OPTIONAL_FIELDS},
}

SUMMARY_FIELDS = ("email", "phone", "job_title", "industry", "date_added")


def completeness_score(checks: dict[str, FieldCheck]) -> float:
    total = sum(FIELD_WEIGHTS.values())
    earned = sum(w for f, w in FIELD_WEIGHTS.items() if checks[f].is_valid)
    return round(100 * earned / total, 1)


def field_summary(all_checks: list[dict[str, FieldCheck]]) -> dict[str, dict]:
    n = len(all_checks)
    summary = {}
    for f in SUMMARY_FIELDS:
        missing = sum(1 for c in all_checks if c[f].status == MISSING)
        invalid = sum(1 for c in all_checks if c[f].status == INVALID)
        problems = missing + invalid
        summary[f] = {
            "missing": missing,
            "invalid": invalid,
            "missing_or_invalid": problems,
            "pct_missing_or_invalid": round(100 * problems / n, 1) if n else 0.0,
        }
    return summary


def overall_score(record_scores: list[float]) -> float:
    return round(mean(record_scores), 1) if record_scores else 0.0
