"""Three-way reconciliation. A favorable scenario is a question, not a payment instruction."""

from .engine import Scenario
from .models import Case


def compare(case: Case, scenario: Scenario) -> dict:
    rows = []
    for result in scenario.lines:
        claim = next(cl for cl in case.claim.lines if cl.id == result.claim_line_id)
        bill = next(bl for bl in case.bill.lines if bl.claim_line_id == claim.id)
        eob = claim.insurer
        refs = sorted({ref for step in result.trace for ref in step.clause_ids})
        explanations = []
        terms = case.policy.networks[result.network]
        benefit = next(b for b in case.policy.benefits if b.id == result.benefit_id)
        component_refs = {
            "deductible_cents": [terms.deductible_clause, *benefit.clause_ids, terms.oop_clause],
            "copay_cents": [*benefit.clause_ids, terms.oop_clause],
            "coinsurance_cents": [*benefit.clause_ids, terms.deductible_clause, terms.oop_clause],
            "noncovered_cents": benefit.clause_ids,
            "balance_cents": [terms.network_clause],
            "adjustment_cents": [terms.network_clause, *benefit.clause_ids],
        }
        for field, label in (("allowed_cents", "allowed amount"), ("deductible_cents", "deductible"),
                             ("copay_cents", "copay"), ("coinsurance_cents", "coinsurance"),
                             ("noncovered_cents", "exclusion"), ("balance_cents", "balance billing"),
                             ("insurer_paid_cents", "insurer payment"), ("adjustment_cents", "contractual adjustment")):
            actual, expected = getattr(eob, field), getattr(result, field)
            if actual != expected:
                explanations.append({"kind": "eob_vs_fineprint", "component": field,
                                     "difference_cents": actual - expected,
                                     "message": f"EOB {label} is {actual} cents; policy evaluation gives {expected} cents under this scenario.",
                                     "clause_ids": list(dict.fromkeys(component_refs.get(field, refs)))})
        if bill.patient_total_cents != eob.patient_cents:
            explanations.append({"kind": "bill_vs_eob", "component": "patient_cents",
                                 "difference_cents": bill.patient_total_cents - eob.patient_cents,
                                 "message": "Hospital patient payments plus balance due differ from EOB patient responsibility. Check credits and adjustments.",
                                 "clause_ids": refs})
        if bill.patient_total_cents != result.patient_cents:
            explanations.append({"kind": "bill_vs_fineprint", "component": "patient_cents",
                                 "difference_cents": bill.patient_total_cents - result.patient_cents,
                                 "message": "Hospital patient responsibility differs from policy evaluation. Request itemized adjudication and review the cited terms.",
                                 "clause_ids": refs})
        if not explanations:
            explanations.append({"kind": "match", "component": "patient_cents", "difference_cents": 0,
                                 "message": "Independent cost-sharing calculation, EOB, and bill agree under the stated inputs.", "clause_ids": refs})
        rows.append({"claim_line_id": claim.id, "code": claim.code, "description": claim.description,
                     "fineprint_patient_cents": result.patient_cents, "eob_patient_cents": eob.patient_cents,
                     "bill_patient_cents": bill.patient_total_cents, "already_paid_cents": bill.patient_paid_cents,
                     "bill_balance_due_cents": bill.balance_due_cents,
                     "fineprint_remaining_cents": max(0, result.patient_cents - bill.patient_paid_cents),
                     "potential_refund_cents": max(0, bill.patient_paid_cents - result.patient_cents),
                     "potential_overpayment_cents": max(0, bill.patient_total_cents - result.patient_cents),
                     "eob_difference_cents": eob.patient_cents - result.patient_cents,
                     "bill_eob_difference_cents": bill.patient_total_cents - eob.patient_cents,
                     "explanations": explanations})
    fineprint = sum(row["fineprint_patient_cents"] for row in rows)
    eob = sum(row["eob_patient_cents"] for row in rows)
    hospital = sum(row["bill_patient_cents"] for row in rows)
    paid = sum(row["already_paid_cents"] for row in rows)
    return {"scenario_id": scenario.id, "conditional": scenario.conditional, "lines": rows,
            "fineprint_patient_cents": fineprint, "eob_patient_cents": eob, "bill_patient_cents": hospital,
            "already_paid_cents": paid, "bill_balance_due_cents": sum(r["bill_balance_due_cents"] for r in rows),
            # Keep per-line credit/refund allocation; do not silently offset providers.
            "fineprint_remaining_cents": sum(r["fineprint_remaining_cents"] for r in rows),
            "potential_refund_cents": sum(r["potential_refund_cents"] for r in rows),
            "potential_overpayment_cents": max(0, hospital - fineprint),
            "eob_difference_cents": eob - fineprint, "bill_eob_difference_cents": hospital - eob}
