#!/usr/bin/env python3
import tempfile
from pathlib import Path
from adapter import contract,grade
c=contract('grep-and-report','L0')
with tempfile.TemporaryDirectory() as d:
 ev={'workspace_files':{'config/api_config.ini':'[api]\nendpoint = https://api.example.com/v2\n'}}
 assert grade(c,ev,'The endpoint is https://api.example.com/v2.')['passed']
 assert not grade(c,ev,'')['passed']
for task in ('alias-add','config-value-change','doc-fix','function-add','grep-and-report','multi-file-rename-reference'):
 c=contract(task,'L0'); assert 'postcondition' in c
print('PASS all-six output/grader bridge coverage; synthesis output required for output_contains; missing output fails')
