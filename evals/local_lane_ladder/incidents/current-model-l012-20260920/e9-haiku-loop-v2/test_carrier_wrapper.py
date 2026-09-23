#!/usr/bin/env python3
from json import JSONDecodeError
from adapter import contract
from carrier_wrapper import *
c=contract('alias-add','L0'); m=workspace_manifest(c); assert 'bash/.bash_aliases' in m['declared_files']; prompt=planner_prompt(c); assert c['prompt'] in prompt; assert prompt.index(c['prompt']) >= 0
assert len(parse_plan(__import__('json').dumps(VALID_PLANNER_EXAMPLE),c))==3
valid='{"steps":[{"tool":"read_file","args":{"path":"bash/.bash_aliases"}}]}'
assert len(parse_plan(valid,c))==1
assert len(parse_plan('Planner note: '+valid+' trailing explanation',c))==1
assert len(parse_plan('```json\n'+valid+'\n```',c))==1
multi='{"steps":[{"tool":"read_file","args":{"path":"bash/.bash_aliases"}},{"tool":"write_file","args":{"path":"bash/.bash_aliases","content":"x"}},{"tool":"run_check","args":{}}]}'
assert len(parse_plan(multi,c))==3
import tempfile
with tempfile.TemporaryDirectory() as d:
 f=Path(d)/'fixture'; ev=__import__('adapter').execute_deterministic(c,VALID_PLANNER_EXAMPLE['steps'],f); assert "alias 200='sudo nvidia-smi -pl 200'" in ev['workspace_files']['bash/.bash_aliases']; assert not (Path(d)/'outside').exists()
for bad in [
 valid+'\n'+valid,
 '{"steps":[{"action":"read_file","path":"~/.bash_aliases"}]}',
 '{"steps":[{"tool":"read_file","args":{"path":"/home/x"}}]}',
 '{"steps":[{"tool":"read_file","args":{"path":"../../escape"}}]}',
 '{"steps":[{"tool":"write_file","args":{"path":"bash/.bash_aliases","content":"x","extra":1}}]}']:
 try: parse_plan(bad,c); raise AssertionError('accepted invalid planner output')
 except (ValueError,KeyError,TypeError,JSONDecodeError): pass
print('PASS exact raw prompt/manifest; bare or complete-fence JSON only; wrong schema/home/absolute/traversal rejected')
