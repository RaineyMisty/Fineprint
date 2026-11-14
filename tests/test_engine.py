import unittest
from copy import deepcopy

from fineprint.comparison import compare
from fineprint.engine import CalculationError, calculate
from fineprint.service import analyze
from tests.helpers import case, payload


class EngineTests(unittest.TestCase):
    def result(self, data=None):
        return calculate(case(data))[0].lines[0]

    def test_deductible_then_coinsurance(self):
        r = self.result()
        self.assertEqual((r.deductible_cents, r.coinsurance_cents, r.patient_cents, r.insurer_paid_cents), (10000, 2000, 12000, 8000))

    def test_deductible_only(self):
        p = payload()
        p["allowed_evidence"]["L1"]["allowed_cents"] = 5000
        self.assertEqual(self.result(p).patient_cents, 5000)

    def test_waived_deductible_and_copay(self):
        p = payload()
        p["policy"]["benefits"][0].update(deductible_applies=False, copay_cents=2500, coinsurance_bps=0)
        r = self.result(p)
        self.assertEqual((r.deductible_cents, r.copay_cents, r.patient_cents), (0, 2500, 2500))

    def test_combined_copay_and_coinsurance(self):
        p = payload()
        p["policy"]["benefits"][0].update(copay_cents=1000)
        r = self.result(p)
        self.assertEqual((r.deductible_cents, r.copay_cents, r.coinsurance_cents), (10000, 1000, 1800))

    def test_copay_cannot_exceed_allowance(self):
        p = payload()
        p["policy"]["benefits"][0].update(deductible_applies=False, copay_cents=30000, coinsurance_bps=5000)
        self.assertEqual(self.result(p).patient_cents, 20000)

    def test_oop_cap_including_deductible(self):
        p = payload()
        p["claim"]["accumulators"]["in"].update(oop_paid_cents=49000)
        r = self.result(p)
        self.assertEqual((r.patient_cents, r.deductible_cents, r.coinsurance_cents, r.closing_oop_cents), (1000, 1000, 0, 50000))

    def test_oop_already_met(self):
        p = payload()
        p["claim"]["accumulators"]["in"].update(oop_paid_cents=50000)
        r = self.result(p)
        self.assertEqual((r.patient_cents, r.insurer_paid_cents), (0, 20000))

    def test_exclusions_do_not_count_toward_oop(self):
        p = payload()
        p["policy"]["benefits"][0].update(covered=False, deductible_applies=False, coinsurance_bps=0)
        r = self.result(p)
        self.assertEqual((r.noncovered_cents, r.patient_cents, r.closing_oop_cents, r.insurer_paid_cents), (30000, 30000, 0, 0))

    def test_out_of_network_balance_outside_cap(self):
        p = payload()
        p["claim"]["lines"][0]["network"] = "out"
        p["claim"]["accumulators"]["out"].update(oop_paid_cents=50000)
        r = self.result(p)
        self.assertEqual((r.patient_cents, r.balance_cents, r.insurer_paid_cents, r.closing_oop_cents), (10000, 10000, 20000, 50000))

    def test_half_up_rounding(self):
        p = payload()
        p["allowed_evidence"]["L1"]["allowed_cents"] = 101
        p["policy"]["benefits"][0].update(deductible_applies=False, coinsurance_bps=5000)
        self.assertEqual(self.result(p).coinsurance_cents, 51)

    def test_zero_allowance(self):
        p = payload()
        p["allowed_evidence"]["L1"]["allowed_cents"] = 0
        self.assertEqual(self.result(p).patient_cents, 0)

    def test_multiline_updates_spending_and_does_not_mutate(self):
        p = payload()
        p["claim"]["lines"].append({**deepcopy(p["claim"]["lines"][0]), "id": "L2"})
        p["bill"]["lines"].append({**p["bill"]["lines"][0], "id": "BL2", "claim_line_id": "L2"})
        p["allowed_evidence"]["L2"] = deepcopy(p["allowed_evidence"]["L1"])
        original = deepcopy(p)
        results = calculate(case(p))[0]
        self.assertEqual([r.patient_cents for r in results.lines], [12000, 4000])
        self.assertEqual(results.closing_accumulators["in"]["oop_paid_cents"], 16000)
        self.assertEqual(p, original)

    def test_unknown_network_produces_both_scenarios(self):
        p = payload()
        p["claim"]["lines"][0]["network"] = "unknown"
        results = calculate(case(p))
        self.assertEqual({r.lines[0].network for r in results}, {"in", "out"})
        self.assertTrue(all(r.conditional for r in results))

    def test_missing_allowed_is_explicit_endpoints(self):
        p = payload()
        p["allowed_evidence"].clear()
        results = calculate(case(p))
        self.assertEqual({r.lines[0].allowed_cents for r in results}, {0, 30000})
        self.assertTrue(all("endpoint" in " ".join(r.assumptions) for r in results))

    def test_missing_accumulators_never_invent_inconsistent_history(self):
        for ded, oop in ((None, None), (None, 5000), (3000, None)):
            p = payload()
            p["claim"]["accumulators"]["in"].update(deductible_paid_cents=ded, oop_paid_cents=oop)
            for scenario in calculate(case(p)):
                r = scenario.lines[0]
                self.assertLessEqual(r.opening_deductible_cents, r.opening_oop_cents)
                self.assertTrue(scenario.conditional)

    def test_explicit_policy_ambiguity(self):
        p = payload()
        rule = p["policy"]["benefits"][0]
        rule.update(ambiguity_group="office")
        p["policy"]["benefits"].append({**rule, "id": "alternate", "label": "Waived", "deductible_applies": False})
        scenarios = calculate(case(p))
        self.assertEqual({s.patient_cents for s in scenarios}, {4000, 12000})
        self.assertTrue(all(s.conditional for s in scenarios))

    def test_fail_closed_and_scenario_cap(self):
        p = payload()
        p["claim"]["member_id"] = "wrong"
        with self.assertRaises(CalculationError):
            calculate(case(p))
        self.assertEqual(analyze(case(p))["status"], "blocked")
        p = payload()
        p["claim"]["lines"][0]["network"] = "unknown"
        with self.assertRaisesRegex(CalculationError, "silently dropped"):
            calculate(case(p), max_scenarios=1)

    def test_eob_dependency_is_not_claimed_independent(self):
        p = payload()
        p["allowed_evidence"]["L1"].update(source="eob")
        self.assertIn("cost-sharing audit only", " ".join(calculate(case(p))[0].assumptions))

    def test_money_conservation_across_inputs(self):
        # Cross product catches cap/rounding/network edge interactions, not implementation mirroring.
        for allowed in (0, 1, 101, 20000, 30000):
            for oop in (0, 49000, 50000):
                for net in ("in", "out"):
                    p = payload()
                    p["allowed_evidence"]["L1"]["allowed_cents"] = allowed
                    p["claim"]["lines"][0]["network"] = net
                    p["claim"]["accumulators"][net]["oop_paid_cents"] = oop
                    r = self.result(p)
                    self.assertEqual(r.patient_cents + r.insurer_paid_cents + r.adjustment_cents, 30000)
                    self.assertLessEqual(r.closing_oop_cents, 50000)
                    self.assertTrue(all(getattr(r, f) >= 0 for f in ("patient_cents", "insurer_paid_cents", "adjustment_cents")))


