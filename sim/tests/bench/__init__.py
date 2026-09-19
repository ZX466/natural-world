"""性能基准（性能域 — pi）。

运行方式：`uv run pytest -m bench`（nightly；每提交 CI 跑 `-m "not bench"`）。
阈值与预算依据 docs/perf/budget.md、docs/perf/bench-plan.md；集中见 thresholds.py。
"""
