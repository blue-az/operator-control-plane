#!/usr/bin/env python3
"""Read-only live gate for a unified-memory (amdgpu) comparison contract.

Runtime identity is checked exactly as the discrete-card gates do: llama-server
/props plus a fresh GGUF sha256, or the Ollama tag/blob/parameter snapshot. Only
placement differs (uma_placement.py). Exit 2 unless all pass. Does not generate,
start, stop or reconfigure anything.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
import uuid
from pathlib import Path

from comparison_preflight import (
    LLAMA_SCHEMA,
    PreflightError,
    validate_contract,
    validate_llama_props,
    validate_model_snapshot,
    validate_request,
)
from uma_placement import UMA_CAPTURE, validate_uma_placement


def get(base: str, path: str, data: dict | None = None) -> dict:
    request = urllib.request.Request(base.rstrip('/') + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def capture_remote(contract: dict, model: str, local: bool = False) -> dict:
    placement = contract['placement']
    port = placement['port']
    if type(port) is not int or not 1 <= port <= 65535:
        raise PreflightError('invalid remote port')
    nonce = uuid.uuid4().hex
    argv = [str(port), nonce]
    if contract['schema'] == LLAMA_SCHEMA:
        argv.append(contract['models'][model]['gguf_path'])
    if local:
        command = ['python3', '-', *argv]
    else:
        host = placement['ssh_host']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._@-]*', host):
            raise PreflightError('invalid SSH host')
        command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', host, 'python3', '-', *argv]
    result = subprocess.run(command, input=UMA_CAPTURE, text=True, capture_output=True, timeout=600, check=True)
    remote = json.loads(result.stdout)
    if remote.get('nonce') != nonce:
        raise PreflightError('stale remote capture')
    return remote


def check(contract: dict, model: str, local: bool = False) -> dict:
    """Identity + placement; returns a report with 'errors' (empty when passed)."""
    report = {'mode': 'read-only preflight; no generation', 'errors': []}
    validate_contract(contract)
    if model not in contract['models']:
        raise PreflightError('selected model outside roster')
    base = contract['endpoint']
    remote = capture_remote(contract, model, local)
    report['remote'] = remote
    if contract['schema'] == LLAMA_SCHEMA:
        props = get(base, '/props')
        report['props'] = {k: v for k, v in props.items() if k != 'chat_template'}
        checks = (('model', lambda: validate_llama_props(contract, model, props, remote['gguf'])),
                  ('placement', lambda: validate_uma_placement(contract, model, remote)))
    else:
        tags = {row['name']: row for row in get(base, '/api/tags')['models']}
        if model not in tags:
            raise PreflightError(f'{model}: missing tag')
        snapshot = {'name': model, 'digest': tags[model]['digest'],
                    'ollama_version': get(base, '/api/version')['version'],
                    'show': get(base, '/api/show', {'model': model})}
        report['snapshot'] = snapshot
        local_ps = get(base, '/api/ps')
        report['local_ps'] = local_ps
        checks = (('model', lambda: validate_model_snapshot(contract, model, snapshot)),
                  ('placement', lambda: validate_uma_placement(contract, model, remote, local_ps)))
    for name, fn in checks:
        try:
            report[name] = fn()
        except PreflightError as exc:
            report['errors'].append(str(exc))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--request-body', type=Path)
    parser.add_argument('--capture', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    report = {'errors': []}
    try:
        report = check(contract, args.model)
        if args.request_body is None:
            report['errors'].append('no actual outbound request capture; defaults alone do not prove effective sampling')
        else:
            body = json.loads(args.request_body.read_text())
            if body.get('model') != args.model:
                raise PreflightError('captured request is for another model')
            validate_request(contract, body)
            report['request_options'] = {k: v for k, v in body.items() if k not in ('messages', 'tools')}
    except (PreflightError, OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        report['errors'].append(str(exc))
    report['passed'] = not report['errors']
    args.capture.parent.mkdir(parents=True, exist_ok=True)
    args.capture.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': report['passed'], 'errors': report['errors'], 'capture': str(args.capture)}, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
