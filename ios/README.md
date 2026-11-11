# Tasks Health — iOS app

The Android companion app (`android/`), in Swift and SwiftUI: the day's plan
(Today), trips with notes and photos, health metrics pushed to the server, and
logging the phone in. It talks to the same endpoints and behaves the same;
where the two platforms differ, this is what stands in for what:

| Android | iOS |
| --- | --- |
| Health Connect | HealthKit (steps, walking + running distance, active + resting energy, workouts) |
| WorkManager jobs (hourly, daily, outbox) | The outbox drains in the app (`Sync/OutboxSync.swift`: on every change, when the app comes to the front, when the network is back, with a growing wait between retries). The health sync runs when the app comes to the front and the last one is over an hour old, and from a background app refresh when iOS grants one. |
| Foreground service recording the trip's trail | Location updates that go on in the background on a "while using" permission (`Location/TripTracker.swift`) |
| DataStore | UserDefaults, and the keychain for the token |
| Navigation drawer, FAB, dialogs | Tabs, a "+" menu in the navigation bar, sheets |
| `local.properties` | `ios/Local.xcconfig` |

It is set up for local development only: no development team, no signing. It
builds and runs in the simulator as it is. The icon is the Android launcher
icon, enlarged from its largest size (192 px) onto a white square. For a real phone, pick
your team under Signing & Capabilities in Xcode (HealthKit is the one
capability it needs).

## Building and running

Open `ios/TasksHealth.xcodeproj` in Xcode and run the `TasksHealth` scheme on
a simulator. Or from the shell:

```bash
cd ios
xcodebuild -project TasksHealth.xcodeproj -scheme TasksHealth \
  -destination 'platform=iOS Simulator,name=iPhone 17' -derivedDataPath build build
xcrun simctl boot "iPhone 17"
xcrun simctl install "iPhone 17" build/Build/Products/Debug-iphonesimulator/TasksHealth.app
xcrun simctl launch "iPhone 17" org.polybrain.tasks.health.debug
```

The source folders are synchronized with the project: a file added under
`TasksHealth/` or `TasksHealthTests/` is part of its target without touching
the project file.

## Pointing it at the dev server

The simulator shares the Mac's network, so the server is `http://localhost:8000`
(or `<prefix>000` in a `/devenv` environment). Plain HTTP is allowed for local
addresses only (`NSAllowsLocalNetworking`).

To have a debug build come up logged in, mint a token into `ios/Local.xcconfig`
(gitignored):

```bash
# A token for <username>, and the URL of the stack this checkout runs
ios/scripts/get-ios-token <username>

# Another server
ios/scripts/get-ios-token <username> --server http://192.168.1.20:8000

# Already there? -f overwrites, --rotate also revokes the old one
ios/scripts/get-ios-token <username> --rotate -f
```

The two values end up in the app's Info.plist (`TasksDevServerURL`,
`TasksDevAPIToken`) in Debug builds only; Release sets them to nothing. The
app falls back to them while nothing is saved. Logging in from Settings works
too, and then the token is the phone's own (in the keychain).

In `ios/Local.xcconfig` the URL is written `http:/$()/localhost:8000`: an
xcconfig file reads `//` as the start of a comment, and the empty `$()` keeps
the slashes apart. The script does that for you.

### Photos

Photos are uploaded straight to object storage, at a URL the server signs for
where *the phone* finds this machine. The dev stack signs for the Android
emulator (`10.0.2.2`) unless told otherwise; for the iOS simulator add this to
`docker/development/.env` and bring the backend and celery up again:

```
TASKS_DEVICE_HOST=localhost
```

(For a real phone it is the Mac's address on the LAN.)

## Logging in

Settings → enter the server URL → **Log in**. The server's login page opens in
a browser sheet; log in as on the web and confirm. The phone gets a token of
its own, listed in the account settings on the web as "Tasks Health on
<phone>", where it can be logged out; **Log out** in the app does the same.
The server knows the app as the OAuth client `tasks-ios`
(`settings.OAUTH_CLIENTS`).

## Health

On the Health tab, **Grant access to Health**, then **Sync now**. The server
needs a habit with the keyword `health-metrics` (see `android/README.md`,
"One-time backend setup"); without one the sync fails with HTTP 404. Each sync
pushes the last seven days, and every bike ride once, as the Android app does.

HealthKit doesn't tell an app whether reading was allowed, only whether the
user was asked: a refusal reads as zeros. The simulator has no health data
unless you add some in its Health app.

## Tests

Unit tests (Swift Testing) are in `TasksHealthTests/`, the Android app's JVM
tests ported:

```bash
cd ios
xcodebuild test -project TasksHealth.xcodeproj -scheme TasksHealth \
  -destination 'platform=iOS Simulator,name=iPhone 17' -derivedDataPath build
```
