import csv
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import tempfile

from fineprint.compiler import FallbackCompiler, validate_output
from fineprint.models import ModelError
from scripts.compile_real_policies import DOCUMENTS, compile_document, source_excerpts

ROOT = Path(__file__).resolve().parents[1]


class RealCorpusTests(unittest.TestCase):
    def test_manifest_has_provenance_and_rights_but_no_policy_text(self):
        with (ROOT / "data/real_manifest.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len({row["local_path"] for row in rows}), len(rows))
        self.assertGreaterEqual(sum(row["local_path"].endswith(".pdf") for row in rows), 28)
        for row in rows:
            self.assertTrue(row["local_path"].startswith("data/real_private/"))
            self.assertNotIn("..", Path(row["local_path"]).parts)
            self.assertRegex(row["sha256"], r"^[a-f0-9]{64}$")
            self.assertGreater(int(row["bytes"]), 0)
            self.assertIn("No redistribution license; PDF/text not in this repo", row["redistribution_note"])
            self.assertTrue(row["retrieval_notes"])
            if row["local_path"].endswith(".pdf"):
                self.assertTrue(row["source_url"].startswith("https://"))
                self.assertTrue(row["retrieved_utc"])
            local = ROOT / row["local_path"]
            if local.is_file():
                payload = local.read_bytes()
                self.assertEqual(hashlib.sha256(payload).hexdigest(), row["sha256"])
                self.assertEqual(len(payload), int(row["bytes"]))
            if "SYNTHETIC_" in row["local_path"]:
                self.assertEqual(row["synthetic"], "true")

    def test_private_paths_are_ignored_and_never_tracked(self):
        paths = ["data/real_private/docs/kaiser_2026_ca_gold80_sbc.pdf",
                 "data/real_private/docs/kaiser_2026_ca_gold80_sbc.txt",
                 "data/real_private/sources.csv", "data/future_private/policy.txt"]
        result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT,
                                input="\n".join(paths) + "\n", text=True, capture_output=True, check=True)
        self.assertEqual(set(result.stdout.splitlines()), set(paths))
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        self.assertFalse(any(path.startswith("data/real_private/") for path in tracked))
        with (ROOT / "data/real_manifest.csv").open(newline="", encoding="utf-8") as stream:
            private_rows = [row for row in csv.DictReader(stream) if row["local_path"].endswith((".pdf", ".txt"))]
        private_names = {Path(row["local_path"]).name for row in private_rows}
        self.assertFalse(any(Path(path).name in private_names for path in tracked))
        private_hashes = {row["sha256"] for row in private_rows}
        tracked_hashes = {hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                          for path in tracked if path and (ROOT / path).is_file()}
        self.assertFalse(private_hashes & tracked_hashes, "A renamed private PDF/text copy is tracked")

    def test_real_text_smoke_preserves_fail_closed_behavior(self):
        present = False
        for stem in DOCUMENTS.values():
            path = ROOT / "data/real_private/docs" / (stem + ".txt")
            if not path.is_file():
                continue
            present = True
            document = path.read_bytes().decode("utf-8")
            try:
                result = FallbackCompiler().compile(document, stem)
            except ModelError as exc:
                self.assertIn("Fallback requires", str(exc))
            else:
                validate_output(result.as_dict()["output"], document, stem)
            for evidence in source_excerpts(document):
                self.assertEqual(document[evidence["start"]:evidence["end"]], evidence["quote"])
                self.assertEqual(document[:evidence["start"]].count("\f") + 1, evidence["pdf_page"])
        if not present:
            self.skipTest("Private insurer texts intentionally absent in CI")

    def test_missing_key_never_makes_a_provider_request(self):
        # A tiny raw source exercises the reporting boundary even in public CI.
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            docs = root / "data/real_private/docs"
            docs.mkdir(parents=True)
            (docs / "tiny.txt").write_text("Raw insurer format. Individual deductible $0.\n")
            (root / "fineprint").mkdir()
            for filename in ("compiler.py", "providers.py"):
                (root / "fineprint" / filename).write_text("# test-only hash input\n")
            with patch("scripts.compile_real_policies.ROOT", root), \
                 patch.dict("os.environ", {"DEEPSEEK_API_KEY": ""}), \
                 patch("scripts.compile_real_policies.LLMCompiler._request", side_effect=AssertionError("network called")):
                compile_document("tiny", "tiny", deepseek=True, output=root / "reports")
            report = json.loads((root / "reports/real-tiny-rules.json").read_text())
            self.assertEqual([row["status"] for row in report["runs"]], ["failed", "skipped"])
            self.assertTrue(all(row["compilation"] is None for row in report["runs"]))
