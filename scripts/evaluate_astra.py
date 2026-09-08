#!/usr/bin/env python3
"""Offline, scenario-based adaptive contract checks; never a model quality score.

Expected scope outcomes are authored in the corpus before evaluation. This runner
does not synthesize an Astra decision and call that a successful live run.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from laneorchestrator.adaptive import validate_selection, spawn_settings
from laneorchestrator.config import DEFAULT_ROLES
from laneorchestrator.models import Availability, EffectiveConfig, RoleEvidence
from laneorchestrator.orchestration import build_adaptive_card
from laneorchestrator.routing import RouteFacts, validate_route_facts

HOST = {
    'gpt-6-astra': ['low', 'medium', 'high', 'xhigh', 'max', 'ultra'],
    'gpt-5.6-sol': ['low', 'medium', 'high', 'xhigh', 'max', 'ultra'],
    'gpt-5.6-terra': ['low', 'medium', 'high', 'xhigh', 'max', 'ultra'],
    'gpt-5.6-luna': ['low', 'medium', 'high', 'xhigh', 'max'],
}


def validate_corpus_rows(rows, prefix, count):
    if len(rows) != count or {c['id'] for c in rows} != {f'{prefix}{i:03d}' for i in range(1, count + 1)}:
        raise ValueError('Incorrect corpus count or identifiers')
    if len({(c['objective'], c['context']) for c in rows}) != count:
        raise ValueError('Duplicate scenarios')
    if prefix == 'U':
        categories = Counter(c['category'] for c in rows)
        if len(categories) != 20 or set(categories.values()) != {10}:
            raise ValueError('Normal corpus must have 20 categories of 10')
        if any(len({c[key] for c in rows}) != count for key in ('objective', 'context')):
            raise ValueError('Normal objectives and contexts must each be unique')
    for case in rows:
        validate_route_facts(RouteFacts(objective=case['objective'], **case['facts']))
        expected = case['expected']
        if any(not isinstance(case[key], str) or not case[key].strip() for key in ('context', 'category')):
            raise ValueError('Missing scenario evidence: ' + case['id'])
        if case.get('preset', 'astra-adaptive') not in ('astra-adaptive', 'all-astra', 'manual') or type(case.get('user_override', False)) is not bool:
            raise ValueError('Invalid selection policy: ' + case['id'])
        for key, allowed in (
            ('task_kinds', {'small', 'routine', 'demanding', 'investigation', 'review'}),
            ('models', set(HOST)),
            ('efforts', {effort for efforts in HOST.values() for effort in efforts}),
        ):
            values = expected[key]
            if not isinstance(values, list) or not values or any(value not in allowed for value in values):
                raise ValueError('Invalid expected ' + key + ': ' + case['id'])
        if expected['action'] not in ('implement', 'investigate', 'review', 'clarify') or expected['card_kind'] not in ('small', 'routine', 'investigation'):
            raise ValueError('Invalid expected action or card kind: ' + case['id'])
        if any(type(expected[key]) is not bool for key in ('independent_review', 'card_review')):
            raise ValueError('Review expectations must be booleans: ' + case['id'])
        checks = expected['output_checks']
        if not isinstance(checks, list) or not 2 <= len(checks) <= 4 or any(not isinstance(check, str) or not check.strip() for check in checks):
            raise ValueError('Invalid output checks: ' + case['id'])


def corpus():
    cases, hashes = [], {}
    for filename, prefix, count in (
        ('astra-use-cases-v1.json', 'U', 200),
        ('astra-edge-cases-v1.json', 'E', 100),
    ):
        path = ROOT / 'benchmarks' / filename
        raw = path.read_bytes()
        data = json.loads(raw)
        rows = data['cases']
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported corpus schema: ' + filename)
        validate_corpus_rows(rows, prefix, count)
        cases.extend(rows)
        hashes[filename] = hashlib.sha256(raw).hexdigest()
    return cases, hashes


def permitted(model, effort, host, kind, preset, override):
    """Independent published policy oracle, deliberately not the implementation."""
    if model not in host or effort not in host[model]:
        return False
    if override or preset == 'manual':
        return True
    if preset == 'all-astra':
        return model == 'gpt-6-astra'
    if kind == 'small':
        return model in ('gpt-5.6-luna', 'gpt-5.6-terra') and effort == 'high'
    if kind == 'routine':
        return model in ('gpt-5.6-sol', 'gpt-5.6-terra')
    return True


def evaluate(case):
    failures, assertions = [], 0
    def check(condition, message):
        nonlocal assertions
        assertions += 1
        if not condition:
            failures.append(message)

    preset = case.get('preset', 'astra-adaptive')
    config = EffectiveConfig(2, DEFAULT_ROLES, 'evaluation-fixture', preset)
    evidence = {r: RoleEvidence(r, v.model, None, Availability.UNKNOWN) for r, v in DEFAULT_ROLES.items()}
    facts = RouteFacts(objective=case['objective'], **case['facts'])
    card = build_adaptive_card(facts, config, evidence, [], [case['context']])
    expected = case['expected']
    check(card['task_kind'] == expected['card_kind'], 'card kind: ' + card['task_kind'] + ' != ' + expected['card_kind'])
    check(card['verification']['independent_review_required'] == expected['card_review'], 'card review requirement differs from inspected scope')
    check(card['selection_status'] == 'awaiting_astra_decision', 'CLI fabricated a model decision')
    check(card['execution']['status'] == 'not_dispatched' and card['execution']['runtime_observed'] is False,
          'CLI fabricated execution evidence')
    check(not card['execution']['profile_readiness'], 'unknown profiles reported ready')
    if expected['card_kind'] == 'investigation':
        check(card['verification']['required_roles'] == ['router'], 'unknown scope creates implementation role')
    host = case.get('host_models', HOST)
    override = case.get('user_override', False)
    pairs = [(m, e) for m, es in HOST.items() for e in es]
    pairs += [(m, e) for m, es in host.items() for e in es if (m, e) not in pairs]
    pairs += [('unavailable-model', 'high'), ('gpt-5.6-luna', 'ultra'), ('gpt-6-astra', 'invented')]
    for kind in expected['task_kinds']:
        for model, effort in pairs:
            want = permitted(model, effort, host, kind, preset, override)
            decision = {'model': model, 'reasoning_effort': effort, 'reason': 'Contract probe: ' + case['id']}
            try:
                result = validate_selection(decision, host, task_kind=kind, preset=preset, user_override=override)
            except ValueError:
                check(not want, 'valid policy pair rejected: ' + kind + '/' + model + '/' + effort)
            else:
                check(want, 'invalid policy pair accepted: ' + kind + '/' + model + '/' + effort)
                check(spawn_settings(result) == {'model': model, 'reasoning_effort': effort, 'fork_turns': 'none'},
                      'dispatch changes the selected model or effort')
    return {'id': case['id'], 'category': case['category'], 'passed': not failures,
            'assertions': assertions, 'failures': failures, 'card': card,
            'semantic_model_choice': 'not_evaluated_offline', 'task_execution': 'not_executed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases, hashes = corpus()
    rows = [evaluate(case) for case in cases]
    counts = {prefix: {'passed': sum(r['passed'] for r in rows if r['id'].startswith(prefix)),
                       'total': sum(r['id'].startswith(prefix) for r in rows)} for prefix in ('U', 'E')}
    report = {'schema_version': 1, 'scope': 'offline adaptive contracts on authored scenario facts',
              'live_model_calls': 0, 'task_implementations_executed': 0,
              'corpus_sha256': hashes, 'counts': counts,
              'assertions': sum(r['assertions'] for r in rows), 'results': rows}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: report[k] for k in ('scope', 'counts', 'assertions')}))
    for row in rows:
        if not row['passed']:
            print(row['id'] + ': ' + '; '.join(row['failures']))
    return 0 if all(r['passed'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
