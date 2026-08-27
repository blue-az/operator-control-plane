# Anonymous stills — human grade

**What this is.** A local page that shows the four 1.37 / VL stills as
Picture A–D, shuffled, sources hidden. You grade against the brief, then
save JSON. Same A/B/C idea as z13 quality: one grader (you), several
writers (frontier / Apr local / Jun 12b / Jun 26b).

**Not** `qwen3-vl:30b`. That pack already labeled these files
(`FINDING.md`). This is the human pass VL cannot substitute — brief-match
and rank, with the source names off the screen.

## Run

```bash
# from this directory, so stills/ resolve
python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/anonymous-grade.html
```

Or open `anonymous-grade.html` as a file if the browser allows local
images. Add `?seed=N` to lock a permutation.

## Grade axes

- brief match 1–5
- vehicle: TRICYCLE / BICYCLE / CART / NONE (same vocabulary as `gold.json`)
- rider: ELEPHANT-RIDER / OTHER-RIDER / NO-RIDER
- rank 1–4
- optional notes

Save downloads `anonymous-grade-<seed>.json`. Reveal only after you save
if you want a clean blind.

## Deck (unblinded, for the file, not the page)

| id | file | writer |
|---|---|---|
| frontier | Mar 23 color trike | frontier image model |
| local | Apr 8 Comfy draft | early local prompt |
| comfy12b | Jun 4 SDXL | `gemma4:12b` prompt |
| comfy26b | Jun 4 SDXL | `gemma4:26b` prompt |

Composite is omitted — it is labeled Frontier / Local.

## Limits

Four stills, one brief, one human. A new Comfy sweep (fresh seeds, 31b
prompt as a fifth writer) is a different pack. Do not fold these grades
into Elo or the local-lane seat table.
