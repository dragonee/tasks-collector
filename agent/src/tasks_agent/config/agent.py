"""Agent config (``tasks-agent.toml``): workdir, ollama endpoint, per-task model
map and job schedule. Parsed with the stdlib ``tomllib`` (Python 3.11+)."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Keys under [models.<name>] that map to explicit LM params; anything else is
# passed through verbatim as ``extra`` (e.g. num_ctx).
_MODEL_KNOWN_KEYS = {"model", "temperature", "max_tokens"}

DEFAULT_WORKDIR = "~/.tasks-agent"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1:8b"


@dataclass
class ModelSpec:
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduleEntry:
    name: str
    cron: str
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


class AgentConfig:
    def __init__(self, data: dict[str, Any]):
        self._data = data

        agent = data.get("agent", {})
        self.workdir = Path(agent.get("workdir", DEFAULT_WORKDIR)).expanduser()

        ollama = data.get("ollama", {})
        self.ollama_base_url = ollama.get("base_url", DEFAULT_OLLAMA_BASE_URL)
        self.default_model = ollama.get("default_model", DEFAULT_MODEL)

        self._models = data.get("models", {})
        self._schedule = data.get("schedule", {})

    @classmethod
    def paths(cls):
        return [
            Path.home() / ".config" / "tasks-agent" / "config.toml",
            Path.home() / ".tasks-agent.toml",
            Path() / "tasks-agent.toml",
        ]

    @classmethod
    def load(cls) -> "AgentConfig":
        """Merge every config file found (later paths override earlier ones)."""
        merged: dict[str, Any] = {}
        for path in cls.paths():
            if path.exists():
                with path.open("rb") as f:
                    _deep_merge(merged, tomllib.load(f))
        return cls(merged)

    def model_for(self, task: str) -> ModelSpec:
        entry = self._models.get(task, {})
        return ModelSpec(
            model=entry.get("model", self.default_model),
            temperature=entry.get("temperature"),
            max_tokens=entry.get("max_tokens"),
            extra={k: v for k, v in entry.items() if k not in _MODEL_KNOWN_KEYS},
        )

    @property
    def schedule(self) -> list[ScheduleEntry]:
        entries = []
        for name, cfg in self._schedule.items():
            entries.append(
                ScheduleEntry(
                    name=name,
                    cron=cfg["cron"],
                    enabled=cfg.get("enabled", True),
                    params=cfg.get("params", {}),
                )
            )
        return entries


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
