"""Sending without an editor (a script, an assistant): --no-edit, --dry-run
and `tc habits --track`, and the key each send carries so that a retry adds
nothing twice."""

import io
import json
from types import SimpleNamespace

import pytest
from requests.exceptions import ConnectionError
from tasks_collector_tools import habits, journal, observation, update
from tasks_collector_tools.plans import Plan

URL = "http://tasks"


def plans():
    return {
        "daily": Plan("2026-11-11", "Daily", []),
        "weekly": Plan("2026-11-15", "Weekly", []),
        "monthly": Plan("2026-11-30", "big-picture", []),
    }


def response(status=201, body=None):
    return SimpleNamespace(
        ok=status < 400, status_code=status, json=lambda: body or {}, text=""
    )


@pytest.fixture
def server(monkeypatch):
    """What is posted to the server, and what it answers."""
    sent = SimpleNamespace(posts=[], answers={}, queue_sent=0)

    def post(url, json=None, auth=None, **kwargs):
        sent.posts.append((url.removeprefix(URL), json))
        answer = sent.answers.get(url.removeprefix(URL))
        if isinstance(answer, Exception):
            raise answer
        return answer or response(body=json)

    def retry_queue(metadata):
        sent.queue_sent += 1

    config = SimpleNamespace(
        url=URL, auth=None, observation_list_count=10, observation_list_characters=70
    )
    for module in (journal, observation, update, habits):
        monkeypatch.setattr(module.requests, "post", post)
        monkeypatch.setattr(module, "TasksConfigFile", lambda: config)
    for module in (journal, observation, update):
        monkeypatch.setattr(module, "retry_failed_requests", retry_queue)
    monkeypatch.setattr(journal, "get_plans_for_today_sync", lambda config: plans())

    return sent


def stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def journal_answer(payload):
    return response(
        body={
            "id": 1,
            "comment": payload["comment"],
            "published": payload["published"],
            "thread": payload["thread"],
            "tags": [],
        }
    )


ENTRY = "Makimo\n\n- [x] Called the client ^t91bd0a44\n"


def test_no_edit_sends_the_file_as_the_comment(server, monkeypatch, tmp_path):
    entry = tmp_path / "entry.md"
    entry.write_text(ENTRY)
    server.answers["/journal/"] = journal_answer(
        {"comment": ENTRY, "published": "x", "thread": "Weekly"}
    )

    journal.main(
        [
            "--no-edit",
            "-t",
            "Weekly",
            "-d",
            "2026-11-15T23:59:59+00:00",
            "-f",
            str(entry),
        ],
        "tc journal",
    )

    [(url, payload)] = server.posts
    assert url == "/journal/"
    assert payload["thread"] == "Weekly"
    assert payload["published"] == "2026-11-15 23:59:59+00:00"
    assert payload["comment"] == ENTRY.strip().replace("\n", "\r\n")
    assert len(payload["idempotency_key"]) == 32
    assert server.queue_sent == 1


def test_no_edit_reads_standard_input(server, monkeypatch):
    stdin(monkeypatch, "- [x] From a pipe\n")

    journal.main(["--no-edit", "-f", "-"], "tc journal")

    assert server.posts[0][1]["comment"] == "- [x] From a pipe"


def test_no_edit_needs_a_file(server):
    with pytest.raises(SystemExit) as exit:
        journal.main(["--no-edit"], "tc journal")

    assert exit.value.code == 2
    assert server.posts == []


def test_an_empty_comment_is_an_error_without_an_editor(server, monkeypatch):
    stdin(monkeypatch, "\n\n")

    with pytest.raises(SystemExit) as exit:
        journal.main(["--no-edit", "-f", "-"], "tc journal")

    assert exit.value.code == 1
    assert server.posts == []


def test_a_refused_entry_is_an_error_without_an_editor(server, monkeypatch):
    stdin(monkeypatch, "- [x] something\n")
    server.answers["/journal/"] = response(403, {"detail": "This token can only read."})

    with pytest.raises(SystemExit) as exit:
        journal.main(["--no-edit", "-f", "-"], "tc journal")

    assert exit.value.code == 1


PREVIEW = {
    "thread": "Weekly",
    "published": "2026-11-15T23:59:59Z",
    "comment": "Makimo\n\n- [x] Called the client",
    "reflection": {
        "date": "2026-11-15",
        "good": [{"text": "Called the client", "anchor": "91bd0a44"}],
        "better": [],
        "best": [],
    },
    "habits": [{"habit": "Breakthrough", "occured": True, "note": "a talk"}],
    "tasks_completed": [{"text": "Call the client", "anchor": "91bd0a44"}],
    "unscheduled_tasks_ticked": [],
}


