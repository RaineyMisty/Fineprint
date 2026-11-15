#!/usr/bin/env python3
"""Single-use blind DeepSeek benchmark. No product code is modified.

Usage: python3 scripts/run_blind_benchmark.py run --freeze-commit HASH
       python3 scripts/run_blind_benchmark.py score

The score command never invokes the pipeline. The run command refuses an
existing run directory, including an interrupted run. Do not delete the guard.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data/blind_benchmark"
CASES = ROOT / "cases"
RUN = ROOT / "run"
REPORT = REPO / "reports/benchmark-blind"


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    # All records are made durable before scoring. Exclusive mode prevents
    # accidental overwrites of a previous attempt's raw record.
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def digest_cases():
    digest = hashlib.sha256()
    for path in sorted(CASES.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(CASES).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO, timeout=45)


def normalize(case_dir, policy):
    """Translate observations only. Never open expected.json in this adapter.

    Unsupported narrative facts remain in claim descriptions. We do not repair
    duplicate/code/authorization/legal cases, infer clinical categories, or map
    a compiler's newly invented condition labels to evidence by guesswork.
    """
    eob = read(case_dir / "eob.json")
    bill = read(case_dir / "bill.json")
    claims, bills, allowed = [], [], {}
    for row in eob["lines"]:
        claims.append({
            "id": row["line_id"], "provider_id": row["provider_id"],
            "service_date": row["service_date"], "code": row["code"],
            "description": ("SYNTHETIC submitted service " + row["code"] +
                            "; documented actual service code " + row["actual_service_code"] +
                            "; " + (row["documented_facts"] or "no additional clinical facts")),
            "network": row["network"], "billed_cents": row["charge_cents"],
            "confirmed_conditions": [row["documented_facts"]] if row["documented_facts"] else [],
            "insurer": {
                "allowed_cents": row["allowed_amount_cents"],
                "deductible_cents": row["deductible_cents"],
                "copay_cents": row["copay_cents"],
                "coinsurance_cents": row["coinsurance_cents"],
                "noncovered_cents": row["noncovered_cents"],
                "balance_cents": row["balance_bill_cents"],
                "insurer_paid_cents": row["insurer_payment_cents"],
                "adjustment_cents": row["adjustment_cents"],
            },
        })
        allowed[row["line_id"]] = {"allowed_cents": row["allowed_amount_cents"],
                                   "source": row["allowed_source"],
                                   "reference": row["allowed_reference"]}
    for row in bill["lines"]:
        bills.append({"id": "B-" + row["line_id"], "claim_line_id": row["claim_line_id"],
                      "provider_id": row["provider_id"], "service_date": row["service_date"],
                      "code": row["code"], "charged_cents": row["charge_cents"],
                      "insurance_paid_cents": row["insurance_credit_cents"],
                      "adjustment_cents": row["adjustment_cents"],
                      "patient_paid_cents": row["patient_paid_cents"],
                      "balance_due_cents": row["balance_due_cents"]})
    opening = eob["opening_accumulators_cents"]
    return {"schema_version": "1.0", "id": eob["case_id"], "title": eob["title"],
            "synthetic": True, "policy": policy,
            "claim": {"id": eob["claim_id"], "policy_id": eob["policy_id"],
                      "member_id": eob["member_id"], "accumulators": {
                          network: {"deductible_paid_cents": opening[network + "_deductible"],
                                    "oop_paid_cents": opening[network + "_oop"]}
                          for network in ("in", "out")}, "lines": claims},
            "bill": {"id": bill["bill_id"], "claim_id": bill["claim_id"],
                     "member_id": bill["member_id"], "lines": bills},
            "allowed_evidence": allowed}


def run(freeze_commit):
    frozen = read(ROOT / "freeze.json")
    actual = digest_cases()
    if actual != frozen["cases_directory_sha256"]:
        raise SystemExit("Frozen cases digest mismatch; refusing to run")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is required; refusing offline substitution")
    freeze_commit = git("rev-parse", freeze_commit).decode().strip()
    # A successful push must already have made the freeze reachable remotely.
    git("merge-base", "--is-ancestor", freeze_commit, "origin/main")
    for path in sorted(CASES.rglob("*")):
        if path.is_file():
            rel = path.relative_to(REPO).as_posix()
            if git("show", freeze_commit + ":" + rel) != path.read_bytes():
                raise SystemExit("A case differs from the freeze commit")
    dirs = sorted(p for p in CASES.iterdir() if p.is_dir())
    if len(dirs) != 40:
        raise SystemExit("Expected 40 cases")
    # Atomic permanent guard, made before the first import or request.
    RUN.mkdir(exist_ok=False)
    os.environ["FINEPRINT_LLM_PROVIDER"] = "deepseek"
    os.environ["FINEPRINT_LLM_ATTEMPTS"] = "1"
    os.environ["FINEPRINT_LLM_TIMEOUT"] = "120"
    os.environ["FINEPRINT_DEEPSEEK_MODEL"] = "deepseek-v4-pro"
    with tempfile.TemporaryDirectory(prefix="fineprint-blind-runtime-") as tmp:
        # Execute actual committed product source from the freeze revision, so
        # concurrent repository edits cannot change code halfway through a run.
        archive_bytes = git("archive", freeze_commit, "fineprint")
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as archive:
            archive.extractall(tmp, filter="data")
        runtime = Path(tmp)
        hashes = {p.relative_to(runtime).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted((runtime / "fineprint").rglob("*.py"))}
        sys.path.insert(0, str(runtime))
        from fineprint.compiler import get_compiler
        from fineprint.models import case_from_dict, to_dict
        from fineprint.service import analyze
        # Load transitive modules from the fixed snapshot before starting threads.
        from fineprint import providers  # noqa: F401

        def compiler_instance():
            compiler = get_compiler("deepseek")
            # Instance configuration only; no transport substitution or source edit.
            # Disable both validation retries AND underlying network retries.
            compiler.transport_attempt_limit = 1
            return compiler

        metadata = {"synthetic": True, "started_at_utc": now(),
                    "freeze_commit": freeze_commit, "product_revision": freeze_commit,
                    "freeze_pushed_before_run": True,
                    "cases_directory_sha256": actual,
                    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "product_source_sha256": hashes,
                    "runtime_archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                    "provider": "deepseek", "model": "deepseek-v4-pro", "workers": 4,
                    "request_config": compiler_instance().request_config,
                    "entry_point": "get_compiler('deepseek').compile → case_from_dict → service.analyze(unresolved=...)",
                    "adapter": "Frozen observation fields translated mechanically; narrative facts retained without clinical/legal inference.",
                    "expected_answers_read_during_inference": False,
                    "policy_sent_to_provider": True, "claim_bill_gold_sent_to_provider": False,
                    "case_count": len(dirs)}
        write(RUN / "metadata.json", metadata)

        def once(case_dir):
            case_id = case_dir.name
            write(RUN / (case_id + ".started.json"), {"case_id": case_id, "started_at_utc": now(), "pipeline_invocations": 1})
            result = {"case_id": case_id, "started_at_utc": now()}
            started = time.monotonic()
            compiler = compiler_instance()
            phase = "compile"
            try:
                document = (case_dir / "policy.md").read_text()
                compilation = compiler.compile(document, case_id + "/policy.md")
                result["compilation"] = compilation.as_dict()
                phase = "normalize"
                inputs = normalize(case_dir, to_dict(compilation.policy))
                result["normalized_case"] = inputs
                decoded = case_from_dict(inputs)
                phase = "analyze"
                report = analyze(decoded, unresolved=compilation.output.unresolved)
                report["limitations"].extend(getattr(compilation.output, "coverage_gaps", []))
                result["report"] = report
            except Exception as exc:
                # Provider errors exclude credentials/response bodies by contract;
                # redact the actual key as a second precaution without printing it.
                message = str(exc).replace(os.environ["DEEPSEEK_API_KEY"], "[REDACTED]")
                result["error"] = {"phase": phase, "type": type(exc).__name__, "message": message}
            result["provider_attempt_audit"] = getattr(compiler, "attempt_audit", [])
            result["provider_request_config"] = compiler.request_config
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result["completed_at_utc"] = now()
            write(RUN / (case_id + ".json"), result)
            return case_id

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(once, path) for path in dirs]
            for completed, future in enumerate(as_completed(futures), 1):
                print(f"Saved {future.result()} ({completed}/40); no retries or reruns", flush=True)
        ending_hash = digest_cases()
        write(RUN / "completion.json", {"completed_at_utc": now(), "case_records": len(dirs),
                                       "cases_directory_sha256_after": ending_hash,
                                       "cases_unchanged": ending_hash == actual})
        if ending_hash != actual:
            raise SystemExit("Cases changed during the run; records retained, benchmark invalid")
    # Gold is first deserialized for evaluation only after every raw result exists.
    score()


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def classify(raw):
    if raw.get("error"):
        return "error", None, None
    report = raw.get("report", {})
    summary = report.get("summary")
    if not summary or report.get("status") == "blocked":
        return "needs clarification", None, None
    low, high = summary["illustrated_min_patient_cents"], summary["illustrated_max_patient_cents"]
    status = "range" if summary.get("conditional") or low != high or summary["scenario_count"] > 1 else "answer"
    return status, low, high


def score():
    metadata = read(RUN / "metadata.json")
    completion = read(RUN / "completion.json")
    if not completion["cases_unchanged"] or digest_cases() != metadata["cases_directory_sha256"]:
        raise SystemExit("Cases digest changed; refusing scoring")
    dirs = sorted(p for p in CASES.iterdir() if p.is_dir())
    # Check the entire run is complete BEFORE deserializing the first gold file.
    raws = {p.name: read(RUN / (p.name + ".json")) for p in dirs}
    if len(raws) != 40:
        raise SystemExit("Incomplete run; no inference reruns are allowed")
    rows = []
    counts = {key: 0 for key in ("answer", "range", "needs clarification", "error",
                                 "exact", "range_contains_truth", "any_interval_contains_truth",
                                 "tp", "fp", "fn", "tn", "abstained_positive", "abstained_negative",
                                 "line_exact", "line_count", "resolved_line_count")}
    for path in dirs:
        raw = raws[path.name]
        expected, eob, bill = (read(path / name) for name in ("expected.json", "eob.json", "bill.json"))
        status, low, high = classify(raw)
        counts[status] += 1
        gold = expected["total_patient_responsibility_cents"]
        comparison = raw.get("report", {}).get("comparisons", [])
        first = comparison[0] if comparison else {}
        predicted = low if status == "answer" else None
        exact = predicted is not None and abs(predicted - gold) <= 100
        contains = low is not None and low <= gold <= high
        counts["exact"] += exact
        counts["any_interval_contains_truth"] += contains
        counts["range_contains_truth"] += status == "range" and contains
        flag = None
        if status == "answer":
            # A total-responsibility discrepancy per line is the explicit finding;
            # isolated EOB component reallocation is not scored as a bill error.
            flag = any(row.get("eob_difference_cents", 0) != 0
                       or row.get("bill_eob_difference_cents", 0) != 0
                       or any(ex.get("kind") == "bill_vs_fineprint" and ex.get("difference_cents", 0) != 0
                              for ex in row.get("explanations", []))
                       for row in first.get("lines", []))
        truth = expected["true_error"]
        if flag is None:
            counts["abstained_positive" if truth else "abstained_negative"] += 1
            if truth:
                counts["fn"] += 1
        else:
            counts["tp" if flag and truth else "fp" if flag else "fn" if truth else "tn"] += 1
        by_line = {row["claim_line_id"]: row for row in first.get("lines", [])}
        line_rows = []
        for line_gold in expected["lines"]:
            lid = line_gold["line_id"]
            output = by_line.get(lid, {})
            point = output.get("fineprint_patient_cents") if status == "answer" else None
            line_exact = point is not None and abs(point - line_gold["patient_responsibility_cents"]) <= 100
            counts["line_count"] += 1
            counts["line_exact"] += line_exact
            counts["resolved_line_count"] += point is not None
            line_rows.append({**line_gold, "predicted_patient_responsibility_cents": point,
                              "predicted_remaining_owed_cents": output.get("fineprint_remaining_cents") if status == "answer" else None,
                              "exact_within_100_cents": line_exact})
        billed_patient = sum(r["patient_paid_cents"] + r["balance_due_cents"] for r in bill["lines"])
        billed_remaining = sum(r["balance_due_cents"] for r in bill["lines"])
        gross_charge = sum(r["charge_cents"] for r in bill["lines"])
        reason = raw.get("error") or raw.get("report", {}).get("blocked_reason")
        row = {"case_id": path.name, "title": eob["title"], "status": status,
               "expected_patient_responsibility_cents": gold,
               "predicted_patient_responsibility_cents": predicted,
               "illustrated_min_cents": low, "illustrated_max_cents": high,
               "expected_remaining_owed_cents": expected["total_remaining_owed_cents"],
               "predicted_remaining_owed_cents": first.get("fineprint_remaining_cents") if status == "answer" else None,
               "billed_patient_total_cents": billed_patient, "billed_remaining_cents": billed_remaining,
               "gross_charge_cents": gross_charge, "exact_within_100_cents": exact,
               "interval_contains_truth": contains if low is not None else None,
               "flagged_error": flag, "true_error": truth,
               "predicted_above_billed_patient_total": predicted is not None and predicted > billed_patient,
               "range_upper_above_billed_patient_total": status == "range" and high > billed_patient,
               "predicted_above_gross_charge": predicted is not None and predicted > gross_charge,
               "range_upper_above_gross_charge": status == "range" and high > gross_charge,
               "predicted_remaining_above_bill_balance": status == "answer" and first.get("fineprint_remaining_cents", 0) > billed_remaining,
               "rationale": expected["rationale"], "failure": reason,
               "lines": line_rows, "elapsed_seconds": raw.get("elapsed_seconds"),
               "attempts": raw.get("compilation", {}).get("attempts"),
               "provider_attempt_audit": raw.get("provider_attempt_audit", []),
               "raw_record": "data/blind_benchmark/run/" + path.name + ".json"}
        rows.append(row)
    n = len(rows)
    positives = sum(r["true_error"] for r in rows)
    negatives = n - positives
    metrics = {
        "case_count": n, "true_errors": positives, "true_correct": negatives,
        "status_counts": {k: counts[k] for k in ("answer", "range", "needs clarification", "error")},
        "exact_amount_accuracy_within_one_dollar": ratio(counts["exact"], n),
        "exact_amount_correct_cases": counts["exact"],
        "answer_only_exact_accuracy": ratio(counts["exact"], counts["answer"]),
        "per_line_exact_amount_accuracy": ratio(counts["line_exact"], counts["line_count"]),
        "per_line_counts": {"correct": counts["line_exact"], "all": counts["line_count"], "resolved": counts["resolved_line_count"]},
        "range_contains_truth_rate": ratio(counts["range_contains_truth"], counts["range"]),
        "range_contains_truth_counts": {"contains": counts["range_contains_truth"], "ranges": counts["range"]},
        "point_or_range_contains_truth_rate_all_cases": ratio(counts["any_interval_contains_truth"], n),
        "abstain_dead_end_rate": ratio(counts["needs clarification"] + counts["error"], n),
        "without_confirmed_answer_rate": ratio(n - counts["answer"], n),
        "error_detection_precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
        "error_detection_recall": ratio(counts["tp"], positives),
        "false_positive_rate": ratio(counts["fp"], negatives),
        "error_detection_counts": {k: counts[k] for k in ("tp", "fp", "fn", "tn", "abstained_positive", "abstained_negative")},
        "resolved_negative_coverage": ratio(counts["tn"] + counts["fp"], negatives),
        "error_decision_coverage": ratio(counts["tp"] + counts["fp"] + counts["tn"] + counts["fn"] - counts["abstained_positive"], n),
        "predicted_above_billed_patient_total": [r["case_id"] for r in rows if r["predicted_above_billed_patient_total"]],
        "range_upper_above_billed_patient_total": [r["case_id"] for r in rows if r["range_upper_above_billed_patient_total"]],
        "predicted_above_gross_charge": [r["case_id"] for r in rows if r["predicted_above_gross_charge"]],
        "range_upper_above_gross_charge": [r["case_id"] for r in rows if r["range_upper_above_gross_charge"]],
    }
    method = {
        "blinding": "Independent writer read root README and docs/architecture.md only before authoring; no product source, tests, existing benchmark cases or gold. README disclosed prior examples/aggregate results. All 40 expectations were hand-authored and pushed before interface inspection and inference.",
        "freeze_commit": metadata["freeze_commit"], "cases_directory_sha256": metadata["cases_directory_sha256"],
        "single_run": "One compiler invocation and at most one DeepSeek HTTP request per case; four concurrent workers; both provider and transport attempt limits one; no fallback, repairs, reruns or tuning. All raw records saved before gold scoring.",
        "runtime": "Unmodified real pipeline imported from a temporary git archive of the freeze revision to isolate concurrent repo edits. Compiler receives original policy only. Compiled policy is the only policy supplied to the deterministic app analysis.",
        "input_scope": "Text policy compilation plus mechanical schema normalization of independently supplied EOB, bill, contract allowance and opening accumulators. This does not evaluate PDF/OCR or automatic raw-document extraction.",
        "fact_limitations": "Narrative clinical/legal/coding facts are retained in claim descriptions and literal confirmation strings. No hand-written benefit corrections, category inference, legal protection override, duplicate removal or semantic mapping of compiled condition labels. Unsupported cases can block or fail; they stay in denominators.",
        "exact": "Nonconditional answer within 100 cents inclusive, denominator 40; range results are not exact answers. Patient responsibility is pre-payment liability; remaining balance is separately reported.",
        "range": "Inclusive illustrative scenario extrema, no tolerance; rate denominator is range cases. Also report point/range containment over all 40. Scenario endpoints are not proven exhaustive bounds.",
        "abstain": "Needs clarification or error / 40. A separate without-confirmed-answer rate includes conditional ranges.",
        "detection": "Only nonconditional answers yield a binary flag. An explicit per-line total patient difference versus EOB or statement establishes a flag; component reallocations alone do not. Failed positive cases count as FN; failed negatives abstain, not TN. Precision TP/(TP+FP), recall TP/24, FPR FP/16, resolved-negative coverage separately. Null indicates a zero denominator.",
        "billed_comparison": "List predictions above statement patient-paid-plus-balance, and separately above gross charges. Also retain remaining-balance comparisons. Some gold cases intentionally underbill, so a higher prediction is not automatically incorrect.",
    }
    result = {"synthetic": True, "generated_at_utc": now(), "method": method,
              "run_metadata": metadata, "run_completion": completion, "metrics": metrics, "cases": rows}
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    def pct(value):
        return "n/a" if value is None else f"{100*value:.1f}%"

    def usd(value):
        return "—" if value is None else f"${value/100:,.2f}"

    def yes(value):
        return "abstain" if value is None else "yes" if value else "no"

    md = ["# Blind held-out benchmark — SYNTHETIC", "",
          f"40 cases; 16 correct bills and 24 erroneous bills. Run completed {completion['completed_at_utc']}.", "",
          f"Exact amount (±$1): **{counts['exact']}/40 ({pct(metrics['exact_amount_accuracy_within_one_dollar'])})**. "
          f"Range contains truth: **{counts['range_contains_truth']}/{counts['range']} ({pct(metrics['range_contains_truth_rate'])})**. "
          f"Abstain/dead-end: **{counts['needs clarification']+counts['error']}/40 ({pct(metrics['abstain_dead_end_rate'])})**.", "",
          f"Error detection precision **{pct(metrics['error_detection_precision'])}**, recall **{pct(metrics['error_detection_recall'])}**, "
          f"false-positive rate **{pct(metrics['false_positive_rate'])}**. "
          f"TP={counts['tp']}, FP={counts['fp']}, FN={counts['fn']}, TN={counts['tn']}; "
          f"abstained positives={counts['abstained_positive']}, abstained negatives={counts['abstained_negative']}. "
          f"Resolved negative coverage **{pct(metrics['resolved_negative_coverage'])}**; a zero FPR with abstentions is not proof of correct negative decisions.", "",
          f"Statuses: {counts['answer']} answer; {counts['range']} range; {counts['needs clarification']} needs clarification; {counts['error']} error. "
          f"Answer-only exact accuracy: {pct(metrics['answer_only_exact_accuracy'])}; "
          f"per-line exact: {counts['line_exact']}/{counts['line_count']}. "
          f"All-case point/range containment: {pct(metrics['point_or_range_contains_truth_rate_all_cases'])}. "
          f"Without confirmed answer (including ranges): {pct(metrics['without_confirmed_answer_rate'])}.", "",
          "## Method and freeze", "",
          f"Freeze commit: `{metadata['freeze_commit']}` (pushed before phase 2). "
          f"Cases SHA-256: `{metadata['cases_directory_sha256']}`; unchanged after the run.", "",
          f"Provider: `{metadata['provider']}`; model: `{metadata['model']}`. "
          f"Configuration: `{json.dumps(metadata['request_config'], sort_keys=True)}`.", ""]
    for key, text in method.items():
        if key not in ("freeze_commit", "cases_directory_sha256"):
            md += [text, ""]
    md += ["The benchmark is small, synthetic and authored by this agent. It is a procedural holdout from product implementation inspection, not independent real-world clinical validation. Gold applicability facts about legal protections and coding are stipulated. Failures below are preserved without repairs. The frozen authoring protocol is in `data/blind_benchmark/README.md`; full per-line gold/prediction data, raw errors and source hashes are in the companion JSON and raw run records.", "",
           "## Per-case results", "",
           "Predicted and expected columns are total patient liability before payments. ‘Flag’ is the app's error decision; ‘Truth’ is whether the frozen bill has a real error. Conditional totals are illustrative ranges.", "",
           "| Case | Status | Predicted | Expected | Statement patient total | Flag | Truth | Within $1 |",
           "| --- | --- | ---: | ---: | ---: | --- | --- | --- |"]
    for row in rows:
        prediction = (usd(row['illustrated_min_cents']) + "–" + usd(row['illustrated_max_cents'])
                      if row['status'] == 'range' else usd(row['predicted_patient_responsibility_cents']))
        md.append(f"| {row['case_id']} | {row['status']} | {prediction} | {usd(row['expected_patient_responsibility_cents'])} | {usd(row['billed_patient_total_cents'])} | {yes(row['flagged_error'])} | {yes(row['true_error'])} | {yes(row['exact_within_100_cents'])} |")
    md += ["", "## Predictions above billed", "",
           "Point predictions above statement patient responsibility: " + (", ".join(metrics['predicted_above_billed_patient_total']) or "none") + ".",
           "Range upper endpoints above statement patient responsibility: " + (", ".join(metrics['range_upper_above_billed_patient_total']) or "none") + ".",
           "Point predictions above gross charges: " + (", ".join(metrics['predicted_above_gross_charge']) or "none") + ".",
           "Range upper endpoints above gross charges: " + (", ".join(metrics['range_upper_above_gross_charge']) or "none") + ".", "",
           "## Failures as observed", ""]
    failures = [r for r in rows if not r['exact_within_100_cents'] or r['flagged_error'] != r['true_error']]
    for row in failures:
        raw = raws[row['case_id']]
        detail = json.dumps(row['failure'], ensure_ascii=False) if row['failure'] else "No runtime error; amount and/or error decision differs from gold."
        detail = detail.replace("|", "\\|").replace("\n", " ")
        md += [f"- **{row['case_id']} — {row['title']}**: {row['status']}. {detail} Gold rationale: {row['rationale']}"]
        audit = raw.get('provider_attempt_audit', [])
        if audit:
            md += ["  Provider attempt audit: `" + json.dumps(audit, ensure_ascii=False).replace('`', "'") + "`."]
    REPORT.with_suffix(".md").write_text("\n".join(md) + "\n")
    print(json.dumps(metrics, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "score"))
    parser.add_argument("--freeze-commit")
    args = parser.parse_args()
    if args.mode == "run":
        if not args.freeze_commit:
            parser.error("run requires --freeze-commit")
        run(args.freeze_commit)
    else:
        score()


if __name__ == "__main__":
    main()
