"""Reading for a script or an assistant: a span of days in one request per
year, the dumps as JSON, and which server tc talks to as whom."""

import json
from datetime import date
from types import SimpleNamespace

import pytest
from tasks_collector_tools import cli, days, eventdump, reflectiondump, whoami
from tasks_collector_tools.config.tasks import TasksConfigFile, TokenAuth

URL = "http://tasks"


def response(status=200, body=None):
    return SimpleNamespace(
        ok=status < 400, status_code=status, json=lambda: body, text=str(body)
    )


def day(date, events=(), plan=None, reflection=None):
    return {
        "date": date,
        "events": list(events),
        "plan": plan,
        "reflection": reflection,
    }


JOURNAL = {
    "id": 5,
    "published": "2026-11-09T20:00:00Z",
    "resourcetype": "JournalAdded",
    "comment": "A long day",
    "tags": ["work"],
}
HABIT = {
    "id": 6,
    "published": "2026-11-09T00:00:00+00:00",
    "resourcetype": "HabitTracked",
    "note": "#jestem said what I want",
    "occured": True,
    "habit": {
        "id": 1,
        "name": "Jestem",
        "description": None,
        "slug": "jestem",
        "keywords": ["jestem"],
    },
}
REFLECTION = {
    "id": 1,
    "good": "Called the client ^t91bd0a44\nA walk",
    "better": "",
    "best": "Finished it",
    "pub_date": "2026-11-09",
}
PLAN = {"id": 2, "focus": "Call the client ^t91bd0a44\nWrite", "pub_date": "2026-11-09"}


@pytest.fixture
def server(monkeypatch):
    """The requests made, and the answers to them by path."""
    asked = SimpleNamespace(gets=[], answers={})

    def get(url, params=None, auth=None, **kwargs):
        path = url.removeprefix(URL)
        asked.gets.append((path, params))
        answer = asked.answers.get(path)
        return answer(params) if callable(answer) else answer

    monkeypatch.setattr(days.requests, "get", get)
    monkeypatch.setattr(whoami.requests, "get", get)
    config = SimpleNamespace(url=URL, auth=None, token=None, files=["~/.ini"])
    for module in (reflectiondump, eventdump, whoami):
        monkeypatch.setattr(module, "TasksConfigFile", lambda: config)
    return asked


def test_a_span_is_asked_a_year_at_a_time(server):
    server.answers["/api/events/"] = lambda params: response(body={"days": []})

    days.get_days(
        SimpleNamespace(url=URL, auth=None),
        date(2025, 1, 1),
        date(2026, 6, 30),
        thread="Weekly",
        anchors=True,
    )

    assert server.gets == [
        (
            "/api/events/",
            {
                "from": "2025-01-01",
                "to": "2026-01-01",
                "thread": "Weekly",
                "anchors": "1",
            },
        ),
        (
            "/api/events/",
            {
                "from": "2026-01-02",
                "to": "2026-06-30",
                "thread": "Weekly",
                "anchors": "1",
            },
        ),
    ]


def test_anchors_are_asked_for_only_where_text_is_sent_back(server):
    server.answers["/api/events/"] = lambda params: response(body={"days": []})

    days.get_days(
        SimpleNamespace(url=URL, auth=None), date(2026, 11, 9), date(2026, 11, 9)
    )

    assert server.gets == [
        ("/api/events/", {"from": "2026-11-09", "to": "2026-11-09", "thread": "Daily"})
    ]


def test_an_older_server_is_asked_a_day_at_a_time(server):
    server.answers["/api/events/"] = response(404, {"detail": "Not found."})
    server.answers["/api/events/daily/"] = lambda params: response(
        body=day(params["date"])
    )

    fetched = days.get_days(
        SimpleNamespace(url=URL, auth=None), date(2026, 11, 9), date(2026, 11, 11)
    )

    assert [d["date"] for d in fetched] == ["2026-11-09", "2026-11-10", "2026-11-11"]
    assert [path for path, _ in server.gets] == ["/api/events/"] + [
        "/api/events/daily/"
    ] * 3


