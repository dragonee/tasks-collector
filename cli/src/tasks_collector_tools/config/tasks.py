import os
from configparser import ConfigParser
from pathlib import Path

from requests.auth import AuthBase, HTTPBasicAuth

CONFIG_ENV = "TC_CONFIG"


class TokenAuth(AuthBase):
    """``Authorization: Token <key>``: a token issued for a script (Settings,
    Devices on the server)."""

    def __init__(self, key):
        self.key = key

    def __call__(self, request):
        request.headers["Authorization"] = f"Token {self.key}"
        return request


class TasksConfigFile:
    url = None
    user = None
    password = None
    # Sent in place of user and password when set.
    token = None

    observation_list_count: int = 10
    observation_list_characters: int = 70

    ignore_habits: list[str] = []
    current_thread: str = None

    def __init__(self):
        self.reader = ConfigParser()

        explicit = os.environ.get(CONFIG_ENV)
        # The files read, in the order they were: a later one overrides.
        self.files = self.reader.read(self.paths())

        if explicit and not self.files:
            raise KeyError(f"{CONFIG_ENV} names {explicit}, which can't be read")

        try:
            self.url = self.reader["Tasks"]["url"]
            self.token = self.reader.get("Tasks", "token", fallback="") or None
            if self.token is None:
                self.user = self.reader["Tasks"]["user"]
                self.password = self.reader["Tasks"]["password"]
            else:
                self.user = self.reader.get("Tasks", "user", fallback=None)

            self.observation_list_count = self.reader.getint(
                "Display",
                "observation_list_count",
                fallback=self.observation_list_count,
            )
            self.observation_list_characters = self.reader.getint(
                "Display",
                "observation_list_characters",
                fallback=self.observation_list_characters,
            )

            self.ignore_habits = self.reader.get(
                "Tasks", "ignore_habits", fallback=""
            ).split(",")

            # Initialize current thread to Daily
            self.current_thread = "Daily"

        except KeyError:
            raise KeyError(
                "Create ~/.tasks-collector.ini file with section [Tasks] containing"
                " url and user/password, or url and token"
            )

    @property
    def auth(self):
        """What requests to the server are sent with: the token, or the user
        and password."""
        if self.token:
            return TokenAuth(self.token)
        return HTTPBasicAuth(self.user, self.password)

    def paths(self):
        """The files read: the one $TC_CONFIG names, or else these, each
        overriding what the ones before it say."""
        explicit = os.environ.get(CONFIG_ENV)
        if explicit:
            return [Path(explicit).expanduser()]

        return [
            "/etc/tasks-collector.ini",
            Path.home() / ".tasks-collector.ini",
            # Used for development by the tasks-collector repository
            Path() / "tasks-collector.ini",
        ]
