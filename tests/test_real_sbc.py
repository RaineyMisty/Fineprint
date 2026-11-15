import csv
import json
from pathlib import Path
import unittest

from fineprint.real_sbc import compare_total, evaluate, render_markdown, ROUNDING_TOLERANCE_CENTS

ROOT = Path(__file__).resolve().parents[1]


class RealSbcEvaluationTests(unittest.TestCase):
    def test_comparison_tolerance_and_missing_predictions(self):
        published = 467_000
        self.assertIsNone(compare_total(None, published)["within_tolerance"])
        self.assertIsNone(compare_total(None, published)["absolute_error_cents"])
        self.assertTrue(compare_total(published, published)["within_tolerance"])
        self.assertTrue(compare_total(published + ROUNDING_TOLERANCE_CENTS, published)["within_tolerance"])
        self.assertFalse(compare_total(published + ROUNDING_TOLERANCE_CENTS + 1, published)["within_tolerance"])
        self.assertTrue(compare_total(published - ROUNDING_TOLERANCE_CENTS, published)["within_tolerance"])
        self.assertFalse(compare_total(published - ROUNDING_TOLERANCE_CENTS - 1, published)["within_tolerance"])
        for value in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                compare_total(value, published)

    def test_labels_and_denominators_do_not_claim_arithmetic_as_accuracy(self):
        report = evaluate()
        summary = report["summary"]
        self.assertEqual(summary["published_labels"], 18)
        self.assertEqual(summary["insurers"], 6)
        self.assertEqual(summary["blocked"], 9)
        self.assertEqual(summary["not_attempted"], 9)
        self.assertEqual(summary["recalculated"], 0)
        self.assertEqual(summary["matches_within_tolerance"], 0)
        self.assertEqual(summary["label_arithmetic_checks_passed"], 18)
        self.assertIsNone(summary["accuracy"])
        self.assertIsNone(summary["mean_absolute_error_cents"])
        for row in report["examples"]:
            self.assertIsNone(row["predicted_patient_cents"])
            self.assertIsNone(row["absolute_error_cents"])
            self.assertTrue(row["reasons"])
            self.assertIn("not actual claim", row["label_status"])
        self.assertIn("This is not recalculation accuracy", render_markdown(report))

    def test_committed_report_reproduces_without_private_documents_or_live_calls(self):
        saved = json.loads((ROOT / "reports/evaluation-real-sbc.json").read_text())
        fresh = evaluate()
        saved.pop("generated_at")
        fresh.pop("generated_at")
        self.assertEqual(saved, fresh)
        with (ROOT / "data/real_coverage_example_labels.csv").open(newline="", encoding="utf-8") as stream:
            labels = list(csv.DictReader(stream))
        self.assertEqual([int(row["patient_total"]) * 100 for row in labels],
                         [row["published_patient_cents"] for row in fresh["examples"]])
