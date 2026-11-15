"""Public site entry points."""
import unittest
from pathlib import Path


class SiteTests(unittest.TestCase):
    def test_site_entry_points(self):
        site = Path(__file__).resolve().parents[1] / "site"
        self.assertTrue((site / "index.html").is_file())
        self.assertIn("data.json", (site / "app.js").read_text(encoding="utf-8"))
