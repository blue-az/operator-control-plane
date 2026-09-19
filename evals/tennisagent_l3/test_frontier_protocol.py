from tool_loop import _json

def test_plain_tool_json():
 assert _json('{"tool":"get_linked_session_data","args":{"date":"2026-01-05"}}')['tool']=='get_linked_session_data'

def test_fenced_json():
 assert _json('```json\n{"final":"grounded"}\n```')['final']=='grounded'

def test_preface_json():
 assert _json('Here is the result: {"final":"grounded"}')['final']=='grounded'

def test_reject_non_object():
 assert _json('[1,2]') is None
