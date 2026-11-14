"""Natural-language policy compiler. The fallback is deliberately bounded, never an LLM.

No insurer names or gold fixtures are consulted. Unknown language fails closed.
Source spans are Unicode character offsets into the exact submitted document.
"""

import hashlib
import json
import re
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from types import UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints

from .models import Benefit, Clause, ModelError, NetworkTerms, Policy, decode, to_dict


@dataclass(frozen=True)
class Evidence:
    source_document_id: str
    section: str
    quote: str
    start: int
    end: int


@dataclass(frozen=True)
class RuleEvidence:
    rule_path: str
    evidence: list[Evidence]
    confidence_bps: int
    ambiguity: str  # "none" or an explanation; confidence is not calibrated probability


@dataclass(frozen=True)
class CompilerOutput:
    policy: Policy
    rule_evidence: list[RuleEvidence]
    warnings: list[str]
    unresolved: list[str]


@dataclass(frozen=True)
class Compilation:
    output: CompilerOutput
    backend: str
    source_document_id: str
    source_sha256: str
    attempts: int

    @property
    def policy(self):
        return self.output.policy

    def as_dict(self):
        return to_dict(self)


def json_schema(cls):
    """Generate the closed JSON Schema used both by providers and local validation."""
    origin, args = get_origin(cls), get_args(cls)
    if origin in (Union, UnionType):
        return {"anyOf": [json_schema(t) for t in args]}
    if origin is Literal:
        return {"type": "string", "enum": list(args)}
    if is_dataclass(cls):
        props = {f.name: json_schema(get_type_hints(cls)[f.name]) for f in fields(cls)}
        for key, spec in props.items():
            if key.endswith("_cents"):
                spec.update(minimum=0, maximum=10**12)
            if key in ("coinsurance_bps", "confidence_bps"):
                spec.update(minimum=0, maximum=10000)
            if key in ("start", "end"):
                spec.update(minimum=0)
        return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if origin is list:
        return {"type": "array", "items": json_schema(args[0])}
    if origin is dict:
        # Policy network keys are fixed by the supported engine contract.
        return {"type": "object", "properties": {n: json_schema(args[1]) for n in ("in", "out")},
                "required": ["in", "out"], "additionalProperties": False}
    return {"type": {str: "string", int: "integer", bool: "boolean", type(None): "null"}[cls]}


OUTPUT_SCHEMA = json_schema(CompilerOutput)


