"""Measure the unmodified production PDF/DeepSeek/validation path on local PDFs.

No policy text, model responses, evidence quotes or exception messages are saved.
Run with a pre-model, manually reviewed numeric label JSON in the ignored directory.
One provider/transport attempt per independent run preserves the held-out protocol.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fineprint.documents_pdf import extract_upload
from fineprint.providers import LLMCompiler

MODEL = "deepseek-v4-pro"
PRIVATE = ROOT / "data/real_private/benchmark-real-sbc"
CODE_FILES = ["fineprint/providers.py", "fineprint/compiler.py", "fineprint/models.py",
              "fineprint/validation.py", "fineprint/policy_sections.py", "fineprint/documents_pdf.py"]
METHODOLOGY = {
    "pipeline": ["production extract_upload(policy, PDF bytes)", "DeepSeek LLMCompiler.compile",
                 "production recover_evidence and validate_output"],
    "sampling": "Three independent extractions and compile calls per document; no response selection or fallback",
    "attempts": "One compile attempt and one transport attempt per run, including dev; interactive default is three",
    "model_identity": "Exact requested model alias; provider does not expose an immutable weight revision through this adapter",
    "split": "Kaiser/Highmark dev; other insurer SBCs held_out; previously measured holdouts are not freshly unseen",
    "rules": "Raw proposed rule_evidence entries versus retained validated rule paths; micro-averaged, not recall",
    "quote_accuracy": "Whitespace-normalized source containment; source-line citations are locally copied, not model-authored quotes",
    "page_accuracy": "No predicted page field. Physical offset locatability and limited labeled-field page overlap reported separately",
    "claim_ready": "Benefits present, no unresolved entries, all retained networks have explicit balance_billing",
    "key_numbers": "Manual pre-model labels; compare individual in-network limits and service copay/coinsurance pairs; missing and ambiguous count as misses",
    "stability": "Population variance of three retained counts, failures zero; limits must be present and identical in all three runs",
    "latency": "Monotonic wall time from worker start; includes extraction and compile/validation, excludes queue delay; provider timeout is per I/O, not a hard total deadline",
    "privacy": "No raw responses, quotes, policy text or free-form exceptions are saved",
    "limitations": ["Small corpus and three repetitions", "No all-rule gold inventory or service recall",
                    "No independent full condition/waiver or real-claim correctness assessment",
                    "Horizon tiered network excluded from single-network numeric score",
                    "Other policy documents have no numeric reference labels",
                    "Provider load from concurrent work is uncontrolled; timeout variance is not model-output nondeterminism",
                    "Concurrent compiler edits after import are not evaluated"],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprints():
    return {name: sha((ROOT / name).read_bytes()) for name in CODE_FILES}


def normalized(text):
    return " ".join(text.split())


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def inventory():
    with (ROOT / "data/real_manifest.csv").open(newline="") as stream:
        manifest = {r["local_path"]: r for r in csv.DictReader(stream)}
    result = []
    for path in sorted((ROOT / "data/real_private/docs").glob("*.pdf")):
        relative = path.relative_to(ROOT).as_posix()
        row = manifest.get(relative, {})
        kind = row.get("doc_type", "unmanifested")
        included = kind in ("SBC", "EOC", "Schedule of benefits")
        reason = None if included else (
            "Multi-plan brochure; no plan-selection input in the single-policy compiler"
            if "brochure" in kind.lower() else "Not a real insurer SBC or supported policy document")
        result.append(dict(document_id=path.stem, filename=path.name, document_type=kind,
                           group="sbc" if kind == "SBC" else "other_policy",
                           split="dev" if path.stem.startswith(("kaiser_", "highmark_")) else "held_out",
                           included=included, exclusion_reason=reason,
                           pdf_sha256=sha(path.read_bytes()),
                           manifest_sha256_matches=sha(path.read_bytes()) == row.get("sha256")))
    return result


def error_code(exc):
    """Only fixed codes cross the publication boundary; exception text stays private."""
    message = str(exc).lower()
    for needle, code in [
        ("timed out", "transport_timeout"), ("provider http", "provider_http_error"),
        ("transport failed", "transport_failure"), ("no selectable text", "no_selectable_text"),
        ("readable pdf", "unreadable_pdf"), ("password", "pdf_password"),
        ("no supported executable", "no_supported_rules"),
        ("malformed", "malformed_json_or_schema"), ("json response", "incomplete_json"),
        ("overlapping benefits", "overlapping_benefits"),
        ("missing or unknown fields", "schema_fields"), ("expected", "schema_type"),
        ("evidence", "evidence_validation"), ("unresolved", "unresolved_validation"),
    ]:
        if needle in message:
            return code
    return "compile_or_extraction_error"


def citation_metrics(value, document):
    """Raw line references are resolved without editing the model's proposed output."""
    result = dict(citations=0, verbatim=0, line_references=0, legacy_quotes=0)
    lines = document.splitlines(keepends=True)
    source = normalized(document)
    if not isinstance(value, dict):
        return result
    for rule in value.get("rule_evidence", []) or []:
        if not isinstance(rule, dict):
            continue
        for evidence in rule.get("evidence", []) or []:
            if not isinstance(evidence, dict):
                continue
            if isinstance(evidence.get("source_lines"), list):
                for number in evidence["source_lines"]:
                    result["citations"] += 1
                    result["line_references"] += 1
                    result["verbatim"] += (type(number) is int and 1 <= number <= len(lines)
                                           and bool(lines[number - 1].strip()))
            elif isinstance(evidence.get("quote"), str):
                result["citations"] += 1
                result["legacy_quotes"] += 1
                quote = normalized(evidence["quote"])
                result["verbatim"] += bool(quote) and quote in source
    return result


