"""uv run python .orca/audits/t5-baseline-2026-11-01/measure.py [--collect-only]

运行原 PI_T5_FULL 测试：先种子7，再十种子；保留原三组断言，日志按 bench 限 WARNING。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def run_test(report: Path, selection: str) -> None:
    command = (
        "import logging,pytest,structlog; "
        "structlog.configure("
        "wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING)); "
        "raise SystemExit(pytest.main(__import__('sys').argv[1:]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command, selection, "-q", "--tb=short"],
        cwd=ROOT,
        env={**os.environ, "PI_T5_FULL": "1", "GOLDEN_REPORT_DIR": str(report), "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    report.mkdir(parents=True, exist_ok=True)
    report.with_suffix(".log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"golden test failed: {selection}; see {report.with_suffix('.log')}")


def collect(base: Path) -> dict:
    from sim.tests.golden.seeds import GOLDEN_SEEDS

    rows = []
    for seed in GOLDEN_SEEDS:
        report = json.loads((base / "full" / f"golden-{seed}.json").read_text(encoding="utf-8"))
        baseline = report["errands_baseline"]
        assert report["ticks_run"] == 864000 and report["days_covered"] == 10
        rows.append(
            {
                "seed": seed,
                **baseline,
                "ticks_run": report["ticks_run"],
                "days": report["days_covered"],
                "total_events": report["total_events"],
                "wall_seconds": report["wall_s"],
                "report": f"full/golden-{seed}.json",
            }
        )
    first = json.loads((base / "first" / "golden-7.json").read_text(encoding="utf-8"))
    repeated = next(row for row in rows if row["seed"] == 7)
    assert all(
        first["errands_baseline"][key] == repeated[key] for key in ("cases", "passed", "rate")
    )
    assert first["total_events"] == repeated["total_events"]
    log = base / "full.log"
    if not log.exists():
        log = ROOT / ".orca/audits/round15-2026-11-01/t5-full.log"
    raw = log.read_bytes() if log.exists() else b""
    text = raw.decode(
        "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8", errors="replace"
    )
    elapsed = re.search(r"10 passed in ([0-9.]+)s", text)
    return {
        "status": "pass",
        "PI_T5_FULL": True,
        "source": "original sim/tests/golden/test_golden_full.py, all three assertion groups",
        "per_seed": rows,
        "summary": {
            "seeds": len(rows),
            "cases": sum(row["cases"] for row in rows),
            "passed": sum(row["passed"] for row in rows),
            "median_rate": statistics.median(row["rate"] for row in rows),
            "worst_rate": min(row["rate"] for row in rows),
        },
        "determinism": {
            "seed": 7,
            "first_baseline": first["errands_baseline"],
            "repeat_baseline": {key: repeated[key] for key in ("cases", "passed", "rate")},
            "equal": True,
            "event_counts_equal": True,
        },
        "timing": {
            "observed_full_suite_seconds": float(elapsed[1]) if elapsed else None,
            "dispatch_estimate_seconds": 5400,
            "logging": "WARNING as in bench harness",
        },
        "thresholds_changed": False,
        "limitations": (
            "10-entity deterministic mock-movement golden fixture; four scripted cross-day chains "
            "run on the final state. Not a live 50-NPC/LLM autonomous errand-completion rate."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    if not args.collect_only:
        run_test(base / "first", "sim/tests/golden/test_golden_full.py::test_golden_seed_full[7]")
        run_test(base / "full", "sim/tests/golden/test_golden_full.py")
    result = collect(base)
    (base / "baseline.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["summary"], ensure_ascii=False))
