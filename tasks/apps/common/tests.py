from django.test import TestCase


class HealthCheckTest(TestCase):
    def test_responds_without_authentication(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy"})
