"""Benchmark accounting tests use synthetic text and never contact a provider."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import bench_real_sbc as bench


class BenchmarkRealSbcTests(unittest.TestCase):
    def test_raw_citations_include_invalid_references_and_normalize_whitespace(self):
        source = "Synthetic amount $25.\n\nSecond page\f\nLast line"
        raw = {"rule_evidence": [{"evidence": [
            {"source_lines": [1, 2, 900, True]},
            {"quote": "Synthetic   amount\n$25."},
            {"quote": "Synthetic amount $35."},
        ]}]}
        metrics = bench.citation_metrics(raw, source)
        self.assertEqual(metrics, dict(citations=6, verbatim=2, line_references=4, legacy_quotes=2))

    def test_numeric_scoring_never_selects_matching_variant_or_rewards_missing(self):
        labels = {"deductible": {"value": 10000, "page": 1}}
        for values, expected in (([], "missing"), ([10000], "correct"),
                                 ([20000], "incorrect"), ([10000, 20000], "ambiguous")):
            self.assertEqual(bench.score_fields({"deductible": values}, labels)["deductible"]["status"], expected)

    def test_service_comparison_retains_coinsurance_and_distinct_prices(self):
        benefits = [SimpleNamespace(network="in", covered=True, service_category="Primary care visit",
                                    copay_cents=copay, coinsurance_bps=2000, id=str(i))
                    for i, copay in enumerate((0, 2500, 0))]
        values, paths = bench.field_values(SimpleNamespace(networks={}, benefits=benefits))
        self.assertEqual(len(values["primary_care"]), 2)
        self.assertEqual(len(paths["primary_care"]), 3)
        self.assertTrue(all(v["coinsurance_bps"] == 2000 for v in values["primary_care"]))

    def failed_run(self):
        class FailingCompiler:
            def __init__(self, *args, **kwargs):
                self.transport = lambda *_: json.dumps({"rule_evidence": [{"evidence": [{"source_lines": [1]}]}]})
                self.request_config = {}

            def compile(self, document, document_id):
                self.transport("synthetic prompt", {})
                raise ValueError("Malformed provider JSON response PRIVATE_SENTINEL")

        with patch.object(bench, "extract_upload", return_value={
            "text": "Synthetic amount $25.", "pages": 1, "warnings": []
        }), patch.object(bench, "LLMCompiler", FailingCompiler), patch.object(Path, "read_bytes", return_value=b"synthetic"):
            return bench.benchmark_run({"document_id": "synthetic", "filename": "synthetic.pdf"}, 1,
                                       {"deductible": {"value": 10000, "page": 1}})

    def test_json_valid_but_validation_failed_stays_in_denominators_without_private_text(self):
        run = self.failed_run()
        self.assertTrue(run["valid_json"])
        self.assertFalse(run["compile_success"])
        self.assertEqual(run["proposed_rules"], 1)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(run))
        self.assertNotIn("Synthetic amount", json.dumps(run))
        metrics = bench.aggregate([run])
        self.assertEqual(metrics["validated_rule_rate"], 0)
        self.assertEqual(metrics["key_number_end_to_end_accuracy"], 0)
        self.assertIsNone(metrics["key_number_observed_accuracy"])
        self.assertIsNone(metrics["retained_quote_accuracy"])
        self.assertEqual(metrics["raw_quote_accuracy"], 1)

    def test_all_failed_runs_do_not_count_as_stable_values(self):
        run = self.failed_run()
        result = bench.stability([run, run, run])
        self.assertEqual(result["rule_count_population_variance"], 0)
        self.assertIsNone(result["successful_run_rule_count_population_variance"])
        self.assertFalse(result["deductible_stable_all_three"])
        self.assertFalse(result["oop_max_stable_all_three"])


if __name__ == "__main__":
    unittest.main()
