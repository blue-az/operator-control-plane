import json
from pathlib import Path
root=Path(__file__).parent
d=json.loads((root/'fusion_l31_fixtures.json').read_text())
assert len(d['fixtures'])==6 and d['pilot']['cells']==54
s=Path('/home/blueaz/Python/project-phoenix/domains/TennisAgent/cockpit_poc/agent/core/tool_registry.py').read_text()
for f in d['fixtures']:
 for n in f['required_tools']: assert f'name="{n}"' in s,n
assert all(f['ground_truth'] for f in d['fixtures'])
print('L31_FIXTURES_VALID')
