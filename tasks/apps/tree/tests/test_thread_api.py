from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Board, Thread


class ThreadAPIReadOnlyTestCase(APITestCase):
    """threads/ only lists threads for the board UI and the CLI. Writes would
    rename a thread the code looks up by name, or cascade-delete everything
    filed under it, so the endpoint refuses them."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(username="u", password="x")
        cls.daily = Thread.objects.create(name="Daily")
        cls.board = Board.objects.create(thread=cls.daily, state=[])

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_and_retrieve(self):
        response = self.client.get("/threads/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json()["results"], [{"id": self.daily.id, "name": "Daily"}]
        )
        response = self.client.get(f"/threads/{self.daily.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_is_not_allowed(self):
        response = self.client.post("/threads/", {"name": "Monthly"})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertFalse(Thread.objects.filter(name="Monthly").exists())

    def test_rename_is_not_allowed(self):
        response = self.client.patch(f"/threads/{self.daily.id}/", {"name": "Other"})

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.daily.refresh_from_db()
        self.assertEqual(self.daily.name, "Daily")

    def test_delete_is_not_allowed(self):
        response = self.client.delete(f"/threads/{self.daily.id}/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Board.objects.filter(pk=self.board.pk).exists())
