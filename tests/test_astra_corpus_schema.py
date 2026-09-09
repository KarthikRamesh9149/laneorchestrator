"""The evaluation must reject malformed rubrics rather than report a green run."""
import copy
import unittest

from scripts.evaluate_astra import corpus, validate_corpus_rows


class CorpusSchemaTests(unittest.TestCase):
    def test_malformed_normal_corpus_is_rejected(self):
        cases, _ = corpus()
        normal = [case for case in cases if case['id'].startswith('U')]
        for field, value in [('models', ['invented-model']), ('efforts', ['invented']),
                             ('task_kinds', ['imaginary']), ('output_checks', []),
                             ('independent_review', 'false')]:
            with self.subTest(field=field):
                rows = copy.deepcopy(normal)
                rows[0]['expected'][field] = value
                with self.assertRaises(ValueError):
                    validate_corpus_rows(rows, 'U', 200)
        for field in ('objective', 'context', 'category'):
            with self.subTest(field=field):
                rows = copy.deepcopy(normal)
                rows[0][field] = rows[10][field]
                with self.assertRaises(ValueError):
                    validate_corpus_rows(rows, 'U', 200)
