#!/usr/bin/env python3
"""Read-only live gate: metadata + fresh remote placement + actual outbound body.

Exit 2 unless all checks pass. Does not generate, warm, unload, create models,
change Pi configuration, or launch the ladder. A saved request is diagnostic
only: the dispatch integration must validate EVERY actual outgoing request.
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
    PreflightError,
    validate_contract,
    validate_model_snapshot,
    validate_remote_placement,
    validate_request,
)

REMOTE_CAPTURE = r'''
import csv,json,re,subprocess,sys,urllib.request
port=int(sys.argv[1]); nonce=sys.argv[2]
def run(args): return subprocess.check_output(args,text=True,timeout=15)
def rows(args): return list(csv.reader(run(args).splitlines(),skipinitialspace=True))
listeners=run(['ss','-ltnp',f'sport = :{port}'])
pids=sorted(set(int(p) for p in re.findall(r'pid=(\d+)',listeners)))
if len(pids)!=1: raise RuntimeError('expected one visible serving listener PID')
processes=[dict(zip(('pid','ppid'),map(int,line.split()))) for line in run(['ps','-eo','pid=,ppid=']).splitlines()]
gpus=[dict(zip(('uuid','name'),row)) for row in rows(['nvidia-smi','--query-gpu=uuid,name','--format=csv,noheader,nounits'])]
apps=[{'gpu_uuid':r[0],'pid':int(r[1]),'used_mib':float(r[2])} for r in rows(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'])]
ps=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ps',timeout=5))
print(json.dumps({'nonce':nonce,'host':run(['hostname']).strip(),'port':port,'listener_pid':pids[0],'processes':processes,'gpus':gpus,'compute_apps':apps,'api_ps':ps}))
'''


def get(base: str, path: str, data: dict | None = None) -> dict:
    request = urllib.request.Request(base.rstrip('/') + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--request-body', type=Path)
    parser.add_argument('--capture', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    report = {'mode': 'read-only preflight; no generation', 'errors': [], 'models': {}}
    try:
        validate_contract(contract)
        if args.model not in contract['models']:
            raise PreflightError('selected model outside roster')
        base = contract['endpoint']
        version = get(base, '/api/version')['version']
        tags = {row['name']: row for row in get(base, '/api/tags')['models']}
        for tag in contract['models']:
            try:
                if tag not in tags:
                    raise PreflightError(f'{tag}: missing tag')
                snapshot = {'name': tag, 'digest': tags[tag]['digest'], 'ollama_version': version,
                            'show': get(base, '/api/show', {'model': tag})}
                report['models'][tag] = snapshot
                validate_model_snapshot(contract, tag, snapshot)
            except (PreflightError, OSError) as exc:
                report['errors'].append(str(exc))
        placement = contract['placement']
        host = placement['ssh_host']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._@-]*', host):
            raise PreflightError('invalid SSH host')
        port = placement['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise PreflightError('invalid remote port')
        nonce = uuid.uuid4().hex
        capture = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
            host, 'python3', '-', str(port), nonce], input=REMOTE_CAPTURE, text=True,
            capture_output=True, timeout=40, check=True)
        remote = json.loads(capture.stdout)
        if remote.get('nonce') != nonce:
            raise PreflightError('stale remote capture')
        local_ps = get(base, '/api/ps')
        report['remote'] = remote
        report['local_ps'] = local_ps
        try:
            report['placement'] = validate_remote_placement(contract, args.model, local_ps, remote)
        except PreflightError as exc:
            report['errors'].append(str(exc))
        if args.request_body is None:
            report['errors'].append('no actual outbound request capture; tag parameters alone do not prove effective sampling')
        else:
            body = json.loads(args.request_body.read_text())
            if body.get('model') != args.model:
                raise PreflightError('captured request is for another model')
            validate_request(contract, body)
            # Do not duplicate prompts, tool content, or credentials into the gate record.
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
