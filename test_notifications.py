import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from AI_service import api, database, rag
from AI_service.services.notification_service import create_notification


class NotificationApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_directory.name, "notifications.sqlite")
        self.env = patch.dict(os.environ, {
            "DATABASE_PATH": self.db_path,
            "AUTH_SECRET": "test-auth-secret-not-for-production",
            "GEMINI_API_KEY": "test-provider-key"
        })
        self.env.start()
        database.initialize_database()
        self.client = TestClient(api.app)
        self.client.__enter__()
        first = self.client.post("/api/auth/register", json={
            "email": "recipient@example.com",
            "password": "a-secure-test-password"
        })
        self.assertEqual(first.status_code, 201)
        self.headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
        second = self.client.post("/api/auth/register", json={
            "email": "another@example.com",
            "password": "another-secure-password"
        })
        self.other_headers = {
            "Authorization": f"Bearer {second.json()['access_token']}"
        }

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp_directory.cleanup()

    def _create_notification(self, title, *, dedupe_key=None):
        with database.connect() as connection:
            return create_notification(
                connection,
                user_id=1,
                title=title,
                message=f"{title} details.",
                notification_type="system_activity",
                created_at="2026-11-03T12:00:00+00:00",
                dedupe_key=dedupe_key
            )

    def test_authentication_pagination_and_read_filtering(self):
        self._create_notification("First")
        self._create_notification("Second")
        self._create_notification("Third")

        unauthenticated = self.client.get("/api/notifications")
        page = self.client.get(
            "/api/notifications?limit=2&offset=0",
            headers=self.headers
        )
        unread = self.client.get(
            "/api/notifications?unread=true",
            headers=self.headers
        )
        invalid_page = self.client.get(
            "/api/notifications?limit=0",
            headers=self.headers
        )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(page.status_code, 200, page.text)
        self.assertEqual(page.json()["total"], 3)
        self.assertEqual(len(page.json()["notifications"]), 2)
        self.assertEqual(unread.json()["total"], 3)
        self.assertTrue(all(not item["is_read"] for item in unread.json()["notifications"]))
        self.assertEqual(invalid_page.status_code, 422)

        notification_id = page.json()["notifications"][0]["id"]
        marked = self.client.patch(
            f"/api/notifications/{notification_id}/read",
            headers=self.headers
        )
        read = self.client.get(
            "/api/notifications?unread=false",
            headers=self.headers
        )
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertTrue(marked.json()["notification"]["is_read"])
        self.assertEqual(read.json()["total"], 1)
        self.assertEqual(
            self.client.get(
                "/api/notifications/unread-count",
                headers=self.headers
            ).json()["unread_count"],
            2
        )

    def test_notifications_are_private_and_can_be_marked_and_deleted(self):
        self._create_notification("Private")
        notification_id = self.client.get(
            "/api/notifications",
            headers=self.headers
        ).json()["notifications"][0]["id"]

        forbidden_read = self.client.patch(
            f"/api/notifications/{notification_id}/read",
            headers=self.other_headers
        )
        forbidden_delete = self.client.delete(
            f"/api/notifications/{notification_id}",
            headers=self.other_headers
        )
        other_user_list = self.client.get(
            "/api/notifications",
            headers=self.other_headers
        )
        marked_all = self.client.patch(
            "/api/notifications/mark-all-read",
            headers=self.headers
        )
        deleted = self.client.delete(
            f"/api/notifications/{notification_id}",
            headers=self.headers
        )
        missing = self.client.delete(
            f"/api/notifications/{notification_id}",
            headers=self.headers
        )

        self.assertEqual(forbidden_read.status_code, 404)
        self.assertEqual(forbidden_delete.status_code, 404)
        self.assertEqual(other_user_list.json()["total"], 0)
        self.assertEqual(marked_all.json()["updated_count"], 1)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(missing.status_code, 404)

    def test_duplicate_event_key_is_ignored(self):
        self.assertTrue(self._create_notification("Event", dedupe_key="event-1"))
        self.assertFalse(self._create_notification("Duplicate", dedupe_key="event-1"))
        response = self.client.get("/api/notifications", headers=self.headers)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["notifications"][0]["title"], "Event")

    def test_successful_document_upload_creates_notification(self):
        with patch.object(rag, "create_embedding", return_value=[1.0, 0.0]):
            upload = self.client.post(
                "/api/documents",
                headers=self.headers,
                files={"file": ("business.txt", b"Business update", "text/plain")}
            )

        self.assertEqual(upload.status_code, 201, upload.text)
        response = self.client.get("/api/notifications", headers=self.headers)
        item = response.json()["notifications"][0]
        self.assertEqual(item["type"], "document_ready")
        self.assertEqual(item["related_entity_id"], upload.json()["id"])
        self.assertEqual(item["related_entity_type"], "document")
        self.assertIn("business.txt", item["message"])