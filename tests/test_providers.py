"""Provider transport contracts use test doubles only; no measured LLM results."""
import json
from copy import deepcopy
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead

from fineprint.compiler import FallbackCompiler, PROVIDER_SCHEMA, get_compiler
from fineprint.models import to_dict
from fineprint.providers import LLMCompiler, ProviderError, _post

DOC=Path('fineprint/samples/aurora-imaging/policy.md').read_text()


class ProviderTransportTests(unittest.TestCase):
    def test_deepseek_json_mode_model_selection_and_shared_validation(self):
        good=to_dict(FallbackCompiler().compile(DOC).output)
        for model in ('', 'deepseek-flash'):
            with self.subTest(model=model), patch.dict(os.environ, {
                'FINEPRINT_LLM_PROVIDER':'deepseek', 'DEEPSEEK_API_KEY':'test-only',
                'FINEPRINT_DEEPSEEK_MODEL':model, 'FINEPRINT_LLM_MODEL':'ignored-other-provider-model',
            }), patch('fineprint.providers._post', return_value={
                'choices':[{'finish_reason':'stop','message':{'content':json.dumps(good)}}]
            }) as post:
                compiler=get_compiler()
                result=compiler.compile(DOC)
                self.assertEqual(result.backend,'deepseek')
                url,headers,body=post.call_args.args
                self.assertEqual(url,'https://api.deepseek.com/chat/completions')
                self.assertEqual(headers,{'Authorization':'Bearer test-only'})
                self.assertEqual(body['model'],model or 'deepseek-v4-pro')
                self.assertEqual(body['response_format'],{'type':'json_object'})
                self.assertEqual(body['max_tokens'],32768)
                self.assertEqual(body['thinking'],{'type':'disabled'})
                self.assertIn('SCHEMA:',body['messages'][0]['content'])
                self.assertEqual(to_dict(result.output),good)

    def test_deepseek_rejects_invalid_outputs_without_patching(self):
        good=to_dict(FallbackCompiler().compile(DOC).output)
        forged=deepcopy(good)
        for rule in forged['rule_evidence']:
            for evidence in rule['evidence']:
                evidence['quote']='invented quote'
        unknown=deepcopy(good);unknown['invented']=True
        float_money=deepcopy(good);float_money['policy']['networks']['in']['deductible_cents']=1.5
        malformed_nested=deepcopy(good);malformed_nested['rule_evidence']=[42]
        for invalid in ({},[],None,42,True,malformed_nested,forged,unknown,float_money,'null','[]','   ','{broken'):
            with self.subTest(invalid=type(invalid).__name__):
                transport=Mock(return_value=invalid)
                with self.assertRaisesRegex(ProviderError,'No fallback was substituted'):
                    LLMCompiler('deepseek',transport=transport,retries=2,sleep=lambda _:None).compile(DOC)
                self.assertEqual(transport.call_count,2)

    def test_deepseek_retries_http_transport_and_validation_failures(self):
        good=to_dict(FallbackCompiler().compile(DOC).output)
        def response(content,finish='stop'):
            return {'choices':[{'finish_reason':finish,'message':{'content':content}}]}
        failures=[HTTPError('https://api.deepseek.com',429,'private-body',{},None),
                  URLError('private-body'),TimeoutError('private-body'),IncompleteRead(b'private-body')]
        for failure in failures:
            reply=Mock();reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
            reply.read.return_value=json.dumps(response(json.dumps(good))).encode()
            sleep=Mock()
            with self.subTest(error=type(failure).__name__),patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}),patch('fineprint.providers.urlopen',side_effect=[failure,reply]):
                result=LLMCompiler('deepseek',retries=2,sleep=sleep).compile(DOC)
            self.assertEqual(result.attempts,1)
            sleep.assert_called_once_with(1)
        for invalid in (response(' ', 'length'),response(' '),{'choices':[]}):
            with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}),patch('fineprint.providers._post',return_value=invalid):
                with self.assertRaisesRegex(ProviderError,'No fallback was substituted'):
                    LLMCompiler('deepseek',retries=1).compile(DOC)

    def test_deepseek_missing_key_and_http_errors_are_sanitized(self):
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}),patch('fineprint.providers._post') as post:
            with self.assertRaisesRegex(ProviderError,'Set DEEPSEEK_API_KEY'):
                LLMCompiler('deepseek',retries=1).compile(DOC)
            post.assert_not_called()
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}),patch('fineprint.providers.urlopen',side_effect=HTTPError(
            'https://api.deepseek.com',401,'test-only-secret-body',{},None)):
            with self.assertRaises(ProviderError) as error:
                LLMCompiler('deepseek',retries=1).compile(DOC)
        self.assertIn('HTTP 401',str(error.exception))
        self.assertNotIn('test-only',str(error.exception))

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
        self.assertEqual(call['toolConfig']['tools'][0]['toolSpec']['inputSchema']['json'],PROVIDER_SCHEMA)
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
        self.assertEqual(send.call_args.kwargs['timeout'],300)

    def test_truncated_response_retries_with_larger_budget(self):
        good=to_dict(FallbackCompiler().compile(DOC).output)
        replies=[{'choices':[{'finish_reason':'length','message':{'content':'{"policy":'}}]},
                 {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(good)}}]}]
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}),patch('fineprint.providers._post',side_effect=replies) as post:
            result=LLMCompiler('deepseek',sleep=lambda _:None).compile(DOC)
        self.assertEqual(result.attempts,2)
        self.assertEqual([c.args[2]['max_tokens'] for c in post.call_args_list],[32768,65536])

    def test_transport_retries_do_not_consume_validation_attempt(self):
        reply=Mock();reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
        reply.read.return_value=b'{"ok":true}'
        with patch('fineprint.providers.urlopen',side_effect=[TimeoutError(),reply]) as send:
            self.assertEqual(_post('https://example.invalid',{}, {},sleep=lambda _:None),{'ok':True})
        self.assertEqual(send.call_count,2)

    def test_truncated_http_json_envelope_retries_transport(self):
        replies=[]
        for body in (b'{"choices":', b'{"ok":true}'):
            reply=Mock();reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
            reply.read.return_value=body
            replies.append(reply)
        with patch('fineprint.providers.urlopen',side_effect=replies) as send:
            self.assertEqual(_post('https://example.invalid',{}, {},sleep=lambda _:None),{'ok':True})
        self.assertEqual(send.call_count,2)
