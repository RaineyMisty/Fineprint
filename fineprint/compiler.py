"""Natural-language policy compiler. The fallback is deliberately bounded, never an LLM.

No insurer names or gold fixtures are consulted. Unknown language fails closed.
Source spans are Unicode character offsets into the exact submitted document.
"""

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
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
    # Omitted rows/networks do not invalidate independently supported benefits.
    coverage_gaps: list[str] = field(default_factory=list)


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
        return {"type": "object", "properties": props, "required": [f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING], "additionalProperties": False}
    if origin is list:
        return {"type": "array", "items": json_schema(args[0])}
    if origin is dict:
        # Policy network keys are fixed by the supported engine contract.
        return {"type": "object", "properties": {n: json_schema(args[1]) for n in ("in", "out")},
                "required": [], "additionalProperties": False}
    return {"type": {str: "string", int: "integer", bool: "boolean", type(None): "null"}[cls]}


OUTPUT_SCHEMA = json_schema(CompilerOutput)

# Providers supply quotes, never offsets. The saved/validated output still has
# exact Unicode spans into the original source, computed only by local code.
PROVIDER_SCHEMA = deepcopy(OUTPUT_SCHEMA)
# Source text is emitted once. Local code builds clause IDs/references from
# located quotes, so the provider cannot disagree with its own copied clause.
_provider_policy = PROVIDER_SCHEMA["properties"]["policy"]
del _provider_policy["properties"]["clauses"]
_provider_policy["required"].remove("clauses")
for _network in ("in", "out"):
    _terms = _provider_policy["properties"]["networks"]["properties"][_network]
    for _amount in ("deductible_cents", "oop_max_cents"):
        _terms["properties"][_amount] = {"anyOf": [_terms["properties"][_amount], {"type": "null"}]}
    for _key in ("deductible_clause", "oop_clause", "network_clause"):
        del _terms["properties"][_key]
        _terms["required"].remove(_key)
_benefit = _provider_policy["properties"]["benefits"]["items"]
del _benefit["properties"]["clause_ids"]
_benefit["required"].remove("clause_ids")
_evidence_schema = PROVIDER_SCHEMA["properties"]["rule_evidence"]["items"]["properties"]["evidence"]["items"]
for _key in ("start", "end"):
    del _evidence_schema["properties"][_key]
    _evidence_schema["required"].remove(_key)
# New requests select numbered source lines; quote-only clients remain accepted.
_line_evidence_schema = deepcopy(_evidence_schema)
del _line_evidence_schema["properties"]["quote"]
_line_evidence_schema["required"].remove("quote")
_line_evidence_schema["properties"]["source_lines"] = {"type": "array", "items": {"type": "integer", "minimum": 1}}
_line_evidence_schema["required"].append("source_lines")
PROVIDER_SCHEMA["properties"]["rule_evidence"]["items"]["properties"]["evidence"]["items"] = {
    "anyOf": [_line_evidence_schema, _evidence_schema]
}
PROVIDER_SCHEMA["properties"]["rule_evidence"]["items"]["properties"]["rule_path"]["description"] = (
    "Relative policy rule path, with NO policy. prefix: networks.in.deductible_cents, "
    "networks.in.oop_max_cents, networks.in.balance_billing (or networks.out.*); "
    "benefits.<actual benefit id> for the WHOLE benefit, without any field suffix."
)


def _normalized_text(text):
    return " ".join(text.split())


def _balance_supported(value, quotes):
    """Require explicit billing language, not an inferred network protection."""
    for quote in quotes:
        text = _normalized_text(quote).lower().replace("balance-bill", "balance bill")
        negative = bool(re.search(r"\b(?:no|not|never|cannot|can't)\b.{0,60}\bbalance bill", text)
                        or re.search(r"balance billing.{0,40}(?:not permitted|prohibited)", text))
        if value is False and negative:
            return True
        if value is True and not negative and re.search(r"\b(?:may|can|permitted|allowed)\b.{0,150}\bbalance bill", text):
            return True
    return False


def _selector_supported(benefit, quotes):
    category = benefit.get("service_category")
    codes = benefit["codes"]
    if category is not None:
        # Wrapped table headings can have other columns between their words.
        # Only the selector is reconstructed; every evidence quote remains an
        # exact source slice. Require the heading's literal tokens in order.
        tokens = re.findall(r"\w+|[^\w\s]", category.casefold())
        source = iter(re.findall(r"\w+|[^\w\s]", " ".join(quotes).casefold()))
        return not codes and bool(tokens) and all(any(word == token for word in source) for token in tokens)
    return bool(codes) and all(re.fullmatch(r"(?:\d{5}|[A-Z]\d{4})", code) and any(
        re.search(r"(?<!\w)" + re.escape(code) + r"(?!\w)", q) for q in quotes) for code in codes)


