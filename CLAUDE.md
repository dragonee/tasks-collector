# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Frontend Development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run dev` - Start rsbuild in watch mode for development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run build` - Build assets for development
- `docker compose -f docker/development/docker-compose.yml exec tasks-frontend npm run build-dist` - Build production-ready assets

### Backend Development
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py runserver` - Start Django development server
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py migrate` - Run database migrations
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py createsuperuser` - Create admin user
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py test` - Run Django tests
- `docker compose -f docker/development/docker-compose.yml exec tasks-backend python manage.py loaddata tasks/fixtures/dev/initial_state.json` - Load development fixtures

### Docker Development
- `docker-compose up` (from docker/development/) - Start full development environment
- `docker-compose exec tasks-backend bash` - Access running container

### Several environments at once
- `/devenv` (`.claude/skills/devenv`) gives a piece of work a worktree under `.claude/worktrees/` with a stack, database and ports of its own, and moves the session into it with EnterWorktree. `/devenv resume` goes back to it after /clear.
- It runs `docker/development/devenv.py` (`start | list | status | resume | down`). The worktree's `docker/development/.env` sets `TASKS_PORT_PREFIX`: prefix 4 is the project `tasks-4` with the app on localhost:4000. Unset (the main checkout), ports stay 8000, 9000, 9001 and 7079.
- Inside an environment the commands above reach its stack unchanged. A new database is seeded by `manage.py seed_dev` (django / django, and alice / django who is shared a board and an observation).

## Architecture Overview

### Core Structure
This is a Django-based personal productivity application with a Vue.js frontend. The system uses an **event-driven architecture** where all user activities are tracked as events with stream IDs.

### Django Apps

1. **Common App** (`tasks.apps.common`)
   - Provides shared functionality and custom User model
   - Contains template tags and management commands

2. **Tree App** (`tasks.apps.tree`) - **Main Application**
   - Core productivity system with comprehensive life tracking
   - **Thread-based organization**: Daily, Weekly, Monthly threads
   - **Event sourcing**: All activities tracked as polymorphic events
   - Key models: Thread, Event, Board, Task, Habit, Observation, Plan, Reflection, JournalAdded, Breakthrough

### Multi-user and sharing
- Every user owns their threads (Daily, Weekly and big-picture are provisioned and can't be deleted), habits, breakthroughs and statistics.
- Every stream is an `EventStream` row with an access list (`EventStreamAccess`: one owner, optional viewers); events belong to a home stream and may be members of others (`EventStreamEntry`, e.g. a trip). `Event.created_by` is provenance only.
- Query with `owned_by(user)` for personal pages and writes, `visible_to(user)` for what can be read (own + shared). Trips, observations and projected outcomes can be shared view-only (a shared complex observation shares what's attached to it); a board (not Daily, Weekly or big-picture) can be shared to edit, and board code uses `Board.objects.editable_by(user)` / `Thread.objects.board_editable_by(user)` (`services/streams.py`).
- `tests/test_route_isolation.py` walks every route as a second user, a stranger and a viewer of shared items; a new route with URL parameters fails it until `targets` names the objects to call it with.
- Design, history and open items: `docs/design/multiuser-event-streams.md`.
- API tokens are `common.ApiToken` rows, one per device or script, revoked from the account settings. The Android app gets its own by logging in through the browser (`oauth/authorize/`, `oauth/token/` in `apps/common/oauth.py`); `manage.py issue_mobile_token` issues one for a script. In tests use `factories.make_token(user)`.
- The phone apps are `android/` (Kotlin) and `ios/` (Swift, the same app reimplemented; `ios/README.md` says what stands in for what). They share the `api/v1/android/` endpoints; a change to one app's behaviour usually belongs in the other too.

### Key Architectural Patterns

- **Event Sourcing**: All changes tracked as events with stream IDs
- **Polymorphic Events**: Different event types share common Event base class
- **Thread-Based Organization**: Activities organized into Daily/Weekly/Monthly threads
- **API-First Design**: Full REST API coverage alongside traditional Django views

### Language: unscheduled tasks and tasks
- A board is a tree of items. A board item is an **unscheduled task**: something to do that isn't planned yet. Code that creates, finds or appends board items says `unscheduled_task` (`board_operations.create_unscheduled_task`, `add_unscheduled_task`, `services/today/board_tree.py`). Don't call a board item a task.
- A **task** is something planned (for a day, a week, a month): a `Task` row, made when an item is planned or a line is written into a plan. It stays once done, and done is the task's, whatever plan it is read from.
- A plan is its `PlanLine` rows and a reflection its `ReflectionLine` rows; `plan.focus` and `reflection.good|better|best` are those lines as text (read-only properties). Get a document with `services.tasks.documents.plan_for` / `reflection_for`, write text into one with `documents.write`, and change tasks through `services/tasks/operations.py`.
- A task lives in the stream of a board, so access to the board is access to the task: `Task.objects.visible_to(user)` / `editable_by(user)`.
- Design and what is left: `docs/design/tasks.md`.

### Frontend Architecture
- **Vue 3** with Pinia for state management (the board page; the other pages are server-rendered)
- **Rsbuild** for asset bundling (faster Rspack-based alternative to Webpack)
- **Bootstrap 4** for UI components

### Database
- **PostgreSQL** for production
- Uses Django migrations for schema management
- Event streams for tracking all user activities

### Development Environment
- Supports both traditional Python/Django setup and Docker development
- Auto-reloading for both backend and frontend changes
- Separate configurations for local/development/production environments

## Important Notes

- Settings are environment-specific (local.py, dist.py)
- Outside Docker, local database and email configurations can use separate .py files (db.py, email.py)
- Production (dist.py) reads its configuration from environment variables via django-environ; see `docker/production/.env.example`
- Production runs as a Docker image (`docker/production/`) pushed to GHCR and deployed by `.github/workflows/deploy.yml`
- All user activities are tracked through the event system
- The system is designed around personal productivity and development workflows
- Uses Django Polymorphic for event inheritance
