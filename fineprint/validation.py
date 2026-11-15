"""Semantic validation and explicit cross-document links, independent of arithmetic."""

import re
from dataclasses import asdict, dataclass

from .models import Case, benefit_matches


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


def validate(case: Case) -> list[Issue]:
    issues = []

    def add(code, path, message, severity="error"):
        issues.append(Issue(severity, code, path, message))

    def unique(items, path):
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)):
            add("duplicate_id", path, "IDs must be unique within this document.")
        if not ids:
            add("empty_document", path, "At least one entry is required.")

    p, c, b = case.policy, case.claim, case.bill
    for path, items in (("policy.clauses", p.clauses), ("policy.benefits", p.benefits),
                        ("claim.lines", c.lines), ("bill.lines", b.lines)):
        unique(items, path)
    if p.effective_from and p.effective_to and p.effective_from > p.effective_to:
        add("policy_dates", "policy", "Policy end precedes policy start.")
    identities = [("bill.member_id", b.member_id, c.member_id),
                                   ("claim.policy_id", c.policy_id, p.id),
                                   ("bill.claim_id", b.claim_id, c.id)]
    if p.member_id is not None:
        identities.append(("claim.member_id", c.member_id, p.member_id))
    for path, actual, expected in identities:
        if actual != expected:
            add("identity_mismatch", path, f"{actual!r} does not match {expected!r}.")
    if not p.networks or set(p.networks) - {"in", "out"} or any(r.network not in p.networks for r in p.benefits):
        add("networks", "policy.networks", "Benefits must reference established network terms; omitted networks are unsupported.")
    if set(c.accumulators) != set(p.networks):
        add("accumulators", "claim.accumulators", "Accumulator networks must match policy networks.")
    clauses = {cl.id for cl in p.clauses}

    def references(refs, path):
        if not refs or set(refs) - clauses:
            add("clause_reference", path, "Every rule must reference existing policy clauses.")

    for net, terms in p.networks.items():
        references([ref for ref in (terms.deductible_clause, terms.oop_clause, terms.network_clause) if ref is not None], f"policy.networks.{net}")
        if terms.balance_billing is None:
            relevant = [line for line in c.lines if line.network in (net, "unknown")]
            if any((fact := case.allowed_evidence.get(line.id)) is None or fact.source != "contract" or fact.balance_billing is None for line in relevant):
                add("incomplete_network", f"policy.networks.{net}.balance_billing", "Balance-billing terms are unknown; supply independent contract evidence for each affected line.")
        if terms.deductible_cents > terms.oop_max_cents:
            add("unsupported_plan", f"policy.networks.{net}", "This engine requires deductible <= OOP maximum.")
        a = c.accumulators.get(net)
        if a:
            for key, limit in (("deductible_paid_cents", terms.deductible_cents), ("oop_paid_cents", terms.oop_max_cents)):
                val = getattr(a, key)
                if val is None:
                    add("missing_accumulator", f"claim.accumulators.{net}.{key}", "Missing prior spending; endpoint scenarios will be shown.", "warning")
                elif val > limit:
                    add("accumulator_limit", f"claim.accumulators.{net}.{key}", "Opening accumulator exceeds policy limit.")
            if (a.deductible_paid_cents is not None and a.oop_paid_cents is not None
                    and a.deductible_paid_cents > a.oop_paid_cents):
                add("accumulator_order", f"claim.accumulators.{net}", "Deductible spending cannot exceed OOP spending in supported plans.")
    groups = {}
    for benefit in p.benefits:
        references(benefit.clause_ids, f"policy.benefits.{benefit.id}")
        if (not benefit.codes and not benefit.service_category) or (benefit.codes and benefit.service_category) or len(benefit.codes) != len(set(benefit.codes)):
            add("benefit_codes", f"policy.benefits.{benefit.id}", "Codes must be nonempty and unique.")
        if not benefit.covered and (benefit.copay_cents or benefit.coinsurance_bps or benefit.deductible_applies):
            add("excluded_cost_sharing", f"policy.benefits.{benefit.id}", "Excluded benefits cannot also specify covered cost sharing.")
        for code in benefit.codes or [benefit.service_category]:
            groups.setdefault((code, benefit.network, tuple(benefit.conditions)), []).append(benefit)
    for key, rules in groups.items():
        if len(rules) > 1 and (not rules[0].ambiguity_group or len({r.ambiguity_group for r in rules}) != 1):
            add("overlapping_rules", "policy.benefits", f"{key}: alternatives require one explicit ambiguity group.")
        if len({r.label for r in rules}) != len(rules):
            add("duplicate_interpretation", "policy.benefits", f"{key}: interpretation labels must be unique.")
    interpretations = {}
    for rules in groups.values():
        for rule in rules:
            if rule.ambiguity_group:
                interpretations.setdefault(rule.ambiguity_group, set()).add(rule.label)
    for key, rules in groups.items():
        for rule in rules:
            if rule.ambiguity_group and {r.label for r in rules} != interpretations[rule.ambiguity_group]:
                add("incomplete_interpretations", "policy.benefits", f"{key}: each shared ambiguity group must define the same interpretations for every affected code/network.")
    # A shared ambiguity group selects the same interpretation across all claim lines.
    for line in c.lines:
        path = f"claim.lines.{line.id}"
        if not re.fullmatch(r"(?:\d{5}|[A-Z]\d{4})", line.code):
            add("service_code", path, "Expected a five-digit CPT or letter + four-digit HCPCS code.")
        if ((p.effective_from is not None and line.service_date < p.effective_from)
                or (p.effective_to is not None and line.service_date > p.effective_to)):
            add("outside_policy", path, "Service date falls outside the policy period.")
        nets = [line.network] if line.network != "unknown" else ["in", "out"]
        for net in nets:
            if net not in p.networks:
                add("networks", path, f"Network {net} was not compiled; no coverage or emergency exception is inferred.")
            candidates = [r for r in p.benefits if r.network == net and benefit_matches(r, line)]
            if not candidates:
                add("missing_rule", path, f"No explicit coverage rule with confirmed conditions for {line.service_category or line.code}/{net}; calculation blocked.")
            elif len(candidates) > 1 and (not candidates[0].ambiguity_group or len({r.ambiguity_group for r in candidates}) != 1):
                add("overlapping_rules", path, "Confirmed category conditions select multiple rules; resolve before calculation.")
        if line.service_category:
            add("category_assignment", path, "Service category and conditions were supplied by the claim reviewer, not inferred from the procedure code.", "warning")
        if line.network == "unknown":
            add("unknown_network", path, "Network missing: evaluate both networks.", "warning")
        eob = line.insurer
        if eob.allowed_cents > line.billed_cents:
            add("allowed_exceeds_charge", path, "EOB allowed amount exceeds charge.")
        if eob.patient_cents + eob.insurer_paid_cents + eob.adjustment_cents != line.billed_cents:
            add("eob_arithmetic", path, "EOB patient + insurer + adjustment does not equal charge.")
        fact = case.allowed_evidence.get(line.id)
        if fact is None or fact.allowed_cents is None:
            add("missing_allowed", path, "Allowed amount missing: show illustrative $0 and full-charge endpoints.", "warning")
        elif fact.allowed_cents > line.billed_cents:
            add("allowed_exceeds_charge", f"allowed_evidence.{line.id}", "Evidence allowed amount exceeds charge.")
        if fact and fact.source == "unknown" and fact.allowed_cents is not None:
            add("evidence_source", f"allowed_evidence.{line.id}", "A known allowance requires a contract or EOB source.")
        if fact and fact.source == "eob":
            add("eob_dependency", path, "Cost sharing is independently evaluated, but allowance depends on the EOB.", "warning")
            if fact.allowed_cents != eob.allowed_cents:
                add("evidence_mismatch", f"allowed_evidence.{line.id}", "Evidence marked EOB must match the EOB allowance.")
    claim_ids = {line.id for line in c.lines}
    if set(case.allowed_evidence) - claim_ids:
        add("orphan_evidence", "allowed_evidence", "Evidence refers to nonexistent claim lines.")
    linked = set()
    for line in b.lines:
        path = f"bill.lines.{line.id}"
        match = next((cl for cl in c.lines if cl.id == line.claim_line_id), None)
        if not match:
            add("orphan_bill_line", path, "Bill line has no matching claim line.")
            continue
        if line.claim_line_id in linked:
            add("duplicate_link", path, "Multiple bill lines linked to one claim line; split/aggregation is not supported yet.")
        linked.add(line.claim_line_id)
        for field in ("provider_id", "service_date", "code"):
            if getattr(line, field) != getattr(match, field):
                add("line_mismatch", f"{path}.{field}", "Bill and claim disagree.")
        if line.charged_cents != match.billed_cents:
            add("charge_mismatch", path, "Bill charge differs from EOB charge.")
        if (line.insurance_paid_cents + line.adjustment_cents + line.patient_total_cents != line.charged_cents):
            add("bill_arithmetic", path, "Bill insurer + adjustment + patient paid + due does not equal charge.")
        if line.insurance_paid_cents != match.insurer.insurer_paid_cents:
            add("payment_mismatch", path, "Bill insurance credit differs from EOB payment.", "warning")
        if line.patient_total_cents != match.insurer.patient_cents:
            add("bill_eob_difference", path, "Bill total patient responsibility differs from EOB; review comparison.", "warning")
    for missing in claim_ids - linked:
        add("unbilled_claim_line", "bill.lines", f"Claim line {missing} is missing from the bill.")
    return issues


def links(case: Case) -> list[dict]:
    return [{"claim_line_id": cl.id, "member_id": case.claim.member_id,
             "provider_id": cl.provider_id, "service_date": cl.service_date,
             "code": cl.code, "claim_id": case.claim.id,
             "bill_line_ids": [bl.id for bl in case.bill.lines if bl.claim_line_id == cl.id]}
            for cl in case.claim.lines]


def issue_dicts(issues):
    return [asdict(i) for i in issues]
