#!/usr/bin/env python3
"""Standalone deterministic parity grader for all frozen e4 postcondition types."""
import ast, re, subprocess
from pathlib import Path

def grade(post, root, output=''):
 kind=post['type']; target=Path(root)/post.get('file','')
 if kind=='grep':
  if not target.is_file(): return False,f'file does not exist: {post["file"]}'
  text=target.read_text(errors='replace'); pat=post['pattern']
  if pat not in text:return False,f'pattern not found: {pat!r}'
  if post.get('must_not_contain') and post['must_not_contain'] in text:return False,'forbidden content present'
  return True,f'pattern found: {pat!r}'
 if kind=='output_contains': return (post['value'] in output),('value found' if post['value'] in output else 'value not found')
 if kind=='exec':
  try:r=subprocess.run(post['command'],shell=True,cwd=root,capture_output=True,text=True,timeout=post.get('timeout',30))
  except subprocess.TimeoutExpired:return False,'postcondition command timed out'
  return (r.returncode==0),(f'postcondition command exited {r.returncode}' if r.returncode else 'postcondition command exited 0')
 return False,f'unimplemented postcondition type: {kind}'
