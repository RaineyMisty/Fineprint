"""Measure the production PDF/DeepSeek/validation path on real insurer SBCs.

No policy text, model responses, evidence quotes or exception messages are saved.
Run with a pre-model, manually reviewed numeric label JSON in the ignored directory.
After: one pipeline run per SBC, plus one conditional retry after failure.
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
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fineprint.documents_pdf import extract_upload
from fineprint.providers import LLMCompiler

MODEL = "deepseek-v4-pro"
PRIVATE = ROOT / "data/real_private/benchmark-real-sbc"
CODE_FILES = ["fineprint/providers.py", "fineprint/compiler.py", "fineprint/models.py",
              "fineprint/validation.py", "fineprint/policy_sections.py", "fineprint/documents_pdf.py",
              "fineprint/interpretations.py"]



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
        if kind != "SBC":
            continue
        included, reason = True, None
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
        request = compiler.transport

        def observe(prompt, schema):
            response = request(prompt, schema)
            try:
                value = json.loads(response) if isinstance(response, str) else response
                record["valid_json"] = True
                record["proposed_rules"] += proposed_rules(value)
                for key, count in citation_metrics(value, document).items():
                    record["raw_citations"][key] += count
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
            record["transport_audit"] = getattr(compiler, "transport_audit", [])
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


def percent(value):
    return "N/A" if value is None else f"{value:.1%}"


def summarize_phase(phase, *, after=False):
    for d in phase['documents']:
        d['runs'].sort(key=lambda r: r['run'])
        d['metrics'] = aggregate(d['runs'])
        if after:
            d['first_try_success'] = d['runs'][0]['compile_success']
            d['retry_attempted'] = len(d['runs']) > 1
            d['success_after_one_retry'] = d['retry_attempted'] and d['runs'][-1]['compile_success']
            d['eventual_success'] = d['runs'][-1]['compile_success']
            d['stability'] = {'measured': False, 'reason': 'One initial run plus failure-only retry; not independent repeated samples'}
        else:
            d['stability'] = stability(d['runs'])
    phase['aggregates'] = {}
    for split in ('dev', 'held_out', 'all'):
        docs = [d for d in phase['documents'] if split == 'all' or d['split'] == split]
        all_calls = [r for d in docs for r in d['runs']]
        # Final document outcomes exclude duplicate failure opportunities; call metrics retain them.
        outcomes = [d['runs'][-1] for d in docs] if after else all_calls
        m = aggregate(outcomes)
        if after:
            m.update(first_try_success=sum(d['first_try_success'] for d in docs),
                     retry_attempted=sum(d['retry_attempted'] for d in docs),
                     success_after_one_retry=sum(d['success_after_one_retry'] for d in docs),
                     total_pipeline_calls=len(all_calls), all_call_metrics=aggregate(all_calls),
                     total_document_latency_mean=statistics.mean(sum(r['elapsed_seconds'] for r in d['runs']) for d in docs),
                     transport_attempts=sum(len(r.get('transport_audit', [])) for r in all_calls),
                     compile_response_attempts=sum(len(r.get('attempt_audit', [])) for r in all_calls))
            # Retention/quote accounting includes all proposals, even failed first calls.
            accounting = m['all_call_metrics']
            for key in ('proposed_rules', 'retained_rules', 'benefit_rules', 'validated_rule_rate',
                        'raw_citation_count', 'raw_quote_accuracy', 'retained_citation_count', 'retained_quote_accuracy'):
                m[key] = accounting[key]
        phase['aggregates']['sbc:' + split] = m
    return phase


def sbc_baseline(source):
    source = source.get('before', source)
    keys = ('started_at', 'completed_at', 'revision', 'model', 'python_version', 'pypdf_version',
            'code_hashes_before', 'code_hashes_after', 'script_sha256', 'workers')
    phase = {k: source[k] for k in keys if k in source}
    phase['protocol'] = 'Three independent one-attempt runs per SBC; original measured numbers, never rerun'
    phase['documents'] = [d for d in source['documents'] if d['document_type'] == 'SBC']
    return summarize_phase(phase)


def markdown(report):
    before, after = report['before'], report['after']
    lines = ['# Real SBC benchmark: before and after', '',
             '**Scope: Summary of Benefits and Coverage documents only**', '',
             f"Date: {after['started_at'][:10]}. Exact requested model: `{MODEL}`. Seven insurer SBCs; CMS sample/template are excluded. No non-SBC document is part of this benchmark.", '',
             '## Protocol and changes', '',
             'The production path is PDF bytes → `extract_upload(policy)` → `LLMCompiler(deepseek).compile` → source-evidence recovery and validation. Kaiser and Highmark remain dev; Aetna, Ambetter, Cigna, Horizon and Oscar remain held-out. Previously tested holdouts are not newly unseen.', '',
             'Before preserves all 21 SBC runs from the original measurement (three independent runs per SBC, one compile/transport attempt). After follows the revised instruction: one initial pipeline call per SBC, plus one further call only if the first fails. A validated partial compilation counts as success and is not retried merely for missing fields. There is no after-fix three-run stability measurement.', '',
             'General changes are confined to `fineprint/providers.py`:', '',
             '- DeepSeek transport now permits three attempts total (two retries), using the existing exponential backoff of 1 and 2 seconds for transient HTTP/transport/malformed-envelope errors. Exhausted transport retries do not multiply through compile retries.',
             '- Default DeepSeek I/O timeout increased from 300 to 450 seconds; the existing environment override remains available. This is not a hard total wall-time deadline.',
             '- Requests explicitly set temperature to zero with thinking disabled. No seed is sent: the endpoint does not document one. Lower temperature does not guarantee identical responses. [DeepSeek API reference](https://api-docs.deepseek.com/api/create-chat-completion/).',
             '- A no-supported-rules validation result receives at most one retry, using the existing general validation-feedback mechanism. There is no insurer-specific prompt or parser change.',
             '- A privacy-safe transport attempt audit records only status and elapsed seconds.', '',
             f"After uses {after['workers']} concurrent document workers and one normal compile-validation attempt per pipeline call, plus the new no-supported-rules retry. Internal transport/compile retries can occur inside the first or second pipeline call; first-try success below means first **pipeline call**, not first HTTP request. All internal attempts are recorded. No gold labels enter the request.", '',
             '**Comparison caveat:** the shared repository also changed between phases. The after run includes concurrent general compiler/validation fixes by another agent, in addition to this task’s client changes. This is an operational before/after comparison, not an isolated causal experiment. Full code hashes and changed-file lists are in JSON. Provider load and retry effort also differ.', '',
             '## Headline metrics', '',
             '| Phase / split | Outcome denominator | Extraction | Valid JSON | Validated compile | First pipeline call | Recovered on second call | Rules retained / proposed | Rule retention | Quote accuracy | Claim-ready | Key numbers |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for name, phase in [('Before', before), ('After', after)]:
        for split in ('dev', 'held_out', 'all'):
            m = phase['aggregates']['sbc:' + split]
            n = m['runs']
            first = f"{m['first_try_success']}/{m['documents']}" if name == 'After' else 'N/A'
            recovered = f"{m['success_after_one_retry']}/{m['retry_attempted']}" if name == 'After' else 'N/A'
            lines.append(f"| {name} / {split} | {n} {'documents' if name == 'After' else 'runs'} | {m['extraction_success']}/{n} | {m['valid_json']}/{n} | {m['compile_success']}/{n} | {first} | {recovered} | {m['retained_rules']}/{m['proposed_rules']} | {percent(m['validated_rule_rate'])} | {percent(m['retained_quote_accuracy'])} | {m['claim_ready']}/{n} | {percent(m['key_number_end_to_end_accuracy'])} |")
    lines += ['', 'After outcome rates and key-number accuracy use one final outcome per document. Proposed-rule and citation accounting include failed initial calls and all internal response attempts; all-call aggregates are separately saved in JSON. Recovery 0/0 means no second call was needed.', '',
              '## Per-document results', '',
              '| Document | Split | Before validated / 3 | Before rule counts | Before variance | Before deductible / OOP stable | After first call | Second call needed / recovered | After retained / proposed rules | After key numbers | Total after seconds |',
              '|---|---|---:|---|---:|---|---|---|---:|---:|---:|']
    old = {d['document_id']: d for d in before['documents']}
    for d in after['documents']:
        b = old[d['document_id']]
        final = d['runs'][-1]
        score = aggregate([final])
        s = b['stability']
        lines.append(f"| {d['document_id']} | {d['split']} | {b['metrics']['compile_success']}/3 | {s['retained_rule_counts']} | {s['rule_count_population_variance']:.2f} | {s['deductible_stable_all_three']} / {s['oop_max_stable_all_three']} | {d['first_try_success']} | {d['retry_attempted']} / {d['success_after_one_retry']} | {d['metrics']['retained_rules']}/{d['metrics']['proposed_rules']} | {percent(score['key_number_end_to_end_accuracy'])} | {sum(r['elapsed_seconds'] for r in d['runs']):.1f} |")
    lines += ['', '**After stability: not measured.** Failure-only retries cannot estimate nondeterministic run-to-run variance. Before population variance includes failures as zero; successful-only variance and exact deductible/OOP values remain in JSON.', '',
              '## Citation, page and latency checks', '',
              '| Phase / split | Raw reference accuracy | Retained spans | Retained quote accuracy | Physical page locatable | Key-field page checks / match | Mean elapsed seconds |',
              '|---|---:|---:|---:|---:|---|---:|']
    for name, phase in [('Before', before), ('After', after)]:
        for split in ('dev', 'held_out', 'all'):
            m = phase['aggregates']['sbc:' + split]
            elapsed = m.get('total_document_latency_mean', m['elapsed_seconds']['mean'])
            lines.append(f"| {name} / {split} | {percent(m['raw_quote_accuracy'])} | {m['retained_citation_count']} | {percent(m['retained_quote_accuracy'])} | {percent(m['physical_page_locatable_rate'])} | {m['key_field_page_checks']} / {percent(m['key_field_page_match_rate'])} | {elapsed:.1f} |")
    lines += ['', 'Latency is measured from worker start, excluding queue time. After document latency includes both calls when a retry was necessary; each extraction/compile latency is also saved. The reported provider timeout is per I/O, not a total deadline.', '',
              '## Pre-model reference labels', '',
              f"Codex hand-read the reference values from original SBC text at **{report['references']['labeled_at']}**, before viewing any benchmark model output or prior compilation report. The unchanged reference-file SHA256 is `{report['reference_file_sha256']}`. These same labels were frozen for both phases; they were not fed to the compiler.", '',
              'The existing coverage-example CSV labels whole episodes, not the requested plan limits/copays. It is not used as plan-field gold. Six SBCs have five reference fields each: 90 before opportunities and 30 after final-outcome opportunities. Horizon has multiple in-network tiers that cannot be identified faithfully by the current in/out schema; its tier values are recorded, but excluded from the single-network numeric score.', '',
              '| Document | Deductible cents | OOP cents | PCP copay cents / coin bps | Specialist copay cents / coin bps | ER copay cents / coin bps |',
              '|---|---:|---:|---|---|---|']
    for doc, fields in report['references']['labels'].items():
        cells = [str(fields[k]['value']) for k in ('deductible', 'oop_max')]
        cells += [f"{fields[k]['value']['copay_cents']} / {fields[k]['value']['coinsurance_bps']}" for k in ('primary_care', 'specialist', 'er')]
        lines.append('| ' + doc + ' | ' + ' | '.join(cells) + ' |')
    lines += ['', '## Definitions and caveats', '',
              '- Extraction success means nonempty production-parser text, not verified table or character accuracy. No cached text replaces PDF extraction.',
              '- Valid JSON is observed before validation. Compile success is a returned validated, potentially partial compilation. Proposed rules are raw rule-evidence entries; retained rules are validated financial/network/benefit paths. Retention is not all-service recall. All emitted proposals, including failed internal attempts, remain in its denominator.',
              '- Quote accuracy means whitespace-normalized source containment. Line IDs are copied locally into exact quotes, so high accuracy mainly measures reference integrity, not semantic correctness. Duplicate citations are counted. Invalid raw references remain in raw accuracy.',
              '- No page-number prediction exists in the schema: independently predicted page accuracy is N/A. Physical-page location is available only when extraction retains all pages. The limited labeled-field check asks whether its evidence includes its reference PDF page; broad citations can pass without proving correct interpretation.',
              '- Claim-ready uses the existing benchmark definition: benefits present, no unresolved items, and explicit balance-billing terms for every retained network. It does not prove complete coverage, correct conditions/waivers or successful real-claim processing.',
              '- Numeric scoring covers individual in-network medical deductible/OOP, ordinary in-person primary/specialist care and non-admitted emergency facility cost sharing. Service scores compare copay and coinsurance jointly. Missing/ambiguous fields and failed final outcomes are nonmatches; observed-only accuracy excludes missing fields. Conditions and fee-component completeness are not scored.',
              '- Seven documents are a small corpus. No confidence intervals, all-rule gold recall or patient-total correctness is claimed. Concurrent traffic and transport failures affect latency. Before failures contribute zero to rule variance; this is not pure model-output variance.', '',
              '## Failures and omissions', '']
    for name, phase in [('Before', before), ('After', after)]:
        for d in phase['documents']:
            for r in d['runs']:
                misses = [f"{field}: {v['status']}" for field, v in r['key_numbers'].items() if v['status'] != 'correct']
                if r['failure'] or misses or r.get('dropped_rule_count'):
                    lines.append(f"- {name}, {d['document_id']}, call {r['run']}: failure={r['failure'] or 'none'}; dropped rules={r.get('dropped_rule_count', 0)}; " + (', '.join(misses) or 'no scored numeric misses') + '.')
    lines += ['', 'Failures use fixed privacy-safe codes. No raw model response, policy text, evidence quote or free-form exception message is published.', '',
              '## Provenance and verification', '',
              f"Before revision: `{before['revision']}`. After starting revision: `{after['revision']}` plus the recorded DeepSeek client patch. Modules are imported once per phase; on-disk concurrent edits are not reloaded. PDF hashes, extraction hashes, source-label hashes, script hashes, dependency versions, code hashes and attempt audits are in JSON. The before baseline was preserved from commit `f40e893`; only its SBC rows are retained here.", '',
              report.get('verification', {}).get('summary', 'Repository verification pending.'), '',
              'Private PDFs/text remain gitignored. `reports/evaluation-real-sbc.json` is unchanged by this task.', '',
              'Reproduction (requires ignored PDFs and the frozen labels; preserve the baseline before rerunning):', '',
              '```sh', 'timeout 1500 .venv/bin/python scripts/bench_real_sbc.py --labels data/real_private/benchmark-real-sbc/labels.json --before data/real_private/benchmark-real-sbc/before-sbc.json --workers 7', '```']
    return '\n'.join(lines).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=7)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/benchmark-real-sbc.json')
    args = parser.parse_args()
    if not os.getenv('DEEPSEEK_API_KEY'):
        parser.error('DEEPSEEK_API_KEY is required')
    references = json.loads(args.labels.read_text())
    before = sbc_baseline(json.loads(args.before.read_text()))
    started = now()
    specs = inventory()
    assert {d['document_id']: d['pdf_sha256'] for d in before['documents']} == {d['document_id']: d['pdf_sha256'] for d in specs}
    after = dict(started_at=started, model=MODEL, workers=args.workers,
                 protocol='One initial pipeline call, one conditional retry only on failure; no repeated-run stability',
                 revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                 python_version=sys.version.split()[0], pypdf_version=importlib.metadata.version('pypdf'),
                 code_hashes_before=fingerprints(), script_sha256=sha(Path(__file__).read_bytes()),
                 documents=[{**s, 'runs': []} for s in specs])
    report = dict(schema_version=2, kind='real_sbc_before_after_benchmark', synthetic=False,
                  scope='Scope: Summary of Benefits and Coverage documents only', model=MODEL,
                  references=references, reference_file_sha256=sha(args.labels.read_bytes()),
                  manifest_sha256=sha((ROOT / 'data/real_manifest.csv').read_bytes()),
                  before=before, after=after,
                  changed_production_files_between_phases=[name for name, digest in after['code_hashes_before'].items()
                                                          if before['code_hashes_before'].get(name) != digest])
    PRIVATE.mkdir(parents=True, exist_ok=True)
    checkpoint = PRIVATE / 'after-checkpoint.json'
    if checkpoint.exists():
        parser.error('After checkpoint already exists; preserve it before a new measurement')
    lock = Lock()

    def measure_document(spec):
        for call in (1, 2):
            result = benchmark_run(spec, call, references['labels'].get(spec['document_id'], {}))
            with lock:
                spec['runs'].append(result)
                checkpoint.write_text(json.dumps(report, indent=2) + '\n')
                print(json.dumps({k: result[k] for k in ('document_id', 'run', 'extraction_success', 'valid_json', 'compile_success', 'retained_rules', 'failure', 'elapsed_seconds')}), flush=True)
            if result['compile_success']:
                break

    checkpoint.write_text(json.dumps(report, indent=2) + '\n')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(measure_document, spec) for spec in after['documents']]
        for future in as_completed(futures):
            future.result()
    summarize_phase(after, after=True)
    after['completed_at'] = now()
    after['code_hashes_after'] = fingerprints()
    after['wall_seconds'] = (datetime.fromisoformat(after['completed_at']) - datetime.fromisoformat(started)).total_seconds()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    args.output.with_suffix('.md').write_text(markdown(report))
    print('Completed', len(specs), 'SBCs', flush=True)


if __name__ == '__main__':
    main()
