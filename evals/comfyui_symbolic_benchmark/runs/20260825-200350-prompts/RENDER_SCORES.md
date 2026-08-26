# Repeatable ComfyUI render scores — 20260825-200350-prompts

Renderer: local ComfyUI 0.18.1 on CPU (`--cpu`), SDXL base checkpoint, 512×512, 8 Euler steps. Prompt authors: local text models via Pi/Ollama, tools disabled.

| prompt author | image | score | notes |
|---|---|---:|---|
| qwen3.8:27b | `qwen38.render.png` | 2/4 | Recognizable elephant and a red wheeled object under/behind it, but not a clearly recognizable tiny child's tricycle; no ATS/hiring satire is legible. |
| qwen3.6:35b | `qwen36-35b.render.png` | 1/4 | Tricycle/bicycle form is present, but the animal is not a recognizable elephant and the ATS/hiring metaphor is absent. |
| gemma4:31b | `gemma31.render.png` | 1/4 | Recognizable elephant riding a wheeled contraption, but not a tiny child's tricycle, not visibly overloaded in the intended way, and no ATS/hiring satire is legible. |
| gemma4:26b | `gemma26.render.png` | 1/4 | Recognizable elephant/elephant head motif, but no recognizable tricycle/riding proposition and no ATS/hiring satire. |

Result: repeatable scaffold produced new local renders and reproduced the core negative result. None of the four local prompt-author + SDXL renders solved the symbolic cartoon task; all missed the meaning-carrying ATS/hiring satire constraint.
