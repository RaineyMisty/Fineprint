import hashlib
import json
import unittest
from pathlib import Path

from fineprint.models import Policy, case_from_dict, decode
from fineprint.validation import validate

ROOT = Path('fineprint/benchmark')


class BenchmarkDataTests(unittest.TestCase):
    def test_holdout_freeze_and_distinct_insurers(self):
        manifest = json.loads((ROOT/'manifest.json').read_text())
        self.assertEqual(hashlib.sha256(Path('fineprint/compiler.py').read_bytes()).hexdigest(),manifest['parser_sha256'])
        names = {'seen':set(),'held_out':set()}
        for spec in manifest['policies']:
            policy=decode(Policy,json.loads((ROOT/spec['gold']).read_text()))
            names[spec['split']].add(policy.insurer)
            self.assertIn('SYNTHETIC',(ROOT/spec['document']).read_text())
        self.assertEqual(len(names['held_out']),2)
        self.assertFalse(names['seen'] & names['held_out'])

    def test_authored_cases_are_consistent(self):
        for file in (ROOT/'cases').glob('*.json'):
            case=case_from_dict(json.loads(file.read_text()))
            self.assertTrue(case.synthetic)
            self.assertEqual([i for i in validate(case) if i.severity=='error'],[])
        manifest=json.loads((ROOT/'manifest.json').read_text())
        self.assertEqual(len({c['id'] for c in manifest['cases']}),10)
        self.assertEqual(sum(c['gold_discrepancy'] is False for c in manifest['cases']),3)
        self.assertEqual(sum(c['gold_discrepancy'] is None for c in manifest['cases']),1)
