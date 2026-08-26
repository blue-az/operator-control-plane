# ComfyUI symbolic constraint scores

| label | artifact/region | score | notes |
|---|---|---:|---|
| frontier_reference | assets/frontier_vs_local_elephants_corrected.png#frontier_left | 4/4 | Elephant in business suit rides a tiny tricycle labeled ATS; company HQ, speech bubble, rejected resumes, and creaking tricycle make satire legible. |
| local_reference_composite_region | assets/frontier_vs_local_elephants_corrected.png#local_right | 1/4 | Recognizable elephant, but it is not riding a tiny tricycle; small human bicycle/rider elements and sign do not carry the ATS hiring metaphor. |
| gemma4_12b_raw_local | assets/ats_cartoon_12b_00001_.png | 3/4 | Large suited elephant on a small wheeled cycle, but no clear ATS/hiring/company/rejected-resume semantic marker. |
| gemma4_26b_raw_local | assets/ats_cartoon_26b_00001_.png | 3/4 | Large suited elephant on a small tricycle-like vehicle; metaphor is not legible as ATS/hiring without external prompt context. |
| harness_assisted_hybrid | assets/ats_cartoon_hybrid_clean_00004.png | 3/4 | Harness/compositing adds ATS/caption cues, but the image itself still reads as an elephant next to/overlaid with a bicycle-like diagram rather than a clean political cartoon. Caption rescue is not counted as raw image-legible satire. |

Status: `artifact_scored_not_fully_rerunnable`
