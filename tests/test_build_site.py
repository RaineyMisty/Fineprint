import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fineprint.models import case_from_dict
from fineprint.service import analyze
from scripts.build_site import build, collect_cases


class SiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        # A configured live provider must never affect a public, offline build.
        with patch.dict("os.environ", {"FINEPRINT_LLM_PROVIDER": "openai"}):
            cls.data = build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exports_actual_cli_evaluation_without_modification(self):
        evaluation = json.loads((self.output / "evaluation.json").read_text())
        self.assertEqual(self.data["evaluation"], evaluation)
        self.assertEqual(evaluation["backend"], "fallback")
        self.assertTrue(evaluation["parser_matches_holdout_freeze"])
        self.assertTrue((self.output / "evaluation.md").is_file())
        self.assertEqual(json.loads((self.output / "data.json").read_text()), self.data)

    def test_every_ready_case_equals_python_analysis_of_compiled_policy(self):
        for item in self.data["cases"]:
            with self.subTest(case=item["id"]):
                self.assertTrue(item["synthetic"])
                if item["case"] is None:
                    continue
                self.assertEqual(item["case"]["policy"], item["compilation"]["output"]["policy"])
                self.assertEqual(item["report"], analyze(case_from_dict(item["case"])))
                for rule in item["compilation"]["output"]["rule_evidence"]:
                    for evidence in rule["evidence"]:
                        self.assertEqual(item["document"][evidence["start"]:evidence["end"]], evidence["quote"])

    def test_failed_policies_remain_visible_without_gold_rules_or_totals(self):
        self.assertEqual(len(self.data["cases"]), self.data["evaluation"]["groups"]["all"]["cases"])
        failed = [item for item in self.data["cases"] if item["report"]["status"] == "blocked"]
        self.assertEqual({item["id"] for item in failed}, {row["id"] for row in self.data["evaluation"]["cases"] if row["error"]})
        for item in failed:
            self.assertIsNone(item["compilation"])
            self.assertIsNone(item["case"])
            self.assertIsNone(item["report"]["summary"])
            self.assertEqual(item["report"]["scenarios"], [])
            self.assertTrue(item["document"])

    def test_unexpected_engine_errors_fail_the_build(self):
        with patch("scripts.build_site.analyze", side_effect=RuntimeError("engine failed")):
            with self.assertRaisesRegex(RuntimeError, "engine failed"):
                collect_cases()
