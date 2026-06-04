# ENFP cognitive-function tracker design document

A new domain (`tasks.apps.enfp`) for tracking the four Jungian cognitive functions of
the ENFP type — **Ne, Fi, Te, Si** — and gamifying keeping them in balance. Inspired by
Heidi Priebe's *The Comprehensive ENFP Survival Guide*.

The purpose is twofold:

1. **Log** small concrete acts ("elements"), each tagged with the function it exercised,
   and see the four scores at a glance.
2. **Gamify** balance: configurable, multi-stage *Challenges* grant rewards as the four
   scores reach successive targets — reusing the existing `rewards` app for payout.

A deliberate longer-term goal: the free-text descriptions captured on every element form
the dataset for a future "propose me items to do" recommender. We can't build that later
without collecting the raw "what did I do, under which function" data now.

## Glossary

- **Function**: one of the four ENFP cognitive functions — `Ne` (Extraverted Intuition),
  `Fi` (Introverted Feeling), `Te` (Extraverted Thinking), `Si` (Introverted Sensing).
- **Element**: one logged act, tagged with a single Function, plus a free-text description
  and a timestamp. The unit that increments a score.
- **Score / tally**: the count of Elements per Function, *derived by aggregation* — never
  stored as a mutable counter.
- **Challenge**: a configurable progression with a `started_at` epoch and an ordered ladder
  of stages, each granting a reward. Different challenges can use any vector progression —
  e.g. `(4,3,2,1)` (function-stack order) or `(1,2,3,4)` (inferior-first growth).
- **Stage**: one rung of a Challenge — a cumulative target vector `(ne, fi, te, si)` and the
  reward granted when it is reached. One stage per challenge may be marked *completion*.

## Core design decisions

1. **Append-only log, not mutable counters.** Each Element is an immutable row; the four
   scores are computed with `Count(..., filter=Q(function=...))` at query time. This mirrors
   the existing `Habit` / `HabitTracked` pattern (`tasks/apps/tree/views_habit.py`). The
   payoff: nothing is "committed to" — the scores are a recomputable projection, so the
   taxonomy of "what counts as a Ne act" can evolve without migrations or lost history.

2. **Reuse the rewards app, don't rebuild it.** When a stage is satisfied, the evaluator
   creates a `rewards.Claim` pointing at the stage's `Reward`. This slots straight into the
   existing Claim → `claim_reward()` → `Claimed` flow (`tasks/apps/rewards/`). The only genuinely
   new logic is the trigger that watches the scores.

3. **Stage targets are cumulative-absolute.** A stage `(ne, fi, te, si)` is the *total* you
   need to have reached since the challenge's `started_at` — not an increment over the prior
   stage. You advance a stage when the tally meets-or-exceeds **every** component. This makes
   "progress toward the next stage" a trivial componentwise comparison and is append-only
   friendly. (Switching to per-stage increments would be a small, isolated change in the
   evaluator + progress computation.)

4. **Standalone app, off the unified timeline.** `enfp` uses its own plain models rather than
   subclassing `tree`'s polymorphic `Event`, so logging stays decoupled and easy to reshape;
   Elements do not appear in the observation/journal timeline.

### Worked example

The seed challenge (`tasks/fixtures/dev/enfp_starter.json`) demonstrates the ladder:

| stage | target (Ne, Fi, Te, Si) | reward | |
|-------|-------------------------|--------|---|
| 1 | (0, 0, 0, 1) | A small treat 🍵 | |
| 2 | (1, 1, 1, 1) | An hour for yourself ☕ | |
| 3 | (1, 2, 3, 4) | A proper reward 🎁 | completion |

Logging one `Si` element satisfies stage 1. Crossing `(1,1,1,1)` satisfies stage 2 — and if a
later batch reaches `(1,2,3,4)` it satisfies stage 3, which is *completion*: the challenge is
marked done and deactivated. All stages reached in a single evaluation pass are granted at once.

## Data model

`tasks/apps/enfp/models.py`:

