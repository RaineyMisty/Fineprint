import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fineprint.models import case_from_dict
from fineprint.service import analyze
from scripts.build_site import build, collect_cases, load_llm_evaluations, load_real_evaluation


class SiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        # A configured live provider must never affect a public, offline build.
        with patch.dict("os.environ", {"FINEPRINT_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": ""}):
            cls.data = build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exports_actual_cli_evaluation_without_modification(self):
        evaluation = json.loads((self.output / "evaluation.json").read_text())
        self.assertEqual(self.data["evaluation"], evaluation)
        self.assertEqual(evaluation["backend"], "fallback")
        self.assertEqual(evaluation["parser_matches_holdout_freeze"], evaluation["parser_sha256"] == json.loads(Path("fineprint/benchmark/manifest.json").read_text())["parser_sha256"])
        self.assertTrue((self.output / "evaluation.md").is_file())
        self.assertEqual(json.loads((self.output / "data.json").read_text()), self.data)

    def test_saved_llm_reports_are_included_verbatim_without_live_calls(self):
        paths=sorted((Path(__file__).resolve().parents[1]/'reports').glob('evaluation-deepseek-*.json'))
        self.assertEqual(self.data['llm_evaluations'],[json.loads(p.read_text()) for p in paths])
        for path in paths:
            self.assertEqual(json.loads((self.output/path.name).read_text()),json.loads(path.read_text()))

    def test_saved_real_report_is_included_without_private_sources_or_live_calls(self):
        path = Path(__file__).resolve().parents[1] / "reports/evaluation-real-sbc.json"
        report = json.loads(path.read_text())
        self.assertEqual(self.data["real_evaluation"], report)
        self.assertEqual(json.loads((self.output / path.name).read_text()), report)
        self.assertTrue((self.output / "evaluation-real-sbc.md").is_file())
        self.assertEqual(report["title"], "real published SBC examples (rounded)")
        self.assertIsNone(report["summary"]["accuracy"])

    def test_saved_real_report_loader_rejects_synthetic_or_mislabeled_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(load_real_evaluation(root))
            path = root / "evaluation-real-sbc.json"
            for report in ({"synthetic": True}, {"kind": "real_published_sbc_examples", "synthetic": False}):
                path.write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    load_real_evaluation(root)

    def test_saved_report_loader_handles_absent_and_incompatible_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertEqual(load_llm_evaluations(root,'corpus'),[])
            path=root/'evaluation-deepseek-test.json'
            report=dict(backend='deepseek',synthetic=True,model='test-only',generated_at='2026-11-15',corpus_sha256='corpus')
            path.write_text(json.dumps(report))
            self.assertEqual(load_llm_evaluations(root,'corpus'),[(path.name,report)])
            for field,value in [('backend','fallback'),('synthetic',False),('corpus_sha256','other')]:
                with self.subTest(field=field):
                    path.write_text(json.dumps({**report,field:value}))
                    with self.assertRaises(ValueError):load_llm_evaluations(root,'corpus')

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
