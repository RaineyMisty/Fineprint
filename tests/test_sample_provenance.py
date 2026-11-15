"""Server-derived sample labels survive compile/check; client flags do not."""
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch

from fineprint.repository import demo_inputs, input_metadata, sample_inputs
from fineprint.server import Handler
from fineprint.models import ModelError


class SampleProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict('os.environ', {'FINEPRINT_LLM_PROVIDER': 'fallback'})
        cls.env.start()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.env.stop()

    def post(self, path, value):
        conn = HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('POST', path, json.dumps(value), {'Content-Type': 'application/json'})
        response = conn.getresponse(); status = response.status; body = json.load(response); conn.close()
        return status, body

    def test_all_sample_receipts_keep_manifest_title_id_and_synthetic_label(self):
        for name in ('aurora-imaging', 'mosaic-oop', 'mosaic-therapy'):
            sample = sample_inputs(name)
            inputs = {**sample['inputs'], 'sample_id': name, 'synthetic': False}
            status, compiled = self.post('/api/compile', {'document': inputs['policy'], 'document_id': name+'/policy.md'})
            self.assertEqual(status, 200)
            with patch('fineprint.compiler.FallbackCompiler.compile', side_effect=AssertionError('Recompiled')):
                status, result = self.post('/api/check', {**inputs, **compiled})
            self.assertEqual(status, 200)
            self.assertEqual(result['case']['id'], sample['id'])
            self.assertEqual(result['case']['title'], sample['title'])
            self.assertIs(result['case']['synthetic'], True)
            self.assertEqual(result['report']['status'], 'ready')

    def test_upload_boolean_does_not_claim_sample_provenance(self):
        inputs = {**sample_inputs('aurora-imaging')['inputs'], 'synthetic': True}
        status, result = self.post('/api/check', inputs)
        self.assertEqual(status, 200)
        self.assertIs(result['case']['synthetic'], False)
        self.assertEqual(result['case']['title'], 'Your claim')

    def test_unknown_or_changed_sample_is_rejected(self):
        inputs = {**sample_inputs('aurora-imaging')['inputs'], 'sample_id': 'aurora-imaging'}
        for change in ({'sample_id': '../../elsewhere'}, {'sample_id': True},
                       {'policy': inputs['policy']+'\n'}, {'bill': inputs['bill']+'\n'},
                       {'allowed_evidence': {}}):
            self.assertEqual(self.post('/api/check', {**inputs, **change})[0], 400)

    def test_demo_accepts_uploaded_policy_identity_but_not_changed_synthetic_facts(self):
        demo = demo_inputs('kaiser-real-sbc')
        inputs = deepcopy(demo['inputs'])
        inputs.update(sample_id=demo['id'], policy='A real uploaded policy', synthetic=False)
        inputs['claim_context']['policy_id'] = 'compiler-assigned-id'
        self.assertEqual(input_metadata(inputs), {k: demo[k] for k in ('id', 'title', 'synthetic')})
        inputs['claim_context']['accumulators']['in']['oop_paid_cents'] += 1
        with self.assertRaises(ModelError):
            input_metadata(inputs)
        inputs['claim_context'] = None
        with self.assertRaises(ModelError):
            input_metadata(inputs)
