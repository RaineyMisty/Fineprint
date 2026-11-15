import hashlib
import json
from pathlib import Path
import unittest
from dataclasses import replace
from unittest.mock import patch

from fineprint.compiler import FallbackCompiler
from fineprint.eval import aggregate, extraction_counts, markdown_report, outcome_signature, run_evaluation
from fineprint.models import ModelError
from fineprint.providers import LLMCompiler
from fineprint.repository import load_case


class EvaluationTests(unittest.TestCase):
    def test_deepseek_metadata_and_failed_denominators_with_mock_transport(self):
        with patch.dict('os.environ',{'FINEPRINT_DEEPSEEK_MODEL':'deepseek-flash','FINEPRINT_LLM_MODEL':'ignored'}):
            compiler=LLMCompiler('deepseek',transport=lambda *_: {},retries=1)
        report=run_evaluation(compiler)
        self.assertEqual(report['model'],'deepseek-flash')
        self.assertEqual(report['request_config']['attempt_limit'],1)
        self.assertEqual(report['groups']['all']['end_to_end'],dict(success=0,total=10,rate=0))
        self.assertEqual(len([p for p in report['policies'] if p['error']]),5)
        self.assertIn('deepseek-flash',markdown_report(report))

    def test_real_offline_pipeline_counts_and_holdout_failure(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Evaluation must stay offline')):
            report=run_evaluation(FallbackCompiler())
        self.assertEqual(report['backend'],'fallback')
        self.assertEqual(report['parser_matches_holdout_freeze'], report['parser_sha256'] == json.loads(Path('fineprint/benchmark/manifest.json').read_text())['parser_sha256'])
        self.assertEqual(report['groups']['seen']['end_to_end']['success'],6)
        self.assertEqual(report['groups']['held_out']['end_to_end']['success'],2)
        all=report['groups']['all']
        self.assertEqual((all['policies'],all['cases']),(5,10))
        self.assertEqual(all['calculation']['exact'],8)
        self.assertEqual(all['discrepancy']['fn'],1)
        self.assertEqual(all['discrepancy']['tn'],2)
        self.assertEqual(all['discrepancy']['abstentions'],3)
        self.assertLess(all['evidence']['coverage_rate'],1)
        self.assertEqual(all['evidence']['traceability_rate'],1)
        self.assertEqual(len([p for p in report['policies'] if p['error']]),1)
        self.assertIn('harbor-correct-office',markdown_report(report))

    def test_wrong_field_counts_both_false_positive_and_false_negative(self):
        case,_=load_case('aurora-imaging')
        gold=case.policy
        benefits=[replace(gold.benefits[0],copay_cents=2600),*gold.benefits[1:]]
        counts=extraction_counts(replace(gold,benefits=benefits),gold)
        self.assertEqual((counts['fp'],counts['fn']),(1,1))
        self.assertEqual(extraction_counts(None,gold)['tp'],0)
        self.assertGreater(extraction_counts(None,gold)['fn'],0)

    def test_same_patient_total_does_not_hide_component_error(self):
        line=dict(claim_line_id='L',network='in',allowed_cents=10000,deductible_cents=1000,
                  copay_cents=1000,coinsurance_cents=0,noncovered_cents=0,balance_cents=0,
                  patient_cents=2000,insurer_paid_cents=8000,adjustment_cents=0)
        wrong={**line,'deductible_cents':0,'copay_cents':2000}
        self.assertNotEqual(outcome_signature([line]),outcome_signature([wrong]))

    def test_false_positives_abstentions_and_zero_denominators(self):
        policies=[dict(fields=dict(tp=2,fp=1,fn=3),emitted_rules=2,traceable_rules=1,gold_rules=3)]
        cases=[dict(gold_discrepancy=g,predicted_discrepancy=p,calculation_exact=False,end_to_end_success=False)
               for g,p in [(True,True),(True,None),(False,True),(False,False),(None,None)]]
        g=aggregate(policies,cases)
        self.assertEqual(g['discrepancy']['precision'],0.5)
        self.assertEqual(g['discrepancy']['recall'],0.5)
        self.assertEqual(g['discrepancy']['false_positive_rate'],0.5)
        self.assertEqual(g['discrepancy']['abstentions'],2)
        self.assertIsNone(aggregate([],[])['extraction']['precision'])
        self.assertIsNone(aggregate([],[])['calculation']['accuracy'])

    def test_total_compilation_failure_is_never_dropped(self):
        class FailingCompiler:
            name='fallback'
            def compile(self,text,document_id):
                self_test.assertIsInstance(text,str)
                self_test.assertIsInstance(document_id,str)
                raise ModelError('Deliberately failed unit-test transport')
        self_test=self
        report=run_evaluation(FailingCompiler())
        g=report['groups']['all']
        self.assertEqual(g['extraction']['recall'],0)
        self.assertEqual(g['calculation']['accuracy'],0)
        self.assertEqual(g['end_to_end']['total'],10)
        self.assertEqual(g['evidence']['coverage_rate'],0)
        self.assertEqual(g['discrepancy']['recall'],0)


class EndToEndOracleTests(unittest.TestCase):
    def test_wrong_final_bill_cannot_pass_end_to_end(self):
        from fineprint.service import analyze
        def broken_bill(*args,**kwargs):
            report=analyze(*args,**kwargs)
            for comparison in report['comparisons']:
                comparison['fineprint_remaining_cents']+=1
            return report
        with patch('fineprint.eval.analyze',side_effect=broken_bill):
            report=run_evaluation(FallbackCompiler())
        self.assertEqual(report['groups']['all']['calculation']['exact'],8)
        self.assertEqual(report['groups']['all']['end_to_end']['success'],0)
