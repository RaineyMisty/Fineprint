"""Evidence grammar regressions, independent of benchmark cases/insurers."""
from copy import deepcopy
from pathlib import Path
import unittest

from fineprint.billing_language import explicit_balance_values
from fineprint.compiler import FallbackCompiler, recover_evidence, validate_output
from fineprint.models import to_dict


class BillingLanguageTests(unittest.TestCase):
    def test_participating_provider_writeoffs_in_prose_and_clause_tables(self):
        sentence = "Covered participating-provider charges above the allowed amount must be written off; no balance billing."
        for text in (sentence, "| N-in | " + sentence + " |",
                     "Participating providers may not balance bill.",
                     "In-network charges above the allowed amount must be written off.",
                     "Participating providers cannot bill you for the difference.",
                     "For participating providers, you are not responsible for amounts above the allowed amount."):
            with self.subTest(text=text):
                self.assertEqual(explicit_balance_values([text], 'in'), {False})
                self.assertEqual(explicit_balance_values([text], 'out'), set())

    def test_source_line_table_evidence_preserves_sample_billing_terms(self):
        from fineprint.providers import LLMCompiler
        source = Path('fineprint/samples/aurora-imaging/policy.md').read_text()
        value = to_dict(FallbackCompiler().compile(source).output)
        del value['policy']['clauses']
        for terms in value['policy']['networks'].values():
            for field in ('deductible_clause', 'oop_clause', 'network_clause'):
                del terms[field]
        for benefit in value['policy']['benefits']:
            del benefit['clause_ids']
        for rule in value['rule_evidence']:
            for evidence in rule['evidence']:
                quote = evidence['quote']
                numbers = [n for n,line in enumerate(source.splitlines(),1) if quote in line]
                evidence.clear()
                evidence.update(source_document_id='uploaded-policy', section='Benefits', source_lines=numbers)
        result = LLMCompiler('deepseek', transport=lambda *_: value, retries=1).compile(source)
        self.assertIs(result.policy.networks['in'].balance_billing, False)
        self.assertIs(result.policy.networks['out'].balance_billing, True)
        self.assertFalse(any('balance_billing' in warning and 'Dropped' in warning for warning in result.output.warnings))

    def test_missing_or_contradictory_billing_evidence_is_still_rejected(self):
        from fineprint.compiler import _balance_supported
        self.assertFalse(_balance_supported(False, [] , 'in'))
        self.assertFalse(_balance_supported(True, ['Participating providers may not balance bill.'], 'in'))
        self.assertFalse(_balance_supported(False, ['Out-of-network balance billing is permitted.'], 'in'))
        self.assertTrue(_balance_supported(False, ['Participating providers absorb residual negotiated-price variance.'], 'in'))

    def test_unmatched_billing_quote_does_not_get_source_backed_fallback(self):
        source = Path('fineprint/samples/aurora-imaging/policy.md').read_text()
        value = to_dict(FallbackCompiler().compile(source).output)
        rule = next(r for r in value['rule_evidence'] if r['rule_path'] == 'networks.in.balance_billing')
        for evidence in rule['evidence']:
            evidence['quote'] = 'Invented participating provider billing terms absent from this document.'
        recovered = recover_evidence(value, source, 'uploaded-policy')
        checked = validate_output(recovered, source, 'uploaded-policy')
        self.assertIsNone(checked.policy.networks['in'].balance_billing)
        self.assertNotIn('networks.in.balance_billing', {r.rule_path for r in checked.rule_evidence})

    def test_explicit_permission_in_both_word_orders(self):
        for text in ("Out-of-network providers may balance bill excess charges.",
                     "Out-of-network: excess balance billing is permitted.",
                     "OUT OF NETWORK: balance billing = yes."):
            with self.subTest(text=text):
                self.assertEqual(explicit_balance_values([text], "out"), {True})
                self.assertEqual(explicit_balance_values([text], "in"), set())

    def test_prohibitions_and_unrelated_negations(self):
        for text in ("No excess billing is allowed in network.",
                     "IN NETWORK: balance billing = no.",
                     "Participating providers: excess balance billing prohibited.",
                     "No balance-billing is allowed for participating providers."):
            with self.subTest(text=text):
                self.assertEqual(explicit_balance_values([text], "in"), {False})
        self.assertEqual(explicit_balance_values([
            "No referral required. Out-of-network providers may balance bill."], "out"), {True})
        for text in ("Out-of-network providers are not permitted to balance bill.",
                     "Out-of-network providers are not allowed to balance bill.",
                     "Out-of-network providers are prohibited from balance billing."):
            self.assertEqual(explicit_balance_values([text], "out"), {False})
        for text in ("You pay less in network.", "Balance billing is not discussed.",
                     "Can providers balance bill?", "Balance billing is not prohibited."):
            self.assertEqual(explicit_balance_values([text], "in"), set())

    def test_network_question_answers_do_not_cross_networks(self):
        text = "Can providers collect excess charges? Participating providers cannot. Nonparticipating providers may."
        self.assertEqual(explicit_balance_values([text], "in"), {False})
        self.assertEqual(explicit_balance_values([text], "out"), {True})

    def test_table_columns_and_network_rows(self):
        text = "| Network | Deductible | Excess balance billing |\n| --- | --- | --- |\n| In-network | $725 | prohibited |\n| Out-of-network | $1450 | permitted |"
        self.assertEqual(explicit_balance_values([text], "in"), {False})
        self.assertEqual(explicit_balance_values([text], "out"), {True})
        transposed = "| Term | In network | Out of network |\n| Balance billing | No | Yes |"
        self.assertEqual(explicit_balance_values([transposed], "in"), {False})
        self.assertEqual(explicit_balance_values([transposed], "out"), {True})
        self.assertEqual(explicit_balance_values(["| Network | Covered |\n| In network | No |"], "in"), set())

    def test_conflicts_remain_conflicts(self):
        self.assertEqual(explicit_balance_values([
            "Out-of-network balance billing is permitted.",
            "Out-of-network balance billing is prohibited."], "out"), {False, True})

    def test_missing_display_name_preserves_sourced_rules(self):
        source = Path("fineprint/samples/aurora-imaging/policy.md").read_text()
        good = to_dict(FallbackCompiler().compile(source).output)
        for missing in (None, "", "  "):
            value = deepcopy(good)
            value['policy']['name'] = missing
            recovered = recover_evidence(value, source, 'uploaded-policy')
            result = validate_output(recovered, source, 'uploaded-policy')
            self.assertTrue(result.policy.name.strip())
            self.assertEqual(result.policy.networks, FallbackCompiler().compile(source).policy.networks)
            self.assertEqual(result.policy.benefits, FallbackCompiler().compile(source).policy.benefits)
