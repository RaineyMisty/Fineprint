"""Deterministic policy evaluation. Never infer a rule from the insurer's result.

Supported order: deductible -> copay -> coinsurance on remaining allowance ->
OOP cap. Excluded charges and permitted balance billing stay outside the cap.
One unit/visit per line; per-network, individual, annual accumulators only.
"""

from dataclasses import asdict, dataclass, replace
from itertools import product
from math import prod

from .models import Benefit, Case, benefit_matches
from .validation import validate


class CalculationError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    explanation: str
    amount_cents: int
    clause_ids: list[str]


@dataclass(frozen=True)
class LineResult:
    claim_line_id: str
    network: str
    benefit_id: str
    allowed_cents: int
    deductible_cents: int
    copay_cents: int
    coinsurance_cents: int
    noncovered_cents: int
    balance_cents: int
    patient_cents: int
    insurer_paid_cents: int
    adjustment_cents: int
    opening_deductible_cents: int
    opening_oop_cents: int
    closing_deductible_cents: int
    closing_oop_cents: int
    trace: list[Step]


@dataclass(frozen=True)
class Scenario:
    id: str
    assumptions: list[str]
    conditional: bool
    lines: list[LineResult]
    patient_cents: int
    insurer_paid_cents: int
    closing_accumulators: dict


def _share(cents: int, bps: int) -> int:
    """Round positive rational currency once, half up, to the nearest cent."""
    return (cents * bps + 5000) // 10000


def _dimensions(case: Case):
    dims = []
    relevant = {line.network for line in case.claim.lines}
    if "unknown" in relevant:
        relevant = {"in", "out"}
    for net in sorted(relevant):
        a, t = case.claim.accumulators[net], case.policy.networks[net]
        ds = [a.deductible_paid_cents] if a.deductible_paid_cents is not None else [0, min(t.deductible_cents, a.oop_paid_cents if a.oop_paid_cents is not None else t.oop_max_cents)]
        pairs = []
        for ded in sorted(set(ds)):
            os = [a.oop_paid_cents] if a.oop_paid_cents is not None else [ded, t.oop_max_cents]
            for oop in sorted(set(os)):
                if ded <= oop:
                    label = f"{net}-network opening deductible ${ded / 100:.2f}, OOP ${oop / 100:.2f} (missing history: endpoint assumption)"
                    pairs.append(((ded, oop), label if None in (a.deductible_paid_cents, a.oop_paid_cents) else None))
        dims.append((f"acc:{net}", pairs))
    groups = {}
    for rule in case.policy.benefits:
        if rule.ambiguity_group and any(benefit_matches(rule, line) and line.network in (rule.network, "unknown") for line in case.claim.lines):
            groups.setdefault(rule.ambiguity_group, set()).add(rule.label)
    for group, labels in sorted(groups.items()):
        dims.append((f"group:{group}", [(label, f"Policy interpretation {group}: {label}") for label in sorted(labels)]))
    for line in case.claim.lines:
        if line.network == "unknown":
            dims.append((f"net:{line.id}", [(net, f"Line {line.id}: assume {net}-network") for net in ("in", "out")]))
        evidence = case.allowed_evidence.get(line.id)
        if evidence is None or evidence.allowed_cents is None:
            dims.append((f"allowed:{line.id}", [(val, f"Line {line.id}: allowed ${val / 100:.2f} (illustrative endpoint, obtain contracted rate)") for val in sorted({0, line.billed_cents})]))
    return dims


