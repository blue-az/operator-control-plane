#!/usr/bin/env python3
"""Retrospective audit only: no inference, network, live ledger, or config writes.

Recount saved cells/traces and grade untouched disposable fixtures from the run's
recorded git revision. Optional hardware-root aggregates existing TSV/JSONL data.
Print JSON to stdout; never overwrite the run's state, traces, or RESULTS files.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys

import yaml

PACK = Path(__file__).resolve().parent
LADDER = PACK.parents[1]
ROOT = LADDER.parents[1]
sys.path.insert(0, str(LADDER))
from fixtures import build_fixture, cleanup_fixture, hash_tree
from grading import grade


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline(task: dict) -> dict:
    fixture = build_fixture(task['files'], prefix='takeover-baseline', remove=task.get('remove'))
    try:
        result = grade(task['postcondition'], fixture, '', hash_tree(fixture))
        return {'passed_without_model': result.passed, 'detail': result.detail}
    finally:
        cleanup_fixture(fixture)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware-root', type=Path)
    args = parser.parse_args()
    inputs = {}
    states = {}
    all_records = []
    trace_problems = []
    booking_reads = []
    for name in ('state_A.json', 'state_B.json'):
        path = PACK / name
        inputs[name] = digest(path)
        state = json.loads(path.read_text())
        states[name] = {'done': len(state['done']), 'results': len(state['results']),
                        'failure_records': len(state['failures'])}
        keys = set()
        for record in state['results']:
            key = '|'.join(str(record[k]) for k in ('task_id', 'level', 'model', 'trial'))
            assert key not in keys, f'duplicate cell: {key}'
            keys.add(key)
            path = PACK / 'traces' / Path(record['trace']).name
            inputs[str(path.relative_to(PACK))] = digest(path)
            trace = json.loads(path.read_text())
            for field in ('task_id', 'level', 'model', 'trial', 'passed', 'outcome', 'proofs'):
                if trace.get(field) != record.get(field):
                    trace_problems.append({'cell': key, 'field': field})
            assert trace['cell_key'] == key
            if record['task_id'] == 'booking-off-by-one':
                calls = {}
                read_text = None
                for line in trace.get('stdout', '').splitlines():
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get('type') == 'tool_execution_start':
                        calls[event['toolCallId']] = event
                    if event.get('type') == 'tool_execution_end':
                        call = calls.get(event.get('toolCallId'), {})
                        if (read_text is None and call.get('toolName') == 'read'
                            and str(call.get('args', {}).get('path', '')).endswith('src/bookings.py')):
                            read_text = '\n'.join(c.get('text', '') for c in event.get('result', {}).get('content', []))
                booking_reads.append({'cell': key, 'first_read_already_fixed':
                    read_text is not None and 'return start1 < end2 and start2 < end1' in read_text,
                    'recorded_attempted_edit': record.get('attempted_edit')})
            all_records.append(record)
        assert keys == set(state['done']), f'{name}: done/result mismatch'
    assert len(all_records) == 120
    assert not trace_problems, trace_problems
    by_model = {}
    for model in sorted({r['model'] for r in all_records}):
        rows = [r for r in all_records if r['model'] == model]
        by_model[model] = {
            'recorded_outcomes': dict(Counter(r.get('outcome') for r in rows)),
            'recorded_passes': sum(r['passed'] for r in rows),
            'missing_placement_proof': sum(not r.get('proofs', {}).get('placement') for r in rows),
            'per_task': {task: dict(Counter(r['outcome'] for r in rows if r['task_id'] == task))
                         for task in sorted({r['task_id'] for r in rows})},
            'excluding_pre_solved_booking': dict(Counter(r['outcome'] for r in rows if r['task_id'] != 'booking-off-by-one')),
            'nonpasses': [{k: r.get(k) for k in ('task_id', 'trial', 'outcome', 'detail', 'unproven_reasons', 'wall_clock_s')}
                         for r in rows if not r['passed']],
        }
    prerun = PACK / 'evidence/prerun.txt'
    inputs['evidence/prerun.txt'] = digest(prerun)
    revision = next(line.split(': ', 1)[1] for line in prerun.read_text().splitlines() if line.startswith('git_rev: '))
    tasks = {}
    for task_id in sorted({r['task_id'] for r in all_records}):
        relative = f'evals/local_lane_ladder/tasks/{task_id.replace("-", "_")}.yaml'
        raw = subprocess.check_output(['git', 'show', f'{revision}:{relative}'], cwd=ROOT)
        task = yaml.safe_load(raw)
        tasks[task_id] = {'run_revision_source_sha256': hashlib.sha256(raw).hexdigest(), **baseline(task)}
        if task_id == 'booking-off-by-one':
            task['files']['src/bookings.py'] = task['files']['src/bookings.py'].replace(
                'return start1 < end2 and start2 < end1', 'return start1 <= end2 and start2 <= end1')
            tasks[task_id]['restored_bug_in_disposable_fixture'] = baseline(task)
    historical = defaultdict(list)
    for path in sorted((LADDER / 'fixtures/qnext-80b-e9-ceiling/traces').glob('*.json')):
        trace = json.loads(path.read_text())
        inputs['historical/' + path.name] = digest(path)
        historical[trace['model']].append(trace)
    historical_summary = {}
    for model, traces in historical.items():
        historical_summary[model] = {
            'cells': len(traces), 'recorded_passes': sum(t['passed'] for t in traces),
            'recorded_revisions': sorted({t['git_rev'] for t in traces}),
            'executables': sorted({t['argv'][0] for t in traces}),
            'excluding_booking_passes': sum(t['passed'] for t in traces if t['task_id'] != 'booking-off-by-one'),
            'all_think_off': all('--think' in t['argv'] and t['argv'][t['argv'].index('--think') + 1] == 'off' for t in traces),
        }
    comparison = {}
    old_revision = '3e495641589fe445c72a359f38e5d03401ec4185'
    for task_id in tasks:
        relative = f'evals/local_lane_ladder/tasks/{task_id.replace("-", "_")}.yaml'
        old, new = [yaml.safe_load(subprocess.check_output(['git', 'show', f'{rev}:{relative}'], cwd=ROOT))
                    for rev in (old_revision, revision)]
        comparison[task_id] = {f'{key}_match': old.get(key) == new.get(key) for key in ('files', 'prompts', 'postcondition')}
    report = {'mode': 'retrospective audit; no new inference', 'recorded_run_revision': revision,
              'historical_trace_summary': historical_summary, 'historical_task_comparison': comparison,
              'states': states, 'models': by_model, 'trace_state_mismatches': trace_problems,
              'booking_trace_reads': booking_reads, 'untouched_fixture_baselines_at_run_revision': tasks,
              'input_sha256': inputs}
    if args.hardware_root:
        hardware = {}
        # Arithmetic checks only: these do not prove the causal interpretations.
        for packet, pattern, group_fields, measures in [
            ('PCIE-X4-CARD-001', 'results_*.tsv', ('model', 'gpu'), ('tok_s',)),
            ('TESTBENCH-MATCHED-PAIR-001', 'results_*.tsv', ('model', 'config', 'num_ctx'), ('tok_s',)),
            ('LONGCTX-PREFILL-001', 'results_*.tsv', ('model', 'config', 'target'), ('decode_tok_s', 'prefill_tok_s')),
        ]:
            groups = defaultdict(list)
            skipped = 0
            hashes = {}
            for path in sorted((args.hardware_root / packet).glob(pattern)):
                hashes[path.name] = digest(path)
                with path.open() as stream:
                    for row in csv.DictReader(stream, delimiter='\t'):
                        if row.get('error') or any(not row.get(m) for m in measures):
                            skipped += 1
                            continue
                        groups[tuple(row[k] for k in group_fields)].append(row)
            assert groups, f'no hardware rows for {packet}'
            hardware[packet] = {'input_sha256': hashes, 'error_rows_excluded': skipped,
                'means': [{'group': dict(zip(group_fields, key)), 'n': len(rows),
                           **{m: round(statistics.mean(float(r[m]) for r in rows), 4) for m in measures}}
                          for key, rows in sorted(groups.items())]}
        packet = args.hardware_root / 'ONE-MODEL-PER-CARD-N4-001'
        starvation = []
        for path in sorted(packet.glob('starve_*.jsonl')):
            groups = defaultdict(list)
            for line in path.read_text().splitlines():
                row = json.loads(line)
                groups[row['rep']].append(row)
            starvation.append({'file': path.name, 'sha256': digest(path),
                'rep_max_wall_s': {str(rep): max(row['wall_s'] for row in rows) for rep, rows in groups.items()}})
        hardware['starvation_saved_bursts'] = starvation
        report['hardware_arithmetic'] = hardware
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
