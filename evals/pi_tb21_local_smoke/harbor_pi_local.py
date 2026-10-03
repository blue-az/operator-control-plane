"""Harbor's pi agent with explicit limits for a local Ollama model.

Harbor writes pi's models.json with only the model id. pi 1.0.0 then assumes
contextWindow=128000 and maxTokens=16384, so it never compacts against an
Ollama model with num_ctx=32768. Once the conversation outgrows 32k (one large
tool output is enough), Ollama silently drops the oldest part, including the
system prompt and task (seen 2026-10-02 on extract-elf).

pi also sends the output cap as max_completion_tokens to generic
OpenAI-compatible endpoints, which Ollama ignores (tested 2026-10-02: a cap of
20 returned 1053 tokens; max_tokens=20 returned 20). compat.maxTokensField
switches pi to max_tokens.

reasoning + thinkingLevelMap.off="none" + supportsReasoningEffort let
`thinking: "off"` reach Ollama as reasoning_effort="none", which disables
qwen3.6's thinking (tested 2026-10-02: unset 8121 reasoning chars, none 0;
low/high did not shorten it reliably).

Use with: "import_path": "harbor_pi_local:PiLocalLimits" and PYTHONPATH set to
this directory.
"""

import os

from harbor.agents.installed.pi import _CUSTOM_PROVIDER, Pi

# Must match the Ollama num_ctx of the loaded model.
CONTEXT_WINDOW = int(os.environ.get("PI_LOCAL_CONTEXT_WINDOW", "32768"))
MAX_TOKENS = int(os.environ.get("PI_LOCAL_MAX_TOKENS", "4096"))


class PiLocalLimits(Pi):
    def _build_custom_models_json(self, access, model_id):
        models_json = super()._build_custom_models_json(access, model_id)
        if models_json is not None:
            for model in models_json["providers"][_CUSTOM_PROVIDER]["models"]:
                model.update(
                    contextWindow=CONTEXT_WINDOW,
                    maxTokens=MAX_TOKENS,
                    reasoning=True,
                    thinkingLevelMap={"off": "none"},
                    compat={
                        "maxTokensField": "max_tokens",
                        "supportsReasoningEffort": True,
                        # reasoning=True makes pi send the system prompt as the
                        # "developer" role; qwen3.8's Ollama template rejects it.
                        "supportsDeveloperRole": False,
                    },
                )
        return models_json
