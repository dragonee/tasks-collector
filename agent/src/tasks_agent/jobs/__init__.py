"""Job registry. Importing this package registers all built-in jobs."""

# Import job modules so their @register decorators run (side-effect import).
from . import review  # noqa: E402,F401
from .base import JOB_REGISTRY, Job, JobContext, build_context, register

__all__ = [
    "JOB_REGISTRY",
    "Job",
    "JobContext",
    "build_context",
    "register",
]
