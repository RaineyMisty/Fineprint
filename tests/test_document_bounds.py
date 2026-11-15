"""Physical ledger bounds are separate from the uncapped policy audit."""
from copy import deepcopy
import unittest
from fineprint.engine import calculate
from fineprint.service import analyze
from tests.helpers import payload, case


class DocumentBoundsTests(unittest.TestCase):
    def low_bill(self):
        p = payload()
        p['claim']['lines'][0]['insurer'].update(deductible_cents=0, copay_cents=4000,
            coinsurance_cents=0, insurer_paid_cents=16000)
        p['bill']['lines'][0].update(insurance_paid_cents=16000, balance_due_cents=4000)
        return p

    def test_every_reading_is_bounded_by_posted_charge_payment_and_patient_bill(self):
        p = self.low_bill()
        p['claim']['lines'][0]['network'] = 'unknown'
        for scenario in calculate(case(p)):
            r = scenario.lines[0]
            self.assertGreaterEqual(r.patient_cents, 0)
            self.assertLessEqual(r.patient_cents, 4000)
            self.assertEqual(r.patient_cents, r.deductible_cents+r.copay_cents+r.coinsurance_cents+r.noncovered_cents+r.balance_cents)
            self.assertEqual(r.patient_cents+r.insurer_paid_cents+r.adjustment_cents, 30000)
            self.assertLessEqual(scenario.patient_cents, 4000)

    def test_missing_price_uses_eob_and_payments_instead_of_gross_charge_endpoints(self):
        p = self.low_bill(); p['allowed_evidence'].clear()
        p['claim']['lines'][0]['network'] = 'unknown'
        p['claim']['accumulators']['in'].update(deductible_paid_cents=None, oop_paid_cents=None)
        results = calculate(case(p))
        self.assertTrue(results)
        self.assertEqual({r.lines[0].allowed_cents for r in results}, {20000})
        self.assertEqual({r.patient_cents for r in results}, {4000})
        self.assertTrue(all('recorded' in ' '.join(r.assumptions) for r in results))

    def test_bill_inside_range_is_not_an_overcharge(self):
        p = self.low_bill(); b = p['policy']['benefits'][0]
        b.update(deductible_applies=False, copay_cents=0, coinsurance_bps=0, ambiguity_group='alternatives')
        p['policy']['benefits'].append({**deepcopy(b), 'id':'alternate', 'label':'Other clause', 'copay_cents':4000})
        r = analyze(case(p))
        self.assertEqual(r['status'], 'ready')
        self.assertEqual((r['summary']['illustrated_min_patient_cents'],r['summary']['illustrated_max_patient_cents']), (0,4000))
        self.assertEqual(r['summary']['potential_overpayment_min_cents'],0)
        self.assertEqual(r['summary']['bill_status'],'consistent')

    def test_paid_amount_is_counted_once_and_can_be_refunded(self):
        p = self.low_bill(); p['bill']['lines'][0].update(patient_paid_cents=3000,balance_due_cents=1000)
        p['policy']['benefits'][0].update(deductible_applies=False,copay_cents=2000,coinsurance_bps=0)
        r=analyze(case(p))['comparisons'][0]['lines'][0]
        self.assertEqual((r['fineprint_patient_cents'],r['fineprint_remaining_cents'],r['potential_refund_cents']),(2000,0,1000))

    def test_uncapped_contract_arithmetic_remains_available_for_audit(self):
        p=self.low_bill(); r=calculate(case(p))[0].lines[0]
        self.assertEqual(r.policy_patient_cents,12000)
        self.assertEqual(r.patient_cents,4000)

    def test_in_network_is_limited_by_eob_allowance_after_recorded_plan_payment(self):
        p=payload()
        # The contract allowance is higher than the recorded EOB allowance.
        p['claim']['lines'][0]['insurer'].update(allowed_cents=15000)
        r=calculate(case(p))[0].lines[0]
        self.assertLessEqual(r.patient_cents,15000-8000)
        self.assertEqual(r.policy_patient_cents,12000)

    def test_upload_payload_cannot_disable_document_bounds(self):
        from fineprint.repository import sample_inputs
        from fineprint.service import check_documents
        from fineprint.compiler import FallbackCompiler
        inputs={**sample_inputs('mosaic-therapy')['inputs'],'policy_audit':True,'bound_to_documents':False}
        result=check_documents(inputs,compiler=FallbackCompiler())
        self.assertEqual(result['report']['summary']['illustrated_max_patient_cents'],4000)
