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

    def test_receipt_is_bound_to_exact_source_and_compilation(self):
        from pathlib import Path
        from fineprint.compilation_receipts import sign, verify
        from fineprint.models import ModelError
        doc = Path('fineprint/samples/aurora-imaging/policy.md').read_text()
        compiled = FallbackCompiler().compile(doc).as_dict()
        receipt = sign(compiled)
        self.assertEqual(verify(compiled, receipt, doc).as_dict(), compiled)
        with self.assertRaises(ModelError):
            verify(compiled, receipt, doc + ' ')
        edited = deepcopy(compiled)
        edited['output']['policy']['benefits'][0]['copay_cents'] += 100
        with self.assertRaises(ModelError):
            verify(edited, receipt, doc)

    def test_provider_selects_source_lines_without_reconstructing_table_cells(self):
        from pathlib import Path
        from fineprint.providers import LLMCompiler
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
                line = len(doc[:e['start']].splitlines())
                e.pop('quote'); e.pop('start'); e.pop('end')
                e['source_lines'] = [line]
        result = LLMCompiler('deepseek', transport=lambda *_: value, retries=1).compile(doc)
        self.assertEqual(len(result.policy.benefits), 3)
        self.assertTrue(all(doc[e.start:e.end] == e.quote for r in result.output.rule_evidence for e in r.evidence))
        value['rule_evidence'][0]['evidence'][0]['source_lines'] = [999999]
        with self.assertRaisesRegex(ValueError, 'nonexistent or blank source line'):
            LLMCompiler('deepseek', transport=lambda *_: value, retries=1).compile(doc)

    def test_wrapped_heading_support_preserves_exact_quote_text(self):
        from fineprint.compiler import _selector_supported
        benefit = dict(codes=[], service_category='Primary care visit to treat an injury or illness')
        quotes = ['Primary care visit to      $25 / visit    Not covered',
                  'treat an injury or', 'illness']
        self.assertTrue(_selector_supported(benefit, quotes))
        self.assertFalse(_selector_supported({**benefit, 'service_category': 'Surgery visit'}, quotes))

    def test_day_caps_and_drug_coinsurance_caps_are_not_implemented_by_conditions(self):
        from fineprint.compiler import _costs_supported
        for benefit, quotes in (
            (dict(copay_cents=30000, coinsurance_bps=0), ['$300 / day up to 4 days']),
            (dict(copay_cents=0, coinsurance_bps=2000), ['20% coinsurance up to $200 / prescription']),
            (dict(copay_cents=0, coinsurance_bps=5000), ['50% coinsurance', '$250/$500 min', '$1,000/$2,000 max per prescription']),
            (dict(copay_cents=0, coinsurance_bps=0), ['Physician/surgeon fees Not Applicable Included in facility fee']),
        ):
            self.assertFalse(_costs_supported(benefit, quotes))
        self.assertTrue(_costs_supported(dict(copay_cents=0, coinsurance_bps=0), ['Hospice No charge']))
