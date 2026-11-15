"""Reader labels and repeated rows do not create patient-facing dead ends."""
from copy import deepcopy
from pathlib import Path
import unittest
from fineprint.compiler import FallbackCompiler
from fineprint.models import to_dict
from fineprint.providers import LLMCompiler
from fineprint.engine import calculate
from fineprint.service import analyze
from tests.helpers import payload,case

class InterpretationTests(unittest.TestCase):
    def test_identical_meanings_are_deduplicated_regardless_of_labels_or_ids(self):
        p=payload(); original=p['policy']['benefits'][0]
        p['policy']['benefits'].append({**deepcopy(original),'id':'repeated','label':'Other wording'})
        r=analyze(case(p));self.assertEqual(r['status'],'ready');self.assertEqual(len(r['scenarios']),1)
        self.assertEqual(r['summary']['illustrated_max_patient_cents'],12000)
        self.assertFalse(any(i['severity']=='error' for i in r['validation']))

    def test_same_label_with_genuinely_different_costs_computes_both(self):
        p=payload(); original=p['policy']['benefits'][0]
        p['policy']['benefits'].append({**deepcopy(original),'id':'other','deductible_applies':False})
        r=analyze(case(p));self.assertEqual(r['status'],'ready')
        self.assertEqual({s['patient_cents'] for s in r['scenarios']},{4000,12000})
        self.assertFalse(any(i['severity']=='error' for i in r['validation']))

    def test_same_ambiguity_label_across_networks_does_not_require_matching_display_labels(self):
        p=payload();p['claim']['lines'][0]['network']='unknown'
        for b in p['policy']['benefits']:b.update(ambiguity_group='one-group',label='Identical label')
        p['policy']['benefits'].append({**deepcopy(p['policy']['benefits'][0]),'id':'variant','deductible_applies':False})
        self.assertEqual(analyze(case(p))['status'],'ready')

    def test_actual_provider_recovery_merges_equivalent_rules_and_keeps_evidence(self):
        doc=Path('fineprint/samples/aurora-imaging/policy.md').read_text();value=to_dict(FallbackCompiler().compile(doc).output)
        b=value['policy']['benefits'][0];copy={**deepcopy(b),'id':'duplicate-source'};value['policy']['benefits'].append(copy)
        r=deepcopy(next(r for r in value['rule_evidence'] if r['rule_path']=='benefits.'+b['id']));r['rule_path']='benefits.duplicate-source';value['rule_evidence'].append(r)
        compiled=LLMCompiler('deepseek',transport=lambda *_:value,retries=1).compile(doc)
        self.assertEqual(len(compiled.policy.benefits),3)
        self.assertTrue(all(doc[e.start:e.end]==e.quote for r in compiled.output.rule_evidence for e in r.evidence))

    def test_unrelated_validation_errors_use_plain_words(self):
        p=payload();p['claim']['member_id']='different'
        r=analyze(case(p));self.assertEqual(r['status'],'blocked')
        self.assertNotIn('identity_mismatch',r['blocked_reason'])
        self.assertNotIn('duplicate_interpretation',r['blocked_reason'])

    def test_duplicate_machine_id_with_different_meaning_gets_distinct_readings(self):
        p=payload();original=p['policy']['benefits'][0]
        p['policy']['benefits'].append({**deepcopy(original),'deductible_applies':False})
        result=analyze(case(p))
        self.assertEqual(result['status'],'ready')
        self.assertEqual({s['patient_cents'] for s in result['scenarios']},{4000,12000})

    def test_normalization_is_idempotent_with_repeated_display_labels(self):
        from fineprint.interpretations import normalize_case
        p=payload();p['policy']['benefits'].append({**deepcopy(p['policy']['benefits'][0]),'id':'other','deductible_applies':False})
        first=normalize_case(case(p))
        self.assertEqual(normalize_case(first),first)
