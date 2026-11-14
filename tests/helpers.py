from copy import deepcopy

from fineprint.models import case_from_dict


def payload():
    """One conserved EOB/bill with independently supplied contractual allowance."""
    terms = {"deductible_cents": 10000, "oop_max_cents": 50000, "balance_billing": False,
             "deductible_clause": "D", "oop_clause": "O", "network_clause": "N"}
    rule = {"id": "office-in", "label": "Office", "codes": ["99213"], "network": "in",
            "covered": True, "deductible_applies": True, "copay_cents": 0,
            "coinsurance_bps": 2000, "clause_ids": ["B"], "ambiguity_group": ""}
    line = {"id": "L1", "provider_id": "SYN-P", "service_date": "2026-06-01", "code": "99213",
            "description": "Synthetic office visit", "network": "in", "billed_cents": 30000,
            "insurer": {"allowed_cents": 20000, "deductible_cents": 10000, "copay_cents": 0,
                        "coinsurance_cents": 2000, "noncovered_cents": 0, "balance_cents": 0,
                        "insurer_paid_cents": 8000, "adjustment_cents": 10000}}
    return {"schema_version": "1.0", "id": "test-case", "title": "Synthetic unit fixture", "synthetic": True,
            "policy": {"id": "P1", "insurer": "Fictional", "name": "Synthetic Individual", "member_id": "SYN-M",
                       "effective_from": "2026-01-01", "effective_to": "2026-12-31", "currency": "USD",
                       "networks": {"in": terms, "out": {**deepcopy(terms), "balance_billing": True}},
                       "benefits": [rule, {**deepcopy(rule), "id": "office-out", "network": "out"}],
                       "clauses": [{"id": x, "text": f"Synthetic clause {x}", "location": f"Section {x}"} for x in "DONB"]},
            "claim": {"id": "C1", "policy_id": "P1", "member_id": "SYN-M",
                      "accumulators": {n: {"deductible_paid_cents": 0, "oop_paid_cents": 0} for n in ("in", "out")},
                      "lines": [line]},
            "bill": {"id": "B1", "claim_id": "C1", "member_id": "SYN-M", "lines": [
                {"id": "BL1", "claim_line_id": "L1", "provider_id": "SYN-P", "service_date": "2026-06-01", "code": "99213",
                 "charged_cents": 30000, "insurance_paid_cents": 8000, "adjustment_cents": 10000,
                 "patient_paid_cents": 0, "balance_due_cents": 12000}]},
            "allowed_evidence": {"L1": {"allowed_cents": 20000, "source": "contract", "reference": "Synthetic contract R1"}}}


def case(data=None):
    return case_from_dict(payload() if data is None else data)
