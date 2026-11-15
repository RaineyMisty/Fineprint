"""Offline contract tests. Injected transports below are test doubles, not LLM results."""
import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fineprint.compiler import FallbackCompiler, OUTPUT_SCHEMA, get_compiler, rule_paths, validate_output, validate_schema
from fineprint.models import ModelError, to_dict
from fineprint.providers import LLMCompiler, ProviderError

DOC = Path('fineprint/samples/aurora-imaging/policy.md').read_text()


class CompilerTests(unittest.TestCase):
    def test_prose_compilation_and_exact_unicode_spans(self):
        result = FallbackCompiler().compile(DOC, 'doc-1')
        self.assertEqual(result.backend, 'fallback')
        self.assertEqual(len(result.policy.benefits), 3)
        self.assertEqual(result.policy.networks['in'].deductible_cents, 100000)
        self.assertFalse(result.output.unresolved)
        self.assertEqual({r.rule_path for r in result.output.rule_evidence}, rule_paths(result.policy))
        for r in result.output.rule_evidence:
            for e in r.evidence:
                self.assertEqual(DOC[e.start:e.end], e.quote)
                self.assertEqual(e.source_document_id, 'doc-1')

    def test_schema_is_closed_and_rejects_coercion(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        mutations = [lambda d: d.update(extra=True), lambda d: d['policy'].update(currency='EUR'),
                     lambda d: d['policy']['networks']['in'].update(deductible_cents=1.0),
                     lambda d: d['policy']['networks']['in'].update(deductible_cents=True),
                     lambda d: d['policy']['benefits'][0].update(coinsurance_bps=10001),
                     lambda d: d['rule_evidence'][0].update(confidence_bps=-1)]
        for mutate in mutations:
            value = deepcopy(good); mutate(value)
            with self.assertRaises(ModelError): validate_schema(value)
        validate_schema(good, OUTPUT_SCHEMA)

    def test_source_fabrication_and_missing_evidence_rejected(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        mutations = [lambda d: d['rule_evidence'][0]['evidence'][0].update(start=0),
                     lambda d: d['rule_evidence'][0]['evidence'][0].update(source_document_id='wrong'),
                     lambda d: d['rule_evidence'].pop(),
                     lambda d: d['policy']['clauses'][0].update(text='Invented clause')]
        for mutate in mutations:
            value = deepcopy(good); mutate(value)
            with self.assertRaises(ModelError): validate_output(value, DOC, 'uploaded-policy')

    def test_ambiguity_is_preserved(self):
        text = Path('fineprint/samples/mosaic-therapy/policy.md').read_text()
        result = FallbackCompiler().compile(text)
        alternatives = [b for b in result.policy.benefits if b.network == 'in']
        self.assertEqual(len(alternatives), 2)
        self.assertTrue(alternatives[0].ambiguity_group)
        self.assertEqual(alternatives[0].ambiguity_group, alternatives[1].ambiguity_group)
        self.assertTrue(any(r.confidence_bps < 10000 for r in result.output.rule_evidence))

    def test_missing_terms_fail_closed_and_unknown_benefit_is_unresolved(self):
        with self.assertRaises(ModelError): FallbackCompiler().compile('A plan pays some claims')
        with self.assertRaises(ModelError): FallbackCompiler().compile(DOC.replace('Apply OOP cap in that order.', ''))
        result = FallbackCompiler().compile(DOC.replace('deductible then 20% member coinsurance', 'subject to administrator discretion'))
        self.assertTrue(result.output.unresolved)
        self.assertFalse(any('70551' in b.codes and b.network == 'in' for b in result.policy.benefits))

    def test_environment_selection_and_no_silent_fallback(self):
        with patch.dict(os.environ, {'FINEPRINT_LLM_PROVIDER': 'fallback'}):
            self.assertIsInstance(get_compiler(), FallbackCompiler)
        with self.assertRaises(ProviderError): get_compiler('typo')
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with self.assertRaisesRegex(ProviderError, 'No fallback was substituted'):
                LLMCompiler('openai', retries=1).compile(DOC)

    def test_validation_retries_test_transport_only(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        calls = []
        def transport(prompt, schema):
            calls.append(prompt)
            return '{}' if len(calls) == 1 else json.dumps(good)
        result = LLMCompiler('openai', transport=transport, sleep=lambda _: None).compile(DOC)
        self.assertEqual(result.attempts, 2)
        self.assertIn('Previous attempt failed validation', calls[1])
        with self.assertRaisesRegex(ProviderError, '3 attempts'):
            LLMCompiler('anthropic', transport=lambda *_: {}, sleep=lambda _: None).compile(DOC)

    def test_llm_recovers_wrapped_quotes_and_ignores_model_offsets(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        # Simulate PDF wrapping while the model returns collapsed whitespace.
        wrapped = DOC.replace('annual in-network', 'annual\n  in-network')
        for rule in good['rule_evidence']:
            for evidence in rule['evidence']:
                evidence.pop('start'); evidence.pop('end')
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(wrapped)
        for rule in result.output.rule_evidence:
            for evidence in rule.evidence:
                self.assertEqual(wrapped[evidence.start:evidence.end], evidence.quote)
        self.assertFalse(result.output.unresolved)

    def test_llm_multiple_evidence_entries_merge_and_bad_benefit_drops(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        benefit_rule = next(r for r in good['rule_evidence'] if r['rule_path'].startswith('benefits.'))
        first, second = deepcopy(benefit_rule), deepcopy(benefit_rule)
        first['evidence'] = first['evidence'][:1]
        second['evidence'] = second['evidence'][1:]
        good['rule_evidence'].remove(benefit_rule)
        good['rule_evidence'] += [first, second]
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertFalse(result.output.unresolved)
        rule = next(r for r in result.output.rule_evidence if r.rule_path == benefit_rule['rule_path'])
        self.assertEqual(len(rule.evidence), 2)
        first['evidence'][0]['quote'] = 'This quote is not in the source.'
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertEqual(len(result.policy.benefits), 2)
        self.assertTrue(any(benefit_rule['rule_path'] in warning for warning in result.output.unresolved))
        self.assertNotIn(benefit_rule['rule_path'], {r.rule_path for r in result.output.rule_evidence})

    def test_plan_level_null_metadata_and_partial_network_remain_explicit(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        good['policy'].update(member_id=None, effective_from=None, effective_to=None)
        for rule in good['rule_evidence']:
            if rule['rule_path'] == 'networks.out.oop_max_cents':
                rule['evidence'][0]['quote'] = 'An invented out-of-network cap.'
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertIsNone(result.policy.member_id)
        self.assertIsNone(result.policy.effective_from)
        self.assertEqual(set(result.policy.networks), {'in'})
        self.assertTrue(all(b.network == 'in' for b in result.policy.benefits))
        self.assertTrue(any('networks.out' in issue for issue in result.output.unresolved))

    def test_llm_path_errors_give_exact_contract_on_retry(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        invalid = deepcopy(good)
        invalid['rule_evidence'][0]['rule_path'] = 'policy.networks.in.deductible_cents'
        calls = []
        def transport(prompt, schema):
            calls.append(prompt)
            return invalid if len(calls) == 1 else good
        result = LLMCompiler('deepseek', transport=transport, sleep=lambda _:None).compile(DOC)
        self.assertEqual(result.attempts, 2)
        self.assertIn('Invalid rule_evidence.rule_path', calls[1])
        self.assertIn('No \'policy.\' prefix or benefit field suffix', calls[1])
        self.assertFalse(result.output.unresolved)
        invalid['rule_evidence'][0]['rule_path'] = 'benefits.B1.copay_cents'
        with self.assertRaisesRegex(ProviderError, 'Invalid rule_evidence.rule_path'):
            LLMCompiler('deepseek', transport=lambda *_:invalid, retries=1).compile(DOC)

    def test_compact_provider_quotes_generate_exact_local_clauses(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        expected = good['policy']['benefits'][0]['copay_cents']
        del good['policy']['clauses']
        for terms in good['policy']['networks'].values():
            for key in ('deductible_clause', 'oop_clause', 'network_clause'):
                del terms[key]
        for benefit in good['policy']['benefits']:
            del benefit['clause_ids']
        for rule in good['rule_evidence']:
            for e in rule['evidence']:
                del e['start']; del e['end']
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertFalse(result.output.unresolved)
        self.assertEqual(result.policy.benefits[0].copay_cents, expected)
        for clause in result.policy.clauses:
            self.assertIn(clause.text, DOC)
        good['policy']['benefits'][0]['codes'] = ['99999']
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertEqual(len(result.policy.benefits), 2)
        self.assertTrue(any('code' in warning for warning in result.output.unresolved))
        good['policy']['benefits'][0]['codes'] = []
        result = LLMCompiler('deepseek', transport=lambda *_:good, sleep=lambda _:None).compile(DOC)
        self.assertEqual(len(result.policy.benefits), 2)
        self.assertTrue(result.output.unresolved)

    def test_explicit_policy_id_is_validated_from_source_not_claim_or_gold(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        wrong = deepcopy(good)
        wrong['policy']['id'] = 'uploaded-policy'
        calls = []
        def transport(prompt, schema):
            calls.append(prompt)
            return wrong if len(calls) == 1 else good
        result = LLMCompiler('deepseek', transport=transport, sleep=lambda _:None).compile(DOC)
        self.assertEqual(result.policy.id, good['policy']['id'])
        self.assertEqual(result.attempts, 2)
        self.assertIn('policy.id must copy the explicit Policy:', calls[1])

    def test_generic_quote_cannot_establish_balance_billing_and_claim_is_blocked(self):
        from dataclasses import replace
        from fineprint.repository import load_case
        from fineprint.service import analyze
        value = to_dict(FallbackCompiler().compile(DOC).output)
        del value['policy']['clauses']
        for terms in value['policy']['networks'].values():
            for key in ('deductible_clause', 'oop_clause', 'network_clause'):
                del terms[key]
        for benefit in value['policy']['benefits']:
            del benefit['clause_ids']
        for rule in value['rule_evidence']:
            for evidence in rule['evidence']:
                del evidence['start']; del evidence['end']
                if rule['rule_path'] == 'networks.in.balance_billing':
                    evidence['quote'] = 'Individual annual in-network deductible: $1000.00.'
        result = LLMCompiler('deepseek', transport=lambda *_:value, sleep=lambda _:None).compile(DOC)
        self.assertIsNone(result.policy.networks['in'].balance_billing)
        self.assertIsNone(result.policy.networks['in'].network_clause)
        paths = {r.rule_path for r in result.output.rule_evidence}
        self.assertIn('networks.in.deductible_cents', paths)
        self.assertIn('networks.in.oop_max_cents', paths)
        self.assertNotIn('networks.in.balance_billing', paths)
        references = {ref for benefit in result.policy.benefits for ref in benefit.clause_ids}
        for terms in result.policy.networks.values():
            references.update(ref for ref in (terms.deductible_clause, terms.oop_clause, terms.network_clause) if ref)
        self.assertEqual({clause.id for clause in result.policy.clauses}, references)
        self.assertTrue(result.output.unresolved)
        original, _ = load_case('aurora-imaging')
        report = analyze(replace(original, policy=result.policy))
        self.assertEqual(report['status'], 'blocked')
        self.assertFalse(report['scenarios'])
        self.assertIn('incomplete_network', {issue['code'] for issue in report['validation']})

    def test_partial_quote_failure_retries_and_keeps_only_validated_output(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        partial = deepcopy(good)
        rule = next(r for r in partial['rule_evidence'] if r['rule_path'].startswith('benefits.'))
        rule['evidence'][0]['quote'] = 'This sentence does not occur in the policy.'
        calls = []
        def transport(prompt, schema):
            calls.append(prompt)
            return partial if len(calls) == 1 else good
        result = LLMCompiler('deepseek', transport=transport, retries=2, sleep=lambda _:None).compile(DOC)
        self.assertEqual(result.attempts, 2)
        self.assertFalse(result.output.unresolved)
        self.assertEqual(len(result.policy.benefits), 3)
        self.assertIn('Local source validation rejected these rules', calls[1])
        replies = iter([partial, {}])
        result = LLMCompiler('deepseek', transport=lambda *_:next(replies), retries=2, sleep=lambda _:None).compile(DOC)
        self.assertEqual(len(result.policy.benefits), 2)
        self.assertTrue(result.output.unresolved)
        self.assertTrue(any('from attempt 1 after 2 attempts' in w for w in result.output.warnings))

    def test_out_of_network_limit_cannot_reuse_an_unqualified_in_network_quote(self):
        value = to_dict(FallbackCompiler().compile(DOC).output)
        in_rule = next(r for r in value['rule_evidence'] if r['rule_path'] == 'networks.in.deductible_cents')
        out_rule = next(r for r in value['rule_evidence'] if r['rule_path'] == 'networks.out.deductible_cents')
        out_rule['evidence'] = deepcopy(in_rule['evidence'])
        value['policy']['networks']['out']['deductible_clause'] = value['policy']['networks']['in']['deductible_clause']
        result = LLMCompiler('deepseek', transport=lambda *_:value, retries=1).compile(DOC)
        self.assertNotIn('out', result.policy.networks)
        self.assertTrue(result.output.unresolved)

    def test_live_request_payload_contracts_with_test_http(self):
        good = to_dict(FallbackCompiler().compile(DOC).output)
        for provider in ('openai', 'anthropic'):
            response = ({'choices': [{'message': {'content': json.dumps(good)}}]} if provider == 'openai'
                        else {'content': [{'type': 'text', 'text': json.dumps(good)}]})
            with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only', 'ANTHROPIC_API_KEY': 'test-only'}), patch('fineprint.providers._post', return_value=response) as post:
                LLMCompiler(provider).compile(DOC)
                url, headers, body = post.call_args.args
                self.assertTrue(url.startswith('https://api.'))
                self.assertIn('messages', body)
                self.assertTrue('response_format' in body or 'output_config' in body)
