#!/usr/bin/env python3
import tempfile
from pathlib import Path
from adapter import *
assert len(plan())==54
c=contract('alias-add','L0')
try: validate_step({'tool':'shell','args':{'cmd':'touch /tmp/pwn'}},c); raise AssertionError
except ValueError: pass
for bad in ({'tool':'read_file','args':{'path':'../../escape'}},{'tool':'write_file','args':{'path':'/absolute','content':'x'}},{'tool':'run_check','args':{'check':'shell'}}):
 try: validate_step(bad,c); raise AssertionError('bad step accepted')
 except ValueError: pass
with tempfile.TemporaryDirectory() as d:
 f=Path(d)/'fixture'; result=execute_deterministic(c,[{'tool':'write_file','args':{'path':'bash/.bash_aliases','content':"alias 200='sudo nvidia-smi -pl 200'"}},{'tool':'run_check','args':{}}],f); assert grade(c,result)['passed']; assert not (Path('/tmp')/'pwn').exists()
 assert redact({'token':'secret','ok':1})['token']=='[REDACTED]'
 try: fresh_root(Path(d),'x'); fresh_root(Path(d),'x'); raise AssertionError
 except FileExistsError: pass
assert cli_argv('x')[2:4]==['--model','haiku'] and cli_argv('x')[-3]=='--tools' and cli_argv('x')[-2]==''
print('PASS 54-cell plan; malformed/traversal/tool rejection; deterministic fixture executor/grader; redaction; fresh root; text-only alias CLI argv; no Claude call')