def _amount_supported(cents, quotes):
    text = " ".join(quotes)
    amounts = {int(Decimal(m.replace(",", "")) * 100) for m in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)}
    return cents in amounts or (cents == 0 and bool(re.search(r"\b(?:no deductible|deductible does not apply|none)\b", text, re.I)))


def _costs_supported(benefit, quotes):
    """Necessary numeric support; reject known arithmetic outside the engine."""
    text = " ".join(quotes)
    amounts = {int(Decimal(m.replace(",", "")) * 100) for m in re.findall(r"\$\s*([\d,]+(?:\.\d{1,2})?)", text)}
    rates = {int(Decimal(m) * 100) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)}
    copay, coin = benefit["copay_cents"], benefit["coinsurance_bps"]
    for quote in quotes:
        # Per-day episode limits cannot be converted to a single visit copay.
        for match in re.finditer(r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:copay\s*)?(?:/|per)\s*day", quote, re.I):
            if copay and copay == int(Decimal(match[1].replace(",", "")) * 100):
                return False
        if coin and (re.search(r"%\s*coinsurance.{0,80}(?:up to|minimum|maximum)", quote, re.I)
                     or re.search(r"\$[\d,/. $]+\s*(?:min|max)\b", quote, re.I)):
            return False
    if benefit.get("covered", True) and not copay and not coin and not benefit.get("deductible_applies", False):
        if not re.search(r"no charge|\$\s*0(?:[\s/.,]|$)|0\s*%", text, re.I):
            return False
    if benefit.get("covered") is False and not re.search(r"not covered|exclu(?:ded|sion)", text, re.I):
        return False
    return (not copay or copay in amounts) and (not coin or coin in rates)


