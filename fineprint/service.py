"""Application boundary shared by the HTTP API, UI and external integrations."""

from .comparison import compare
from .engine import CalculationError, calculate, scenario_dict
from .models import Case
from .validation import issue_dicts, links, validate


def analyze(case: Case) -> dict:
    issues = validate(case)
    report = {"validation": issue_dicts(issues), "links": links(case),
              "status": "ready", "scenarios": [], "comparisons": [], "summary": None,
              "method": "Deterministic policy evaluation; no LLM is used for arithmetic. All figures are USD cents.",
              "limitations": ["Individual annual, separate network accumulators; one unit/visit per claim line.",
                              "Allowed amounts must be supplied; rates are not inferred from an SBC.",
                              "Missing-fact endpoints are illustrative, not exhaustive outcomes or guaranteed savings.",
                              "Legal billing protections, family coordination, prior authorization, coding and medical necessity are not evaluated."]}
    try:
        scenarios = calculate(case)
    except CalculationError as exc:
        report.update(status="blocked", blocked_reason=str(exc))
        return report
    comparisons = [compare(case, scenario) for scenario in scenarios]
    report["scenarios"] = [scenario_dict(s) for s in scenarios]
    report["comparisons"] = comparisons
    totals = [s.patient_cents for s in scenarios]
    report["summary"] = {"scenario_count": len(scenarios), "conditional": any(s.conditional for s in scenarios),
                         "illustrated_min_patient_cents": min(totals), "illustrated_max_patient_cents": max(totals),
                         "eob_patient_cents": comparisons[0]["eob_patient_cents"],
                         "bill_patient_cents": comparisons[0]["bill_patient_cents"],
                         "potential_overpayment_min_cents": min(c["potential_overpayment_cents"] for c in comparisons),
                         "potential_overpayment_max_cents": max(c["potential_overpayment_cents"] for c in comparisons)}
    return report
