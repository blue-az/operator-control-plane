#!/usr/bin/env python3
"""Model-free H1 staged carrier wrapper; no provider invocation."""
import json,re
from pathlib import Path
from bounded_json import extract_one
from adapter import validate_step

VALID_PLANNER_EXAMPLE={"steps":[{"tool":"read_file","args":{"path":"bash/.bash_aliases"}},{"tool":"write_file","args":{"path":"bash/.bash_aliases","content":"alias 200='sudo nvidia-smi -pl 200'\n"}},{"tool":"run_check","args":{}}]}

def workspace_manifest(cell):
 return {'root':'/work','declared_files':sorted(cell['files']), 'forbidden':['/home','/tmp','/etc','..','~'], 'actions':['read_file','write_file','run_check'], 'schema':{'read_file':{'args':['path']},'write_file':{'args':['path','content']},'run_check':{'args':[],'meaning':'adapter-owned grading after trajectory'}}}

def planner_prompt(cell):
 # raw e4 prompt is inserted byte-for-byte as the TASK section.
 return ('Return exactly one JSON object and no markdown/prose. Use only the exact action schema '
  '{"steps":[{"tool":"read_file|write_file|run_check","args":{...}}]}. '
  'All paths must be relative to /work and listed in declared_files. Never use home, absolute, '
  'temporary, traversal, or shell paths. Workspace manifest:\n'+json.dumps(workspace_manifest(cell),sort_keys=True)+
  '\nVALID PLANNER EXAMPLE (schema only):\n'+json.dumps(VALID_PLANNER_EXAMPLE,sort_keys=True)+'\nTASK (verbatim e4 prompt):\n'+cell['prompt'])

def unwrap_json_only(text):
 return extract_one(text)

def parse_plan(text,cell):
 obj=unwrap_json_only(text)
 if set(obj)!={'steps'} or not isinstance(obj['steps'],list): raise ValueError('wrong plan schema')
 for step in obj['steps']:
  if set(step)!= {'tool','args'}: raise ValueError('wrong action schema')
  expected={'read_file':{'path'},'write_file':{'path','content'},'run_check':set()}[step['tool']]
  if set(step['args']) != expected: raise ValueError('wrong argument schema')
  validate_step(step,cell)
 return obj['steps']


# --- Turn loop (v2) ----------------------------------------------------------
#
# v1 asked for the whole trajectory blind, before the model had seen any file
# contents, and scored it in one shot. Local models on the same battery get the
# opposite: Pi with real tools, reading and iterating. Both frontier controls
# scored ~0 under v1 where local 27B/35B score 18/18, which measures the carrier
# rather than the models.
#
# v2 changes only the interaction: the model emits one turn of actions, the
# deterministic adapter executes them and hands back what they produced, and the
# model continues. The executor, the scope validation and the grader are the same
# code v1 used, so a v2 score is comparable to a local E9 score in a way a v1
# score never was.
def turn_prompt(cell, turn, observations, max_turns):
 head = ('Return exactly one JSON object and no markdown/prose, using the exact action schema '
  '{"steps":[{"tool":"read_file|write_file|run_check","args":{...}}]}. '
  'Emit only the next few actions, not the whole task: each turn is executed and its results '
  'are returned to you before you continue. Include run_check when you believe the task is '
  'complete; it ends the episode. All paths must be relative to /work and listed in '
  'declared_files. Never use home, absolute, temporary, traversal, or shell paths.')
 body = ('\nWorkspace manifest:\n' + json.dumps(workspace_manifest(cell), sort_keys=True) +
  '\nVALID SCHEMA EXAMPLE (shape only):\n' + json.dumps(VALID_PLANNER_EXAMPLE, sort_keys=True) +
  f'\nTurn {turn} of at most {max_turns}.')
 if observations:
  body += '\nRESULTS OF YOUR PREVIOUS ACTIONS (authoritative; do not guess file contents):\n'
  body += json.dumps(observations, sort_keys=True)
 return head + body + '\nTASK (verbatim e4 prompt):\n' + cell['prompt']