def recover_evidence(value, document, document_id):
    """Locate supplied quotes; never correct words, numbers or punctuation.

    Whitespace alone may differ after PDF extraction. Saved quotes always equal
    the exact source slice. Unsupported benefits are removed and made unresolved;
    an incomplete network is removed together with its dependent benefits.
    """
    value = deepcopy(value)
    if type(value) is not dict:
        raise ModelError("output: expected object")
    compact = isinstance(value.get("policy"), dict) and "clauses" not in value["policy"]
    # Preserve strict schema checking (including unknown fields), but offsets
    # supplied by old clients are deliberately discarded before checking types.
    if compact:
        validate_schema(value, PROVIDER_SCHEMA)
        source_lines = document.splitlines(keepends=True)
        for rule in value["rule_evidence"]:
            expanded = []
            for evidence in rule["evidence"]:
                if "source_lines" not in evidence:
                    expanded.append(evidence)
                    continue
                for number in evidence["source_lines"]:
                    if not 1 <= number <= len(source_lines) or not source_lines[number - 1].strip():
                        raise ModelError("Evidence selected a nonexistent or blank source line")
                    expanded.append(dict(source_document_id=evidence["source_document_id"], section=evidence["section"],
                                         quote=source_lines[number - 1].strip()))
            rule["evidence"] = expanded
    else:
        if isinstance(value.get("rule_evidence"), list):
            for rule in value["rule_evidence"]:
                if isinstance(rule, dict) and isinstance(rule.get("evidence"), list):
                    for evidence in rule["evidence"]:
                        if isinstance(evidence, dict):
                            evidence["start"], evidence["end"] = 0, 0
        validate_schema(value)
    if compact:
        for net, terms in list(value["policy"]["networks"].items()):
            if terms["deductible_cents"] is None or terms["oop_max_cents"] is None:
                del value["policy"]["networks"][net]
                value["policy"]["benefits"] = [b for b in value["policy"]["benefits"] if b["network"] != net]
                benefit_paths = {"benefits." + b["id"] for b in value["policy"]["benefits"]}
                value["rule_evidence"] = [r for r in value["rule_evidence"] if
                    (r["rule_path"].startswith("benefits.") and r["rule_path"] in benefit_paths) or
                    (not r["rule_path"].startswith("benefits.") and not r["rule_path"].startswith(f"networks.{net}."))]
                value.setdefault("coverage_gaps", []).append(f"Network {net} omitted: deductible or OOP limit is not established. Claims in that network require separate review, including emergency exceptions.")
    expected_paths = {f"networks.{net}.{field}" for net in value["policy"]["networks"]
                      for field in ("deductible_cents", "oop_max_cents", "balance_billing")}
    expected_paths.update("benefits." + b["id"] for b in value["policy"]["benefits"])
    explicit_id = re.search(r"(?m)^\s*Policy:\s*([A-Za-z0-9][A-Za-z0-9_.:/-]*)(?=\s*\||\s*$)", document)
    if explicit_id and value["policy"]["id"] != explicit_id[1]:
        raise ModelError("policy.id must copy the explicit Policy: identifier from the source header: " + explicit_id[1]
                         + ". The evidence source document id is a different identifier.")
    if any(r["rule_path"] not in expected_paths for r in value["rule_evidence"]):
        raise ModelError("Invalid rule_evidence.rule_path. Use only these exact paths: "
                         + ", ".join(sorted(expected_paths))
                         + ". No 'policy.' prefix or benefit field suffix; group a benefit's supporting quotes together.")
    tokens = list(re.finditer(r"\S+", document))
    normalized = " ".join(t.group() for t in tokens)
    # Map normalized character positions back to original source positions.
    starts, ends = [], []
    for token in tokens:
        if starts:
            starts.append(token.start())  # spaces are never match endpoints
            ends.append(token.start())
        starts.extend(range(token.start(), token.end()))
        ends.extend(range(token.start() + 1, token.end() + 1))
    merged, dropped = {}, []
    for rule in value["rule_evidence"]:
        found = []
        for evidence in rule["evidence"]:
            quote = _normalized_text(evidence["quote"])
            index = normalized.find(quote) if quote else -1
            if evidence["source_document_id"] != document_id or index < 0:
                continue
            start, end = starts[index], ends[index + len(quote) - 1]
            found.append({**evidence, "quote": document[start:end], "start": start, "end": end})
        path = rule["rule_path"]
        if not found:
            dropped.append(path)
            continue
        if path not in merged:
            merged[path] = {**rule, "evidence": []}
        merged[path]["confidence_bps"] = min(merged[path]["confidence_bps"], rule["confidence_bps"])
        if rule["ambiguity"] != "none":
            merged[path]["ambiguity"] = rule["ambiguity"]
        for evidence in found:
            if evidence not in merged[path]["evidence"]:
                merged[path]["evidence"].append(evidence)
    if compact:
        clauses_by_span, references = {}, {}
        for path, rule in merged.items():
            references[path] = []
            for evidence in rule["evidence"]:
                span = (evidence["start"], evidence["end"])
                if span not in clauses_by_span:
                    clauses_by_span[span] = dict(id=f"source-{len(clauses_by_span) + 1}",
                                                text=evidence["quote"], location=evidence["section"])
                references[path].append(clauses_by_span[span]["id"])
        value["policy"]["clauses"] = list(clauses_by_span.values())
        for net, terms in value["policy"]["networks"].items():
            for field, ref in (("deductible_cents", "deductible_clause"), ("oop_max_cents", "oop_clause"),
                               ("balance_billing", "network_clause")):
                terms[ref] = next(iter(references.get(f"networks.{net}.{field}", [])), "unmatched-source")
        for benefit in value["policy"]["benefits"]:
            benefit["clause_ids"] = references.get("benefits." + benefit["id"], [])
    # Legacy clients still supply clauses; they must independently agree with
    # located quotes. No text, number or punctuation is repaired.
    clauses = {c["id"]: c for c in value["policy"]["clauses"]}
    for rule in merged.values():
        for evidence in rule["evidence"]:
            for clause in clauses.values():
                if _normalized_text(clause["text"]) == _normalized_text(evidence["quote"]):
                    clause["text"] = evidence["quote"]
    for net, terms in list(value["policy"]["networks"].items()):
        supported = True
        for field, ref_field in (("deductible_cents", "deductible_clause"), ("oop_max_cents", "oop_clause")):
            rule = merged.get(f"networks.{net}.{field}")
            ref = terms[ref_field]
            if (not rule or ref not in clauses or clauses[ref]["text"] not in {e["quote"] for e in rule["evidence"]}
                    or not _amount_supported(terms[field], [e["quote"] for e in rule["evidence"]])):
                supported = False
            if net == "out" and rule and not any(re.search(
                    r"out[\s-]*(?:of[\s-]*)?network|non[\s-]*participating", e["quote"], re.I)
                    for e in rule["evidence"]):
                supported = False
        if not supported:
            del value["policy"]["networks"][net]
            for field in ("deductible_cents", "oop_max_cents", "balance_billing"):
                path = f"networks.{net}.{field}"
                merged.pop(path, None)
                dropped.append(path)
        else:
            path = f"networks.{net}.balance_billing"
            rule = merged.get(path)
            quotes = {e["quote"] for e in rule["evidence"]} if rule else set()
            ref = terms["network_clause"]
            if terms["balance_billing"] is None:
                terms["network_clause"] = None
                merged.pop(path, None)
            elif (ref not in clauses or clauses[ref]["text"] not in quotes
                    or not _balance_supported(terms["balance_billing"], quotes)):
                terms["balance_billing"], terms["network_clause"] = None, None
                merged.pop(path, None)
                dropped.append(path)
    retained = []
    for benefit in value["policy"]["benefits"]:
        path = "benefits." + benefit["id"]
        rule = merged.get(path)
        quotes = {e["quote"] for e in rule["evidence"]} if rule else set()
        if (not _selector_supported(benefit, quotes)
                or benefit["network"] not in value["policy"]["networks"]
                or not rule or not benefit["clause_ids"] or any(
                ref not in clauses or clauses[ref]["text"] not in quotes for ref in benefit["clause_ids"]) or not _costs_supported(benefit, quotes)):
            merged.pop(path, None)
            dropped.append(path)
        else:
            retained.append(benefit)
    value["policy"]["benefits"] = retained
    value["rule_evidence"] = list(merged.values())
    referenced = {terms[key] for terms in value["policy"]["networks"].values()
                  for key in ("deductible_clause", "oop_clause", "network_clause") if terms[key] is not None}
    referenced.update(ref for benefit in retained for ref in benefit["clause_ids"])
    value["policy"]["clauses"] = [clause for clause in value["policy"]["clauses"] if clause["id"] in referenced]
    for path in sorted(set(dropped) - set(merged)):
        message = f"Dropped rule {path}: missing or unmatched source quote/clause/code/category/amount, or unsupported network; no executable rule retained."
        value["warnings"].append(message)
        value.setdefault("coverage_gaps", []).append(message)
    return value


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
        if set(value) - set(props) or set(schema["required"]) - set(value):
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
            for field in ("deductible_cents", "oop_max_cents", "balance_billing")
            if getattr(policy.networks[net], field) is not None} | {f"benefits.{b.id}" for b in policy.benefits}


