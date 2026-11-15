"""General SBC contracts using fabricated snippets, never real held-out text."""
from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from fineprint.compiler import FallbackCompiler, default_provider, recover_evidence, validate_output
from fineprint.engine import calculate, CalculationError
from fineprint.models import case_from_dict, to_dict
from tests.helpers import payload


class SbcContractTests(unittest.TestCase):
    def category_case(self):
        p = payload()
        p['policy']['networks'].pop('out')
        p['policy']['benefits'] = p['policy']['benefits'][:1]
        p['claim']['accumulators'].pop('out')
        p['policy']['benefits'][0].update(codes=[], service_category='Office consultation', conditions=['Referral obtained'])
        p['claim']['lines'][0].update(service_category='Office consultation', confirmed_conditions=['Referral obtained'])
        return p

    def test_single_network_with_explicit_category_assignment(self):
        p = self.category_case()
        result = calculate(case_from_dict(p))[0]
        self.assertEqual(result.patient_cents, 12000)
        self.assertTrue(result.conditional)
        for mutation in (lambda p: p['claim']['lines'][0].pop('service_category'),
                         lambda p: p['claim']['lines'][0].update(confirmed_conditions=[]),
                         lambda p: p['claim']['lines'][0].update(network='out'),
                         lambda p: p['claim']['lines'][0].update(network='unknown')):
            bad = deepcopy(p)
            mutation(bad)
            with self.assertRaises(CalculationError):
                calculate(case_from_dict(bad))

    def test_unknown_billing_needs_independent_contract_evidence(self):
        p = self.category_case()
        p['policy']['networks']['in'].update(balance_billing=None, network_clause=None)
        with self.assertRaises(CalculationError):
            calculate(case_from_dict(p))
        p['allowed_evidence']['L1']['balance_billing'] = False
        self.assertEqual(calculate(case_from_dict(p))[0].patient_cents, 12000)
        p['allowed_evidence']['L1']['balance_billing'] = True
        self.assertEqual(calculate(case_from_dict(p))[0].patient_cents, 22000)
        p['allowed_evidence']['L1']['source'] = 'eob'
        with self.assertRaises(CalculationError):
            calculate(case_from_dict(p))

    def test_runtime_default_provider_and_explicit_offline_override(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': '', 'FINEPRINT_LLM_PROVIDER': ''}):
            self.assertEqual(default_provider(), 'fallback')
            os.environ['DEEPSEEK_API_KEY'] = 'test-only'
            self.assertEqual(default_provider(), 'deepseek')
            os.environ['FINEPRINT_LLM_PROVIDER'] = 'fallback'
            self.assertEqual(default_provider(), 'fallback')

    def test_nullable_provider_network_is_omitted_without_invented_values(self):
        from pathlib import Path
        doc = Path('fineprint/samples/aurora-imaging/policy.md').read_text()
        value = to_dict(FallbackCompiler().compile(doc).output)
        del value['policy']['clauses']
        for terms in value['policy']['networks'].values():
            for key in ('deductible_clause', 'oop_clause', 'network_clause'):
                del terms[key]
        for b in value['policy']['benefits']:
            del b['clause_ids']
        for r in value['rule_evidence']:
            for e in r['evidence']:
                del e['start']; del e['end']
        value['policy']['networks']['out'].update(deductible_cents=None, oop_max_cents=None)
        result = validate_output(recover_evidence(value, doc, 'uploaded-policy'), doc, 'uploaded-policy')
        self.assertEqual(set(result.policy.networks), {'in'})
        self.assertTrue(all(b.network == 'in' for b in result.policy.benefits))
        self.assertTrue(result.coverage_gaps)

    def test_category_and_numeric_values_need_source_support(self):
        from fineprint.compiler import _selector_supported, _costs_supported
        b = dict(codes=[], service_category='Office consultation', copay_cents=3500, coinsurance_bps=0)
        quotes = ['Office consultation $35 / visit']
        self.assertTrue(_selector_supported(b, quotes))
        self.assertTrue(_costs_supported(b, quotes))
        self.assertFalse(_selector_supported({**b, 'service_category': 'Invented service'}, quotes))
        self.assertFalse(_costs_supported({**b, 'copay_cents': 3600}, quotes))
        self.assertFalse(_selector_supported({**b, 'codes': ['99213']}, quotes))
