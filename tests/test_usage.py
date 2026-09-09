import copy
import unittest
import contextlib
import io
import json
from pathlib import Path
import tempfile
from laneorchestrator.usage import assess_usage
from laneorchestrator.cli import main


def call(identifier='one', status='completed', usage=None):
    return dict(id=identifier, packet='task', agent='worker', status=status, usage=usage)


class UsageTests(unittest.TestCase):
    def test_cache_is_not_double_counted_and_agent_totals_are_available(self):
        ledger = dict(schema_version=1, calls=[call(usage=dict(input_tokens=100, output_tokens=20, cached_input_tokens=80))])
        result = assess_usage(ledger, 'next', max_tokens=121)
        self.assertTrue(result['allowed'])
        self.assertEqual(result['observed_tokens'], 120)
        self.assertEqual(result['agents']['worker']['input_tokens'], 100)
        self.assertFalse(assess_usage(ledger, 'next', max_tokens=120)['allowed'])

    def test_unknown_failed_and_pending_calls_consume_budget(self):
        ledger = dict(schema_version=1, calls=[call(status='failed'), call('two', 'pending')])
        result = assess_usage(ledger, 'task', max_calls=2, max_retries=1, max_tokens=100)
        self.assertEqual(set(result['stop_reasons']), {'call_limit_reached', 'packet_attempt_limit_reached', 'token_usage_unknown'})
        self.assertEqual(result['token_coverage'], 'partial')

    def test_limits_cannot_be_bypassed_by_duplicate_ids_or_invalid_counters(self):
        with self.assertRaises(ValueError):
            assess_usage(dict(schema_version=1, calls=[call(), call()]), 'task')
        for bad in (-1, True, 1.5, '100', 10**13):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assess_usage(dict(schema_version=1, calls=[call(usage=dict(input_tokens=bad, output_tokens=0, cached_input_tokens=0))]), 'task')
        with self.assertRaises(ValueError):
            assess_usage(dict(schema_version=1, calls=[]), 'task', max_retries=3)

    def test_pending_usage_and_excess_cache_are_rejected(self):
        for status, usage in [('pending', dict(input_tokens=0, output_tokens=0, cached_input_tokens=0)),
                              ('completed', dict(input_tokens=1, output_tokens=0, cached_input_tokens=2))]:
            with self.assertRaises(ValueError):
                assess_usage(dict(schema_version=1, calls=[call(status=status, usage=usage)]), 'task')

    def test_assessment_does_not_mutate_host_ledger(self):
        ledger = dict(schema_version=1, calls=[call()])
        before = copy.deepcopy(ledger)
        self.assertTrue(assess_usage(ledger, 'task')['allowed'])
        self.assertEqual(ledger, before)

    def test_zero_limits_stop_initial_launch(self):
        self.assertFalse(assess_usage(dict(schema_version=1, calls=[]), 'task', max_calls=0)['allowed'])
        self.assertFalse(assess_usage(dict(schema_version=1, calls=[]), 'task', max_tokens=0)['allowed'])

    def test_cli_stop_is_nonzero_with_machine_readable_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / 'usage.json'
            ledger.write_text(json.dumps(dict(schema_version=1, calls=[])))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(['usage', '--ledger', str(ledger), '--packet', 'task', '--max-calls', '0', '--json'])
            result = json.loads(output.getvalue())
            self.assertEqual(status, 1)
            self.assertEqual(result['errors'][0]['code'], 'USAGE_LIMIT')
            self.assertFalse(result['data']['allowed'])