def validate_output(value, document, document_id):
    validate_schema(value)
    output = decode(CompilerOutput, value, "output")
    p = output.policy
    if p.effective_from and p.effective_to and p.effective_from > p.effective_to:
        raise ModelError("Policy dates are reversed")
    clauses = {c.id: c for c in p.clauses}
    if len(clauses) != len(p.clauses) or len({b.id for b in p.benefits}) != len(p.benefits):
        raise ModelError("Duplicate clause or benefit IDs")
    paths = rule_paths(p)
    if not paths:
        dropped = [w for w in output.warnings if w.startswith("Dropped rule ")]
        raise ModelError("No supported executable rules found" + (". " + " ".join(dropped) if dropped else ""))
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
            if getattr(terms, field) is None:
                if ref is not None:
                    raise ModelError("Unknown network term must not have an executable clause reference")
                continue
            if ref not in clauses or clauses[ref].text not in [e.quote for e in evidence_by_path[f"networks.{net}.{field}"].evidence]:
                raise ModelError("Network clause must match its rule evidence")
            if field in ("deductible_cents", "oop_max_cents") and not _amount_supported(getattr(terms, field),
                    [e.quote for e in evidence_by_path[f"networks.{net}.{field}"].evidence]):
                raise ModelError("Network amount is not present in its source evidence")
            if field == "balance_billing" and not _balance_supported(terms.balance_billing,
                    [e.quote for e in evidence_by_path[f"networks.{net}.{field}"].evidence]):
                raise ModelError("Balance billing requires explicit source billing language")
    groups = {}
    for b in p.benefits:
        if not b.covered and (b.deductible_applies or b.copay_cents or b.coinsurance_bps):
            raise ModelError("Excluded service has covered cost sharing")
        quotes = [e.quote for e in evidence_by_path[f"benefits.{b.id}"].evidence]
        if not _selector_supported(to_dict(b), quotes):
            raise ModelError("Benefit code/category is not present in its source evidence")
        if not _costs_supported(to_dict(b), quotes):
            raise ModelError("Benefit cost share is not present in its source evidence")
        if not b.clause_ids or any(ref not in clauses or clauses[ref].text not in quotes for ref in b.clause_ids):
            raise ModelError("Benefit clauses must match its rule evidence")
        for code in b.codes or [b.service_category]:
            groups.setdefault((code, b.network, tuple(b.conditions)), []).append(b)
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


def default_provider():
    import os
    return os.getenv("FINEPRINT_LLM_PROVIDER") or ("deepseek" if os.getenv("DEEPSEEK_API_KEY") else "fallback")


def get_compiler(provider=None):
    import os
    name = provider or default_provider()
    if name == "fallback":
        return FallbackCompiler()
    from .providers import LLMCompiler
    return LLMCompiler(name)


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Compile English policy text with traceable rules")
    parser.add_argument("document", type=Path)
    parser.add_argument("--provider", choices=["fallback", "openai", "anthropic", "bedrock", "deepseek"])
    args = parser.parse_args()
    result = get_compiler(args.provider).compile(args.document.read_text(encoding="utf-8"), args.document.name)
    print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
