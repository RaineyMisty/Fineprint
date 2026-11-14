import json
import unittest

from fineprint.adapters import dollars
from fineprint.extraction import ProviderPolicyExtractor, StructuredPolicyExtractor
from fineprint.models import ModelError
from tests.helpers import payload


class ExtractionTests(unittest.TestCase):
    def test_offline_structured_provider(self):
        result = StructuredPolicyExtractor().extract(json.dumps(payload()["policy"]))
        self.assertEqual(result.policy.id, "P1")
        self.assertFalse(result.review_required)

    def test_prose_is_not_silently_guessed(self):
        with self.assertRaisesRegex(ModelError, "structured policy JSON"):
            StructuredPolicyExtractor().extract("You owe 20% subject to some exceptions")

    def test_pluggable_provider_marks_review_required(self):
        result = ProviderPolicyExtractor(lambda text: payload()["policy"], "fake-llm").extract("Synthetic prose")
        self.assertTrue(result.review_required)
        self.assertEqual(result.provider, "fake-llm")

    def test_provider_output_still_schema_checked(self):
        with self.assertRaises(ModelError):
            ProviderPolicyExtractor(lambda text: {}, "bad-provider").extract("Synthetic")

    def test_decimal_dollars_exact(self):
        self.assertEqual(dollars("1.01"), 101)
        for val in ("1.001", "NaN", "Infinity", "-1", "garbage"):
            with self.subTest(val=val), self.assertRaises(ModelError):
                dollars(val)
