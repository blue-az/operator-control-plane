# VL smoke — qwen3-vl:30b sees the still; 167 tok/s is think-prefix

**Run:** desktop, 2026-08-15T04:12:24Z, rev `18611de`, 27/27 cells, 27/27
valid, 27/27 traces. Model `qwen3-vl:30b`, `/api/chat` + `images` base64,
ctx 16384, temp 0.8, `num_predict` 2048. Grade is `message.content` only.
**Not UID-verified.** Not mixed into Elo. Not a seat claim.

Question: does the model read the image; is `think=false` leaky; is the
~167 tok/s figure an answer rate.

Gold is per-run nonce, not a prior. `smi` still is live `nvidia-smi` plus
`PROBE=A83DFF`. `dash` is `SPAN_COUNT=932`. `mark` is `PHOENIX-VL-A4F9`.
Image-omitted cells must *not* hit gold.

## Result

| Condition | n | gold hit | leaky | mean s | tok/s band |
|---|---:|---:|---:|---:|---|
| image + think off | 9 | **9/9** | **9/9** | 3.1 | 151.8–168.6 |
| image + think on | 9 | **9/9** | 0/9 | 0.6 | 158.1–168.0 |
| no image + think off | 9 | **0/9** | **9/9** | 4.8 | 157.8–174.9 |

Image-on after the cold first cell (20.86s load) is 0.48–1.58s. Every
cell sat at 100% GPU on the 3090 / 320 W.

Exact `content` on image-on: `A83DFF`, `932`, `PHOENIX-VL-A4F9`. Image-off
guesses: `PROBE`, `0`, `3`, `X`, `19`, `F1`. Prompt leakage (`PROBE`) is
not the nonce.

## What the 167 tok/s figure is

`tok/s` is Ollama `eval_count / eval_duration`. Image-on answers are 3–15
characters. `eval_count` on those cells is 42–114. The extra tokens are
the think prefix (`thinking_chars` 101–322). The earlier text-only sweep
(128 think tokens, empty `content`) was the same meter with no answer.

Image-off keeps the same 158–175 tok/s while spending 2–13s on 218–8296
chars of think and then a one-token guess. Decode rate is real; it is
not time-to-gold.

## Think leak

`think=false` still fills `message.thinking` on every cell (18/18).
`think=true` also thinks, as asked, and is not scored leaky. The flag
does not suppress the prefix. Grade-on-`content` is what made the
image-on cells pass.

## Limits

n=3 per still × condition, one machine, rendered text stills (not
photographs or UI screenshots of the live Grafana panel). First-cell
20.86s is load, not vision latency. This pack does not compare VL
against 26b / 3.8 on the text ladder and does not change the seat.
