"""A single reusable HTTP client for the tasks-collector backend.

This replaces the cli's per-command copy-paste of ``requests`` + ``HTTPBasicAuth``
with one class: Basic auth from :class:`BackendConfig`, a shared session, DRF
``next``-walking pagination and uniform error handling.
"""

import requests
from requests.auth import HTTPBasicAuth

# Interactive reads in the cli use a very short timeout; batch reads over a weekly
# window can legitimately take longer, so give them more room.
SHORT_TIMEOUT = 3.05
BATCH_TIMEOUT = 30


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, backend, timeout: float = BATCH_TIMEOUT):
        self.base = backend.url.rstrip("/")
        self.auth = HTTPBasicAuth(backend.user, backend.password)
        self.timeout = timeout
        self.session = requests.Session()

    def _abs(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return f"{self.base}{path_or_url}"

    def _get(self, path: str, params: dict | None = None):
        r = self.session.get(
            self._abs(path), params=params, auth=self.auth, timeout=self.timeout
        )
        if not r.ok:
            raise ApiError(f"{r.status_code} GET {path}: {r.text[:500]}")
        return r.json()

    def paginate(self, path: str, params: dict | None = None):
        """Yield every item across DRF ``{count,next,previous,results}`` pages.

        Also tolerates endpoints that return a bare list or object.
        """
        data = self._get(path, params)
        while True:
            if isinstance(data, dict) and "results" in data:
                yield from data["results"]
                nxt = data.get("next")
                if not nxt:
                    return
                r = self.session.get(nxt, auth=self.auth, timeout=self.timeout)
                if not r.ok:
                    raise ApiError(f"{r.status_code} GET {nxt}: {r.text[:500]}")
                data = r.json()
            elif isinstance(data, list):
                yield from data
                return
            else:
                yield data
                return

    # ---- reads ----
    def daily(self, day, thread: str = "Daily") -> dict:
        """GET /api/events/daily/ -> {date, events[], plan, reflection}."""
        return self._get("/api/events/daily/", {"date": day, "thread": thread})

    def plans_today(self, day) -> dict:
        """GET /api/v1/plans/today/ -> {daily, weekly, monthly}."""
        return self._get("/api/v1/plans/today/", {"date": day})

    def journal(self):
        """GET /journal/ (paginated JournalAdded list)."""
        return self.paginate("/journal/")

    def observation_events(self, published_gte, published_lte):
        """GET /observation-events/ (paginated polymorphic observation feed)."""
        return self.paginate(
            "/observation-events/",
            {"published__gte": published_gte, "published__lte": published_lte},
        )

    def observations(self, pub_date_gte, pub_date_lte):
        """GET /observation-api/?ownership=mine (paginated)."""
        return self.paginate(
            "/observation-api/",
            {
                "ownership": "mine",
                "pub_date__gte": pub_date_gte,
                "pub_date__lte": pub_date_lte,
            },
        )

    def stats(self, year=None) -> dict:
        return self._get("/stats/json/", {"year": year} if year else None)

    def threads(self):
        return self._get("/threads/")

    def profile(self):
        return self._get("/profile/")

    # ---- write-back: designed for, not used by any job yet ----
    # Jobs currently draft to the workdir. When write-back is enabled, these send
    # the same payloads the cli sends; on ConnectionError they enqueue to the
    # workdir dead-letter queue (mirrors the cli's ~/.tasks/queue) for later retry.
    def _post(self, path: str, payload: dict, workdir=None, file_type: str = "item"):
        try:
            r = self.session.post(
                self._abs(path), json=payload, auth=self.auth, timeout=self.timeout
            )
        except requests.exceptions.ConnectionError:
            if workdir is not None:
                workdir.dead_letter(
                    payload, {"url": self._abs(path)}, file_type=file_type
                )
                return None
            raise
        if not r.ok:
            raise ApiError(f"{r.status_code} POST {path}: {r.text[:500]}")
        return r.json()

    def post_journal(self, comment, thread, tags=None, story=None, workdir=None):
        payload = {"comment": comment, "thread": thread, "tags": tags or []}
        if story is not None:
            payload["story"] = story
        return self._post("/journal/", payload, workdir=workdir, file_type="journal")

    def post_update(self, comment, observation, workdir=None):
        return self._post(
            "/updates/",
            {"comment": comment, "observation": observation},
            workdir=workdir,
            file_type="update",
        )

    def append_board(self, text, thread_name=None, workdir=None):
        payload = {"text": text}
        if thread_name is not None:
            payload["thread-name"] = thread_name
        return self._post(
            "/boards/append/", payload, workdir=workdir, file_type="board"
        )

    def add_task(self, text, timeframe="today", workdir=None):
        return self._post(
            "/plans/add-task/",
            {"text": text, "timeframe": timeframe},
            workdir=workdir,
            file_type="task",
        )
