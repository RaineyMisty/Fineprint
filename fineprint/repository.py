"""Read-only synthetic fixture repository, bundled with the installed package."""

import json
import re
from pathlib import Path

from .adapters import CLAIM_ADAPTERS, bill_csv
from .extraction import PolicyExtractor
from .compiler import FallbackCompiler
from .models import ModelError, case_from_dict, to_dict

SAMPLES = Path(__file__).parent / "samples"


def list_cases(root: Path = SAMPLES):
    result = []
    for path in sorted(root.glob("*/manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        result.append({key: manifest[key] for key in ("id", "title", "summary", "insurer", "synthetic")})
    return result


def load_case(case_id: str, *, root: Path = SAMPLES, extractor: PolicyExtractor | None = None):
    if not re.fullmatch(r"[a-z0-9-]{1,80}", case_id):
        raise FileNotFoundError("Unknown case")
    directory = root / case_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    def read(name):
        return (directory / manifest[name]).read_text(encoding="utf-8")

    if extractor is None:
        compilation = FallbackCompiler().compile(read("policy_document"), case_id + "/policy.md")
        if compilation.output.unresolved:
            raise ModelError("Resolve unsupported policy clauses: " + "; ".join(compilation.output.unresolved))
        policy = compilation.policy
    else:
        # Legacy structured import remains explicit; the demo no longer reads gold.
        extracted = extractor.extract(read("policy_rules"))
        if extracted.review_required:
            raise ModelError("Provider-extracted policy requires review against source clauses. Save verified rules as curated policy JSON before loading this case.")
        policy = extracted.policy
    claim = CLAIM_ADAPTERS[manifest["claim_format"]](read("claim_document"), manifest["claim_context"])
    case = case_from_dict({"schema_version": "1.0", "id": manifest["id"], "title": manifest["title"],
                           "synthetic": manifest["synthetic"], "policy": to_dict(policy), "claim": to_dict(claim),
                           "bill": bill_csv(read("bill_document"), manifest["bill_context"]),
                           "allowed_evidence": manifest["allowed_evidence"]})
    documents = {"policy": read("policy_document"), "claim": read("claim_document"), "bill": read("bill_document")}
    return case, documents
