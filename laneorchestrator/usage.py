"""Bounded host-supplied usage accounting and admission checks.

The host owns the ledger and must serialize check/reserve/launch. This module
does not observe account usage, reserve server tokens, or cancel running work.
"""
from collections import Counter
import re

IDENTIFIER = re.compile(r'^[A-Za-z0-9_.-]{1,80}$')


def _integer(value, name, maximum=10**12):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(name + ' must be a bounded nonnegative integer')
    return value


def assess_usage(ledger, packet, max_calls=8, max_retries=2, max_tokens=None):
    """Count every launch, including failed and pending calls; reject duplicates.

    Events are one record per launch, updated by the host on completion. Token
    counts must be incremental per launch, never cumulative session snapshots.
    Cached input is a subset of input, not an additional token category.
    """
    if not isinstance(packet, str) or not IDENTIFIER.fullmatch(packet):
        raise ValueError('packet must be a short identifier')
    _integer(max_calls, 'max_calls', 1000)
    _integer(max_retries, 'max_retries', 2)
    if max_tokens is not None:
        _integer(max_tokens, 'max_tokens')
    if not isinstance(ledger, dict) or set(ledger) != {'schema_version', 'calls'} or type(ledger['schema_version']) is not int or ledger['schema_version'] != 1:
        raise ValueError('usage ledger requires schema_version 1 and calls')
    calls = ledger['calls']
    if not isinstance(calls, list) or len(calls) > 1000:
        raise ValueError('calls must contain at most 1000 records')
    seen, packets, agents, packet_usage = set(), Counter(), {}, {}
    totals = dict(input_tokens=0, output_tokens=0, cached_input_tokens=0)
    unknown = 0
    for call in calls:
        if not isinstance(call, dict) or set(call) != {'id', 'packet', 'agent', 'status', 'usage'}:
            raise ValueError('call has invalid fields')
        for key in ('id', 'packet', 'agent'):
            if not isinstance(call[key], str) or not IDENTIFIER.fullmatch(call[key]):
                raise ValueError('call identifiers must be short identifiers')
        if call['id'] in seen:
            raise ValueError('duplicate call id')
        seen.add(call['id'])
        if call['status'] not in ('pending', 'completed', 'failed'):
            raise ValueError('invalid call status')
        packets[call['packet']] += 1
        rows = [group.setdefault(key, dict(calls=0, input_tokens=0, output_tokens=0, cached_input_tokens=0, unknown_calls=0))
                for group, key in ((agents, call['agent']), (packet_usage, call['packet']))]
        for row in rows:
            row['calls'] += 1
        usage = call['usage']
        if usage is None:
            unknown += 1
            for row in rows:
                row['unknown_calls'] += 1
            continue
        if call['status'] == 'pending':
            raise ValueError('pending calls cannot declare final usage')
        if not isinstance(usage, dict) or set(usage) != set(totals):
            raise ValueError('usage requires input, output and cached input counters')
        for key in totals:
            _integer(usage[key], key)
            totals[key] += usage[key]
            for row in rows:
                row[key] += usage[key]
        if usage['cached_input_tokens'] > usage['input_tokens']:
            raise ValueError('cached input exceeds input')
    reasons = []
    if len(calls) >= max_calls:
        reasons.append('call_limit_reached')
    if packets[packet] >= 1 + max_retries:
        reasons.append('packet_attempt_limit_reached')
    observed = totals['input_tokens'] + totals['output_tokens']
    if max_tokens is not None:
        if unknown:
            reasons.append('token_usage_unknown')
        if observed >= max_tokens:
            reasons.append('observed_token_limit_reached')
    return dict(allowed=not reasons, stop_reasons=reasons, calls=len(calls),
                packet_attempts=packets[packet], observed_tokens=observed,
                token_coverage='complete' if not unknown else 'partial', unknown_calls=unknown,
                totals=totals, agents=agents, packets=packet_usage,
                limits=dict(max_calls=max_calls, max_retries=max_retries, max_tokens=max_tokens),
                enforcement='host_must_check_and_reserve_before_every_launch',
                token_limit_kind='stop_after_observed_usage_not_server_hard_cap')
