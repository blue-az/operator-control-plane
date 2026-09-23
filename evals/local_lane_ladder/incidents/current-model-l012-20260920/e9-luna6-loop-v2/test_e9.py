#!/usr/bin/env python3
from adapter import TASKS,contract,execute_deterministic,grade
from pathlib import Path
import tempfile
assert TASKS==('ambiguous-anchor','csv-summarize-repair','strict-log-format')
for task in TASKS:
 c=contract(task,'L2'); assert c['files'] and c['postcondition']
 with tempfile.TemporaryDirectory() as d:
  f=Path(d)
  for p,v in c['files'].items(): (f/p).parent.mkdir(parents=True,exist_ok=True); (f/p).write_text(v)
  steps=[{'tool':'read_file','args':{'path':next(iter(c['files']))}}]
  ev=execute_deterministic(c,steps,f); assert not grade(c,ev,'')['passed']
  try: execute_deterministic(c,[{'tool':'read_file','args':['bad']}],f); raise AssertionError
  except ValueError: pass
print('PASS E9 three-task L2 contracts, deterministic grading, fixture guards, malformed args')
