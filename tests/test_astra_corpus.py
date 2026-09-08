"""Run the frozen 200 normal and 100 extreme adaptive contract scenarios offline."""
import unittest

from scripts.evaluate_astra import corpus, evaluate


class AstraCorpusTests(unittest.TestCase):
    pass


def case_test(case):
    def test(self):
        result = evaluate(case)
        self.assertFalse(result['failures'], '; '.join(result['failures']))
    test.__doc__ = case['objective']
    return test


for _case in corpus()[0]:
    setattr(AstraCorpusTests, 'test_' + _case['id'], case_test(_case))


if __name__ == '__main__':
    unittest.main()
