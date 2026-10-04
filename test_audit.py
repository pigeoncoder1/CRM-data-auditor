from collections import Counter

from fastapi.testclient import TestClient

from crm_auditor.main import app


def test_audit_finds_issues():
    resp = TestClient(app).get("/audit")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    print(f"\nRecords:            {data['record_count']}")
    print(f"Records w/ issues:  {data['records_with_issues']}")
    print(f"Overall score:      {data['overall_score']}")

    print("\nField summary (missing / invalid / % of rows):")
    for field, s in data["field_summary"].items():
        print(f"  {field:<11} {s['missing']:>3} missing  {s['invalid']:>3} invalid"
              f"  {s['pct_missing_or_invalid']:>5}%")

    counts = Counter(i for r in data["records"] for i in r["issues"])
    print("\nIssue counts:")
    for issue, n in counts.most_common():
        print(f"  {issue:<28} {n}")

    assert data["record_count"] == 70
    assert data["overall_score"] < 95, "suspiciously clean: check the validation logic"
    assert data["records_with_issues"] > data["record_count"] / 2
    assert counts["unparseable_date"] == 6, "v2 has 6 junk/impossible dates"
    assert all(r["date_added_normalized"] for r in data["records"]
               if "unparseable_date" not in r["issues"])


if __name__ == "__main__":
    test_audit_finds_issues()