def test_the_reflection_dump_as_json(server, capsys):
    server.answers["/api/events/"] = lambda params: response(
        body={
            "days": [
                day("2026-11-09", [JOURNAL, HABIT], PLAN, REFLECTION),
                day("2026-11-10"),
            ]
        }
    )

    reflectiondump.main(
        ["-d", "2026-11-09", "-D", "2026-11-15", "--json"], "tc reflect dump"
    )

    out = json.loads(capsys.readouterr().out)
    assert (out["from"], out["to"], out["thread"]) == (
        "2026-11-09",
        "2026-11-15",
        "Daily",
    )
    [monday] = out["days"]
    assert monday["reflection"] == {
        "good": [
            {"text": "Called the client", "anchor": "91bd0a44"},
            {"text": "A walk", "anchor": None},
        ],
        "better": [],
        "best": [{"text": "Finished it", "anchor": None}],
    }
    assert monday["plan"] == [
        {"text": "Call the client", "anchor": "91bd0a44"},
        {"text": "Write", "anchor": None},
    ]
    assert monday["habits"] == [
        {
            "habit": "Jestem",
            "keywords": ["jestem"],
            "occured": True,
            "note": "#jestem said what I want",
            "published": "2026-11-09T00:00:00+00:00",
        }
    ]
    assert monday["journals"] == [
        {
            "published": "2026-11-09T20:00:00+00:00",
            "comment": "A long day",
            "tags": ["work"],
        }
    ]


def test_the_json_leaves_out_what_the_options_leave_out(server, capsys):
    server.answers["/api/events/"] = lambda params: response(
        body={"days": [day("2026-11-09", [JOURNAL, HABIT], PLAN, REFLECTION)]}
    )

    reflectiondump.main(
        ["-d", "2026-11-09", "--json", "--skip-journals", "--no-habits"],
        "tc reflect dump",
    )

    [monday] = json.loads(capsys.readouterr().out)["days"]
    assert set(monday) == {"date", "reflection", "plan", "observations"}


def test_a_line_with_a_box_in_front(server):
    assert reflectiondump.lines_of("- [x] Done it ^t91bd0a44\n\n- [ ] Not yet") == [
        {"text": "Done it", "anchor": "91bd0a44"},
        {"text": "Not yet", "anchor": None},
    ]


def test_the_events_dump_as_json(server, capsys):
    server.answers["/api/events/"] = lambda params: response(
        body={"days": [day("2026-11-09", [JOURNAL], PLAN, REFLECTION)]}
    )

    eventdump.main(
        ["-d", "2026-11-09", "--json", "--no-plans", "-T", "Weekly"], "tc events dump"
    )

    out = json.loads(capsys.readouterr().out)
    assert out["thread"] == "Weekly"
    assert out["days"] == [
        {"date": "2026-11-09", "events": [JOURNAL], "reflection": REFLECTION}
    ]


def test_a_token_in_place_of_a_password(tmp_path, monkeypatch):
    ini = tmp_path / "claude.ini"
    ini.write_text("[Tasks]\nurl = http://tasks\ntoken = abc\n")
    monkeypatch.setenv("TC_CONFIG", str(ini))

    config = TasksConfigFile()

    assert config.files == [str(ini)]
    assert isinstance(config.auth, TokenAuth)
    request = SimpleNamespace(headers={})
    config.auth(request)
    assert request.headers == {"Authorization": "Token abc"}


def test_tc_config_names_a_file_that_isnt_there(tmp_path, monkeypatch):
    monkeypatch.setenv("TC_CONFIG", str(tmp_path / "nothing.ini"))

    with pytest.raises(KeyError, match="can't be read"):
        TasksConfigFile()


def test_config_on_the_command_line(monkeypatch):
    monkeypatch.delenv("TC_CONFIG", raising=False)

    assert cli.take_config(["--config", "a.ini", "journal", "-n"]) == ["journal", "-n"]
    assert cli.take_config(["--config=b.ini", "whoami"]) == ["whoami"]
    assert cli.take_config(["journal"]) == ["journal"]
    assert cli.resolve(["whoami"]).target == "whoami:main"


def test_today_is_the_reflection_dump_of_today(server, capsys):
    server.answers["/api/events/"] = lambda params: response(body={"days": []})

    cli.main(["today"])

    today = date.today().isoformat()
    assert server.gets == [
        ("/api/events/", {"from": today, "to": today, "thread": "Daily"})
    ]
    assert capsys.readouterr().out.strip().startswith("# Reflection")


def test_whoami(server, capsys):
    server.answers["/api/v1/me/"] = response(
        body={"username": "alice", "token": {"name": "Claude", "read_only": True}}
    )

    whoami.main([], "tc whoami")

    assert capsys.readouterr().out.splitlines() == [
        "config     ~/.ini",
        "server     http://tasks",
        "logged in  alice, with the token 'Claude', which can only read",
    ]


def test_whoami_when_the_server_takes_tc_for_nobody(server, capsys):
    server.answers["/api/v1/me/"] = response(401, {"detail": "Invalid token."})

    with pytest.raises(SystemExit) as exit:
        whoami.main(["--json"], "tc whoami")

    assert exit.value.code == 1
    assert json.loads(capsys.readouterr().out)["server"] == {"error": "HTTP 401"}
