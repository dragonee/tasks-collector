"""DSPy + ollama wiring.

Builds a per-task :class:`dspy.LM` from the agent config's ``[models.<task>]`` map.
We bind the LM per job with ``dspy.context(lm=...)`` (never a global
``dspy.configure``) so successive jobs each use their own configured model.
"""

import dspy

from .config.agent import AgentConfig, ModelSpec


def build_lm(task_name: str, cfg: AgentConfig) -> dspy.LM:
    spec: ModelSpec = cfg.model_for(task_name)

    kwargs: dict = dict(spec.extra)
    if spec.temperature is not None:
        kwargs["temperature"] = spec.temperature
    if spec.max_tokens is not None:
        kwargs["max_tokens"] = spec.max_tokens

    return dspy.LM(
        # litellm's ollama *chat* provider; pair with api_base pointing at ollama.
        f"ollama_chat/{spec.model}",
        api_base=cfg.ollama_base_url,
        api_key="",  # ollama needs none
        **kwargs,
    )
