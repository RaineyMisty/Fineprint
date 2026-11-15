import unittest

from fineprint.policy_sections import select_sections


class PolicySectionsTests(unittest.TestCase):
    def test_small_source_is_unchanged(self):
        source = 'Policy metadata\nIn-network deductible $100.'
        selected, manifest = select_sections(source)
        self.assertEqual(selected, source)
        self.assertFalse(manifest['omitted'])

    def test_selects_tables_and_network_notes_excludes_patient_illustrations(self):
        pages = ['Plan identity', 'Unrelated legal text ' * 500,
                 'Important Questions: individual deductible $100. Out-of-pocket $300.',
                 'Common Medical Event: physician visit $20 copay.',
                 'Network notes: balance billing, deductible and out-of-pocket exceptions.',
                 'About these coverage examples: Peg is having a baby. Patient total $1000.']
        source = '\f'.join(pages)
        selected, manifest = select_sections(source, threshold=100, budget=1000)
        for page in (pages[0], pages[2], pages[3], pages[4]):
            self.assertIn(page, selected)
        self.assertNotIn('Patient total', selected)
        self.assertTrue(manifest['omitted'])
        for span in manifest['selected_ranges']:
            self.assertIn(source[span['start']:span['end']], selected)

    def test_long_unpaginated_source_is_bounded(self):
        source = 'deductible $100 network ' * 5000
        selected, manifest = select_sections(source, budget=12000)
        self.assertLessEqual(manifest['selected_characters'], 12000)
        self.assertTrue(manifest['omitted'])
