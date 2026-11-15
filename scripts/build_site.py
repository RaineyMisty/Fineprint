"""Build public demo data from source policies and the real offline evaluator.

Run from any directory: python3 /path/to/Fineprint/scripts/build_site.py
No keys, dependencies or model calls are used. Offline results are rebuilt;
live LLM measurements are read only from committed reports.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fineprint.compiler import FallbackCompiler
from fineprint.eval import BENCHMARK
from fineprint.models import ModelError, case_from_dict, to_dict
from fineprint.repository import load_case
from fineprint.service import analyze


def collect_cases():
    """Compile prose before analysis; never export curated gold as compiled rules."""
    manifest = json.loads((BENCHMARK / "manifest.json").read_text(encoding="utf-8"))
    compiled = {}
    for spec in manifest["policies"]:
        document = (BENCHMARK / spec["document"]).read_text(encoding="utf-8")
        try:
            compilation = FallbackCompiler().compile(document, spec["id"])
            error = None
        except ModelError as exc:
            compilation, error = None, str(exc)
        compiled[spec["id"]] = (spec, document, compilation, error)

    cases = []
    for spec in manifest["cases"]:
        policy_spec, document, compilation, error = compiled[spec["policy"]]
        if not compilation:
            # A failed parser gets no gold-policy substitute and no invented total.
            cases.append(dict(id=spec["id"], title=spec["id"].replace("-", " ").capitalize(),
                              split=policy_spec["split"], synthetic=True, document=document,
                              compilation=None, case=None, report=dict(status="blocked",
                              blocked_reason=error, scenarios=[], comparisons=[], summary=None)))
            continue
        if "sample" in spec:
            original, _ = load_case(spec["sample"])
        else:
            original = case_from_dict(json.loads((BENCHMARK / spec["case"]).read_text(encoding="utf-8")))
        if not original.synthetic:
            raise ValueError("Public demo must contain only synthetic cases")
        case = replace(original, policy=compilation.policy)
        cases.append(dict(id=case.id, title=case.title.removeprefix("SYNTHETIC ").replace("-", " "),
                          split=policy_spec["split"], synthetic=True, document=document,
                          compilation=compilation.as_dict(), case=to_dict(case),
                          report=analyze(case, unresolved=compilation.output.unresolved)))
    return cases


def load_llm_evaluations(reports: Path, corpus_sha256: str):
    """Load saved measurements; never instantiate a live compiler during builds."""
    results = []
    for path in sorted(reports.glob("evaluation-deepseek-*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if (report.get("backend") != "deepseek" or report.get("synthetic") is not True
                or not report.get("model") or not report.get("generated_at")
                or report.get("corpus_sha256") != corpus_sha256):
            raise ValueError(f"Invalid or incompatible saved DeepSeek evaluation: {path.name}")
        results.append((path.name, report))
    return results


def build(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    # Invoke the same documented CLI judges can run; explicitly ignore live-provider env settings.
    subprocess.run([sys.executable, "-m", "fineprint.eval", "--provider", "fallback",
                    "--output-dir", str(output.resolve())], cwd=ROOT, check=True, capture_output=True, text=True)
    evaluation = json.loads((output / "evaluation.json").read_text(encoding="utf-8"))
    saved = load_llm_evaluations(ROOT / "reports", evaluation["corpus_sha256"])
    for filename, report in saved:
        (output / filename).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    payload = dict(schema_version=1, synthetic=True, backend="fallback", cases=collect_cases(),
                   evaluation=evaluation, llm_evaluations=[report for _, report in saved])
    (output / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / ".nojekyll").touch()
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    data = build(args.output_dir)
    print(f"Built {len(data['cases'])} synthetic cases · offline fallback · {args.output_dir}")


if __name__ == "__main__":
    main()