def proposed_rules(value):
    """Count proposed evidence entries, matching the production attempt audit."""
    if isinstance(value, dict) and isinstance(value.get("rule_evidence"), list):
        return len(value["rule_evidence"])
    return 0


def field_values(policy):
    result = {"deductible": [], "oop_max": [], "primary_care": [], "specialist": [], "er": []}
    network = policy.networks.get("in")
    if network:
        result["deductible"] = [network.deductible_cents]
        result["oop_max"] = [network.oop_max_cents]
    paths = {"deductible": ["networks.in.deductible_cents"], "oop_max": ["networks.in.oop_max_cents"]}
    for benefit in policy.benefits:
        if benefit.network != "in" or not benefit.covered:
            continue
        category = normalized(benefit.service_category or "").lower()
        field = ("primary_care" if "primary care" in category else
                 "specialist" if "specialist" in category else
                 "er" if "emergency room" in category else None)
        if field:
            result[field].append(dict(copay_cents=benefit.copay_cents, coinsurance_bps=benefit.coinsurance_bps))
            paths.setdefault(field, []).append("benefits." + benefit.id)
    # Multiple differently priced variants count as ambiguous, never cherry-pick a matching price.
    result = {key: [json.loads(v) for v in sorted({json.dumps(x, sort_keys=True) for x in values})]
              for key, values in result.items()}
    return result, paths


def score_fields(values, labels):
    result = {}
    for field, label in labels.items():
        candidates = values.get(field, [])
        status = ("missing" if not candidates else "ambiguous" if len(candidates) > 1 else
                  "correct" if candidates[0] == label["value"] else "incorrect")
        result[field] = dict(expected=label["value"], predicted=candidates, status=status,
                             reference_pdf_page=label["page"])
    return result