def _line(line, rule: Benefit, terms, allowed, ded_paid, oop_paid):
    refs = rule.clause_ids
    steps = [Step("Allowance supplied as evidence; it is not derived from policy cost-sharing rules.", allowed, refs)]
    ded = copay = coin = noncovered = balance = 0
    if not rule.covered:
        noncovered = line.billed_cents
        steps.append(Step("Explicit exclusion: full charge is patient responsibility and does not accrue to deductible or OOP.", noncovered, refs))
    else:
        deductible_remaining = max(0, terms.deductible_cents - ded_paid)
        raw_ded = min(allowed, deductible_remaining) if rule.deductible_applies else 0
        raw_copay = min(rule.copay_cents, allowed - raw_ded)
        raw_coin = _share(allowed - raw_ded - raw_copay, rule.coinsurance_bps)
        cap = max(0, terms.oop_max_cents - oop_paid)
        ded = min(raw_ded, cap)
        copay = min(raw_copay, cap - ded)
        coin = min(raw_coin, cap - ded - copay)
        steps.extend([
            Step(f"Deductible: min(allowance, remaining deductible {deductible_remaining} cents), then OOP cap; applies={rule.deductible_applies}.", ded, [terms.deductible_clause, terms.oop_clause, *refs]),
            Step(f"Copay: up to {rule.copay_cents} cents after deductible, then OOP cap.", copay, [*refs, terms.oop_clause]),
            Step(f"Coinsurance: {rule.coinsurance_bps}/10000 × {allowed - raw_ded - raw_copay} cents, half-up rounding, then OOP cap.", coin, [*refs, terms.oop_clause]),
            Step(f"Covered cost sharing capped by {cap} cents remaining OOP; exclusions and permitted balance bills do not count.", ded + copay + coin, [terms.oop_clause]),
        ])
        if terms.balance_billing:
            balance = line.billed_cents - allowed
        steps.append(Step("Network rule: excess charge is patient balance billing if permitted; otherwise a contractual write-off.", balance, [terms.network_clause] if terms.network_clause else []))
    patient = ded + copay + coin + noncovered + balance
    insurer = allowed - ded - copay - coin if rule.covered else 0
    adjustment = line.billed_cents - patient - insurer
    return LineResult(line.id, rule.network, rule.id, allowed, ded, copay, coin,
                      noncovered, balance, patient, insurer, adjustment, ded_paid, oop_paid,
                      ded_paid + ded, oop_paid + ded + copay + coin, steps)


def calculate(case: Case, *, max_scenarios=256) -> list[Scenario]:
    errors = [issue for issue in validate(case) if issue.severity == "error"]
    if errors:
        raise CalculationError("Resolve validation errors before recalculation: " + "; ".join(i.code for i in errors))
    dims = _dimensions(case)
    count = prod(len(options) for _, options in dims)
    if count > max_scenarios:
        raise CalculationError(f"{count} scenarios exceed the {max_scenarios} limit; supply missing facts or resolve ambiguities. No scenarios were silently dropped.")
    scenarios = []
    for n, choices in enumerate(product(*(options for _, options in dims)), 1):
        values = {key: val for (key, _), (val, _) in zip(dims, choices)}
        assumptions = [label for _, label in choices if label]
        accs = {key[4:]: list(value) for key, value in values.items() if key.startswith("acc:")}
        results = []
        for line in sorted(case.claim.lines, key=lambda item: (item.service_date, item.id)):
            net = values.get(f"net:{line.id}", line.network)
            candidates = [r for r in case.policy.benefits if benefit_matches(r, line) and net == r.network]
            candidates = [r for r in candidates if not r.ambiguity_group or values.get(f"group:{r.ambiguity_group}") == r.label]
            if len(candidates) != 1:
                raise CalculationError(f"Line {line.id}: ambiguity interpretations must resolve to exactly one rule per code/network.")
            evidence = case.allowed_evidence.get(line.id)
            allowed = values.get(f"allowed:{line.id}", evidence.allowed_cents if evidence else None)
            if evidence and evidence.source == "eob":
                assumptions.append(f"Line {line.id}: allowance relies on EOB ({evidence.reference}); cost-sharing audit only")
            terms = case.policy.networks[net]
            if terms.balance_billing is None:
                terms = replace(terms, balance_billing=evidence.balance_billing)
                assumptions.append(f"Line {line.id}: balance-billing treatment comes from independent contract evidence ({evidence.reference}), not the SBC.")
            if line.service_category:
                assumptions.append(f"Line {line.id}: reviewer assigned category {line.service_category}; confirmed conditions: {', '.join(line.confirmed_conditions) or 'none'}.")
            result = _line(line, candidates[0], terms, allowed, *accs[net])
            accs[net] = [result.closing_deductible_cents, result.closing_oop_cents]
            results.append(result)
        scenarios.append(Scenario(f"scenario-{n}", assumptions, bool(assumptions), results,
                                  sum(r.patient_cents for r in results), sum(r.insurer_paid_cents for r in results),
                                  {net: {"deductible_paid_cents": v[0], "oop_paid_cents": v[1]} for net, v in accs.items()}))
    return scenarios


def scenario_dict(scenario: Scenario):
    return asdict(scenario)
