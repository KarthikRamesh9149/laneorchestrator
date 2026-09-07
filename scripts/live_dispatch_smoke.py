#!/usr/bin/env python3
"""Opt-in live CLI checks; this does not verify desktop profile reloads."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from laneorchestrator.voltagent import render_pack

SOURCE = 'def normalize_counts(entries):\n    return dict(entries)\n'
TESTS = '''import unittest
from counts import normalize_counts
class CountsTests(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_counts([(" A ",2),("a",3),("B",0)]), {"a":5,"b":0})
    def test_unchanged(self):
        rows=[(" A ",2)]; normalize_counts(rows); self.assertEqual(rows,[(" A ",2)])
    def test_quantities(self):
        for value in (True,False,-1,1.5,"2",None):
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_counts([("a",value)])
    def test_names(self):
        for value in (None,1,"", "  "):
            with self.subTest(value=value), self.assertRaises(ValueError): normalize_counts([(value,1)])
    def test_empty_unicode(self):
        self.assertEqual(normalize_counts([]), {})
        self.assertEqual(normalize_counts([(" STRASSE ",2),("Straße",3)]), {"strasse":5})
'''
PROMPT = '''Implement only counts.py in this isolated fixture; preserve test_counts.py.
normalize_counts(entries) returns a new dictionary of stripped, casefolded string keys,
aggregating nonnegative integer counts. Reject non-string/blank names, negatives,
bools and non-integer counts with ValueError. Do not mutate input. Inspect and run tests.
Do not install anything, delegate, access other repositories, or edit outside this fixture.
You are not alone in the broader workspace: preserve unrelated edits. Your only file is counts.py.
This is a functional smoke check, not a performance benchmark. Report your checks.
'''

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--codex', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--review-only', action='store_true', help='Review an existing completed fixture run')
    args = parser.parse_args()
    if not args.run: parser.error('Live calls require --run')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.review_only)
    profile = render_pack()['laneorchestrator-voltagent-python-pro.toml']
    match = re.search(r'developer_instructions\s*=\s*"""(.*?)"""', profile.decode(), re.S)
    if not match: raise ValueError('Missing specialist instructions')
    report = {'scope':'CLI explicit settings and rendered specialist instructions', 'desktop_profile_reload_verified':False, 'cases':[]}
    cases = [('small','gpt-5.6-luna','high'),('routine-terra','gpt-5.6-terra','medium'),('routine-sol','gpt-5.6-sol','medium'),('astra','gpt-6-astra','high')]
    if args.review_only:
        report = json.loads((output / 'report.json').read_text())
        cases = []
    for label,model,effort in cases:
        work = output / label
        work.mkdir()
        (work / 'counts.py').write_text(SOURCE)
        (work / 'test_counts.py').write_text(TESTS)
        command = [args.codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write','--model',model,'--config','model_reasoning_effort='+json.dumps(effort),'--config','developer_instructions='+json.dumps(match.group(1)),'--cd',str(work),'--json','-']
        started = time.monotonic()
        item = {'case':label,'requested_model':model,'requested_reasoning_effort':effort,'runtime_observed_model':None,'runtime_observed_reasoning_effort':None,'profile_sha256':hashlib.sha256(profile).hexdigest()}
        try:
            result = subprocess.run(command,input=PROMPT,text=True,capture_output=True,timeout=args.timeout)
            (work / 'events.jsonl').write_text(result.stdout)
            (work / 'stderr.txt').write_text(result.stderr)
            check = subprocess.run([sys.executable,'-m','unittest','test_counts.py','-v'],cwd=work,capture_output=True,text=True,timeout=30)
            (work / 'checks.txt').write_text(check.stdout+check.stderr)
            item.update(launch_exit_code=result.returncode, checks_passed=result.returncode==0 and check.returncode==0 and (work / 'test_counts.py').read_text()==TESTS)
        except subprocess.TimeoutExpired:
            item.update(checks_passed=False,error='timeout')
        item['elapsed_seconds'] = round(time.monotonic()-started,2)
        report['cases'].append(item)
        (output / 'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(item),flush=True)
    work = output / 'astra'
    before = {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in ('counts.py','test_counts.py')}
    command = [args.codex,'exec','--ignore-user-config','--ephemeral','--skip-git-repo-check','--sandbox','read-only','--model','gpt-5.6-sol','--config','model_reasoning_effort="high"','--cd',str(work),'--json','-']
    prompt = 'Independently review counts.py against these original requirements. Do not edit any files or delegate. Inspect tests and implementation, identify correctness defects or missing edge cases. Return a clear approve or changes-requested verdict with concrete findings. Requirements: ' + PROMPT.split('normalize_counts(entries)',1)[1].split('Do not install',1)[0]
    review = {'requested_model':'gpt-5.6-sol','requested_reasoning_effort':'high','runtime_observed_model':None,'runtime_observed_reasoning_effort':None,'separate_process':True}
    try:
        result = subprocess.run(command,input=prompt,text=True,capture_output=True,timeout=args.timeout)
        (output / 'review-events.jsonl').write_text(result.stdout)
        (output / 'review-stderr.txt').write_text(result.stderr)
        after = {name: hashlib.sha256((work / name).read_bytes()).hexdigest() for name in before}
        review.update(launch_exit_code=result.returncode,completed=result.returncode==0,fixture_unchanged=before==after)
    except subprocess.TimeoutExpired:
        review.update(completed=False,error='timeout')
    report['independent_review'] = review
    (output / 'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(review),flush=True)
    return 0 if all(case['checks_passed'] for case in report['cases']) and review.get('completed') and review.get('fixture_unchanged') else 1

if __name__ == '__main__':
    raise SystemExit(main())
