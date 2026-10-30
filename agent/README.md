# tasks-agent

A scheduled AI agent for tasks-collector. It runs **batch jobs** (no realtime
streaming) that read from the backend's REST API and use **[DSPy](https://dspy.ai)
+ a local [ollama](https://ollama.com) model** to produce written artifacts.

Jobs **draft to a workdir first** — they write Markdown files for you to review and
do *not* post anything back to the backend yet. It is a sibling subproject to `cli/`
and reuses the same `~/.tasks-collector.ini` for the backend connection.

## Install

Requires [`uv`](https://docs.astral.sh/uv/) and a running `ollama`.

```bash
cd agent
uv sync                       # creates .venv from uv.lock (uv fetches Python 3.12)
```

## Configure

1. Backend connection is read from the same file the `cli/` uses,
   `~/.tasks-collector.ini` (section `[Tasks]` with `url`/`user`/`password`).
   Running from the repo root or `agent/` also picks up a local `tasks-collector.ini`.
2. Agent settings (workdir, ollama endpoint, per-task models, schedule):

```bash
cp tasks-agent.toml.example ~/.tasks-agent.toml   # or ~/.config/tasks-agent/config.toml
```

3. Pull the model referenced in `[models.review]`:

```bash
ollama pull llama3.1:8b
```

## Run

```bash
# Standalone job (put this directly in crontab):
uv run tasks-agent-review --window weekly

# Central runner:
uv run tasks-agent list                 # registered jobs + their schedule
uv run tasks-agent run review --window weekly
uv run tasks-agent tick                 # runs jobs whose cron is due (one crontab line)
```

Drafts land in `~/.tasks-agent/drafts/review/<date>-<window>-review.md`.

### Crontab

```cron
# Either drive everything with the central runner:
*/15 * * * *  cd /path/to/tasks-collector/agent && uv run tasks-agent tick

# ...or schedule an individual job directly:
0 7 * * 1     cd /path/to/tasks-collector/agent && uv run tasks-agent-review --window weekly
```

## Test

```bash
uv run pytest        # uses DSPy DummyLM + mocked HTTP, no ollama/backend needed
```

## Layout

```
src/tasks_agent/
  config/backend.py   reuse ~/.tasks-collector.ini for url/user/password
  config/agent.py     tasks-agent.toml: workdir, ollama, per-task models, schedule
  api.py              ApiClient (Basic auth, DRF pagination, error handling)
  models.py           pydantic response models
  llm.py              build a dspy.LM for a task from its ollama model config
  workdir.py          drafts / runs / state / dead-letter under the workdir
  programs/           DSPy Signatures + Modules (pure LLM logic, no HTTP)
  jobs/               job orchestration + registry + standalone entry points
  runner.py           central runner CLI (list / run / tick)
```

## Writing a new job

1. Add a DSPy program in `programs/` (a `Signature` + `Module`).
2. Add a `Job` subclass in `jobs/`, decorate it with `@register`, set `name`.
   `name` doubles as the `[models.<name>]` config key.
3. Optionally expose a standalone `main()` and wire it in `[project.scripts]`.
4. Add a `[schedule.<name>]` block to your config so `tasks-agent tick` runs it.
