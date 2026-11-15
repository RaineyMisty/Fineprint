import unittest
from copy import deepcopy

from fineprint.models import ModelError, case_from_dict, to_dict
from fineprint.validation import links, validate
from tests.helpers import case, payload


class ModelTests(unittest.TestCase):
    def test_roundtrip(self):
        self.assertEqual(to_dict(case()), payload())

    def test_strict_boundary(self):
        mutations = [lambda p: p.update(extra="no"), lambda p: p.update(schema_version="2"),
                     lambda p: p["claim"]["lines"][0].update(billed_cents=3.2),
                     lambda p: p["claim"]["lines"][0].update(billed_cents=True),
                     lambda p: p["claim"]["lines"][0].update(billed_cents=-1),
                     lambda p: p["claim"]["lines"][0].update(billed_cents=10**13),
                     lambda p: p["claim"]["lines"][0].update(service_date="2026-02-30"),
                     lambda p: p["claim"]["lines"][0].update(service_date="20260601"),
                     lambda p: p["claim"]["lines"][0].update(network="maybe"),
                     lambda p: p["policy"]["benefits"][0].update(coinsurance_bps=10001),
                     lambda p: p.update(title=" "), lambda p: p.pop("bill")]
        for mutation in mutations:
            p = payload()
            mutation(p)
            with self.subTest(payload=p), self.assertRaises(ModelError):
                case_from_dict(p)


class ValidationTests(unittest.TestCase):
    def test_valid_case(self):
        self.assertEqual(validate(case()), [])

    def assert_issue(self, mutate, code):
        p = payload()
        mutate(p)
        self.assertIn(code, {i.code for i in validate(case(p))})

    def test_identity_links(self):
        for document, key in (("claim", "member_id"), ("bill", "member_id"), ("claim", "policy_id"), ("bill", "claim_id")):
            self.assert_issue(lambda p: p[document].update({key: "wrong"}), "identity_mismatch")

    def test_plan_level_metadata_may_be_null_but_claim_bill_must_match(self):
        p = payload()
        p['policy'].update(member_id=None, effective_from=None, effective_to=None)
        self.assertEqual(validate(case(p)), [])
        p['bill']['member_id'] = 'different-person'
        self.assertIn('identity_mismatch', {i.code for i in validate(case(p))})

    def test_known_period_endpoint_is_still_enforced(self):
        p = payload()
        p['policy'].update(member_id=None, effective_from=None, effective_to='2026-01-01')
        self.assertIn('outside_policy', {i.code for i in validate(case(p))})

    def test_line_consistency(self):
        for field, val in (("provider_id", "wrong"), ("code", "99214"), ("service_date", "2026-06-02")):
            self.assert_issue(lambda p: p["bill"]["lines"][0].update({field: val}), "line_mismatch")
        self.assert_issue(lambda p: p["bill"]["lines"][0].update(charged_cents=40000), "charge_mismatch")

    def test_broken_arithmetic(self):
        self.assert_issue(lambda p: p["claim"]["lines"][0]["insurer"].update(deductible_cents=1), "eob_arithmetic")
        self.assert_issue(lambda p: p["bill"]["lines"][0].update(balance_due_cents=1), "bill_arithmetic")

    def test_dates_rules_and_clauses(self):
        self.assert_issue(lambda p: p["policy"].update(effective_to="2026-02-01"), "outside_policy")
        self.assert_issue(lambda p: p["policy"]["benefits"][0].update(clause_ids=["missing"]), "clause_reference")
        self.assert_issue(lambda p: p["policy"]["benefits"][0].update(codes=["99214"]), "missing_rule")
        self.assert_issue(lambda p: p["claim"]["lines"][0].update(code="invalid"), "service_code")
        self.assert_issue(lambda p: p["policy"]["networks"].pop("out"), "networks")

    def test_duplicate_and_orphan_links(self):
        self.assert_issue(lambda p: p["claim"]["lines"].append(deepcopy(p["claim"]["lines"][0])), "duplicate_id")
        self.assert_issue(lambda p: p["bill"]["lines"][0].update(claim_line_id="missing"), "orphan_bill_line")
        self.assert_issue(lambda p: p["bill"]["lines"].append({**p["bill"]["lines"][0], "id": "BL2"}), "duplicate_link")
        self.assert_issue(lambda p: p["bill"]["lines"].clear(), "unbilled_claim_line")

    def test_accumulators(self):
        self.assert_issue(lambda p: p["claim"]["accumulators"]["in"].update(deductible_paid_cents=10001), "accumulator_limit")
        self.assert_issue(lambda p: p["claim"]["accumulators"]["in"].update(deductible_paid_cents=1), "accumulator_order")
        self.assert_issue(lambda p: p["claim"]["accumulators"].pop("out"), "accumulators")

    def test_ambiguity_requires_intentional_alternatives(self):
        self.assert_issue(lambda p: p["policy"]["benefits"].append({**p["policy"]["benefits"][0], "id": "new", "label": "Other"}), "overlapping_rules")

    def test_allowance_provenance(self):
        self.assert_issue(lambda p: p["allowed_evidence"]["L1"].update(source="unknown"), "evidence_source")
        self.assert_issue(lambda p: p["allowed_evidence"]["L1"].update(source="eob", allowed_cents=1), "evidence_mismatch")
        self.assert_issue(lambda p: p["allowed_evidence"]["L1"].update(allowed_cents=30001), "allowed_exceeds_charge")

    def test_links_expose_all_join_keys(self):
        link = links(case())[0]
        self.assertEqual(link["bill_line_ids"], ["BL1"])
        self.assertEqual(set(link), {"claim_line_id", "member_id", "provider_id", "service_date", "code", "claim_id", "bill_line_ids"})
