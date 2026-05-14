# 0001 — Defer Google Health API integration

- **Status:** Rejected (revisit late 2026 / early 2027)
- **Date:** 2026-05-14

## Context

We wanted daily health metrics — steps, distance, active minutes, Heart-Points-equivalent — to land automatically as `HabitTracked` events on the Daily thread so they sit alongside the rest of the productivity event stream. The Google Fit REST API was the obvious source, but it's deprecated; Google's documented successor for cloud access is the **Google Health API** (`https://health.googleapis.com/v4/`).

## What we tried

A short-lived branch (`feat/google-health-integration`, PR #202, rolled back in this commit) built the full plumbing:

- New `google_health_integration` Django app with a `GoogleHealthIntegration` model (OneToOne to `Profile`, holding the habit keyword + OAuth tokens).
- `services/oauth.py` running a manual paste-back OAuth flow (Docker-friendly: prints the auth URL, accepts the redirected URL back on stdin).
- `services/health_api.py` calling `users/me/dataTypes/{steps|distance|active-minutes|active-zone-minutes}/dataPoints:dailyRollUp` with the documented civil-time range body.
- `services/sync.py` orchestrator and a `sync_health_metrics` management command for the daily cron.

OAuth, token refresh, and HTTP plumbing all worked end-to-end.

## What we learned

The single scope `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly` is described in the docs as *"See your Fitbit activity and fitness data."* On first call the API returned:

```
HTTP 400 FAILED_PRECONDITION
  reason: ACCOUNT_NOT_LINKED
  message: The account is not linked to Google Health.
  redirect_uri: https://fitbit.google.com/auth/signup
```

Following that link reveals that the **Google Health API is currently backed by a Fitbit/Google Health unified account, not by Google Health Connect data on Android**. There is no cloud-accessible path to phone-collected steps unless either:

1. The user is a Fitbit device owner who has linked their Fitbit account to Google Health, **or**
2. We build our own Android application that reads from Health Connect directly on the device and pushes to our backend ourselves.

Neither option fits — the primary phone is not a Fitbit, and building an Android companion app is well outside the scope of what this integration was meant to be ("a daily cron pulls four numbers").

## Decision

Do not ship a Google Health API integration at this time. Revert the branch entirely (code, requirements, settings) rather than leave a half-wired feature behind.

Revisit in **late 2026 / early 2027**: Google has signaled they want Google Health to absorb Health Connect data over time, and Fitbit-as-prerequisite is most likely a transitional state. The plumbing in PR #202 is preserved in git history if/when the API becomes usable for non-Fitbit users.

## Consequences

- No automated ingestion of phone-collected health metrics for now. Anything that needs to be tracked here happens via the existing manual habit-tracking UI.
- If the requirement becomes pressing before the API matures, the alternative is building a small Android companion app on Health Connect and a simple `POST /habits/track` endpoint to receive its uploads — a much larger project than the original "four numbers via cron" idea, and a separate ADR.
- No code or settings churn left in the tree: requirements, INSTALLED_APPS, OAuth scope config, and the `google_health_integration` app are all gone again.
