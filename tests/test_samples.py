import json
import unittest

from fineprint.engine import calculate
from fineprint.extraction import ProviderPolicyExtractor
from fineprint.models import ModelError, case_from_dict, to_dict
from fineprint.repository import list_cases, load_case
from fineprint.service import analyze
from fineprint.validation import validate


class SampleTests(unittest.TestCase):
    def test_three_fictional_cases_two_insurers(self):
        catalog = list_cases()
        self.assertEqual(len(catalog), 3)
        self.assertEqual(len({c["insurer"] for c in catalog}), 2)
        self.assertTrue(all(c["synthetic"] for c in catalog))

    def test_all_document_sets_are_linked_and_arithmetically_consistent(self):
        for item in list_cases():
            with self.subTest(case=item["id"]):
                case, docs = load_case(item["id"])
                self.assertEqual([i for i in validate(case) if i.severity == "error"], [])
                self.assertEqual(set(docs), {"policy", "claim", "bill"})
                self.assertTrue(all("SYNTHETIC" in doc for doc in docs.values()))
                self.assertEqual(case_from_dict(json.loads(json.dumps(to_dict(case)))), case)

    def test_aurora_manually_worked_numbers(self):
        # Office = $25. MRI = $200 remaining deductible + 20% × $800 = $360.
        # EOB MRI = $440. Hospital MRI = $480, including $100 already paid.
        case, _ = load_case("aurora-imaging")
        report = analyze(case)
        lines = report["scenarios"][0]["lines"]
        self.assertEqual([r["patient_cents"] for r in lines], [2500, 36000])
        self.assertEqual((lines[1]["deductible_cents"], lines[1]["coinsurance_cents"]), (20000, 16000))
        comparison = report["comparisons"][0]
        self.assertEqual((comparison["fineprint_patient_cents"], comparison["eob_patient_cents"], comparison["bill_patient_cents"]), (38500, 46500, 50500))
        self.assertEqual((comparison["eob_difference_cents"], comparison["bill_eob_difference_cents"], comparison["potential_overpayment_cents"]), (8000, 4000, 12000))
        self.assertEqual(comparison["fineprint_remaining_cents"], 28500)

    def test_mosaic_manually_worked_numbers(self):
        # Surgery = min(20% × $1000, $50 OOP left) = $50.
        # Excluded charge $300 + transport $400 deductible + $250 balance.
        case, _ = load_case("mosaic-oop")
        scenario = calculate(case)[0]
        self.assertEqual([r.patient_cents for r in scenario.lines], [5000, 30000, 65000])
        self.assertEqual(scenario.closing_accumulators["in"]["oop_paid_cents"], 150000)
        self.assertEqual(scenario.closing_accumulators["out"]["oop_paid_cents"], 40000)
        report = analyze(case)
        self.assertEqual(report["summary"]["potential_overpayment_min_cents"], 15000)

    def test_ambiguous_case_is_always_conditional(self):
        case, _ = load_case("mosaic-therapy")
        report = analyze(case)
        self.assertEqual(report["summary"]["scenario_count"], 32)
        self.assertTrue(all(s["conditional"] for s in report["scenarios"]))
        self.assertEqual((report["summary"]["illustrated_min_patient_cents"], report["summary"]["illustrated_max_patient_cents"]), (0, 30000))
        self.assertEqual(report["summary"]["potential_overpayment_min_cents"], 0)

    def test_resolving_facts_reduces_to_two_policy_interpretations(self):
        case, _ = load_case("mosaic-therapy")
        p = to_dict(case)
        p["claim"]["lines"][0]["network"] = "in"
        p["claim"]["accumulators"]["in"].update(deductible_paid_cents=0, oop_paid_cents=0)
        p["allowed_evidence"]["T1"].update(allowed_cents=20000, source="contract", reference="Synthetic confirmed contract")
        scenarios = calculate(case_from_dict(p))
        self.assertEqual(len(scenarios), 2)
        self.assertEqual({s.patient_cents for s in scenarios}, {4000, 20000})

    def test_repository_rejects_traversal_and_unknown_cases(self):
        for name in ("../policy", "aurora-imaging/../../", "not-a-case"):
            with self.subTest(name=name), self.assertRaises(FileNotFoundError):
                load_case(name)

    def test_unreviewed_provider_output_cannot_enter_sample_pipeline(self):
        c, _ = load_case("aurora-imaging")
        extractor = ProviderPolicyExtractor(lambda doc: to_dict(c.policy), "stub-provider")
        with self.assertRaisesRegex(ModelError, "requires review"):
            load_case("aurora-imaging", extractor=extractor)
