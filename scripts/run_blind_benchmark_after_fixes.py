#!/usr/bin/env python3
"""One explicitly nonblind follow-up; preserves the official blind artifacts."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time

import run_blind_benchmark as blind

REPO, ROOT = blind.REPO, blind.ROOT
RUN = ROOT / "run-after-fixes"
REPORT = REPO / "reports/benchmark-blind-after-fixes"
OFFICIAL = "36ac3ff3abb3b551667befe39ac685e173c52b73"


def baseline_file(path):
    return blind.git("show", OFFICIAL + ":" + path)


def snapshot(revision, directory):
    data = blind.git("archive", revision, "fineprint")
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(directory, filter="data")
    return hashlib.sha256(data).hexdigest()


def diagnose():
    original = json.loads(baseline_file("reports/benchmark-blind.json"))
    validation, formats = {}, {}
    for case in original["cases"]:
        raw = blind.read(ROOT / "run" / (case["case_id"] + ".json"))
        for issue in raw.get("report", {}).get("validation", []):
            if issue["severity"] == "error":
                validation.setdefault(issue["code"], set()).add(case["case_id"])
        if case["status"] == "needs clarification":
            source = (ROOT / "cases" / case["case_id"] / "policy.md").read_text()
            label = ("Reference card: balance billing = yes/no" if "Financial reference card" in source else
                     "SBC table: prohibited/permitted cell" if "| Network |" in source else
                     "Question and answer: excess charges" if "Can providers collect" in source else
                     "Narrative: excess balance billing permitted")
            formats.setdefault(label, []).append(case["case_id"])
    return {
        "official_blind_commit": OFFICIAL,
        "primary_abstention_causes": [
            {"cause": "Explicit balance/excess billing language rejected by local source validator", "cases": 24,
             "detail": "All 24 clarification cases have incomplete_network at policy.networks.in.balance_billing. The model proposed terms, but local _balance_supported discarded them; not an absent input fact."},
            {"cause": "Null or empty policy display name fails closed schema", "cases": 9,
             "detail": "Six 'expected string' and three 'text must not be empty' errors at output.policy.name; all nine errors were compilation metadata failures, not transport failures."}],
        "secondary_causes_overlap_primary": [
            {"cause": "Compiled condition wording does not equal literal supplied claim confirmations (missing_rule)", "cases": 3},
            {"cause": "Incompatible shared ambiguity interpretation labels (incomplete_interpretations)", "cases": 1, "issues": 2}],
        "validation_case_counts": {key: len(cases) for key, cases in validation.items()},
        "billing_wording_formats": {key: {"count": len(cases), "case_ids": cases} for key, cases in formats.items()},
        "non_abstention_failure": {"cases": 1, "detail": "Acknowledged upcoded visit: pipeline used submitted code rather than the documented actual service, returned $70 instead of $20 and missed the error."},
        "recall_accounting": {"true_positives": 4, "positive_abstentions": 19,
                              "answered_false_negatives": 1, "all_true_errors": 24},
        "eob_bill_format_errors": 0, "transport_errors": 0,
        "missing_allowance_or_opening_history_cases": 0,
        "scope": "The original run normalized structured EOB/bill observations; it did not test PDF/OCR or raw-format adapters. Unsupported legal/clinical/coding semantics remain distinct from the main balance-language gate."}


def run(revision):
    original_md = baseline_file("reports/benchmark-blind.md")
    original_json = baseline_file("reports/benchmark-blind.json")
    if (REPO / "reports/benchmark-blind.md").read_bytes() != original_md:
        raise SystemExit("Official Markdown differs from baseline; refusing to overwrite")
    if (REPO / "reports/benchmark-blind.json").read_bytes() != original_json:
        raise SystemExit("Official JSON differs from baseline")
    frozen = blind.read(ROOT / "freeze.json")
    if blind.digest_cases() != frozen["cases_directory_sha256"]:
        raise SystemExit("Frozen cases changed")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY required")
    revision = blind.git("rev-parse", revision).decode().strip()
    freeze = json.loads(original_json)["method"]["freeze_commit"]
    RUN.mkdir(exist_ok=False)  # never delete or reuse this guard
    blind.write(RUN / "diagnosis.json", diagnose())
    os.environ.update(FINEPRINT_LLM_PROVIDER="deepseek", FINEPRINT_LLM_ATTEMPTS="1",
                      FINEPRINT_LLM_TIMEOUT="120", FINEPRINT_DEEPSEEK_MODEL="deepseek-v4-pro")
    with tempfile.TemporaryDirectory(prefix="fineprint-after-fixes-") as directory:
        archive_hash = snapshot(revision, directory)
        sys.path.insert(0, directory)
        from fineprint.compiler import get_compiler, FallbackCompiler
        from fineprint.models import case_from_dict, to_dict
        from fineprint.service import analyze
        from fineprint import providers  # load fixed source before worker threads

        def compiler_instance():
            compiler = get_compiler("deepseek")
            compiler.transport_attempt_limit = 1
            return compiler

        metadata = {"synthetic": True, "phase": "after fixes, not blind; cases were seen",
                    "started_at_utc": blind.now(), "freeze_commit": freeze,
                    "product_revision": revision, "freeze_pushed_before_run": True,
                    "cases_directory_sha256": frozen["cases_directory_sha256"],
                    "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "original_runner_sha256": hashlib.sha256(Path(blind.__file__).read_bytes()).hexdigest(),
                    "runtime_archive_sha256": archive_hash,
                    "provider": "deepseek", "model": "deepseek-v4-pro", "workers": 4,
                    "request_config": compiler_instance().request_config,
                    "entry_point": "compile → same frozen-observation normalize → service.analyze (patient-facing bill bounds enabled)",
                    "pipeline_invocations_per_case": 1,
                    "retry_note": "Configured validation/transport attempt limits one. Revised client may grant its explicit one extra no-supported-rules retry; actual compiler and HTTP attempts are retained. No case pipeline reruns.",
                    "adapter": "Original blind run normalize() unchanged; no inferred clinical conditions, legal overrides, deduplication or corrected service-code injection.",
                    "case_count": 40,
                    "product_source_sha256": {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                              for p in sorted((Path(directory) / "fineprint").rglob("*.py"))}}
        blind.write(RUN / "metadata.json", metadata)

        def once(path):
            blind.write(RUN / (path.name + ".started.json"), {"case_id": path.name,
                        "started_at_utc": blind.now(), "pipeline_invocations": 1})
            start = time.monotonic()
            result = {"case_id": path.name, "started_at_utc": blind.now()}
            compiler = compiler_instance()
            phase = "compile"
            try:
                compilation = compiler.compile((path / "policy.md").read_text(), path.name + "/policy.md")
                result["compilation"] = compilation.as_dict()
                phase = "normalize"
                normalized = blind.normalize(path, to_dict(compilation.policy))
                result["normalized_case"] = normalized
                case = case_from_dict(normalized)
                phase = "analyze"
                result["report"] = analyze(case, unresolved=compilation.output.unresolved)
                result["report"]["limitations"].extend(getattr(compilation.output, "coverage_gaps", []))
            except Exception as exc:
                result["error"] = {"phase": phase, "type": type(exc).__name__,
                                   "message": str(exc).replace(os.environ["DEEPSEEK_API_KEY"], "[REDACTED]")}
            result.update(provider_attempt_audit=getattr(compiler, "attempt_audit", []),
                          provider_transport_audit=getattr(compiler, "transport_audit", []),
                          provider_request_config=compiler.request_config,
                          completed_at_utc=blind.now(), elapsed_seconds=round(time.monotonic() - start, 3))
            blind.write(RUN / (path.name + ".json"), result)
            return path.name

        paths = sorted(path for path in (ROOT / "cases").iterdir() if path.is_dir())
        assert len(paths) == 40
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(once, path) for path in paths]
            for n, future in enumerate(as_completed(futures), 1):
                print(f"After-fixes saved {future.result()} ({n}/40)", flush=True)
        after_hash = blind.digest_cases()
        blind.write(RUN / "completion.json", {"completed_at_utc": blind.now(), "case_records": 40,
                    "cases_directory_sha256_after": after_hash,
                    "cases_unchanged": after_hash == frozen["cases_directory_sha256"]})
        assert after_hash == frozen["cases_directory_sha256"]

        from fineprint.eval import run_evaluation
        from fineprint.repository import list_cases, load_case
        evaluation = run_evaluation(FallbackCompiler())
        evaluation["runtime_revision"] = revision
        blind.write(RUN / "original-synthetic-benchmark.json", evaluation)
        samples = {}
        for item in list_cases():
            case, _ = load_case(item["id"])
            report = analyze(case)
            samples[item["id"]] = {"status": report["status"], "summary": report["summary"],
                                   "scenarios": report["scenarios"], "comparisons": report["comparisons"]}
        blind.write(RUN / "built-in-samples.json", samples)
        # Establish sample before/after behavior using the original product
        # revision, without any network calls and without rerunning blind cases.
        with tempfile.TemporaryDirectory(prefix="fineprint-before-samples-") as before_dir:
            snapshot(freeze, before_dir)
            code = ("import sys,json;sys.path.insert(0,sys.argv[1]);"
                    "from fineprint.repository import list_cases,load_case;from fineprint.service import analyze;"
                    "print(json.dumps({i['id']:analyze(load_case(i['id'])[0]) for i in list_cases()}))")
            before_samples = json.loads(subprocess.check_output([sys.executable, "-c", code, before_dir],
                                                               cwd=before_dir, timeout=45))
        original_eval = json.loads(baseline_file("reports/evaluation.json"))
        regressions = {"synthetic_provider": "fallback, no LLM requests", "original_groups": original_eval["groups"],
                       "after_groups": evaluation["groups"], "samples": {}}
        regressions["synthetic_calculation_regression"] = evaluation["groups"]["all"]["calculation"]["exact"] < original_eval["groups"]["all"]["calculation"]["exact"]
        for identity, sample in samples.items():
            old = before_samples[identity]
            keys = ("scenario_count", "conditional", "illustrated_min_patient_cents", "illustrated_max_patient_cents")
            before = {k: old["summary"][k] for k in keys} if old["summary"] else None
            after = {k: sample["summary"][k] for k in keys} if sample["summary"] else None
            regressions["samples"][identity] = {"before": before, "after": after,
                "same_status_and_summary": old["status"] == sample["status"] and before == after}
        blind.write(RUN / "regressions.json", regressions)
    summarize(original_md, original_json)


def summarize(original_md=None, original_json=None):
    original_md = original_md or baseline_file("reports/benchmark-blind.md")
    original_json = original_json or baseline_file("reports/benchmark-blind.json")
    # Reuse the original scoring definitions; write only the separate follow-up.
    blind.RUN, blind.REPORT = RUN, REPORT
    blind.score()
    result = blind.read(REPORT.with_suffix(".json"))
    original = json.loads(original_json)
    metadata = result["run_metadata"]
    diagnosis, regressions = blind.read(RUN / "diagnosis.json"), blind.read(RUN / "regressions.json")
    result["phase"] = "After fixes (not blind — cases were seen)"
    result["method"].update(blinding="Not blind: cases and original outcomes were seen before general fixes; official blind results remain unchanged.",
        runtime="Unmodified product source archived at " + metadata["product_revision"] + "; original normalization and scoring definitions retained.",
        single_run=metadata["retry_note"], product_revision=metadata["product_revision"])
    result["diagnosis"] = diagnosis
    result["regressions"] = regressions
    result["code_commits"] = blind.git("log", "--format=%H %s", metadata["freeze_commit"] + ".." + metadata["product_revision"], "--", "fineprint").decode().splitlines()
    result["post_run_hardening_not_live_benchmarked"] = blind.git(
        "log", "--format=%H %s", metadata["product_revision"] + "..HEAD", "--", "fineprint").decode().splitlines()
    test_log = RUN / "unittest-final.log"
    if test_log.exists():
        text = test_log.read_text()
        count = re.search(r"Ran (\d+) tests", text)
        skipped = re.search(r"OK \(skipped=(\d+)\)", text)
        result["final_unittest"] = {"tests": int(count[1]) if count else None,
            "skipped": int(skipped[1]) if skipped else 0,
            "passed": bool(re.search(r"(?m)^OK(?: \(.*\))?$", text)),
            "log_sha256": hashlib.sha256(test_log.read_bytes()).hexdigest()}
    violations = []
    for row in result["cases"]:
        raw = blind.read(RUN / (row["case_id"] + ".json"))
        for comparison in raw.get("report", {}).get("comparisons", []):
            for line in comparison["lines"]:
                if line["fineprint_patient_cents"] > line["bill_patient_cents"] or line["fineprint_remaining_cents"] > line["bill_balance_due_cents"]:
                    violations.append({"case_id": row["case_id"], "scenario": comparison["scenario_id"], "line": line["claim_line_id"]})
    result["owed_above_bill_violations_all_scenarios"] = violations
    result["metrics"]["owed_above_bill_case_count"] = len({v["case_id"] for v in violations})
    result["metrics"]["actual_compile_attempts"] = sum(len(row["provider_attempt_audit"]) for row in result["cases"])
    result["metrics"]["actual_http_attempts"] = sum(len(blind.read(RUN / (row["case_id"] + ".json")).get("provider_transport_audit", [])) for row in result["cases"])
    REPORT.with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    def pct(value): return "n/a" if value is None else f"{value:.1%}"
    def money(value): return "—" if value is None else f"${value/100:,.2f}"
    before, after = original["metrics"], result["metrics"]
    section = ["## After fixes (not blind — cases were seen)", "",
               f"Product revision `{metadata['product_revision']}`. One additional pipeline invocation per case; no frozen input or expected answer changed. "
               "The original blind section above and its JSON are preserved byte for byte. The same observation adapter, gold totals, $1 tolerance and metric denominators are used. "
               "The follow-up is diagnostic and must not be described as new blind performance.", "",
               "| Metric | Official blind | After fixes (not blind) |",
               "| --- | ---: | ---: |"]
    for label, key in (("Exact amount within $1 (all 40)", "exact_amount_accuracy_within_one_dollar"),
                       ("Abstain/dead-end", "abstain_dead_end_rate"), ("Error precision", "error_detection_precision"),
                       ("Error recall (all 24 true errors)", "error_detection_recall"), ("False-positive rate (all 16 correct)", "false_positive_rate"),
                       ("Resolved negative coverage", "resolved_negative_coverage"), ("Range contains truth", "range_contains_truth_rate")):
        section.append(f"| {label} | {pct(before[key])} | {pct(after[key])} |")
    section += [f"| Owed above bill (any scenario/line) | 0 | {after['owed_above_bill_case_count']} |", "",
                f"Statuses: `{json.dumps(after['status_counts'])}`. Detection counts: `{json.dumps(after['error_detection_counts'])}`. "
                f"Provider: DeepSeek `deepseek-v4-pro`; four workers, timeout 120 seconds. "
                f"Actual compiler attempts {after['actual_compile_attempts']}; HTTP attempts {after['actual_http_attempts']}. " + metadata['retry_note'], "",
                "### Root causes in the original run", "",
                "| Cause | Cases | Relationship |", "| --- | ---: | --- |"]
    for cause in diagnosis['primary_abstention_causes']:
        section.append(f"| {cause['cause']} | {cause['cases']} | Primary; sums to 33 abstentions |")
    for cause in diagnosis['secondary_causes_overlap_primary']:
        section.append(f"| {cause['cause']} | {cause['cases']} | Overlaps the 24 billing-language blocks |")
    section += ["| Acknowledged upcode ignored; submitted code used | 1 | Wrong answered case, additional to 33 abstentions |",
                "| EOB/bill format parsing, transport failure, missing allowance/opening history | 0 | None occurred in the official run |", "",
                "Billing-language blocks by format: " + "; ".join(f"{key}: {value['count']}" for key,value in diagnosis['billing_wording_formats'].items()) + ". "
                "All 24 were `incomplete_network` at the in-network balance-billing field. The nine errors were six null-name string failures and three empty-name failures. "
                "Secondary errors were `missing_rule` (3 cases: literal claim confirmations did not match compiled condition labels) and `incomplete_interpretations` (2 issues in 1 case). "
                "Recall was 4/24 because 19 erroneous cases abstained and one answered upcode case missed the error. " + diagnosis['scope'], "",
                "### General code changes", "",
                "- Evidence validation recognizes explicit billing prohibitions/permissions in either word order, yes/no reference fields, network-scoped question/answer text, and row-based/transposed SBC tables. It requires a billing heading, respects network scope, and preserves contradictions.",
                "- Null/blank display names use a source heading or explicit plan name; numeric fields, source evidence and coverage remain strict.",
                "- Combined product revision includes the other agents' generic interpretation normalization, human-readable clarification reasons, separate uncapped policy audits and patient-facing bill/payment bounds, plus bounded zero-temperature DeepSeek compilation. Source revisions are recorded below.", ""]
    section += ["- `" + commit + "`" for commit in result['code_commits']]
    if result['post_run_hardening_not_live_benchmarked']:
        section += ["", "Post-run hardening (unit-tested; no additional live benchmark run):"]
        section += ["- `" + commit + "`" for commit in result['post_run_hardening_not_live_benchmarked']]
        section += ["", "The negation guard additionally preserves prohibitions such as ‘not permitted to balance bill’. The live metrics above remain attributed to the archived product revision, which precedes this final guard."]
    section += ["", "Patient-facing owed remains bounded by the statement, its credits and payments. Four frozen cases intentionally contain underbilling; their contractual gold liability can exceed the bill. They remain in the accuracy denominator, and the bounded payment answer may therefore differ from gold. Uncapped policy arithmetic in raw traces is not a payment recommendation. Unsupported authorization/referral, legal-protection and coding/bundling facts have not been converted into bespoke benchmark rules.", "",
                "### Regressions", ""]
    for label, groups in (("Before (committed original report)", regressions['original_groups']), ("After (fresh fallback run)", regressions['after_groups'])):
        g = groups['all']
        section += [f"{label}: original synthetic benchmark exact calculation {g['calculation']['exact']}/{g['calculation']['total']}; "
                    f"end-to-end {g['end_to_end']['success']}/{g['end_to_end']['total']}; discrepancy precision {pct(g['discrepancy']['precision'])}, "
                    f"recall {pct(g['discrepancy']['recall'])}, FPR {pct(g['discrepancy']['false_positive_rate'])}.", ""]
    section += ["Built-in samples use original prose through the fallback compiler in both archived revisions:", "",
                "| Sample | Before illustrated total | After illustrated total | Scenario count before → after | Same status/summary |",
                "| --- | ---: | ---: | ---: | --- |"]
    for identity, sample in regressions['samples'].items():
        old, new = sample['before'], sample['after']
        section.append(f"| {identity} | {money(old['illustrated_min_patient_cents'])}–{money(old['illustrated_max_patient_cents'])} | "
                       f"{money(new['illustrated_min_patient_cents'])}–{money(new['illustrated_max_patient_cents'])} | "
                       f"{old['scenario_count']} → {new['scenario_count']} | {sample['same_status_and_summary']} |")
    verification = result.get('final_unittest')
    unittest_text = (f"Full unittest before the final report commit: {verification['tests']} tests, {verification['skipped']} skipped; passed={verification['passed']}. "
                     if verification else "Final full unittest verification is pending. ")
    section += ["", "Full unittest passed before both product-fix commits (197 tests; 9 skipped). " + unittest_text +
                "Raw regression outputs are in `data/blind_benchmark/run-after-fixes/`; the original synthetic benchmark's pre-existing held-out failures remain reported.", "",
                "### Per-case follow-up", "", "| Case | Status | Predicted liability | Gold liability | Error flag / truth |", "| --- | --- | ---: | ---: | --- |"]
    for row in result['cases']:
        prediction = money(row['predicted_patient_responsibility_cents']) if row['status'] != 'range' else money(row['illustrated_min_cents']) + "–" + money(row['illustrated_max_cents'])
        section.append(f"| {row['case_id']} | {row['status']} | {prediction} | {money(row['expected_patient_responsibility_cents'])} | {row['flagged_error']} / {row['true_error']} |")
    section += ["", "Remaining failures (preserved, no case repair or rerun):", ""]
    for row in result['cases']:
        if not row['exact_within_100_cents'] or row['flagged_error'] != row['true_error']:
            detail = json.dumps(row['failure'], ensure_ascii=False) if row['failure'] else "Amount or error decision differs from frozen gold."
            section.append(f"- **{row['case_id']}** ({row['status']}): {detail}")
    section += ["", "Full per-line outcomes, validation messages, attempts and code hashes: [after-fixes JSON](benchmark-blind-after-fixes.json).", ""]
    rendered = "\n".join(section)
    REPORT.with_suffix('.md').write_text("# " + rendered[3:])
    target = REPO / "reports/benchmark-blind.md"
    current = target.read_bytes()
    if current != original_md and not current.startswith(original_md + b"\n\n## After fixes"):
        raise SystemExit("Official report prefix changed; refusing to overwrite")
    target.write_bytes(original_md + b"\n\n" + rendered.encode())
    assert (REPO / "reports/benchmark-blind.json").read_bytes() == original_json
    assert target.read_bytes().startswith(original_md)
    print(json.dumps({"before": before, "after": after, "regressions": regressions['samples']}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('run', 'summarize'))
    parser.add_argument('--revision')
    args = parser.parse_args()
    if args.mode == 'run':
        if not args.revision:
            parser.error('run requires --revision')
        run(args.revision)
    else:
        summarize()