def benchmark_run(spec, run_number, labels):
    started = time.monotonic()
    record = dict(document_id=spec["document_id"], run=run_number, started_at=now(),
                  extraction_success=False, compile_success=False, valid_json=False,
                  validation_success=False, claim_ready=False, conditionally_executable=False,
                  proposed_rules=0, retained_rules=0, benefit_rules=0,
                  raw_citations=dict(citations=0, verbatim=0, line_references=0, legacy_quotes=0),
                  retained_citations=dict(citations=0, verbatim=0, exact_offsets=0,
                                          physical_page_locatable=0),
                  key_field_page_checks=0, key_field_page_matches=0,
                  field_values={}, key_numbers=score_fields({}, labels),
                  failure=None, compile_seconds=None, extraction_seconds=None)
    try:
        extracted = extract_upload("policy", spec["filename"],
                                   (ROOT / "data/real_private/docs" / spec["filename"]).read_bytes())
        record["extraction_seconds"] = round(time.monotonic() - started, 4)
        document = extracted["text"]
        pages = document.split("\f")
        physical_pages_known = len(pages) == extracted["pages"]
        record.update(extraction_success=True, pages=extracted["pages"], characters=len(document),
                      source_sha256=sha(document.encode()), extraction_warning_count=len(extracted["warnings"]),
                      physical_page_mapping_available=physical_pages_known)
        compiler = LLMCompiler("deepseek", retries=1)
        compiler.model = MODEL
        compiler.transport_attempt_limit = 1
        compiler.timeout_seconds = 300
        request = compiler.transport

        def observe(prompt, schema):
            response = request(prompt, schema)
            try:
                value = json.loads(response) if isinstance(response, str) else response
                record["valid_json"] = True
                record["proposed_rules"] = proposed_rules(value)
                record["raw_citations"] = citation_metrics(value, document)
            except Exception:
                # Observation must never change the production response or its error handling.
                pass
            return response

        compiler.transport = observe
        compiling = time.monotonic()
        try:
            compiled = compiler.compile(document, spec["document_id"])
            output = compiled.output
            record.update(compile_success=True, validation_success=True,
                          retained_rules=len(output.rule_evidence), benefit_rules=len(compiled.policy.benefits),
                          claim_ready=bool(compiled.policy.benefits and not output.unresolved and
                                           all(t.balance_billing is not None for t in compiled.policy.networks.values())),
                          conditionally_executable=bool(compiled.policy.benefits and not output.unresolved),
                          unresolved_count=len(output.unresolved), coverage_gap_count=len(output.coverage_gaps),
                          dropped_rule_count=sum(w.startswith("Dropped rule ") for w in output.warnings))
            values, paths = field_values(compiled.policy)
            record["field_values"] = values
            record["key_numbers"] = score_fields(values, labels)
            citations = record["retained_citations"]
            evidence_by_path = {r.rule_path: r.evidence for r in output.rule_evidence}
            source = normalized(document)
            for rule in output.rule_evidence:
                for evidence in rule.evidence:
                    citations["citations"] += 1
                    quote = normalized(evidence.quote)
                    citations["verbatim"] += bool(quote) and quote in source
                    exact = document[evidence.start:evidence.end] == evidence.quote
                    citations["exact_offsets"] += exact
                    # Source spans yield a physical page, not an independently predicted page number.
                    citations["physical_page_locatable"] += physical_pages_known and exact
            if physical_pages_known:
                for field, label in labels.items():
                    evidence = [e for path in paths.get(field, []) for e in evidence_by_path.get(path, [])]
                    if evidence:
                        record["key_field_page_checks"] += 1
                        record["key_field_page_matches"] += any(
                            document[:e.start].count("\f") + 1 == label["page"] for e in evidence)
        except Exception as exc:
            record["failure"] = error_code(exc)
        finally:
            record["compile_seconds"] = round(time.monotonic() - compiling, 4)
            record["request_config"] = compiler.request_config
            record["attempt_audit"] = [dict(attempt=a["attempt"], proposed_rules=a.get("proposed_rules"),
                                            validated_rules=a.get("validated_rules"),
                                            failure=error_code(Exception(a["error"])) if a.get("error") else None)
                                       for a in getattr(compiler, "attempt_audit", [])]
            selection = getattr(compiler, "input_selection", {})
            record["input_selection"] = {k: selection.get(k) for k in (
                "source_characters", "selected_characters", "omitted")}
    except Exception as exc:
        record["failure"] = error_code(exc)
        record["extraction_seconds"] = round(time.monotonic() - started, 4)
    record["elapsed_seconds"] = round(time.monotonic() - started, 4)
    record["finished_at"] = now()
    return record


