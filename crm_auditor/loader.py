import csv
from pathlib import Path

EXPECTED_COLUMNS = [
    "contact_id",
    "full_name",
    "email",
    "phone",
    "company",
    "job_title",
    "date_added",
    "industry",
]

Row = dict[str, str | None]


def load_contacts(path: str | Path) -> list[Row]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(EXPECTED_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing expected columns: {sorted(missing)}")

        return [
            {col: (row.get(col) if row.get(col) != "" else None) for col in EXPECTED_COLUMNS}
            for row in reader
        ]
