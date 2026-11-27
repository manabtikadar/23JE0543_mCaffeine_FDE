from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase


class HealthTests(SimpleTestCase):
    @patch("config.views.connection")
    def test_each_request_queries_the_database(self, database):
        cursor = database.cursor.return_value.__enter__.return_value
        for _ in range(2):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
            self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(cursor.execute.call_count, 2)
        cursor.execute.assert_called_with("SELECT 1")

    @patch("config.views.connection")
    def test_database_outage_returns_503_and_hides_driver_details(self, database):
        database.cursor.side_effect = OperationalError("private driver detail")
        with self.assertLogs("config.views", level="ERROR") as logs:
            response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn("private driver detail", " ".join(logs.output))
