"""Local-only smoke test: private insurer PDFs must never be committed as fixtures."""

import importlib.util
from pathlib import Path
import unittest

from fineprint.documents_pdf import extract_upload

DOCS = Path(__file__).resolve().parents[1] / "data/real_private/docs"


@unittest.skipUnless(importlib.util.find_spec("pypdf"), "pypdf is not installed; use the project .venv")
@unittest.skipUnless(DOCS.is_dir(), "Private sample PDFs intentionally absent in CI")
class RealLocalPdfTests(unittest.TestCase):
    def test_all_available_private_pdfs_have_selectable_text(self):
        paths = sorted(DOCS.glob("*.pdf"))
        if not paths:
            self.skipTest("Private sample PDFs intentionally absent in CI")
        for path in paths:
            with self.subTest(filename=path.name):
                kind = "eob" if "eob" in path.stem or "msn" in path.stem else "bill" if "bill" in path.stem else "policy"
                result = extract_upload(kind, path.name, path.read_bytes())
                self.assertGreater(result["pages"], 0)
                self.assertGreater(result["chars"], 0)
                self.assertTrue(result["text"].strip())
                self.assertEqual(result["filename"], path.name)


if __name__ == "__main__":
    unittest.main()
