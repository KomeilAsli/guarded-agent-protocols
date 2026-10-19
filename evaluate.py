"""Run all scenarios, print a results table and save it to results/.

    python evaluate.py

Writes results/results.csv, results/results.md and results/blocked_events.jsonl.
Exits with code 1 if any scenario (other than a known limitation) is not as expected.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from gap.scenarios import Result, run_all  # noqa: E402

COLUMNS = ["Scenario", "Type", "Expected", "Actual", "Blocked/allowed", "Reason", "As expected"]


def row(r: Result) -> list[str]:
    status = "yes" if r.as_expected else ("no (known limitation)" if r.known_limitation else "NO")
    return [r.name, r.type, r.expected, r.actual, r.decision, r.reason, status]


def to_markdown(rows: list[list[str]]) -> str:
    def cell(v: str) -> str:
        return v.replace("|", "\\|")
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def summary(results: list[Result]) -> str:
    ok = sum(r.as_expected for r in results)
    known = sum(r.known_limitation and not r.as_expected for r in results)
    return f"{ok} of {len(results)} scenarios as expected; {known} known limitation(s) shown as 'no'."


def main() -> int:
    results = run_all()
    rows = [row(r) for r in results]
    out = ROOT / "results"
    out.mkdir(exist_ok=True)

    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)

    md = to_markdown(rows)
    (out / "results.md").write_text(f"# Results\n\n{md}\n\n{summary(results)}\n", encoding="utf-8")

    with open(out / "blocked_events.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            for ev in r.blocked_events:
                f.write(json.dumps(ev) + "\n")

    print(md)
    print("\n" + summary(results))
    print(f"Saved to {out.relative_to(ROOT)}/")
    unexpected = [r.name for r in results if not r.as_expected and not r.known_limitation]
    if unexpected:
        print("Unexpected results:", ", ".join(unexpected))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
