#!/usr/bin/env python3
import tempfile,yaml
from pathlib import Path
from grader_parity import grade
ROOT=Path(__file__).parent
for f in sorted(ROOT.glob('*.yaml')):
 d=yaml.safe_load(f.read_text()); post=d['postcondition']
 with tempfile.TemporaryDirectory() as td:
  root=Path(td)
  for rel,content in d['files'].items(): (root/rel).parent.mkdir(parents=True,exist_ok=True); (root/rel).write_text(content)
  output=''
  if d['task_id']=='alias-add': (root/post['file']).write_text((root/post['file']).read_text()+post['pattern']+'\n')
  elif d['task_id']=='config-value-change': (root/post['file']).write_text((root/post['file']).read_text().replace('debug = false',post['pattern']))
  elif d['task_id']=='doc-fix': (root/post['file']).write_text((root/post['file']).read_text().replace(post['must_not_contain'],post['pattern']))
  elif d['task_id']=='function-add': (root/'src/math_helpers.py').write_text((root/'src/math_helpers.py').read_text()+"\n\ndef square(n):\n    return n * n\n")
  elif d['task_id']=='grep-and-report': output=post['value']
  elif d['task_id']=='multi-file-rename-reference': (root/post['file']).write_text((root/post['file']).read_text().replace(post['must_not_contain'],post['pattern']))
  ok,detail=grade(post,root,output); assert ok,(d['task_id'],detail)
print('PASS exact grader parity coverage for all six frozen e4 task contracts')
