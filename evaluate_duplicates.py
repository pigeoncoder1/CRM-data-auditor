"""

    python evaluate_duplicates.py [path/to/ground_truth.md]

"""

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from crm_auditor.duplicates import BANDS, MIN_SCORE, band_for, normalize_record, score_pair
from crm_auditor.main import app, load_rows

Pair = frozenset[int]


def parse_ground_truth(path: Path) -> dict[Pair, str]:
    planted: dict[Pair, str] = {}
    header: list[str] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if header is None:
            header = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells): 
            continue

        def col(*words: str) -> int | None:
            return next((i for i, h in enumerate(header) if any(w in h for w in words)), None)

        id_cols = [col("orig"), col("dup")]
        if None in id_cols:
            id_cols = [i for i, c in enumerate(cells) if re.fullmatch(r"\D{0,2}\d+", c)][:2]
        ids = [int(re.search(r"\d+", cells[i]).group()) for i in id_cols]
        mess_col = col("type", "mess", "kind")
        planted[frozenset(ids)] = cells[mess_col] if mess_col is not None else ""
    return planted


def print_breakdown(score: float, signals: dict) -> None:
    print(f"      score {score}  band {band_for(score) or 'below threshold'}")
    for name, s in signals.items():
        sim = "  -  " if s["similarity"] is None else f"{s['similarity']:5.1f}"
        flag = "FIRED" if s["fired"] else "     "
        note = f"  ({s['note']})" if "note" in s else ""
        print(f"      {name:<13} sim {sim}  {s['points']:>4}/{s['max_points']:<3} {flag}  {s['values']}{note}")


def main() -> None:
    gt_path = Path(sys.argv[1] if len(sys.argv) > 1 else "ground_truth.md")
    if not gt_path.exists():
        sys.exit(f"Ground truth not found: {gt_path}")
    planted = parse_ground_truth(gt_path)

    resp = TestClient(app).get("/duplicates", params={"min_score": MIN_SCORE})
    resp.raise_for_status()
    found = {frozenset({int(p["record_a"]["contact_id"]), int(p["record_b"]["contact_id"])}): p
             for p in resp.json()["pairs"]}

    print(f"Planted pairs: {len(planted)}   Pairs returned (score >= {MIN_SCORE}): {len(found)}\n")
    print(f"{'threshold':<18} {'flagged':>7} {'TP':>4} {'FP':>4} {'precision':>10} {'recall':>8}")
    for band, floor in BANDS:
        flagged = {pair for pair, p in found.items() if p["score"] >= floor}
        tp = len(flagged & planted.keys())
        precision = tp / len(flagged) if flagged else 0.0
        recall = tp / len(planted) if planted else 0.0
        print(f"{band + ' (>= ' + str(floor) + ')':<18} {len(flagged):>7} {tp:>4} {len(flagged) - tp:>4}"
              f" {precision:>10.0%} {recall:>8.0%}")


    contacts = {int(row["contact_id"]): normalize_record(row) for row in load_rows()}
    high_floor = BANDS[0][1]
    missed = [pair for pair in planted if pair not in found or found[pair]["score"] < high_floor]
    print(f"\nMISSED (planted, not in high band): {len(missed)}")
    for pair in sorted(missed, key=sorted):
        a_id, b_id = sorted(pair)
        if a_id not in contacts or b_id not in contacts:
            print(f"  {a_id}-{b_id}  [{planted[pair]}]  contact_id not in dataset")
            continue
        a, b = contacts[a_id], contacts[b_id]
        print(f"  {a_id}-{b_id}  [{planted[pair]}]  {a.row['full_name']} | {b.row['full_name']}")
        print_breakdown(*score_pair(a, b))

    false_pos = [p for pair, p in found.items() if p["band"] == "high" and pair not in planted]
    print(f"\nFALSE POSITIVES (high band, not planted): {len(false_pos)}")
    for p in false_pos:
        a, b = p["record_a"], p["record_b"]
        print(f"  {a['contact_id']}-{b['contact_id']}  {a['full_name']} | {b['full_name']}")
        print_breakdown(p["score"], p["signals"])


if __name__ == "__main__":
    main()
