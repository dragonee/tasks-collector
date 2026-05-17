# Tasks Health — Android companion app

Reads daily steps, distance, and active minutes from Android Health Connect on
the phone and pushes them to the `tasks-collector` backend as `HabitTracked`
events on a single `#health-metrics` habit.

This is the implementation of the alternative named in
`docs/adr/0001-defer-google-health-api-integration.md` — phone-collected
metrics, no Fitbit linkage, no cloud Google Health API.

## What the app pushes

One `HabitTracked` event per day on the `health-metrics` habit, with the
metrics packed into the event `note`, e.g.

```
steps=8520 distance=6.2km active=42min
```

The endpoint is idempotent on `(habit, date)`: re-syncing the same day updates
the row rather than inserting a duplicate.

Heart Points are **not** computed in this version (Health Connect doesn't
expose them; see the ADR).

## One-time backend setup

1. Apply migrations to create the DRF authtoken table:

   ```bash
   docker compose -f docker/development/docker-compose.yml \
     exec tasks-backend python manage.py migrate
   ```

2. In the Django admin (`/admin/`) create:

   - A `Habit` with a `slug` and `name` of your choice.
   - A `HabitKeyword` with `keyword = health-metrics` pointing at that habit.
     The API looks the habit up by keyword text, so the slug can be anything.

3. Mint a token for the user the phone will authenticate as:

   ```bash
   docker compose -f docker/development/docker-compose.yml \
     exec tasks-backend python manage.py issue_mobile_token <username>
   ```

   This prints the token to stdout. Rotate at any time with `--rotate`.

## Building and installing the app

The Gradle wrapper jar (`gradle/wrapper/gradle-wrapper.jar`) is intentionally
not committed. Choose one of:

- **Open `android/` in Android Studio** — it will populate the wrapper for
  you and let you run on a connected device with the green "Run" button.
- Or, with a system Gradle (≥ 8.10) installed, generate the wrapper once:

  ```bash
  cd android
  gradle wrapper --gradle-version 8.10.2
  ```

  Then build and install a debug APK on a connected device:

  ```bash
  ./gradlew :app:assembleDebug
  adb install -r app/build/outputs/apk/debug/app-debug.apk
  ```

## On-device setup

1. Make sure Health Connect is installed (built into Android 14+, available
   from Play Store for Android 13 and earlier) and that another app is
   actually writing step / distance / exercise data to it.
2. Launch **Tasks Health**.
3. Enter the **Server URL** (e.g. `https://tasks.example.com`) and paste the
   **API token** from the management command above. Tap **Save**.
4. Tap **Grant Health Connect permissions** and allow read access for steps,
   distance, and exercise sessions. Health Connect will also ask separately for
   **"Access data while in the background"** — enable that too, otherwise the
   periodic sync worker can't read anything and you'll see a permissions error
   on the next sync.
5. Tap **Sync now** to verify the wiring. The screen shows a "Last sync"
   timestamp on success or an error message on failure.

Two background `WorkManager` jobs handle automatic syncing:

- A **six-hour** periodic worker for best-effort frequent updates.
- A **daily** periodic worker that acts as a backstop, so a day never passes
  without at least one push even if the six-hour worker is deferred by Doze or
  battery throttling.

Both require network and reuse the same idempotent worker code, so the overlap
is harmless — the backend collapses retries on `(habit, day)`. Every run
syncs both today and yesterday so late-evening activity is not lost when the
day rolls over.

## Tests

JVM unit tests live under `app/src/test/`. Run them with:

```bash
./gradlew :app:test
```
