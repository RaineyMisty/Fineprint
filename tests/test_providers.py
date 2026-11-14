"""Provider transport contracts use test doubles only; no measured LLM results."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from fineprint.compiler import FallbackCompiler, OUTPUT_SCHEMA
from fineprint.models import to_dict
from fineprint.providers import LLMCompiler, ProviderError, _post

DOC=Path('fineprint/samples/aurora-imaging/policy.md').read_text()


class ProviderTransportTests(unittest.TestCase):
    def test_bedrock_converse_tool_schema_and_region(self):
        output=to_dict(FallbackCompiler().compile(DOC).output)
        client=Mock()
        client.converse.return_value={'output':{'message':{'content':[{'toolUse':{'name':'compile_policy','input':output}}]}}}
        boto=ModuleType('boto3');boto.client=Mock(return_value=client)
        config=ModuleType('botocore.config');config.Config=lambda **kwargs:kwargs
        modules={'boto3':boto,'botocore':ModuleType('botocore'),'botocore.config':config}
        with patch.dict(sys.modules,modules),patch.dict(os.environ,{'FINEPRINT_LLM_MODEL':'test-only-enabled-profile','AWS_REGION':'us-east-2'}):
            result=LLMCompiler('bedrock',retries=1).compile(DOC)
        self.assertEqual(result.backend,'bedrock')
        self.assertEqual(boto.client.call_args.kwargs['region_name'],'us-east-2')
        call=client.converse.call_args.kwargs
        self.assertEqual(call['modelId'],'test-only-enabled-profile')
        self.assertEqual(call['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'],OUTPUT_SCHEMA)
        self.assertEqual(call['toolConfig']['toolChoice'],{'tool':{'name':'compile_policy'}})

    def test_bedrock_failure_is_sanitized(self):
        client=Mock();client.converse.side_effect=RuntimeError('test-secret-must-not-leak')
        boto=ModuleType('boto3');boto.client=Mock(return_value=client)
        config=ModuleType('botocore.config');config.Config=lambda **kwargs:kwargs
        with patch.dict(sys.modules,{'boto3':boto,'botocore':ModuleType('botocore'),'botocore.config':config}),patch.dict(os.environ,{'FINEPRINT_LLM_MODEL':'test-only'}):
            with self.assertRaises(ProviderError) as error:LLMCompiler('bedrock',retries=1).compile(DOC)
        self.assertNotIn('test-secret',str(error.exception))
        self.assertIn('No fallback was substituted',str(error.exception))

    def test_https_request_uses_actual_json_and_timeout(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'{"ok":true}'
        with patch('fineprint.providers.urlopen',return_value=response) as send:
            self.assertEqual(_post('https://example.invalid',{'Authorization':'test-only'},{'text':'quote " and newline\n'}),{'ok':True})
        request=send.call_args.args[0]
        self.assertEqual(json.loads(request.data),{'text':'quote " and newline\n'})
        self.assertEqual(send.call_args.kwargs['timeout'],60)
