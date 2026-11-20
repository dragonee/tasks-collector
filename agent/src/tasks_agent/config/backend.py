"""Backend connection config.

Reuses the same ``~/.tasks-collector.ini`` ``[Tasks]`` section the ``cli/``
subproject uses. Deliberately re-implemented (rather than importing
``tasks_collector_tools``) so the two packages stay decoupled and the agent does
not drag in the cli's pydantic v1 dependency.
"""

from configparser import ConfigParser
from pathlib import Path


class BackendConfig:
    url: str
    user: str
    password: str

    def __init__(self):
        reader = ConfigParser()
        reader.read([str(p) for p in self.paths()])

        try:
            self.url = reader["Tasks"]["url"]
            self.user = reader["Tasks"]["user"]
            self.password = reader["Tasks"]["password"]
        except KeyError as e:
            raise KeyError(
                "Create ~/.tasks-collector.ini with a [Tasks] section "
                "containing url/user/password"
            ) from e

    def paths(self):
        return [
            Path("/etc/tasks-collector.ini"),
            Path.home() / ".tasks-collector.ini",
            # Used for development from within the tasks-collector repository.
            Path() / "tasks-collector.ini",
        ]
