"""Central data workdir manager.

Owns the on-disk layout under the agent's workdir (default ``~/.tasks-agent``):

    context/     human-maintained prompt context (style.md, persona.md, ...)
    drafts/<job>/<name>.md    job output drafts (reviewed before anything is posted)
    runs/<ts>-<job>.json      per-run metadata
    state/last_run.json       last successful run per job (used by `tick`)
    state/queue/              dead-letter queue for future write-back POSTs
    cache/                    optional cached API responses
"""

import json
from datetime import datetime
from pathlib import Path


class Workdir:
    def __init__(self, root):
        self.root = Path(root).expanduser()

    # ---- directories ----
    @property
    def context_dir(self) -> Path:
        return self.root / "context"

    @property
    def drafts_dir(self) -> Path:
        return self.root / "drafts"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def queue_dir(self) -> Path:
        return self.state_dir / "queue"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @staticmethod
    def _ensure(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ---- context ----
    def read_context(self, *names: str) -> str:
        """Concatenate the given context files, skipping any that don't exist."""
        parts = []
        for name in names:
            path = self.context_dir / name
            if path.exists():
                parts.append(path.read_text().strip())
        return "\n\n".join(p for p in parts if p)

    # ---- drafts ----
    def draft_path(self, job: str, name: str) -> Path:
        return self.drafts_dir / job / name

    def write_draft(self, job: str, name: str, text: str) -> Path:
        path = self._ensure(self.drafts_dir / job) / name
        path.write_text(text)
        return path

    # ---- run logs ----
    def write_run_log(self, job: str, meta: dict, now: datetime) -> Path:
        self._ensure(self.runs_dir)
        stamp = now.strftime("%Y-%m-%dT%H%M%S")
        path = self.runs_dir / f"{stamp}-{job}.json"
        path.write_text(json.dumps(meta, indent=2, default=str))
        return path

    # ---- last-run state (for the runner's `tick`) ----
    def _last_run_file(self) -> Path:
        return self.state_dir / "last_run.json"

    def _read_last_run(self) -> dict:
        path = self._last_run_file()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            # Fail safe: a corrupt/unreadable file is treated as "never ran".
            return {}

    def get_last_run(self, job: str):
        raw = self._read_last_run().get(job)
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def set_last_run(self, job: str, when: datetime) -> None:
        self._ensure(self.state_dir)
        data = self._read_last_run()
        data[job] = when.isoformat()
        self._last_run_file().write_text(json.dumps(data, indent=2))

    # ---- dead-letter queue (used by future write-back) ----
    def dead_letter(self, payload: dict, meta: dict, file_type: str = "item") -> Path:
        self._ensure(self.queue_dir)
        basename = datetime.now().strftime(f"%Y-%m-%d_%H%M%S_{file_type}")
        name = f"{basename}.json"
        i = 0
        while (self.queue_dir / name).exists():
            i += 1
            name = f"{basename}-{i}.json"
        path = self.queue_dir / name
        path.write_text(json.dumps({"payload": payload, "meta": meta}))
        return path
