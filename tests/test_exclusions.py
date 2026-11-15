"""Fabricated service identities and exclusions; never live provider calls."""
from copy import deepcopy
from pathlib import Path
import unittest

from fineprint.compiler import FallbackCompiler
from fineprint.models import to_dict
from fineprint.providers import LLMCompiler
from fineprint.repository import load_case
from fineprint.service import analyze_policy_text


class ExclusionContractTests(unittest.TestCase):
    def provider_value(self, wording, *, category=False):
        document = Path('fineprint/samples/aurora-imaging/policy.md').read_text()
        output = to_dict(FallbackCompiler().compile(document).output)
        old = next(c['text'] for c in output['policy']['clauses'] if c['id'] == 'B1')
        text = 'In-network elective hearing exam (76543): ' + wording
        document = document.replace(old, text)
        for clause in output['policy']['clauses']:
            if clause['text'] == old:
                clause['text'] = text
        for rule in output['rule_evidence']:
            for evidence in rule['evidence']:
                if evidence['quote'] == old:
                    evidence['quote'] = text
        benefit = output['policy']['benefits'][0]
        benefit.update(codes=[] if category else ['76543'], service_category='elective hearing exam' if category else None,
                       covered=False, deductible_applies=False, copay_cents=0, coinsurance_bps=0, conditions=[])
        return document, output

    def test_code_and_category_exclusions_retain_exact_evidence_and_full_liability(self):
        for wording in ('Not covered; full billed charge, no deductible or OOP credit.',
                        'Excluded at full billed charge; no deductible or OOP credit.'):
            for category in (False, True):
                with self.subTest(wording=wording, category=category):
                    document, value = self.provider_value(wording, category=category)
                    compiler = LLMCompiler('deepseek', transport=lambda *_: deepcopy(value), retries=1)
                    case, _ = load_case('aurora-imaging')
                    raw = to_dict(case)
                    raw['claim']['lines'][0].update(code='76543', service_category='elective hearing exam' if category else None)
                    raw['bill']['lines'][0]['code'] = '76543'
                    from fineprint.models import case_from_dict
                    result = analyze_policy_text(case_from_dict(raw), document, 'uploaded-policy', compiler=compiler)
                    self.assertEqual(result['report']['status'], 'ready')
                    line = result['report']['scenarios'][0]['lines'][0]
                    self.assertEqual(line['noncovered_cents'], raw['claim']['lines'][0]['billed_cents'])
                    self.assertEqual(line['patient_cents'], line['noncovered_cents'])
                    self.assertEqual((line['deductible_cents'], line['copay_cents'], line['coinsurance_cents']), (0, 0, 0))
                    exclusion = result['compilation']['output']['policy']['benefits'][0]
                    self.assertFalse(exclusion['covered'])
                    self.assertEqual(exclusion.get('conditions', []), [])
                    for rule in result['compilation']['output']['rule_evidence']:
                        for evidence in rule['evidence']:
                            self.assertEqual(document[evidence['start']:evidence['end']], evidence['quote'])

    def test_exclusion_without_exclusion_evidence_is_not_retained(self):
        document, value = self.provider_value('A fee must be confirmed with the plan.')
        benefit_id = value['policy']['benefits'][0]['id']
        rule = next(r for r in value['rule_evidence'] if r['rule_path'] == 'benefits.' + benefit_id)
        rule['evidence'] = [e for e in rule['evidence'] if '76543' in e['quote']]
        compiled = LLMCompiler('deepseek', transport=lambda *_: value, retries=1).compile(document)
        self.assertNotIn(benefit_id, {b.id for b in compiled.policy.benefits})
        self.assertTrue(compiled.output.coverage_gaps)

    def test_prompt_distinguishes_service_identity_from_eligibility(self):
        document, value = self.provider_value('Not covered; full billed charge.')
        prompts = []
        def transport(prompt, schema):
            prompts.append(prompt)
            return value
        LLMCompiler('deepseek', transport=transport, retries=1).compile(document)
        self.assertIn('Do not turn the identity of the selected service into an additional condition', prompts[0])
        self.assertIn('Explicit exclusions and not-covered services are executable benefits too', prompts[0])
        self.assertIn('referral', prompts[0])

    def test_an_actual_conditional_exclusion_still_requires_confirmation(self):
        document, value = self.provider_value('Not covered when performed outside the approved study; full billed charge.')
        value['policy']['benefits'][0]['conditions'] = ['Performed outside the approved study']
        compiler = LLMCompiler('deepseek', transport=lambda *_: deepcopy(value), retries=1)
        case, _ = load_case('aurora-imaging')
        raw = to_dict(case)
        raw['claim']['lines'][0]['code'] = '76543'
        raw['bill']['lines'][0]['code'] = '76543'
        from fineprint.models import case_from_dict
        result = analyze_policy_text(case_from_dict(raw), document, 'uploaded-policy', compiler=compiler)
        self.assertEqual(result['report']['status'], 'blocked')
        raw['claim']['lines'][0]['confirmed_conditions'] = ['Performed outside the approved study']
        result = analyze_policy_text(case_from_dict(raw), document, 'uploaded-policy', compiler=compiler)
        self.assertEqual(result['report']['status'], 'ready')
