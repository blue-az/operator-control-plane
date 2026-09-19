"""Preflight L3.1 fixture claims; absence is a visible state, not a test failure."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/blueaz/Python/project-phoenix/domains/TennisAgent/cockpit_poc/agent')
from core.data_client import TennisDataClient
from core.execution_context import ExecutionContext
from core.tool_registry import ToolRegistry
root=Path(__file__).parent;reg=ToolRegistry(TennisDataClient(),ExecutionContext());out={}
def call(name,**args):
 try:return reg.execute_tool(name,**args)
 except Exception as e:return {'error':str(e)}
linked=call('get_linked_session_data',date='2026-01-05');recent=call('get_recent_sessions',count=10)
rows=recent.get('sessions',recent.get('apple_watch_sessions',[])) if isinstance(recent,dict) else []
dates=[str(x.get('date','')) for x in rows if isinstance(x,dict)]
out['injected-contradiction']={'present':False,'basis':'no conflicting source identity asserted by live substrate'}
out['partial-join']={'present':bool(linked.get('has_linked_data') is False),'basis':'requested date linked payload state'}
out['weather-nearby-date-trap']={'present':True,'basis':'weather tool is aggregate/not date-specific'}
out['ambiguous-same-date']={'present':len(dates)!=len(set(dates)),'basis':dates}
out['cross-source-metric-conflict']={'present':False,'basis':'no conflicting metric pair asserted by live substrate'}
missing=call('get_linked_session_data',date='1900-01-01');out['bounded-recovery']={'present':missing.get('has_linked_data') is False or missing.get('has_data') is False,'basis':'invalid-date linked query'}
(root/'L31_PREFLIGHT.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
