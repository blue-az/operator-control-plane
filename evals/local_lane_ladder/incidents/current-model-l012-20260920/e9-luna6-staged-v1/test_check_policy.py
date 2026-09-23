#!/usr/bin/env python3
from adapter import TASKS,contract,validate_step,execute_deterministic
from pathlib import Path
import tempfile
for task in TASKS:
 c=contract(task,'L0'); validate_step({'tool':'run_check','args':{}},c)
 for bad in ({'check':'postcondition_grep'},{'check':'find_broken_imports'},{'check':'shell'}):
  try: validate_step({'tool':'run_check','args':bad},c); raise AssertionError((task,bad))
  except ValueError: pass
c=contract('function-add','L2'); steps=[{'tool':'write_file','args':{'path':'src/math_helpers.py','content':'bad'}},{'tool':'run_check','args':{'check':'postcondition_grep'}}]
with tempfile.TemporaryDirectory() as d:
 try: execute_deterministic(c,steps,Path(d)); raise AssertionError('wrong check mutated')
 except ValueError: assert not (Path(d)/'src/math_helpers.py').exists()
 for tool,args in (('read_file',['x']),('write_file',['x','y']),('run_check',['postcondition'])):
  try: validate_step({'tool':tool,'args':args},c); raise AssertionError((task,tool,args))
  except ValueError: pass
print('PASS adapter-owned grading; empty run_check accepted for all six; named/unknown/array args rejected before mutation; cell10/cell36 trajectories covered')
