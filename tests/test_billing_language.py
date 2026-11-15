"""Evidence grammar regressions, independent of benchmark cases/insurers."""
from copy import deepcopy
from pathlib import Path
import unittest

from fineprint.billing_language import explicit_balance_values
from fineprint.compiler import FallbackCompiler, recover_evidence, validate_output
from fineprint.models import to_dict


class BillingLanguageTests(unittest.TestCase):
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
