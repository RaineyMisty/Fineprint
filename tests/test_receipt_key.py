import importlib
import os
import unittest
from unittest import mock


class ReceiptKeyTests(unittest.TestCase):
    def _key(self, env):
        with mock.patch.dict(os.environ, env, clear=False):
            for name in ('FINEPRINT_RECEIPT_KEY', 'DEEPSEEK_API_KEY'):
                if name not in env:
                    os.environ.pop(name, None)
            import fineprint.compilation_receipts as receipts
            return importlib.reload(receipts)._KEY

    def test_replicas_with_same_secret_share_the_signing_key(self):
        a = self._key({'DEEPSEEK_API_KEY': 'sk-test-replica'})
        b = self._key({'DEEPSEEK_API_KEY': 'sk-test-replica'})
        self.assertEqual(a, b)
        self.assertNotIn(b'sk-test-replica', a)

    def test_explicit_key_wins_and_no_secret_falls_back_to_random(self):
        self.assertEqual(self._key({'FINEPRINT_RECEIPT_KEY': 'x'}), self._key({'FINEPRINT_RECEIPT_KEY': 'x'}))
        self.assertNotEqual(self._key({}), self._key({}))

    @classmethod
    def tearDownClass(cls):
        import fineprint.compilation_receipts as receipts
        importlib.reload(receipts)


if __name__ == '__main__':
    unittest.main()
