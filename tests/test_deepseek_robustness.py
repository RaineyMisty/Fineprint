"""DeepSeek retry bounds and sampling contracts; no live requests."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fineprint.compiler import FallbackCompiler
from fineprint.models import ModelError, to_dict
from fineprint.providers import LLMCompiler, ProviderError

DOC = Path('fineprint/samples/aurora-imaging/policy.md').read_text()


class DeepSeekRobustnessTests(unittest.TestCase):
    def test_two_transport_retries_use_backoff_and_do_not_multiply_compile_budget(self):
        sleep = Mock()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only'}), patch(
                'fineprint.providers.urlopen', side_effect=TimeoutError('private-response')) as send:
            compiler = LLMCompiler('deepseek', retries=3, sleep=sleep)
            with self.assertRaises(ProviderError) as error:
                compiler.compile(DOC)
        self.assertEqual(send.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])
        self.assertNotIn('private-response', str(error.exception))
        self.assertEqual(len(compiler.attempt_audit), 1)

    def test_zero_temperature_and_longer_timeout_are_explicit(self):
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test-only', 'FINEPRINT_LLM_TIMEOUT': '450'}), patch(
                'fineprint.providers._post', return_value={'choices': [
                    {'finish_reason': 'stop', 'message': {'content': '{}'}}]}) as post:
            compiler = LLMCompiler('deepseek')
            compiler._request('synthetic prompt', {})
        self.assertEqual(post.call_args.args[2]['temperature'], 0)
        self.assertEqual(post.call_args.args[2]['thinking'], {'type': 'disabled'})
        self.assertNotIn('seed', post.call_args.args[2])
        self.assertEqual(post.call_args.kwargs['timeout'], 450)
        self.assertEqual(post.call_args.kwargs['attempts'], 3)

    def test_no_supported_rules_gets_one_retry_and_records_both_attempts(self):
        good = FallbackCompiler().compile(DOC).output
        transport = Mock(return_value=json.dumps(to_dict(good)))
        with patch('fineprint.providers.validate_output', side_effect=[
                ModelError('No supported executable rules found'), good]):
            compiler = LLMCompiler('deepseek', transport=transport, retries=1, sleep=lambda _: None)
            result = compiler.compile(DOC)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(compiler.attempt_audit), 2)
        self.assertIn('Previous attempt failed validation', transport.call_args.args[0])

    def test_repeated_no_rules_stops_after_one_retry_even_with_larger_budget(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        transport = Mock(return_value=good)
        with patch('fineprint.providers.validate_output', side_effect=ModelError('No supported executable rules found')):
            with self.assertRaises(ProviderError):
                LLMCompiler('deepseek', transport=transport, retries=5, sleep=lambda _: None).compile(DOC)
        self.assertEqual(transport.call_count, 2)


if __name__ == '__main__':
    unittest.main()