def aggregate(runs):
    total = len(runs)
    raw = sum(r["raw_citations"]["citations"] for r in runs)
    kept = sum(r["retained_citations"]["citations"] for r in runs)
    proposed = sum(r["proposed_rules"] for r in runs)
    retained = sum(r["retained_rules"] for r in runs)
    numbers = Counter(item["status"] for r in runs for item in r["key_numbers"].values())
    fields_total = sum(numbers.values())
    observed_fields = fields_total - numbers["missing"]
    page_checks = sum(r["key_field_page_checks"] for r in runs)
    result = dict(runs=total, documents=len({r["document_id"] for r in runs}),
                  extraction_success=sum(r["extraction_success"] for r in runs),
                  valid_json=sum(r["valid_json"] for r in runs),
                  compile_success=sum(r["compile_success"] for r in runs),
                  claim_ready=sum(r["claim_ready"] for r in runs),
                  conditionally_executable=sum(r["conditionally_executable"] for r in runs),
                  proposed_rules=proposed, retained_rules=retained,
                  benefit_rules=sum(r["benefit_rules"] for r in runs),
                  validated_rule_rate=ratio(retained, proposed),
                  raw_citation_count=raw,
                  raw_quote_accuracy=ratio(sum(r["raw_citations"]["verbatim"] for r in runs), raw),
                  retained_citation_count=kept,
                  retained_quote_accuracy=ratio(sum(r["retained_citations"]["verbatim"] for r in runs), kept),
                  physical_page_locatable_rate=ratio(sum(r["retained_citations"]["physical_page_locatable"] for r in runs), kept),
                  independently_predicted_page_accuracy=None,
                  key_field_page_checks=page_checks,
                  key_field_page_match_rate=ratio(sum(r["key_field_page_matches"] for r in runs), page_checks),
                  key_numbers=dict(numbers), key_number_opportunities=fields_total,
                  key_number_end_to_end_accuracy=ratio(numbers["correct"], fields_total),
                  key_number_observed_accuracy=ratio(numbers["correct"], observed_fields),
                  failures=dict(Counter(r["failure"] for r in runs if r["failure"])))
    for field in ("extraction_success", "valid_json", "compile_success", "claim_ready"):
        result[field + "_rate"] = ratio(result[field], total)
    for field in ("elapsed_seconds", "extraction_seconds", "compile_seconds"):
        values = [r[field] for r in runs if r[field] is not None]
        result[field] = dict(mean=statistics.mean(values), median=statistics.median(values),
                             min=min(values), max=max(values)) if values else None
    return result


def stability(runs):
    counts = [r["retained_rules"] for r in runs]
    valid = [r for r in runs if r["compile_success"]]
    result = dict(retained_rule_counts=counts, proposed_rule_counts=[r["proposed_rules"] for r in runs],
                  rule_count_population_variance=statistics.pvariance(counts) if counts else None,
                  successful_run_rule_count_population_variance=statistics.pvariance([r["retained_rules"] for r in valid]) if valid else None)
    for field in ("deductible", "oop_max"):
        values = [r["field_values"].get(field, []) for r in runs]
        result[field + "_values"] = values
        result[field + "_stable_all_three"] = len(runs) == 3 and all(values) and all(v == values[0] for v in values)
    return result


def finalize(report):
    for spec in report["documents"]:
        runs = sorted(spec["runs"], key=lambda r: r["run"])
        spec["runs"] = runs
        spec["metrics"] = aggregate(runs)
        spec["stability"] = stability(runs)
    groups = {}
    for group in ("sbc", "other_policy"):
        for split in ("dev", "held_out", "all"):
            specs = [d for d in report["documents"] if d["group"] == group and (split == "all" or d["split"] == split)]
            runs = [r for d in specs for r in d["runs"]]
            if runs:
                group_metrics = aggregate(runs)
                group_metrics["deductible_stable_documents"] = sum(d["stability"]["deductible_stable_all_three"] for d in specs)
                group_metrics["oop_max_stable_documents"] = sum(d["stability"]["oop_max_stable_all_three"] for d in specs)
                group_metrics["mean_within_document_rule_count_variance"] = statistics.mean(d["stability"]["rule_count_population_variance"] for d in specs)
                groups[group + ":" + split] = group_metrics
    report["aggregates"] = groups
    report["completed_at"] = now()
    report["code_hashes_after"] = fingerprints()
    report["production_files_unchanged_during_measurement"] = report["code_hashes_before"] == report["code_hashes_after"]
    return report


