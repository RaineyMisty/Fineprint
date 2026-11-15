"""Application boundary shared by the HTTP API, UI and external integrations."""

from .comparison import compare
from .engine import CalculationError, audit_policy, calculate, scenario_dict
from .models import Case
from .validation import Issue, issue_dicts, links, validate


def analyze(case: Case, *, unresolved=(), policy_audit=False) -> dict:
    issues = validate(case)
    issues += [Issue("error", "compiler_unresolved", "policy", text) for text in unresolved]
    report = {"validation": issue_dicts(issues), "links": links(case),
              "status": "ready", "scenarios": [], "comparisons": [], "summary": None,
              "method": "Deterministic policy evaluation; no LLM is used for arithmetic. All figures are USD cents.",
              "limitations": ["Individual annual, separate network accumulators; one unit/visit per claim line.",
                              "Allowed amounts must be supplied; rates are not inferred from an SBC.",
                              "Missing-fact endpoints are illustrative, not exhaustive outcomes or guaranteed savings.",
                              "Legal billing protections, family coordination, prior authorization, coding and medical necessity are not evaluated."]}
    if unresolved:
        report.update(status="blocked", blocked_reason="Resolve unsupported policy clauses before calculation: " + "; ".join(unresolved))
        return report
    try:
        scenarios = (audit_policy if policy_audit else calculate)(case)
    except CalculationError as exc:
        report.update(status="blocked", blocked_reason=str(exc))
        return report
    comparisons = [compare(case, scenario) for scenario in scenarios]
    if policy_audit:
        report["method"] += " Uncapped policy-formula audit, not the patient-facing amount constrained by the recorded bill."
    report["scenarios"] = [scenario_dict(s) for s in scenarios]
    report["comparisons"] = comparisons
    totals = [s.patient_cents for s in scenarios]
    report["summary"] = {"scenario_count": len(scenarios), "conditional": any(s.conditional for s in scenarios),
                         "illustrated_min_patient_cents": min(totals), "illustrated_max_patient_cents": max(totals),
                         "eob_patient_cents": comparisons[0]["eob_patient_cents"],
                         "bill_patient_cents": comparisons[0]["bill_patient_cents"],
                         "potential_overpayment_min_cents": min(c["potential_overpayment_cents"] for c in comparisons),
                         "potential_overpayment_max_cents": max(c["potential_overpayment_cents"] for c in comparisons)}
    summary = report["summary"]
    summary["bill_status"] = "overcharge" if summary["bill_patient_cents"] > max(totals) else "consistent"
    summary["unconfirmed_facts"] = list(dict.fromkeys(i.message for i in issues if i.code in
        ("missing_allowed", "missing_accumulator", "unknown_network")))
    return report


def analyze_policy_text(case: Case, document: str, document_id: str, *, compiler=None):
    """Compile the original text before any claim arithmetic; never read gold rules."""
    from dataclasses import replace
    from .compiler import get_compiler
    compilation = (compiler or get_compiler()).compile(document, document_id)
    updated = replace(case, policy=compilation.policy)
    from .models import to_dict
    return {"case": to_dict(updated), "documents": {"policy": document},
            "compilation": compilation.as_dict(), "report": analyze(updated, unresolved=compilation.output.unresolved)}


def check_documents(inputs: dict, *, compiler=None, compilation=None):
    """Pasted policy + EOB + bill -> compile policy, then independent recalculation."""
    from .compiler import get_compiler
    from .models import case_from_dict, to_dict
    from .repository import input_metadata, parse_inputs
    claim, bill, allowed = parse_inputs(inputs)
    metadata = input_metadata(inputs)
    document_id = metadata["id"] + "/policy.md" if metadata else "uploaded-policy"
    compilation = compilation or (compiler or get_compiler(inputs.get("provider"))).compile(inputs["policy"], document_id)
    case = case_from_dict({"schema_version": "1.0", "id": metadata["id"] if metadata else claim.id,
                           "title": metadata["title"] if metadata else "Your claim", "synthetic": metadata["synthetic"] if metadata else False,
                           "policy": to_dict(compilation.policy), "claim": to_dict(claim), "bill": bill, "allowed_evidence": allowed})
    report = analyze(case, unresolved=compilation.output.unresolved)
    report["limitations"].extend(compilation.output.coverage_gaps)
    return {"case": to_dict(case), "documents": {"policy": inputs["policy"]}, "compilation": compilation.as_dict(),
            "report": report}
