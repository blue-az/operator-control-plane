# Successor termination deviation

Trace review of the corrected 36-cell successor run found that every failed
cell had selected valid tools and arguments, but the runner's three-turn limit
ended before final synthesis. Examples:

- qwen3.6 and gemma4 completed the required three-call chains, then had no
  final answer;
- qwen3.8 selected four/five calls on the two-session and contradiction tasks,
  also without final synthesis.

Therefore the observed 18/36 score is a termination-budget result, not a clean
capability ranking. The tool selection and argument traces are retained. The
successor must be rerun with an explicit bounded completion budget (for
example, six turns) and a separate metric for chain completion versus final
synthesis.
