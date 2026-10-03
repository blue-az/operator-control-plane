#!/usr/bin/env python3
"""Read-only live gate for a llama-server comparison contract.

The llama-server counterpart of preflight_comparison.py. Checks the server's own
/props (alias, loaded file, every pinned sampler value, one slot, speculation
off), a fresh sha256 of the GGUF on the serving host, GPU memory attributed to
the listening process on the one declared card, and a captured outbound body.
Exit 2 unless all pass. Does not generate, start, stop or reconfigure anything.
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
    validate_llama_placement,
    validate_llama_props,
    validate_request,
)

REMOTE_CAPTURE = r'''
import csv,hashlib,json,os,re,subprocess,sys
port=int(sys.argv[1]); nonce=sys.argv[2]; path=sys.argv[3]
def run(args): return subprocess.check_output(args,text=True,timeout=15)
def rows(args): return list(csv.reader(run(args).splitlines(),skipinitialspace=True))
listeners=run(['ss','-ltnp',f'sport = :{port}'])
pids=sorted(set(int(p) for p in re.findall(r'pid=(\d+)',listeners)))
if len(pids)!=1: raise RuntimeError('expected one visible serving listener PID')
digest=hashlib.sha256()
with open(path,'rb') as f:
    for block in iter(lambda: f.read(1<<24), b''): digest.update(block)
apps=[{'gpu_uuid':r[0],'pid':int(r[1]),'used_mib':float(r[2])} for r in rows(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'])]
clocks={r[0]:int(r[1]) for r in rows(['nvidia-smi','--query-gpu=uuid,clocks.mem','--format=csv,noheader,nounits'])}
print(json.dumps({'nonce':nonce,'host':run(['hostname']).strip(),'port':port,'listener_pid':pids[0],
  'compute_apps':apps,'memory_clock_mhz':clocks,'gguf':{'path':path,'sha256':digest.hexdigest(),'bytes':os.path.getsize(path)}}))
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--request-body', type=Path)
    parser.add_argument('--capture', type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text())
    report = {'mode': 'read-only preflight; no generation', 'errors': []}
    try:
        validate_contract(contract)
        if args.model not in contract['models']:
            raise PreflightError('selected model outside roster')
        with urllib.request.urlopen(contract['endpoint'].rstrip('/') + '/props', timeout=15) as response:
            props = json.load(response)
        report['props'] = {k: v for k, v in props.items() if k != 'chat_template'}
        placement = contract['placement']
        host = placement['ssh_host']
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._@-]*', host):
            raise PreflightError('invalid SSH host')
        port = placement['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise PreflightError('invalid remote port')
        nonce = uuid.uuid4().hex
        capture = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', host,
            'python3', '-', str(port), nonce, contract['models'][args.model]['gguf_path']],
            input=REMOTE_CAPTURE, text=True, capture_output=True, timeout=600, check=True)
        remote = json.loads(capture.stdout)
        if remote.get('nonce') != nonce:
            raise PreflightError('stale remote capture')
        report['remote'] = remote
        for name, check in (('model', lambda: validate_llama_props(contract, args.model, props, remote['gguf'])),
                            ('placement', lambda: validate_llama_placement(contract, args.model, remote))):
            try:
                report[name] = check()
            except PreflightError as exc:
                report['errors'].append(str(exc))
        if args.request_body is None:
            report['errors'].append('no actual outbound request capture; server defaults alone do not prove effective sampling')
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
