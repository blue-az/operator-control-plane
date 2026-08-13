# E5 finding — the floor is path fidelity, and it sits between 8B and 12B

**Run:** desktop, 2026-08-13, rev `1ef8364`, 90/90 cells, 90/90 traces, zero CPU
spill. Controls identical to `e4-sampled` (`num_ctx 16384`, `temperature 0.8`,
uniform strict-JSON system prompt), n=6.
**Not UID-verified. No claim registered.**

`e4-sampled` showed the fixtures saturated at 14B and above — 62 of 63 cells
passing. This walks the ladder down instead of building harder fixtures.

## Result — monotonic in model size

| Model | Params | Total | alias-add | config-value-change | function-add | median |
|---|---:|---:|---:|---:|---:|---:|
| `granite4` | 3.4B | **8/18** | **0/6** | 6/6 | 2/6 | 1.8s |
| `llama3.1:8b` | 8.0B | **9/18** | **0/6** | 5/6 | 4/6 | 2.0s |
| `gemma4:e4b` | 8.0B | **13/18** | **1/6** | 6/6 | 6/6 | 2.5s |
| `gemma4:12b` | 11.9B | **17/18** | 6/6 | 6/6 | 5/6 | 13.6s |
| `qwen2.5-coder:14b` | 14.8B | **18/18** | 6/6 | 6/6 | 6/6 | 2.5s |

The instrument discriminates cleanly here, and the ordering follows parameter
count without exception.

## The failures are real, not harness artifacts

Classified from the traces by whether a tool was dispatched:

| Mechanism | Count |
|---|---:|
| Tool ran, wrong result | **19** |
| Loop-guard repeat | 4 |
| Never dispatched | 2 |

Nineteen of twenty-five failures are genuine capability. That inverts every
earlier pack, where harness confounds dominated — and it is only interpretable
because those confounds were fixed first.

## What the floor actually is: carrying an exact path

The discriminating fixture is `alias-add`, and the failure is always the same
one. Its L2 prompt names the file explicitly as `bash/.bash_aliases`. The small
models drop the directory prefix:

```
granite4 (3.4B):     "path": ".bash_aliases"   -> Error: File not found
llama3.1:8b (8.0B):  "path": ".bash_aliases"   -> Error: File not found
```

`llama3.1:8b` also corrupts the anchor, truncating
`alias nv='nvidia-smi'` to `alias nv=`.

So the capability that fails first is **not** tool-calling, and **not** code
generation — both of which these models manage. It is carrying an exact literal
path from the prompt into the tool call. That is requirement **R1** of the L2
contract, and it is the first thing to break.

Two supporting observations:

- The tools **errored loudly** (`File not found`) rather than silently
  succeeding. The harness behaved correctly; the models were simply wrong.
- The same error appears once at **26B**: in `e4-sampled`, `gemma4:26b` read
  `bash/.bash_aliases` correctly and then patched `.bash_aliases`. So path
  fidelity is a **probabilistic failure that decays with scale**, not a hard
  threshold — roughly 6/6 → 5/6 → 4/6 → 0/6 → 0/6 → 1/9 across 3.4B to 26B.

## The three fixtures are not equally useful

| Fixture | Verdict |
|---|---|
| `alias-add` | **The discriminator.** Sharp cliff between 8B and 12B. |
| `config-value-change` | **Saturated even at 3.4B** (6/6). Carries no information at any size tested. Retire it or harden it. |
| `function-add` | Partial, and **non-monotonic** — `gemma4:e4b` 6/6 beats `gemma4:12b` 5/6. Weak discriminator. |

`config-value-change` passing 6/6 on a 3.4B model while `alias-add` scores 0/6
is worth noting on its own: the two look similar in the manifest (both are
single anchored string edits) but differ enormously in difficulty. The
difference is that `config-value-change`'s path, `config/settings.ini`, is a
conventional two-part path, while `bash/.bash_aliases` is a dotfile inside a
directory — a shape small models apparently normalise away.

## Practical reading

- **A local seat below ~12B is not viable for plan-shaped edit work** on these
  fixtures, and it fails in the least convenient way: by writing to a path that
  does not exist.
- **12B is the knee.** `gemma4:12b` reaches 17/18, but at a 13.6s median — over
  5x `qwen2.5-coder:14b`'s 2.5s for a *worse* score. Small does not mean fast.
- `qwen2.5-coder:14b` remains the value pick: 18/18 at 2.5s and 9 GB.

## Bearing on the "4B agentic coding" claim

`granite4` at 3.4B scored 8/18 and 0/6 on the discriminating fixture, failing on
path fidelity. On these fixtures, at this prompt shape, a ~3B model does not do
reliable agentic editing.

Worth noting fairly: that failure mode — losing track of an exact path given in
the instructions — is precisely what a context-management runtime claims to fix
by paging exact source and paths back in. This result does not validate any such
system, but it does indicate the failure it targets is real and is the binding
constraint at small scale.

## Limits

n=6, one machine, one prompt shape, three fixtures, one quantisation (Q4_K_M
throughout). `seed` is not honoured by this Ollama build, so these are six
independent draws rather than a reproducible set. Cross-invocation variance
remains unexplained and is not addressed here.
