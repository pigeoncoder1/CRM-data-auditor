import re
from dataclasses import dataclass, field
from datetime import datetime

OK, MISSING, INVALID = "ok", "missing", "invalid"


@dataclass
class FieldCheck:
    status: str
    issues: list[str] = field(default_factory=list)
    normalized: str | None = None
    detail: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status == OK


def _blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


_EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)[A-Za-z0-9._%+'-]+(?<!\.)"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}$"
)


def validate_email(value: str | None) -> FieldCheck:
    if _blank(value):
        return FieldCheck(MISSING, ["missing_email"])
    email = value.strip()
    local, _, _ = email.partition("@")
    if len(email) > 254 or len(local) > 64 or not _EMAIL_RE.match(email):
        return FieldCheck(INVALID, ["invalid_email_format"])
    return FieldCheck(OK, normalized=email.lower())



_PHONE_FORMATS = [
    ("international", re.compile(r"^\+\d{1,3}(?:[ -]?\d+)+$")),     # +44 746 584 044
    ("parenthesized", re.compile(r"^\(0\d+\) ?\d+(?:[ -]?\d+)*$")),  # (0480) 831-3678
    ("plain_national", re.compile(r"^0\d+$")),                       # 0710033092
]
CANONICAL_PHONE_FORMAT = "international"
DEFAULT_COUNTRY_CODE = "44"


def validate_phone(value: str | None) -> FieldCheck:
    if _blank(value):
        return FieldCheck(MISSING, ["missing_phone"])
    raw = value.strip()
    fmt = next((name for name, rx in _PHONE_FORMATS if rx.match(raw)), None)
    if fmt is None:
        return FieldCheck(INVALID, ["invalid_phone_format"])

    digits = re.sub(r"\D", "", raw)
    if fmt != "international":
        digits = DEFAULT_COUNTRY_CODE + digits[1:] 

    if not 8 <= len(digits) <= 15:
        return FieldCheck(INVALID, ["invalid_phone_format"], detail=fmt)

    issues = [] if fmt == CANONICAL_PHONE_FORMAT else ["inconsistent_phone_format"]
    return FieldCheck(OK, issues, normalized="+" + digits, detail=fmt)


_DATE_FORMATS = [
    ("YYYY-MM-DD", re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"), "%Y-%m-%d"),
    ("MM/DD/YYYY", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"), "%m/%d/%Y"),
    ("D Mon YYYY", re.compile(r"^\d{1,2} [A-Za-z]{3} \d{4}$"), "%d %b %Y"),
    ("DD-MM-YYYY", re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"), "%d-%m-%Y"),
]
CANONICAL_DATE_FORMAT = "YYYY-MM-DD"


def validate_date(value: str | None) -> FieldCheck:
    if _blank(value):
        return FieldCheck(MISSING, ["missing_date_added"])
    raw = value.strip()
    for name, shape, strp in _DATE_FORMATS:
        if shape.match(raw):
            try:
                parsed = datetime.strptime(raw, strp).date()
            except ValueError:
                return FieldCheck(INVALID, ["unparseable_date"], detail=name)
            issues = [] if name == CANONICAL_DATE_FORMAT else ["inconsistent_date_format"]
            return FieldCheck(OK, issues, normalized=parsed.isoformat(), detail=name)
    return FieldCheck(INVALID, ["unparseable_date"])


def presence_validator(field_name: str):
    """Build a validator for a free-text field that only needs to be present."""
    def check(value: str | None) -> FieldCheck:
        if _blank(value):
            return FieldCheck(MISSING, [f"missing_{field_name}"])
        return FieldCheck(OK)
    return check

VALIDATORS = {
    "full_name": presence_validator("full_name"),
    "email": validate_email,
    "phone": validate_phone,
    "company": presence_validator("company"),
    "job_title": presence_validator("job_title"),
    "date_added": validate_date,
    "industry": presence_validator("industry"),
}


def validate_record(row: dict[str, str | None]) -> dict[str, FieldCheck]:
    """Run every field validator on a row and return {field: FieldCheck}."""
    return {name: rule(row.get(name)) for name, rule in VALIDATORS.items()}
