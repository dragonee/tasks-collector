# 0002 — Android companion app for Health Connect metrics

- **Status:** Accepted
- **Date:** 2026-05-17
- **Supersedes:** ADR 0001's "alternative" paragraph (referenced below)

## Context

We still want daily phone-collected health metrics — steps, distance, active minutes — to land on the Daily thread as `HabitTracked` events alongside the rest of the event stream. ADR 0001 closed the door on the cloud Google Health API because it currently requires a Fitbit/Google Health unified account, which we don't have. The ADR explicitly named the remaining option:

> build our own Android application that reads from Health Connect directly on the device and pushes to our backend ourselves.

That's what this ADR commits to. The work landed on `main` as PR #203.

## Decision

Ship a Kotlin Android companion app (under `android/` in this repo) that:

1. Reads daily aggregates from Health Connect on-device:
   - `StepsRecord` total → steps
   - `DistanceRecord` total → metres
   - `aggregateGroupByDuration` over `StepsRecord` in 1-minute buckets, counting minutes whose step count meets a low-intensity threshold (currently 30 spm — below brisk walking, above ambient noise), unioned with explicit `ExerciseSessionRecord` minutes → active minutes. Earlier approaches over- or under-counted: summing exercise-session durations missed movement without a logged workout, while marking every minute touched by a non-empty step record over-counted hours-long step records that span mostly-sedentary time.
   - `TotalCaloriesBurnedRecord` energy total, falling back to `ActiveCaloriesBurnedRecord` when total isn't populated → kcal
2. POSTs them to a new backend endpoint, `POST /api/v1/habit/track/`, as a JSON body `{ keyword, date, note }`.
3. Runs on `WorkManager` so the sync happens in the background without a user-visible Service:
   - An hourly `PeriodicWorkRequest` for best-effort frequent updates.
   - A 24-hour `PeriodicWorkRequest` as an explicit "at-least-once-daily" backstop.
   - A one-time `Sync now` action surfaced in the Settings screen.

Backend specifics that this ADR is committing to:

- **Auth:** DRF `TokenAuthentication` (additive — Session and Basic remain for the existing browser UI). Tokens are minted with a one-shot `python manage.py issue_mobile_token <username>` and pasted into the app.
- **Habit resolution by keyword text, not slug.** The endpoint looks up `HabitKeyword.keyword = "health-metrics"` and dereferences `.habit`. Renaming the habit or its slug doesn't break the mobile contract; renaming the keyword would, which is the right level of fragility.
- **Idempotency on `(habit, day)`.** Repeat POSTs for the same day `UPDATE` the single existing `HabitTracked` row's `note` rather than inserting a duplicate. WorkManager retries and overlapping hourly / daily workers therefore can't pollute history. This is what lets us cheaply re-sync the trailing 7-day window every run — wearables sometimes back-fill earlier days after re-connecting, so older `HabitTracked` rows must remain mutable in practice even though the rest of the event store is immutable.
- **One `HabitTracked` per day, metrics packed into `note`** (e.g. `steps=8520 distance=6.2km active=42min`). No model migration; the existing `HabitTracked.note` field is sufficient, and the dedicated `health-metrics` habit prevents the packed-metric row from clobbering manually-journalled `#health` entries.
- **Heart Points deliberately not computed.** Health Connect doesn't expose them; replicating Google Fit's heart-rate-zone formula would require an extra HC permission and bespoke per-user tuning. Out of scope for v1; revisit if/when the data becomes useful enough to justify the complexity.

## Consequences

Good:

- No dependency on Fitbit accounts, the Google Health API, or any external SaaS — the only network hop is phone → our backend.
- The mobile wire format (`keyword`) decouples the API from internal slug churn.
- Idempotency means the app can be aggressive about retries without polluting the event log.
- The Android codebase lives alongside the backend so the API contract is one repo away. It is excluded from the rsync deploy, so the production Django host doesn't pick up Kotlin source.

Bad / accepted trade-offs:

- We now own a Kotlin/Gradle codebase. Future Android Gradle Plugin / Kotlin / Health Connect SDK upgrades are on us. The app is small enough that this should stay cheap.
- Sideloaded only; no Play Store release. Token rotation, app installs, and HC permission grants are manual ops on the device.
- Health Connect requires explicit `READ_HEALTH_DATA_IN_BACKGROUND` on top of the per-record-type read permissions. If the user only grants foreground access, the WorkManager workers fail (with a clear error surfaced in Settings).
- Releases must use HTTPS — debug builds keep a `network_security_config.xml` that permits cleartext to the LAN dev backend; release builds inherit Android's HTTPS-only default.
- Heart Points remain a known gap. If a strong need surfaces later, the implementation options were enumerated during planning (HR-zone classification, step cadence, or `ExerciseSession` intensity proxy) — pick one and ship a follow-up ADR.

## Out of scope, recorded for posterity

- Multi-user / multi-server in the app.
- An in-app history view (the backend habit UI remains the source of truth).
- Real-time push from device → backend; the periodic + daily WorkManager cadence is sufficient.
