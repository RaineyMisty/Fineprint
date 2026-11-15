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
}


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
    path = ROOT / "data/real_private/docs" / (stem + ".txt")
    document = path.read_bytes().decode("utf-8")
    report = dict(schema_version=1, synthetic=False, document_id=stem,
                  local_text_path=path.relative_to(ROOT).as_posix(),
                  source_sha256=hashlib.sha256(document.encode()).hexdigest(),
                  generated_at=datetime.now(timezone.utc).isoformat(),
                  revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  compiler_sha256=hashlib.sha256((ROOT / "fineprint/compiler.py").read_bytes()).hexdigest(),
                  providers_sha256=hashlib.sha256((ROOT / "fineprint/providers.py").read_bytes()).hexdigest(),
                  input="Unmodified complete pdftotext -layout text; form feeds delimit physical PDF pages.",
                  input_excerpts=source_excerpts(document),
                  excerpt_note="Input samples only, not validated executable rule evidence. No full policy text redistributed.",
                  runs=[])
    compilers = [FallbackCompiler()]
    if deepseek:
        compilers.append(LLMCompiler("deepseek"))
    for compiler in compilers:
        run = dict(provider=compiler.name, model=getattr(compiler, "model", None),
                   attempt_limit=getattr(compiler, "attempt_limit", 1), compilation=None)
        if compiler.name == "deepseek" and not os.getenv("DEEPSEEK_API_KEY"):
            run.update(status="skipped", error="DEEPSEEK_API_KEY absent; no request made.", elapsed_seconds=0)
        else:
            started = time.monotonic()
            try:
                compiled = compiler.compile(document, stem)
                run.update(status="validated", error=None, compilation=compiled.as_dict())
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
        report["runs"].append(run)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"real-{slug}-rules.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = [f"# Real {slug} policy compilation", "", f"Source: `{report['local_text_path']}` (private).",
             f"Text SHA256: `{report['source_sha256']}`.", "",
             "Existing compiler and shared provider prompt unchanged. Input is complete raw text; no manual transcription or gold rules.", ""]
    for run in report["runs"]:
        lines += [f"- **{run['provider']}** / {run['model'] or 'no model'}: **{run['status']}**. "
                  + (run['error'] or f"Validated after {run['compilation']['attempts']} attempt(s).")]
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
    args = parser.parse_args()
    # Independent provider requests, bounded to the four known documents.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(compile_document, slug, stem, deepseek=args.deepseek, output=args.output_dir)
                   for slug, stem in DOCUMENTS.items()]
        for future in futures:
            print(future.result(), flush=True)


if __name__ == "__main__":
    main()