def validate_schema(value, schema=OUTPUT_SCHEMA, path="output"):
    """Validate the exact JSON Schema vocabulary emitted above, without a dependency."""
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_schema(value, option, path)
                return
            except ModelError:
                pass
        raise ModelError(f"{path}: no matching schema")
    kind = schema["type"]
    expected = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}[kind]
    if type(value) is not expected:
        raise ModelError(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ModelError(f"{path}: outside enum")
    if kind == "object":
        props = schema["properties"]
        if set(value) != set(props):
            raise ModelError(f"{path}: missing or unknown fields")
        for key in value:
            validate_schema(value[key], props[key], f"{path}.{key}")
    if kind == "array":
        for index, item in enumerate(value):
            validate_schema(item, schema["items"], f"{path}[{index}]")
    if kind == "integer" and not schema.get("minimum", -10**20) <= value <= schema.get("maximum", 10**20):
        raise ModelError(f"{path}: outside numeric bounds")


def rule_paths(policy):
    return {f"networks.{net}.{field}" for net in policy.networks
            for field in ("deductible_cents", "oop_max_cents", "balance_billing")} | {f"benefits.{b.id}" for b in policy.benefits}


def validate_output(value, document, document_id):
    validate_schema(value)
    output = decode(CompilerOutput, value, "output")
    p = output.policy
    if p.effective_from > p.effective_to:
        raise ModelError("Policy dates are reversed")
    clauses = {c.id: c for c in p.clauses}
    if len(clauses) != len(p.clauses) or len({b.id for b in p.benefits}) != len(p.benefits):
        raise ModelError("Duplicate clause or benefit IDs")
    paths = rule_paths(p)
    if {r.rule_path for r in output.rule_evidence} != paths or len(output.rule_evidence) != len(paths):
        raise ModelError("Every executable rule must have exactly one evidence entry")
    for r in output.rule_evidence:
        if not r.evidence:
            raise ModelError("Rule has no evidence")
        for e in r.evidence:
            if (e.source_document_id != document_id or not 0 <= e.start < e.end <= len(document)
                    or document[e.start:e.end] != e.quote):
                raise ModelError("Evidence quote/span does not match the source document")
    evidence_by_path = {r.rule_path: r for r in output.rule_evidence}
    for net, terms in p.networks.items():
        if terms.deductible_cents > terms.oop_max_cents:
            raise ModelError("Unsupported deductible greater than OOP maximum")
        for field, ref in (("deductible_cents", terms.deductible_clause), ("oop_max_cents", terms.oop_clause), ("balance_billing", terms.network_clause)):
            if ref not in clauses or clauses[ref].text not in [e.quote for e in evidence_by_path[f"networks.{net}.{field}"].evidence]:
                raise ModelError("Network clause must match its rule evidence")
    groups = {}
    for b in p.benefits:
        if not b.codes or any(not re.fullmatch(r"(?:\d{5}|[A-Z]\d{4})", c) for c in b.codes):
            raise ModelError("Benefit requires explicit CPT/HCPCS codes")
        if not b.covered and (b.deductible_applies or b.copay_cents or b.coinsurance_bps):
            raise ModelError("Excluded service has covered cost sharing")
        quotes = [e.quote for e in evidence_by_path[f"benefits.{b.id}"].evidence]
        if not b.clause_ids or any(ref not in clauses or clauses[ref].text not in quotes for ref in b.clause_ids):
            raise ModelError("Benefit clauses must match its rule evidence")
        for code in b.codes:
            groups.setdefault((code, b.network), []).append(b)
    for rules in groups.values():
        if len(rules) > 1 and (not rules[0].ambiguity_group or len({b.ambiguity_group for b in rules}) != 1):
            raise ModelError("Overlapping benefits must retain an explicit ambiguity group")
    return output


def _blocks(document):
    """Read Markdown clause grids, numbered headings, and tagged paragraphs."""
    pattern = r"(?m)^\|\s*([A-Z][A-Z0-9]*(?:-[a-z]+)?)\s*\|\s*(.+?)\s*\|\s*$|^###\s+(?:\d+\.\s*)?([A-Z][A-Z0-9]*(?:-[a-z]+)?)\s*\n([^#]+?)(?=\n\s*\n|\Z)|^\[([A-Z][A-Z0-9]*(?:-[a-z]+)?)\]\s*(.+)$"
    for m in re.finditer(pattern, document):
        index = next(i for i in (1, 3, 5) if m.group(i))
        text = m.group(index + 1).strip()
        start = m.start(index + 1) + len(m.group(index + 1)) - len(m.group(index + 1).lstrip())
        yield m.group(index), text, start, start + len(text)


def _money(text):
    return int(Decimal(text.replace(",", "")) * 100)


class FallbackCompiler:
    """Pattern/table parser for a documented subset of English benefit language."""
    name = "fallback"

    def compile(self, document, document_id="uploaded-policy"):
        title = re.search(r"(?m)^# (.+?) — (.+)$", document)
        meta = re.search(r"Policy:\s*(\S+)\s*\| Member:\s*(\S+)\s*\| Period:\s*(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})\s*\| USD", document)
        if not title or not meta:
            raise ModelError("Fallback requires a '# Insurer — Plan' title and Policy/Member/Period/USD header; other formats need a provider or transcription")
        blocks = list(_blocks(document))
        if not blocks or len({b[0] for b in blocks}) != len(blocks):
            raise ModelError("Missing or duplicate source clause identifiers")
        clauses = [Clause(ref, text, f"Clause {ref}") for ref, text, _, _ in blocks]
        source = {ref: Evidence(document_id, f"Clause {ref}", text, start, end) for ref, text, start, end in blocks}
        order = [ref for ref, text, _, _ in blocks if "Apply deductible, then copay, then member coinsurance on the remaining allowance" in text
                 and "Round coinsurance half up to cents" in text and "Apply OOP cap in that order" in text]
        if len(order) != 1:
            raise ModelError("Missing supported calculation-order clause; fallback cannot assume arithmetic semantics")
        terms = {net: {} for net in ("in", "out")}
        refs = []
        benefits = []
        unresolved = []
        warnings = ["Deterministic pattern parser; confidence scores indicate parser coverage, not calibrated probabilities. No LLM was used."]

        def evidence(path, ids, ambiguity="none"):
            refs.append(RuleEvidence(path, [source[i] for i in ids], 10000 if ambiguity == "none" else 5000, ambiguity))

        for ref, text, _, _ in blocks:
            lower = text.lower()
            netmatch = re.search(r"\b(in|out)(?:-of)?-network\b", lower)
            net = netmatch.group(1) if netmatch else None
            limit = re.search(r"individual annual (in|out)(?:-of)?-network (deductible|oop maximum):\s*\$([\d,]+(?:\.\d{1,2})?)", lower)
            if limit:
                net, kind, amount = limit.groups()
                field, clause_field = ("deductible_cents", "deductible_clause") if kind == "deductible" else ("oop_max_cents", "oop_clause")
                if field in terms[net]:
                    raise ModelError("Conflicting network limits require review")
                if kind == "oop maximum" and not all(t in lower for t in ("cap covered deductible, copay and coinsurance together", "exclusions and permitted balance bills do not count", "network pools are separate")):
                    raise ModelError("Unsupported OOP pool or exclusions language")
                terms[net].update({field: _money(amount), clause_field: ref})
                evidence(f"networks.{net}.{field}", [ref])
                continue
            if "no balance billing" in lower and "participating-provider" in lower:
                net, balance = "in", False
            elif net == "out" and "may be balance billed" in lower and "outside oop" in lower:
                balance = True
            else:
                balance = None
            if balance is not None:
                if "balance_billing" in terms[net]:
                    raise ModelError("Conflicting balance billing terms")
                terms[net].update(balance_billing=balance, network_clause=ref)
                evidence(f"networks.{net}.balance_billing", [ref])
                continue
            codes = re.findall(r"\b(?:\d{5}|[A-Z]\d{4})\b", text)
            if not codes:
                if ref not in order:
                    unresolved.append(f"Clause {ref}: unsupported clause; no executable rule inferred")
                continue
            excluded = "excluded at full billed charge" in lower and "no deductible or oop credit" in lower
            # An exclusion with no network qualifier applies to both networks.
            nets = [net] if net else (["in", "out"] if excluded else [])
            waived = bool(re.search(r"(?:deductible (?:waived|does not apply)|waived deductible)", lower))
            copay = re.search(r"\$([\d,]+(?:\.\d{1,2})?) copay", lower)
            coin = re.search(r"(\d+(?:\.\d+)?)% (?:member )?coinsurance", lower)
            free = "no charge" in lower and waived
            ded = "deductible then" in lower or "subject to deductible then" in lower
            # A fixed copay without a percentage is interpreted as copay-only only
            # with an explicit waiver; other incomplete sharing terms fail closed.
            if not nets or not (excluded or free or (waived and copay and ("no coinsurance" in lower or "copay only" in lower)) or (ded and coin)):
                unresolved.append(f"Clause {ref}: missing network or unsupported cost-sharing wording")
                continue
            for n in nets:
                identifier = f"{ref}-{n}"
                b = Benefit(identifier, text.split(":")[0], sorted(set(codes)), n, not excluded,
                            ded and not waived and not excluded, _money(copay.group(1)) if copay and not excluded else 0,
                            int(Decimal(coin.group(1)) * 100) if coin and not excluded else 0, [ref, order[0]], "")
                benefits.append(b)
        if any(set(t) != {f.name for f in fields(NetworkTerms)} for t in terms.values()):
            raise ModelError("Fallback could not establish both network deductibles, OOP caps and balance-billing rules")
        # Preserve overlapping interpretations instead of silently selecting one.
        from dataclasses import replace
        overlap = {}
        for b in benefits:
            for code in b.codes:
                overlap.setdefault((code, b.network), []).append(b.id)
        for i, b in enumerate(benefits):
            keys = [f"{code}-{b.network}" for code in b.codes if len(overlap[(code, b.network)]) > 1]
            ambiguity = "Conflicting benefit clauses; no precedence established" if keys else "none"
            if keys:
                benefits[i] = replace(b, ambiguity_group="conflict-" + "-".join(sorted(keys)))
            evidence(f"benefits.{b.id}", b.clause_ids, ambiguity)
        if not benefits:
            unresolved.append("No supported benefits found")
        policy = Policy(meta[1], title[1], title[2], meta[2], meta[3], meta[4], "USD",
                        {n: NetworkTerms(**t) for n, t in terms.items()}, benefits, clauses)
        output = CompilerOutput(policy, refs, warnings, unresolved)
        checked = validate_output(to_dict(output), document, document_id)
        return Compilation(checked, self.name, document_id, hashlib.sha256(document.encode()).hexdigest(), 1)


def get_compiler(provider=None):
    import os
    name = provider or os.getenv("FINEPRINT_LLM_PROVIDER", "fallback")
    if name == "fallback":
        return FallbackCompiler()
    from .providers import LLMCompiler
    return LLMCompiler(name)


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Compile English policy text with traceable rules")
    parser.add_argument("document", type=Path)
    parser.add_argument("--provider", choices=["fallback", "openai", "anthropic", "bedrock"])
    args = parser.parse_args()
    result = get_compiler(args.provider).compile(args.document.read_text(encoding="utf-8"), args.document.name)
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
