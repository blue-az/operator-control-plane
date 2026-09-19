# Haiku protocol finding

The repeated Haiku regression confirms the main failure is the invocation
contract, not token budget or raw result size. Direct `claude -p` treats the
external JSON-instruction prompt as an attempted behavior override and replies
that it will not act as an external tool executor. It therefore emits no
parseable JSON on most calls.

Compacting tool results improved payload size but did not change this boundary.
A native Claude tool registration/API is required; the text-only CLI cannot be
used as a reliable custom TennisAgent tool-loop provider.