class ComparisonTests(unittest.TestCase):
    def test_match_has_clause_citations(self):
        c = case()
        report = compare(c, calculate(c)[0])
        self.assertEqual(report["potential_overpayment_cents"], 0)
        self.assertEqual(report["lines"][0]["explanations"][0]["kind"], "match")
        self.assertTrue(report["lines"][0]["explanations"][0]["clause_ids"])

    def test_hospital_mismatch_and_prepaid_refund(self):
        p = payload()
        p["policy"]["benefits"][0].update(deductible_applies=False)
        p["bill"]["lines"][0].update(patient_paid_cents=10000, balance_due_cents=2000)
        c = case(p)
        report = compare(c, calculate(c)[0])
        self.assertEqual((report["fineprint_patient_cents"], report["fineprint_remaining_cents"], report["potential_refund_cents"]), (4000, 0, 6000))
        self.assertEqual(report["potential_overpayment_cents"], 8000)
        self.assertTrue(all(item["clause_ids"] for item in report["lines"][0]["explanations"]))

    def test_bill_difference_explained_separately(self):
        p = payload()
        p["bill"]["lines"][0].update(adjustment_cents=9000, balance_due_cents=13000)
        c = case(p)
        report = compare(c, calculate(c)[0])
        self.assertEqual(report["bill_eob_difference_cents"], 1000)
        self.assertIn("bill_vs_eob", {x["kind"] for x in report["lines"][0]["explanations"]})

    def test_undercharge_does_not_become_negative_savings(self):
        p = payload()
        p["bill"]["lines"][0].update(adjustment_cents=20000, balance_due_cents=2000)
        c = case(p)
        report = compare(c, calculate(c)[0])
        self.assertEqual(report["potential_overpayment_cents"], 0)