- **`Element`** — `function` (TextChoices `Ne`/`Fi`/`Te`/`Si`), `description` (text),
  `published` (datetime). Indexed on `(function, published)`. Append-only.
- **`Challenge`** — `name`, `slug` (unique), `description`, `started_at`, `completed_at`,
  `active`.
- **`ChallengeStage`** — `challenge` (FK), `order`, `ne`/`fi`/`te`/`si` (target vector),
  `reward` (FK → `rewards.Reward`, `PROTECT`, string ref), `is_completion`.
- **`ChallengeStageCompleted`** — `stage` (FK), `completed_at`. Append-only grant record;
  its existence is the **idempotency guard** that prevents granting a stage twice.

## Evaluation / trigger

`tasks/apps/enfp/services/evaluation.py` — `evaluate_challenge(challenge)`:

1. Tally Elements per function where `published >= challenge.started_at`.
2. Find stages with no `ChallengeStageCompleted` whose target is `<=` the tally componentwise.
3. For each: create a `ChallengeStageCompleted` **and** a `Claim`
   (`rewarded_for="<challenge name>: stage <order>"`).
4. If a satisfied stage `is_completion`, set `completed_at` and `active = False`.
5. Idempotent and wrapped in a transaction.

**Trigger placement:** `ElementSerializer.save()` is `@transaction.atomic` and, after writing
the element, calls `evaluate_challenge` for each active challenge — directly parallel to
`ObservationSerializer.save()` emitting change events (`tasks/apps/tree/serializers.py`).
Only Element *creation* fires it; the API exposes no update/destroy for Elements.

## API

Mounted under `/enfp/` (`tasks/apps/enfp/urls.py`); DRF defaults enforce `IsAuthenticated`.

- `GET /enfp/` — the dashboard page.
- `GET /enfp/summary/` — lifetime totals across all Elements + each active challenge with its
  current tally, per-stage `reached`/`claimed` state, and the next unmet stage. Feeds the page.
- `GET|POST /enfp/api/elements/` — append-only list/create (create triggers evaluation).
- `GET /enfp/api/challenges/` — read-only, with computed progress.

## Frontend

A standalone Vue page (its own rsbuild entry `enfp_mount`, parallel to `hello_world_mount`):

- `tasks/assets/components/enfp_mount.js`, `EnfpDashboard.vue`,
  `tasks/templates/enfp/dashboard.html`.
- Four function cards showing **both** the lifetime total and a progress bar toward the next
  stage; the challenge stage ladder (claimed / ready badges); and a "log an element" form
  (function picker + description → `POST /enfp/api/elements/`, then refetch).
- Uses the shared CSRF `apiRequest` fetch pattern; entry registered in both the `source.entry`
  map and the `entryPoints` array in `rsbuild.config.ts`.

## Step-by-step guide

- [x] App scaffolding (`tasks.apps.enfp`), registered in `INSTALLED_APPS` and root `urls.py`
- [x] Models: `Element`, `Challenge`, `ChallengeStage`, `ChallengeStageCompleted` + migration
- [x] Admin: `Challenge` with `ChallengeStage` inline; `Element` with function filter
- [x] `evaluate_challenge` service with idempotent, cumulative-absolute stage logic
- [x] Trigger evaluation from `ElementSerializer.save()` in a transaction
- [x] REST API: Element (append-only), Challenge (read-only), `summary` endpoint
- [x] Standalone Vue dashboard page + new rsbuild entry
- [x] Nav link under Habits
- [x] Unit tests for `evaluate_challenge` (grant, no-double-grant, completion, inactive)
- [x] Seed fixture `tasks/fixtures/dev/enfp_starter.json`

## Future directions

- **Recommender**: once enough described Elements accumulate, propose acts per function based
  on past entries — the reason descriptions are captured from day one.
- **Multiple concurrent challenges**: the function-card progress bars currently track the first
  active challenge; a selector or aggregate view could be added.
- **Function metadata**: surface role (dominant/auxiliary/tertiary/inferior) and per-function
  guidance on the page.
