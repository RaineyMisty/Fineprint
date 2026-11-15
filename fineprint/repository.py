"""Read-only synthetic fixture repository, bundled with the installed package."""

import csv
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


def sample_inputs(case_id: str, *, root: Path = SAMPLES) -> dict:
    """Raw documents plus the facts a user would otherwise type in, for the web form."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", case_id):
        raise FileNotFoundError("Unknown case")
    directory = root / case_id
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))

    def read(name):
        return (directory / manifest[name]).read_text(encoding="utf-8")

    return {"id": manifest["id"], "title": manifest["title"], "summary": manifest["summary"],
            "insurer": manifest["insurer"], "synthetic": manifest["synthetic"],
            "inputs": {"policy": read("policy_document"), "eob": read("claim_document"), "bill": read("bill_document"),
                       "claim_format": manifest["claim_format"], "claim_context": manifest["claim_context"],
                       "bill_context": manifest["bill_context"], "allowed_evidence": manifest["allowed_evidence"]}}


def parse_inputs(inputs: dict):
    """Parse user-pasted EOB/bill text (supported adapter formats) into (claim, bill dict, allowed_evidence)."""
    if not isinstance(inputs, dict):
        raise ModelError("Expected a JSON object")
    for key in ("policy", "eob", "bill"):
        if not isinstance(inputs.get(key), str) or not inputs[key].strip():
            raise ModelError(f"Missing {key} text")
    fmt = inputs.get("claim_format")
    if fmt not in CLAIM_ADAPTERS:
        raise ModelError("claim_format must be one of: " + ", ".join(CLAIM_ADAPTERS))
    claim_context, bill_context = inputs.get("claim_context") or {}, inputs.get("bill_context") or {}
    if not isinstance(claim_context, dict) or not isinstance(bill_context, dict):
        raise ModelError("claim_context and bill_context must be objects")
    try:
        claim = CLAIM_ADAPTERS[fmt](inputs["eob"], claim_context)
        bill = bill_csv(inputs["bill"], bill_context)
    except (KeyError, TypeError, json.JSONDecodeError, csv.Error) as exc:
        raise ModelError(f"Could not read the EOB or bill in the selected format ({type(exc).__name__}: {exc})") from None
    if not claim.lines or not bill["lines"]:
        raise ModelError("No line items found in the " + ("EOB" if not claim.lines else "bill") + ". Check the pasted text and format.")
    return claim, bill, inputs.get("allowed_evidence") or {}
