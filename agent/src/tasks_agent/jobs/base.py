"""Job interface, context and registry."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..api import ApiClient
from ..config.agent import AgentConfig
from ..config.backend import BackendConfig
from ..workdir import Workdir

# name -> Job subclass. Populated by @register when job modules are imported.
JOB_REGISTRY: dict[str, type["Job"]] = {}


def register(cls: type["Job"]) -> type["Job"]:
    JOB_REGISTRY[cls.name] = cls
    return cls


@dataclass
class JobContext:
    api: ApiClient
    agent_config: AgentConfig
    workdir: Workdir
    now: datetime
    params: dict[str, Any] = field(default_factory=dict)


class Job:
    name: str = "job"  # also the [models.<name>] / [schedule.<name>] config key

    def run(self, ctx: JobContext) -> Path:
        """Do the work and return the path of the draft written to the workdir."""
        raise NotImplementedError


def build_context(params=None, now=None) -> JobContext:
    """Assemble a JobContext from the two config sources."""
    agent_cfg = AgentConfig.load()
    backend = BackendConfig()
    return JobContext(
        api=ApiClient(backend),
        agent_config=agent_cfg,
        workdir=Workdir(agent_cfg.workdir),
        now=now or datetime.now(),
        params=params or {},
    )