def percent(value):
    return "N/A" if value is None else f"{value:.1%}"


def markdown(report):
    lines = ["# Real insurer PDF benchmark", "", f"Date: {report['started_at'][:10]}; model: `{report['model']}`.", "",
             "Production path: `extract_upload(policy, PDF bytes)` → `LLMCompiler(deepseek).compile` → existing evidence recovery and validation. No parser/compiler edits or fallback substitution.", "",
             "Three independent runs per document, each re-extracting the PDF. One compile attempt and one transport attempt per run, consistently applying the existing held-out configuration to dev too; this differs from the default three-attempt interactive compiler. JSON response mode; thinking disabled; initial 32,768 tokens; 300-second provider timeout. Provider sampling defaults are unchanged; no deterministic seed. Four concurrent workers; latency includes contention. The exact request configuration is saved per run.", "",
             "Inventory: seven real insurer SBCs (not nine). The CMS completed example and blank template are not real insurer policies. Three EOCs and one benefits schedule are evaluated separately through the supported generic policy input. Two multi-plan brochures are excluded: no plan-selection input. The JSON inventories every local PDF and its exclusion reason.", "",
             "Kaiser and Highmark remain dev. All other insurer SBCs are held-out. This is a requested repeated measurement of a frozen pipeline, not a fresh untouched holdout: Cigna/Ambetter had already been measured in the repo. No held-out result was used to alter prompts, selectors or validators. Other-policy split tags follow insurer identity; Kaiser EOC was previously measured too.", "",
             "## Headline metrics", "",
             "| Group | Docs / runs | Extract | Valid JSON | Compile + validate | Rules retained / proposed | Validated-rule rate | Quote accuracy | Claim-ready | Key numbers, end-to-end | Mean seconds |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for key, m in report["aggregates"].items():
        lines.append(f"| {key} | {m['documents']} / {m['runs']} | {m['extraction_success']}/{m['runs']} | {m['valid_json']}/{m['runs']} | {m['compile_success']}/{m['runs']} | {m['retained_rules']}/{m['proposed_rules']} | {percent(m['validated_rule_rate'])} | {percent(m['retained_quote_accuracy'])} | {m['claim_ready']}/{m['runs']} | {percent(m['key_number_end_to_end_accuracy'])} | {m['elapsed_seconds']['mean']:.1f} |")
    lines += ["", "## Per-document results", "",
              "| Document | Split | Extract / JSON / compile | Retained rules (3 runs) | Rule-count variance | Validated-rule rate | Quote accuracy | Claim-ready | Key numbers | Deductible / OOP stable | Mean seconds |",
              "|---|---|---:|---|---:|---:|---:|---:|---:|---|---:|"]
    for d in report["documents"]:
        m, s = d["metrics"], d["stability"]
        lines.append(f"| {d['document_id']} | {d['group']}, {d['split']} | {m['extraction_success']} / {m['valid_json']} / {m['compile_success']} of 3 | {s['retained_rule_counts']} | {s['rule_count_population_variance']:.2f} | {percent(m['validated_rule_rate'])} | {percent(m['retained_quote_accuracy'])} | {m['claim_ready']}/3 | {percent(m['key_number_end_to_end_accuracy'])} | {s['deductible_stable_all_three']} / {s['oop_max_stable_all_three']} | {m['elapsed_seconds']['mean']:.1f} |")
    lines += ["", "## Citation and page checks", "",
              "| Group | Raw citations | Raw reference accuracy | Retained spans | Retained quote accuracy | Physical page locatable | Labeled-field page checks | Labeled-field page match |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key, m in report["aggregates"].items():
        lines.append(f"| {key} | {m['raw_citation_count']} | {percent(m['raw_quote_accuracy'])} | {m['retained_citation_count']} | {percent(m['retained_quote_accuracy'])} | {percent(m['physical_page_locatable_rate'])} | {m['key_field_page_checks']} | {percent(m['key_field_page_match_rate'])} |")
    lines += ["", "## Metric definitions and limitations", "",
              "- Extraction success means the production parser returned nonempty text; it is not a character-level or table-layout accuracy score. All three runs start from original PDF bytes, never cached extracted text.",
              "- Valid JSON is measured before validation. Compile success means the production compiler returned a validated (possibly partial) compilation without crashing. Proposed rules count raw rule-evidence entries; retained rules count validated financial/network/benefit rule paths. The validated-rule rate uses all proposals, including failed runs. Benefit rules are also counted separately in JSON. Missing proposals on transport/malformed-JSON failures contribute zero; this rate is not rule recall.",
              "- Quote accuracy is whitespace-normalized source containment, micro-averaged over cited spans including repetitions. Raw source-line references are measured separately from retained quotes. The current model cites line IDs, and local code copies the text, so high quote accuracy is mainly a reference-integrity/validator property, not proof that the right clause, column or number was selected.",
              "- The provider schema has no page-number field. Independently predicted page accuracy is N/A. Physical-page locatability is computed from exact offsets only when extraction preserved all pages. A separate limited check asks whether evidence for each labeled key field includes its independently labeled PDF page; broad multi-page citations can pass this check. This does not prove semantic page relevance for every cited line.",
              "- Claim-ready uses the existing measurement definition: at least one benefit, no unresolved items, and explicit balance-billing terms for every retained network. It does not guarantee coverage completeness, correct eligibility, all network tiers, a member identity, or successful real-claim replay. Conditionally executable counts omit the balance-billing requirement.",
              "- Stability uses population variance across the three retained-rule counts, with failed runs counted as zero. A second variance excludes failures in JSON. Deductible/OOP stability requires a present identical in-network value in all three runs; missing values never count as stable. Identical values can still be wrong.",
              "- Provider load from other concurrent work is uncontrolled. Transport timeouts are pipeline failures, not evidence of model-output nondeterminism. All attempts remain in the denominators; no successful replacement run was selected.",
              "- The configured 300-second provider timeout is an I/O timeout, not a hard wall-time deadline. Two failed requests took about 361 seconds; their full measured latency is retained.",
              "- No complete gold rule inventory exists. These results do not estimate all-service recall, condition/waiver accuracy, family deductible behavior, or patient-total accuracy. Only three runs and seven related insurer summaries limit generalization; no confidence intervals are claimed.", "",
              "## Pre-model numeric references", "",
              f"Labels were hand-read by Codex from the original cached SBC text at **{report['references']['labeled_at']}**, before any benchmark model output or prior compilation report was viewed. Their frozen file SHA256 is `{report['reference_file_sha256']}`. Labels were never provided to the compiler. Source-text hashes and source page numbers are saved in JSON.", "",
              "The existing `data/real_coverage_example_labels.csv` contains episode spending, not plan deductible/OOP/copay gold labels; its amounts were not used as substitutes. Six SBCs have five labeled fields each, scored three times (90 opportunities). Horizon's multiple in-network tiers cannot be faithfully identified by the current `in`/`out` schema, so its independently recorded tier values are disclosed but excluded from a single-network numeric accuracy score. EOCs/schedules have no hand labels in this benchmark.", "",
              "Numeric scope: individual annual in-network medical deductible/OOP, ordinary in-person primary/specialist care, and the non-admitted emergency facility. Service checks compare the pair (copay cents, coinsurance basis points), so coinsurance-only care is not called free. Multiple differing prices are ambiguous rather than selecting a favorable match. Key-number end-to-end accuracy counts missing/ambiguous fields and compile failures as nonmatches; observed accuracy excludes only missing fields. These checks do not establish service eligibility or fee-component completeness.", "",
              "| Document | Deductible cents | OOP cents | PCP copay cents / coin bps | Specialist copay cents / coin bps | ER copay cents / coin bps |",
              "|---|---:|---:|---|---|---|"]
    for doc, fields in report["references"]["labels"].items():
        cells = [str(fields[k]["value"]) for k in ("deductible", "oop_max")]
        cells += [f"{fields[k]['value']['copay_cents']} / {fields[k]['value']['coinsurance_bps']}" for k in ("primary_care", "specialist", "er")]
        lines.append("| " + doc + " | " + " | ".join(cells) + " |")
    lines += ["", "## Failures and missing fields", ""]
    for d in report["documents"]:
        for r in d["runs"]:
            issues = [f"{k}: {v['status']}" for k, v in r["key_numbers"].items() if v["status"] != "correct"]
            if r["failure"] or issues or r.get("dropped_rule_count"):
                lines.append(f"- {d['document_id']} run {r['run']}: failure={r['failure'] or 'none'}; dropped rules={r.get('dropped_rule_count', 0)}; " + (", ".join(issues) or "no scored numeric misses") + ".")
    lines += ["", "Failure codes are deliberately fixed, privacy-safe categories; exception messages, policy quotes, model responses and full compilations are not published. JSON includes all per-run timings, numeric predictions, citation counts, omissions and request audits. No failure was replaced by a retry or curated rule.", "",
              "## Provenance and reproducibility", "",
              f"Starting revision: `{report['revision']}`. Production files unchanged on disk during measurement: **{report['production_files_unchanged_during_measurement']}**. The compiler, provider, schema and PDF modules were imported once in a single process; concurrent on-disk edits were not reloaded. The initial hashes identify the measured implementation. pypdf: `{report['pypdf_version']}`. Python: `{report['python_version']}`. Production module hashes, manifest hash, PDF hashes, extraction hashes and the script hash at measurement start are in JSON.", "",
              "Reproduction (requires the ignored original PDFs, DEEPSEEK_API_KEY, and a manually reviewed numeric labels JSON):", "",
              "```sh", "timeout 3600 .venv/bin/python scripts/bench_real_sbc.py --labels data/real_private/benchmark-real-sbc/labels.json", "```", "",
              "The public JSON embeds the frozen numeric labels for reconstruction. The script never prints credentials or source text. Reports contain only metrics, numeric facts, identifiers and methodology; private PDFs and text remain ignored. `reports/evaluation-real-sbc.json` is not changed."]
    if report.get("verification"):
        check = report["verification"]
        lines += ["", "## Repository checks", "", check["summary"], ""]
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/benchmark-real-sbc.json")
    args = parser.parse_args()
    if not os.getenv("DEEPSEEK_API_KEY"):
        parser.error("DEEPSEEK_API_KEY is required")
    references = json.loads(args.labels.read_text())
    started = now()
    if datetime.fromisoformat(references["labeled_at"]) >= datetime.fromisoformat(started):
        parser.error("Labels must be frozen before the experiment")
    specs = inventory()
    report = dict(schema_version=1, kind="real_pdf_pipeline_benchmark", synthetic=False,
                  started_at=started, model=MODEL, runs_per_document=3, workers=args.workers,
                  methodology=METHODOLOGY,
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  python_version=sys.version.split()[0], pypdf_version=importlib.metadata.version("pypdf"),
                  code_hashes_before=fingerprints(), script_sha256=sha(Path(__file__).read_bytes()),
                  manifest_sha256=sha((ROOT / "data/real_manifest.csv").read_bytes()),
                  reference_file_sha256=sha(args.labels.read_bytes()), references=references,
                  inventory=specs, documents=[{**s, "runs": []} for s in specs if s["included"]])
    PRIVATE.mkdir(parents=True, exist_ok=True)
    checkpoint = PRIVATE / "checkpoint.json"
    if checkpoint.exists():
        parser.error("Checkpoint already exists; preserve it before starting a new measurement")
    checkpoint.write_text(json.dumps(report, indent=2) + "\n")
    by_id = {d["document_id"]: d for d in report["documents"]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(benchmark_run, d, run, references["labels"].get(d["document_id"], {}))
                   for run in range(1, 4) for d in report["documents"]]
        for future in as_completed(futures):
            result = future.result()
            by_id[result["document_id"]]["runs"].append(result)
            checkpoint.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps({k: result[k] for k in ("document_id", "run", "extraction_success", "valid_json", "compile_success", "retained_rules", "failure", "elapsed_seconds")}), flush=True)
    finalize(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown(report))
    print("Completed", len(futures), "runs", flush=True)


if __name__ == "__main__":
    main()
