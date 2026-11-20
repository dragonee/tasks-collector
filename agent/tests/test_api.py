import pytest
import responses
from tasks_agent.api import ApiClient, ApiError


class _Backend:
    url = "http://testserver"
    user = "u"
    password = "p"


@responses.activate
def test_paginate_walks_next():
    responses.get(
        "http://testserver/journal/",
        json={
            "count": 3,
            "next": "http://testserver/journal/?page=2",
            "previous": None,
            "results": [{"id": 1}, {"id": 2}],
        },
    )
    responses.get(
        "http://testserver/journal/?page=2",
        json={"count": 3, "next": None, "previous": None, "results": [{"id": 3}]},
    )

    client = ApiClient(_Backend())
    assert [item["id"] for item in client.journal()] == [1, 2, 3]


@responses.activate
def test_paginate_tolerates_bare_object():
    responses.get("http://testserver/api/events/daily/", json={"date": "2026-07-07"})
    client = ApiClient(_Backend())
    # daily() is a plain _get, but paginate() should also cope with bare objects.
    assert list(client.paginate("/api/events/daily/")) == [{"date": "2026-07-07"}]


@responses.activate
def test_get_raises_apierror_on_non_ok():
    responses.get("http://testserver/profile/", status=403, body="forbidden")
    client = ApiClient(_Backend())
    with pytest.raises(ApiError):
        client.profile()
