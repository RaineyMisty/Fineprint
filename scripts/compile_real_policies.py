"""Measure existing compilers on private, unmodified insurer text; no downloads.

Run with --deepseek to opt into sending these public policies to the provider.
Rejected responses are never published or replaced with manually invented rules.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
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

from fineprint.compiler import FallbackCompiler
from fineprint.models import ModelError
from fineprint.providers import LLMCompiler

DOCUMENTS = {
    "kaiser": "kaiser_2026_ca_gold80_sbc",
    "kaiser-eoc": "kaiser_2026_ca_gold80_eoc",
    "cigna": "cigna_2026_in_connect_gold_sbc",
    "highmark": "highmark_2026_pa_together_blue_gold_sbc",
    "ambetter": "ambetter_2026_ca_gold80_hmo_sbc",
}

DEV = ("kaiser", "highmark")
HELD_OUT = ("cigna", "ambetter")


def source_excerpts(document):
    """Small, verbatim input samples, explicitly separate from executable rules."""
    excerpts = []
    offset = 0
    for page, contents in enumerate(document.split("\f"), 1):
        for line in contents.splitlines(keepends=True):
            if "$" in line and any(word in line.lower() for word in ("deductible", "individual", "out-of-pocket")):
                quote = line.strip()[:160]
                start = offset + line.index(quote)
                excerpts.append(dict(quote=quote, start=start, end=start + len(quote), pdf_page=page))
                if len(excerpts) == 2:
                    return excerpts
            offset += len(line)
        offset += 1  # physical PDF page delimiter in pdftotext output
    return excerpts


def compile_document(slug, stem, *, deepseek=False, output=ROOT / "reports"):
    split = "dev" if slug in DEV else "held_out" if slug in HELD_OUT else "historical"
    existing = output / f"real-{slug}-rules.json"
    if split == "held_out" and existing.is_file() and json.loads(existing.read_text()).get("split") == "held_out":
        raise ValueError("Held-out measurement already recorded; refusing to read or rerun the source")
    path = ROOT / "data/real_private/docs" / (stem + ".txt")
    document = path.read_bytes().decode("utf-8")
    report = dict(schema_version=2, synthetic=False, document_id=stem, split=split,
                  local_text_path=path.relative_to(ROOT).as_posix(),
                  source_sha256=hashlib.sha256(document.encode()).hexdigest(),
                  generated_at=datetime.now(timezone.utc).isoformat(),
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  compiler_sha256=hashlib.sha256((ROOT / "fineprint/compiler.py").read_bytes()).hexdigest(),
                  providers_sha256=hashlib.sha256((ROOT / "fineprint/providers.py").read_bytes()).hexdigest(),
                  selection_sha256=hashlib.sha256((Path(__file__).resolve().parents[1] / "fineprint/policy_sections.py").read_bytes()).hexdigest(),
                  input="Original pdftotext -layout text; provider input uses ranked source sections with evidence checked against the full source.",
                  input_excerpts=source_excerpts(document),
                  excerpt_note="Input samples only, not validated executable rule evidence. No full policy text redistributed.",
                  runs=[])
    compilers = [FallbackCompiler()]
    if deepseek:
        live = LLMCompiler("deepseek", retries=1 if split == "held_out" else None)
        live.model = "deepseek-v4-pro"
        if split == "held_out":
            live.transport_attempt_limit = 1
        compilers.append(live)
    for compiler in compilers:
        run = dict(provider=compiler.name, model=getattr(compiler, "model", None),
                   attempt_limit=getattr(compiler, "attempt_limit", 1), compilation=None,
                   request_config=compiler.request_config if compiler.name == "deepseek" else None)
        if compiler.name == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
            run.update(status="skipped", error="DEEPSEEK_API_KEY absent; no request made.", elapsed_seconds=0)
        else:
            started = time.monotonic()
            try:
                compiled = compiler.compile(document, stem)
                run.update(status="validated", error=None, compilation=compiled.as_dict())
                run["claim_ready"] = bool(compiled.policy.benefits and not compiled.output.unresolved
                                          and all(t.balance_billing is not None for t in compiled.policy.networks.values()))
                run["conditionally_executable"] = bool(compiled.policy.benefits and not compiled.output.unresolved)
                run["benefit_rules"] = len(compiled.policy.benefits)
                run["validated_quote_spans"] = sum(len(r.evidence) for r in compiled.output.rule_evidence)
                run["distinct_source_spans"] = len({(e.start, e.end) for r in compiled.output.rule_evidence for e in r.evidence})
                run["quote_validation"] = "Every retained quote equals the full source slice at its saved offsets; whitespace alone may be normalized during location. Numeric occurrence and selector support checked locally; table interpretation is not a semantic proof."
                run["compiled_rows"] = [dict(label=b.label, service_category=b.service_category, codes=b.codes,
                                              network=b.network, conditions=b.conditions) for b in compiled.policy.benefits]
                run["not_compiled"] = compiled.output.coverage_gaps + compiled.output.unresolved
                run["row_inventory_note"] = "Compiled rows are measured retained rules. Omitted rows/reasons are the compiler's reported coverage gaps, not an independently exhaustive row-recall score."
                run["validated_rules"] = len(compiled.output.rule_evidence)
                run["unresolved"] = compiled.output.unresolved
                run["evidence_pages"] = [dict(rule_path=r.rule_path, pages=[
                    document[:e.start].count("\f") + 1 for e in r.evidence])
                    for r in compiled.output.rule_evidence]
            except ModelError as exc:
                # Provider transport errors already omit response bodies and credentials.
                error = str(exc)
                secret = os.getenv("DEEPSEEK_API_KEY")
                if secret:
                    error = error.replace(secret, "[REDACTED]")
                run.update(status="failed", error=error[:600])
            run["elapsed_seconds"] = round(time.monotonic() - started, 3)
            if compiler.name == "deepseek":
                run["request_config"] = compiler.request_config
                run["input_selection"] = getattr(compiler, "input_selection", None)
                run["attempt_audit"] = getattr(compiler, "attempt_audit", [])
        report["runs"].append(run)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"real-{slug}-rules.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = [f"# Real {slug} policy compilation", "", f"Split: **{split}**. Held-out documents use one provider request with no validation or transport retries.", "", f"Source: `{report['local_text_path']}` (private).",
             f"Text SHA256: `{report['source_sha256']}`.", "",
             "LLM input uses locally ranked cost-sharing source sections; evidence is located and validated against the complete original source. No manual gold rules or invented member IDs.", ""]
    for run in report["runs"]:
        lines += [f"- **{run['provider']}** / {run['model'] or 'no model'}: **{run['status']}**. "
                  + (run['error'] or f"Validated after {run['compilation']['attempts']} attempt(s).")]
        if run["status"] == "validated":
            lines += [f"  Validated rules: {run['validated_rules']}; claim-ready: **{run['claim_ready']}**."]
            lines += [f"  Service rules: {run['benefit_rules']}; validated quote spans: {run['validated_quote_spans']}; distinct spans: {run['distinct_source_spans']}.",
                      f"  Conditionally executable subset: **{run['conditionally_executable']}**. Missing billing terms need independent contract evidence; categories/conditions need reviewer assignment.",
                      "", "  Compiled services:"]
            lines += [f"  - {row['label']} ({row['network']}); category `{row['service_category']}`; conditions: {', '.join(row['conditions']) or 'none'}." for row in run["compiled_rows"]]
            lines += ["", "  Not compiled / limitations (provider-reported, not an exhaustive recall score):"]
            lines += [f"  - {item}" for item in run["not_compiled"]]
            lines += ["", "  Source-backed rule values:"]
            for rule in run["compilation"]["output"]["rule_evidence"]:
                lines += [f"  - `{rule['rule_path']}`: " + " | ".join(f"[{e['start']}:{e['end']}] “{' '.join(e['quote'].split())}”" for e in rule["evidence"])]
        if run.get("input_selection"):
            selection = run["input_selection"]
            lines += [f"  Source selection: {selection['selected_characters']}/{selection['source_characters']} characters; omitted sections: {selection['omitted']}.",
                      f"  Request configuration: `{json.dumps(run['request_config'])}`."]
    lines += ["", "Only validated compilations contain executable rules and clause evidence. A failure has `compilation: null`; no rule or patient total is inferred.",
              "", "Input excerpts (physical PDF pages; these are not compiled rules):", ""]
    for item in report["input_excerpts"]:
        lines += [f"- p. {item['pdf_page']}: “{item['quote']}”"]
    lines += ["", "Official links and rights notes: [metadata manifest](../data/real_manifest.csv). No redistribution license; PDF/text not in this repo."]
    (output / f"real-{slug}-rules.md").write_text("\n".join(lines) + "\n")
    return slug, [(run["provider"], run["status"]) for run in report["runs"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--documents", nargs="+", choices=list(DOCUMENTS), default=list(DEV),
                        help="Run only these documents when retrying a source-selection fix")
    args = parser.parse_args()
    # Independent provider requests, bounded to the four known documents.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(compile_document, slug, DOCUMENTS[slug], deepseek=args.deepseek, output=args.output_dir)
                   for slug in args.documents]
        for future in futures:
            print(future.result(), flush=True)


if __name__ == "__main__":
    main()
