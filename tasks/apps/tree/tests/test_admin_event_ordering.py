from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from ..admin import EventAdmin
from ..models import Event, JournalAdded, Thread


class EventAdminOrderingTestCase(TestCase):
    def setUp(self):
        self.admin = EventAdmin(Event, AdminSite())
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="admin"
        )

        thread = Thread.objects.create(name="Daily")

        self.events = [
            JournalAdded.objects.create(thread=thread, comment=comment)
            for comment in ("first", "second", "third")
        ]

    def changelist_pks(self, query):
        request = self.factory.get("/admin/tree/event/", query)
        request.user = self.user

        changelist = self.admin.get_changelist_instance(request)

        return list(changelist.get_queryset(request).values_list("pk", flat=True))

    def test_event_column_sorts_by_id_ascending(self):
        expected = [event.pk for event in self.events]

        self.assertEqual(self.changelist_pks({"o": "1"}), expected)

    def test_event_column_sorts_by_id_descending(self):
        expected = [event.pk for event in reversed(self.events)]

        self.assertEqual(self.changelist_pks({"o": "-1"}), expected)
