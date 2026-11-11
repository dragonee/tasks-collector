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

1. Apply migrations:

   ```bash
   docker compose -f docker/development/docker-compose.yml \
     exec tasks-backend python manage.py migrate
   ```

2. In the Django admin (`/admin/`) create:

   - A `Habit` with a `slug` and `name` of your choice.
   - A `HabitKeyword` with `keyword = health-metrics` pointing at that habit.
     The API looks the habit up by keyword text, so the slug can be anything.

The phone gets its token by logging in (see "On-device setup"). To have one
without the phone, for a debug build or a script, mint it:

```bash
docker compose -f docker/development/docker-compose.yml \
  exec tasks-backend python manage.py issue_mobile_token <username>
```

This prints a new token to stdout each time. It is listed in the user's account
settings as `issue_mobile_token` (`--name` to call it something else), where it
can be revoked; `--rotate` revokes the earlier ones of that name first.

## Building and installing the app

- **Open `android/` in Android Studio** and use the green "Run" button to
  install on a connected device.
- Or use the committed Gradle wrapper (pinned to Gradle 9.4.1, matching
  AGP 9.2.x). It needs JDK 17+; Android Studio's bundled one works:

  ```bash
  cd android
  export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
  ./gradlew :app:assembleDebug
  adb install -r app/build/outputs/apk/debug/app-debug.apk
  ```

## Pre-filling Server URL / API token (debug builds)

If you're running the app in an Android emulator (or any debug install)
and don't want to re-enter the server URL and token after every install,
add the values to `android/local.properties` (gitignored):

```properties
tasks.devServerUrl=http://10.0.2.2:8000
tasks.devApiToken=<token-from-issue_mobile_token>
```

`10.0.2.2` is the host-machine alias inside the Android emulator. For a
physical device on the same LAN use the host's LAN IP instead.

The `android/scripts/get-android-token` helper does both steps in one
shot — it runs `issue_mobile_token` inside the dev container and writes
the result into `local.properties`:

```bash
# First time: mint a token for <username> and write it + localhost URL
android/scripts/get-android-token <username>

# Emulator-friendly URL
android/scripts/get-android-token <username> --server http://10.0.2.2:8000

# Already configured? Pass -f to overwrite, optionally with --rotate to
# also invalidate the existing server-side token before writing a new one.
android/scripts/get-android-token <username> --rotate -f
```

Alternatively, export the same values as environment variables before
running Gradle:

```bash
export TASKS_DEV_SERVER_URL=http://10.0.2.2:8000
export TASKS_DEV_API_TOKEN=<token>
```

`local.properties` wins over env vars. Both are read at build time and
exposed through `BuildConfig.DEV_SERVER_URL` / `BuildConfig.DEV_API_TOKEN`
**only in debug builds** — release builds always inject empty strings,
so this can't leak credentials into a published APK.

At runtime the `Settings` DataStore falls back to these defaults when no
value has been saved. As soon as you tap **Save** in the Settings
screen, the DataStore value takes precedence; clearing the DataStore
(uninstall + reinstall, or app data wipe) brings the defaults back.

## On-device setup

1. Make sure Health Connect is installed (built into Android 14+, available
   from Play Store for Android 13 and earlier) and that another app is
   actually writing step / distance / exercise data to it.
2. Launch **Tasks Health**.
3. In **Settings**, enter the **Server URL** (e.g. `https://tasks.example.com`)
   and tap **Log in**. The browser opens the server's login page; log in with
   your username and password as on the web and confirm. The browser hands the
   phone a token of its own (the phone never sees the password). It shows in
   your account settings on the web under **Devices** as "Tasks Health on
   <phone>", where **Log out** revokes it; **Log out** in the app does the same.
   A token from the management command above can be pasted in instead.
4. Tap **Grant Health Connect permissions** and allow read access for steps,
   distance, and exercise sessions. Health Connect will also ask separately for
   **"Access data while in the background"** — enable that too, otherwise the
   periodic sync worker can't read anything and you'll see a permissions error
   on the next sync.
5. Tap **Sync now** to verify the wiring. The screen shows a "Last sync"
   timestamp on success or an error message on failure.

Two background `WorkManager` jobs handle automatic syncing:

- An **hourly** periodic worker for best-effort frequent updates.
- A **daily** periodic worker that acts as a backstop, so a day never passes
  without at least one push even if the hourly worker is deferred by Doze or
  battery throttling.

Both require network and reuse the same idempotent worker code, so the overlap
is harmless — the backend collapses retries on `(habit, day)`. Every run
re-syncs the trailing seven days (today and the six preceding days) so that
late wearable back-fills overwrite the older rows with the corrected aggregates.

## Tests

JVM unit tests live under `app/src/test/`. Run them with:

```bash
./gradlew :app:test
```
