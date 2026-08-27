# VL case study — paper 1.37 stills, qwen3-vl:30b

**Run:** desktop, 2026-08-15T04:20:43Z, rev `18611de`, 20/20 cells.
Model `qwen3-vl:30b`, `/api/chat` + `images`, think off, ctx 16384,
temp 0.8. Grade is `message.content` only. **Not UID-verified.** Not
mixed into Elo. Frozen paper 1.37 is not edited.

Stills are the existing files, not regenerated:

| id | file |
|---|---|
| frontier | `Downloads/Elephant struggles with ATS tricycle.png` (Mar 23) |
| local | Comfy `ats_cartoon_draft_00001_.png` (Apr 8) — right panel of the composite |
| comfy12b / comfy26b | Comfy Jun 4 SDXL regen from `prompts_compare.json` |
| composite | `frontier_vs_local_elephants_corrected.png` (Apr 9) |

Gold is operator-pixel on those files. Image-off cells must not clear.

## Result

| still | image-on all-facet | image-on labels (n=3) | image-off |
|---|---|---|---|
| frontier | **3/3** | `ELEPHANT ELEPHANT-RIDER TRICYCLE COLOR` | 2/4 guess (`TRICYCLE COLOR`) |
| local | 1/2 valid | bicycle; not elephant-rider (see below) | 0/4 |
| comfy12b | **3/3** | `ELEPHANT ELEPHANT-RIDER TRICYCLE MONO` | empty |
| comfy26b | 0/3 vs CART gold | **3/3** `… TRICYCLE MONO` (not CART) | empty |
| composite | **3/3** | `FRONTIER` | empty |

After the 13.64s load cell, image-on is 0.74–2.48s. 100% GPU. `think=false`
is still leaky (20/20). Two image-on empties (`local` t2, and several
image-off) are think-prefix-only, same as the text sweep.

## What VL can see

The **frontier vs local** split is visible. Composite 3/3 names the left
panel. Frontier 3/3 is the brief (elephant, riding, child's tricycle,
color). Local, when it answers, is a bare elephant and a **bicycle**
ridden by someone else (`OTHER-RIDER` once, `NO-RIDER` once). That is
the load-bearing visual of the case study.

Image-off does not reproduce those labels. One control guessed
`TRICYCLE COLOR` from the option list; it did not guess `ELEPHANT
ELEPHANT-RIDER`.

## What VL does not confirm

Paper 1.37's sentence that **12b → bicycle, 26b → tricycle** does not
hold on the **Jun 4 regen pair**. VL labels **both** `TRICYCLE` (12b
3/3, 26b 3/3). Operator gold on 26b was `CART` (two large wheels,
`BUUCKINS` on the frame); VL never said CART. Either way this pair is
not the bicycle/tricycle contrast. That contrast lives on the Apr
frontier vs local stills, not on the later 12b/26b SDXL files.

Local rider label is slightly unstable (`NO-RIDER` vs `OTHER-RIDER`;
one empty). The bicycle / not-elephant-rider part is stable when
`content` is non-empty.

## Limits

n=3, one machine, forced four-label output. Gold for 26b `CART` is an
operator call on an ambiguous vehicle; the 12b `TRICYCLE` call is
clearer (three wheels). Composite was downscaled to 1280px for the
API. This is a grader smoke on existing stills, not a new Comfy run
and not a paper unfreeze. `qwen3-vl:30b` stays off Elo / L0–L2 / seat
tables (`GOLD_STANDARD.md` “Out of field”).