def test_a_dry_run_asks_the_server_and_sends_nothing(server, monkeypatch, capsys):
    stdin(monkeypatch, ENTRY)
    server.answers["/api/v1/journal/preview/"] = response(200, PREVIEW)

    journal.main(["--no-edit", "--dry-run", "-t", "Weekly", "-f", "-"], "tc journal")

    [(url, payload)] = server.posts
    assert url == "/api/v1/journal/preview/"
    assert "idempotency_key" not in payload
    # Not even what waits in the queue.
    assert server.queue_sent == 0

    out = capsys.readouterr().out
    assert "Reflection of 2026-11-15:" in out
    assert "    - Called the client ^t91bd0a44" in out
    assert "  - Breakthrough: a talk" in out
    assert "Tasks completed:" in out
    assert out.strip().endswith("Nothing was sent.")


def test_a_dry_run_as_json(server, monkeypatch, capsys):
    stdin(monkeypatch, ENTRY)
    server.answers["/api/v1/journal/preview/"] = response(200, PREVIEW)

    journal.main(["--no-edit", "--dry-run", "--json", "-f", "-"], "tc journal")

    assert json.loads(capsys.readouterr().out) == PREVIEW


def test_a_dry_run_on_an_older_server(server, monkeypatch):
    stdin(monkeypatch, ENTRY)
    server.answers["/api/v1/journal/preview/"] = response(404)

    with pytest.raises(SystemExit) as exit:
        journal.main(["--no-edit", "--dry-run", "-f", "-"], "tc journal")

    assert exit.value.code == 2


def test_an_observation_from_a_file(server, monkeypatch):
    stdin(monkeypatch, "# Situation\n\nIt broke\n\n# Approach\n\nCheck first\n")
    server.answers["/observation-api/"] = response(
        body={
            "id": 7,
            "pub_date": "2026-11-11",
            "thread": "Daily",
            "type": "observation",
            "situation": "It broke",
            "interpretation": "",
            "approach": "Check first",
        }
    )

    observation.main(
        ["--no-edit", "--thread", "Daily", "--date", "2026-11-11", "-f", "-"],
        "tc observation",
    )

    [(url, payload)] = server.posts
    assert url == "/observation-api/"
    assert payload["pub_date"] == "2026-11-11"
    assert payload["thread"] == "Daily"
    assert payload["type"] == "observation"
    assert payload["situation"] == "It broke"
    assert payload["approach"] == "Check first"
    assert payload["idempotency_key"]


def test_an_update_from_a_file(server, monkeypatch, tmp_path):
    monkeypatch.setattr(update, "OBSERVATION_FILE_PATH", str(tmp_path / "id"))
    stdin(monkeypatch, "Still broken\n")
    server.answers["/updates/"] = response(
        body={"id": 1, "observation": 7, "comment": "Still broken", "published": "x"}
    )

    update.main(["7", "--no-edit", "-f", "-"], "tc update")

    [(url, payload)] = server.posts
    assert (url, payload["observation"], payload["comment"]) == (
        "/updates/",
        "7",
        "Still broken",
    )
    assert payload["idempotency_key"]


def test_habits_tracked_without_asking(server):
    habits.main(
        ["--track", "#workout 100 push-ups", "-t", "!alkohol", "-d", "2026-11-11"],
        "tc habits",
    )

    assert [payload["text"] for _, payload in server.posts] == [
        "#workout 100 push-ups",
        "!alkohol",
    ]
    keys = {payload["idempotency_key"] for _, payload in server.posts}
    assert len(keys) == 2


def test_a_habit_sent_again_after_a_lost_connection_carries_the_same_key(
    server, monkeypatch
):
    answers = iter([ConnectionError("lost"), response(200, {"ok": True})])
    posts = []

    def post(url, json=None, auth=None, **kwargs):
        posts.append(json)
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(habits.requests, "post", post)

    habits.main(["--track", "#workout"], "tc habits")

    assert len(posts) == 2
    assert posts[0]["idempotency_key"] == posts[1]["idempotency_key"]


def test_a_refused_habit_is_an_error(server):
    server.answers["/habit/track/"] = response(400, {"text": ["No habits found"]})

    with pytest.raises(SystemExit) as exit:
        habits.main(["--track", "#nothing"], "tc habits")

    assert exit.value.code == 1


def test_the_habits_as_data():
    listed = [
        {
            "id": 1,
            "name": "Health",
            "slug": "health",
            "description": None,
            "keywords": ["health-metrics", "health"],
            "today_tracked": 0,
        }
    ]

    assert habits.habits_as_data(listed) == [
        {
            "name": "Health",
            "slug": "health",
            "description": None,
            "keywords": ["health", "health-metrics"],
        }
    ]
