from configparser import ConfigParser
from pathlib import Path


class TasksConfigFile:
    url = None
    user = None
    password = None

    observation_list_count: int = 10
    observation_list_characters: int = 70

    ignore_habits: list[str] = []
    current_thread: str = None

    def __init__(self):
        self.reader = ConfigParser()

        self.reader.read(self.paths())

        try:
            self.url = self.reader["Tasks"]["url"]
            self.user = self.reader["Tasks"]["user"]
            self.password = self.reader["Tasks"]["password"]

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
                "Create ~/.tasks-collector.ini file with section [Tasks] containing url/user/password"
            )

    def paths(self):
        return [
            "/etc/tasks-collector.ini",
            Path.home() / ".tasks-collector.ini",
            # Used for development by the tasks-collector repository
            Path() / "tasks-collector.ini",
        ]
