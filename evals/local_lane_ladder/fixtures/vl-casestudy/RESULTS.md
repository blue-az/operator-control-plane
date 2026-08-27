# VL case study — ATS cartoon / paper 1.37 stills

Generated from 20 cells. Model `qwen3-vl:30b`.
Grade is `message.content` only. Gold is operator-pixel on these files.

## Per cell

| still | image | t | all | hits | empty | leaky | s | ctok | think_ch | resp_ch | tok/s | place | response |
|---|:---:|---:|:---:|---:|:---:|:---:|---:|---:|---:|---:|---:|---|---|
| frontier | 1 | 1 | Y | 4/4 | 0 | 1 | 13.64 | 129 | 411 | 38 | 154.3 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE COLOR |
| frontier | 1 | 2 | Y | 4/4 | 0 | 1 | 1.48 | 184 | 616 | 38 | 160.1 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE COLOR |
| frontier | 1 | 3 | Y | 4/4 | 0 | 1 | 0.98 | 101 | 277 | 38 | 157.1 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE COLOR |
| frontier | 0 | 1 | n | 2/4 | 0 | 1 | 1.3 | 168 | 505 | 38 | 169.2 | 100% GPU | NO-ELEPHANT OTHER-RIDER TRICYCLE COLOR |
| local | 1 | 1 | n | 3/4 | 0 | 1 | 2.48 | 218 | 711 | 30 | 156.9 | 100% GPU | ELEPHANT NO-RIDER BICYCLE MONO |
| local | 1 | 2 | n | 0/4 | 1 | 1 | 1.92 | 256 | 916 | 0 | 159.5 | 100% GPU |  |
| local | 1 | 3 | Y | 4/4 | 0 | 1 | 1.78 | 235 | 812 | 33 | 160.3 | 100% GPU | ELEPHANT OTHER-RIDER BICYCLE MONO |
| local | 0 | 1 | n | 0/4 | 0 | 1 | 1.28 | 175 | 528 | 31 | 172.6 | 100% GPU | NO-ELEPHANT NO-RIDER CART COLOR |
| comfy12b | 1 | 1 | Y | 4/4 | 0 | 1 | 1.85 | 126 | 367 | 37 | 163.1 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy12b | 1 | 2 | Y | 4/4 | 0 | 1 | 0.94 | 100 | 274 | 37 | 163.7 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy12b | 1 | 3 | Y | 4/4 | 0 | 1 | 1.35 | 168 | 517 | 37 | 164.1 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy12b | 0 | 1 | n | 0/4 | 1 | 1 | 1.77 | 256 | 896 | 0 | 170.4 | 100% GPU |  |
| comfy26b | 1 | 1 | n | 3/4 | 0 | 1 | 1.74 | 105 | 286 | 37 | 158.3 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy26b | 1 | 2 | n | 3/4 | 0 | 1 | 1.53 | 195 | 591 | 37 | 162.9 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy26b | 1 | 3 | n | 3/4 | 0 | 1 | 1.05 | 116 | 345 | 37 | 161.2 | 100% GPU | ELEPHANT ELEPHANT-RIDER TRICYCLE MONO |
| comfy26b | 0 | 1 | n | 0/4 | 1 | 1 | 1.81 | 256 | 876 | 0 | 169.6 | 100% GPU |  |
| composite | 1 | 1 | Y | 1/1 | 0 | 1 | 1.5 | 68 | 263 | 8 | 159.8 | 100% GPU | FRONTIER |
| composite | 1 | 2 | Y | 1/1 | 0 | 1 | 0.83 | 90 | 358 | 8 | 165.6 | 100% GPU | FRONTIER |
| composite | 1 | 3 | Y | 1/1 | 0 | 1 | 0.74 | 75 | 282 | 8 | 166.9 | 100% GPU | FRONTIER |
| composite | 0 | 1 | n | 0/1 | 1 | 1 | 1.78 | 256 | 1121 | 0 | 172.8 | 100% GPU |  |

## Condition totals (all-facet hit / valid)

| still | image | all | mean facets | leaky | mean s |
|---|:---:|---:|---:|---:|---:|
| comfy12b | 0 | 0/0 | — | 1/1 | 1.8 |
| comfy12b | 1 | 3/3 | 4.00/4 | 3/3 | 1.4 |
| comfy26b | 0 | 0/0 | — | 1/1 | 1.8 |
| comfy26b | 1 | 0/3 | 3.00/4 | 3/3 | 1.4 |
| composite | 0 | 0/0 | — | 1/1 | 1.8 |
| composite | 1 | 3/3 | 1.00/1 | 3/3 | 1.0 |
| frontier | 0 | 0/1 | 2.00/4 | 1/1 | 1.3 |
| frontier | 1 | 3/3 | 4.00/4 | 3/3 | 5.4 |
| local | 0 | 0/1 | 0.00/4 | 1/1 | 1.3 |
| local | 1 | 1/2 | 3.50/4 | 3/3 | 2.1 |
