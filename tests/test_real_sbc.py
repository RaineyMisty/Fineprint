import csv
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from fineprint.real_sbc import (compare_total, compilation_summary, evaluate, render_markdown,
                               ROUNDING_TOLERANCE_CENTS)

ROOT = Path(__file__).resolve().parents[1]


class RealSbcEvaluationTests(unittest.TestCase):
    def test_partial_eoc_validation_is_counted_without_claiming_recalculation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            reports = Path(directory)
            partial = dict(provider="deepseek", model="test-only", status="validated", error=None,
                           compilation={"output": {}}, validated_rules=2, claim_ready=False)
            failed = dict(provider="deepseek", model="test-only", status="failed", error="test-only failure",
                          compilation=None)
            skipped = dict(provider="deepseek", model="test-only", status="skipped", error="missing key",
                           compilation=None)
            audits = json.loads((ROOT / "data/real_coverage_example_input_audit.json").read_text())
            hashes = {row["document"]: row["source_sha256"] for row in audits["examples"]}
            for slug, run in (("kaiser-eoc", partial), ("cigna", failed), ("highmark", skipped)):
                (reports / f"real-{slug}-rules.json").write_text(json.dumps(
                    {"runs": [run], "source_sha256": hashes.get(slug, "test-only-eoc")}))
            group, = compilation_summary(reports)
            self.assertEqual((group["attempted"], group["validated"], group["claim_ready"]), (2, 1, 0))
            self.assertEqual((group["failed"], group["skipped"]), (1, 1))
            eoc = next(row for row in group["documents"] if row["document"] == "kaiser-eoc")
            self.assertEqual(eoc["validated_rules"], 2)
            self.assertFalse(eoc["claim_ready"])
            # Even a validated financial-rule subset never supplies scenario prices.
            (reports / "real-cigna-rules.json").write_text(json.dumps(
                {"runs": [partial], "source_sha256": hashes["cigna"]}))
            report = evaluate(reports_dir=reports)
            self.assertEqual(report["summary"]["recalculated"], 0)
            self.assertIsNone(report["summary"]["accuracy"])
            self.assertTrue(all(row["predicted_patient_cents"] is None for row in report["examples"]))

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

    def test_published_patient_answers_never_become_prediction_inputs(self):
        with (ROOT / "data/real_coverage_example_labels.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            fields, labels = reader.fieldnames, list(reader)
        for label in labels:
            label['patient_total'] = '9999999'
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'changed-labels.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fields)
                writer.writeheader(); writer.writerows(labels)
            with patch('urllib.request.urlopen', side_effect=AssertionError('Must stay offline')):
                report = evaluate(labels_path=path)
        self.assertEqual(report['summary']['recalculated'], 0)
        self.assertIsNone(report['summary']['accuracy'])
        for row in report['examples']:
            self.assertIsNone(row['predicted_patient_cents'])
            if row['input_audit']:
                self.assertFalse(row['input_audit']['per_service_allowed_prices_available'])
                self.assertNotEqual(row['input_audit']['published_total_example_cost_cents'], row['published_patient_cents'])

    def test_dev_and_held_out_denominators_remain_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            for slug, split, status in (('kaiser', 'dev', 'validated'), ('highmark', 'dev', 'validated'),
                                        ('cigna', 'held_out', 'failed'), ('ambetter', 'held_out', 'validated')):
                valid = status == 'validated'
                (reports / f'real-{slug}-rules.json').write_text(json.dumps(dict(split=split, runs=[dict(
                    provider='deepseek', model='test-only', status=status, compilation={} if valid else None,
                    validated_rules=4 if valid else 0, benefit_rules=2 if valid else 0,
                    validated_quote_spans=6 if valid else 0, conditionally_executable=valid, claim_ready=False)])))
            groups = {g['split']: g for g in compilation_summary(reports)}
            self.assertEqual((groups['dev']['validated'], groups['dev']['attempted']), (2, 2))
            self.assertEqual((groups['held_out']['validated'], groups['held_out']['attempted']), (1, 2))
            self.assertEqual(groups['held_out']['failed'], 1)
            self.assertEqual(groups['dev']['conditionally_executable'], 2)

    def test_held_out_report_guard_prevents_reading_or_rerunning(self):
        from scripts.compile_real_policies import compile_document
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory)
            (reports / 'real-cigna-rules.json').write_text(json.dumps({'split': 'held_out', 'runs': []}))
            with patch('scripts.compile_real_policies.LLMCompiler', side_effect=AssertionError('provider constructed')):
                with self.assertRaisesRegex(ValueError, 'refusing to read or rerun'):
                    compile_document('cigna', 'source-must-not-be-read', deepseek=True, output=reports)
