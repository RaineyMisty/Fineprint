#!/usr/bin/env python3
"""Real DeepSeek smoke check: two independent uploads of each built-in sample."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fineprint.compiler import get_compiler
from fineprint.repository import sample_inputs
from fineprint.service import check_documents


def main():
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY required; no offline substitution")
    os.environ["FINEPRINT_DEEPSEEK_MODEL"] = "deepseek-v4-pro"
    os.environ["FINEPRINT_LLM_TIMEOUT"] = "120"
    specs = [(identity, run, expected) for identity, expected in (
        ("aurora-imaging", 38500), ("mosaic-oop", 100000), ("mosaic-therapy", 4000)) for run in (1, 2)]
    report = {"synthetic": True, "provider": "deepseek", "model": "deepseek-v4-pro",
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "revision_before_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=20).strip(),
              "method": "Each run calls the real pasted-document check entry point with original policy/EOB/bill and DeepSeek. No cache, fallback, hand-compiled rules or expected amount is supplied to the pipeline. Therapy remains conditional; its patient-facing document-bounded amount must be $40.",
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted((ROOT / "fineprint").glob("*.py"))}, "runs": []}

    def once(spec):
        identity, number, expected = spec
        compiler = get_compiler("deepseek")
        compiler.transport_attempt_limit = 1
        started = time.monotonic()
        row = {"sample": identity, "run": number, "expected_patient_cents": expected}
        try:
            inputs = {**sample_inputs(identity)["inputs"], "sample_id": identity, "provider": "deepseek"}
            output = check_documents(inputs, compiler=compiler)
            row["output"] = output
            summary = output["report"].get("summary")
            row["status"] = output["report"]["status"]
            row["min_patient_cents"] = summary["illustrated_min_patient_cents"] if summary else None
            row["max_patient_cents"] = summary["illustrated_max_patient_cents"] if summary else None
            row["conditional"] = summary["conditional"] if summary else None
            row["backend"] = output["compilation"]["backend"]
            row["passed"] = row["status"] == "ready" and row["backend"] == "deepseek" and row["min_patient_cents"] == row["max_patient_cents"] == expected
            row["owed_above_bill"] = any(
                line["fineprint_patient_cents"] > line["bill_patient_cents"] or line["fineprint_remaining_cents"] > line["bill_balance_due_cents"]
                for comparison in output["report"]["comparisons"] for line in comparison["lines"])
            row["passed"] = row["passed"] and not row["owed_above_bill"]
        except Exception as exc:
            row.update(status="error", passed=False, error=type(exc).__name__ + ": " + str(exc).replace(os.environ["DEEPSEEK_API_KEY"], "[REDACTED]"))
        row.update(elapsed_seconds=round(time.monotonic()-started,3),
                   compiler_attempt_audit=getattr(compiler, "attempt_audit", []),
                   transport_audit=getattr(compiler, "transport_audit", []), request_config=compiler.request_config)
        return row

    with ThreadPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(once, spec) for spec in specs]):
            row = future.result()
            report["runs"].append(row)
            print(json.dumps({k: row.get(k) for k in ("sample", "run", "status", "min_patient_cents", "max_patient_cents", "passed", "error")}), flush=True)
    report["runs"].sort(key=lambda r:(r["sample"], r["run"]))
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = all(row["passed"] for row in report["runs"])
    target = ROOT / "reports/live-samples-billing"
    target.with_suffix(".json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = ["# Real DeepSeek billing regression check", "", report["method"], "",
             "| Sample | Run | Status | Patient total | Conditional | Passed |", "| --- | ---: | --- | ---: | --- | --- |"]
    for row in report["runs"]:
        amount = "—" if row.get("min_patient_cents") is None else f"${row['min_patient_cents']/100:,.2f}–${row['max_patient_cents']/100:,.2f}"
        lines.append(f"| {row['sample']} | {row['run']} | {row['status']} | {amount} | {row.get('conditional')} | {row['passed']} |")
    lines += ["", f"All six passed: **{report['passed']}**. Model: `deepseek-v4-pro`; source hashes, complete outputs and real request audits are in the companion JSON. No deployment.", ""]
    target.with_suffix(".md").write_text("\n".join(lines))
    if not report["passed"]:
        raise SystemExit("At least one live verification failed; see preserved report")


if __name__ == "__main__":
    main()
