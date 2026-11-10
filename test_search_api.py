import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from AI_service import api


class DocumentSearchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "DATABASE_PATH": os.path.join(
                self.temp_directory.name,
                "document-search.sqlite"
            ),
            "AUTH_SECRET": "test-auth-secret-not-for-production"
        })
        self.env.start()
        api.database.initialize_database()
        self.client = TestClient(api.app)
        self.client.__enter__()
        registration = self.client.post("/api/auth/register", json={
            "email": "search-owner@example.com",
            "password": "a-secure-test-password"
        })
        self.assertEqual(registration.status_code, 201)
        self.user_id = registration.json()["user"]["id"]
        self.headers = {
            "Authorization": f"Bearer {registration.json()['access_token']}"
        }
        self.add_document(
            "customer-one",
            (
                "Customer: Ahmed Khan. Email: ahmed.khan@example.com. "
                "Phone: +1 555 0100. Company: Northwind Traders. "
                "Confidential account notes follow much later in this document."
            ),
            "2026-10-20T12:00:00+00:00"
        )
        self.add_document(
            "task-one",
            (
                "Prepare Monthly Report. Description: prepare the monthly "
                "business report. Assigned user: Ahmed. Status: pending. "
                "Priority: high."
            ),
            "2026-10-25T12:00:00+00:00"
        )
        with api.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO chunks
                    (document_id, chunk_index, page_number, content, embedding_json)
                VALUES ('customer-one', 1, 1, ?, '[]')
                """,
                ("Ahmed Khan customer entry repeated in an overlapping chunk.",)
            )

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.env.stop()
        self.temp_directory.cleanup()

    def add_document(
        self,
        document_id: str,
        content: str,
        uploaded_at: str,
        user_id: int | None = None
    ):
        if user_id is None:
            user_id = self.user_id
        with api.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO documents
                    (id, user_id, filename, media_type, status, created_at)
                VALUES (?, ?, ?, 'text/plain', 'ready', ?)
                """,
                (document_id, user_id, f"{document_id}.txt", uploaded_at)
            )
            connection.execute(
                """
                INSERT INTO chunks
                    (document_id, chunk_index, page_number, content, embedding_json)
                VALUES (?, 0, 1, ?, '[]')
                """,
                (document_id, content)
            )

    def search(self, path: str, query: str, **params):
        return self.client.get(
            path,
            params={"q": query, **params},
            headers=self.headers
        )

    def test_customer_search_matches_name_email_phone_and_company(self):
        for query in (
            "Ahmed Khan",
            "Khan",
            "AHMED.KHAN@EXAMPLE.COM",
            "+1 555 0100",
            "Northwind"
        ):
            with self.subTest(query=query):
                response = self.search("/api/customers/search", query)
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["success"])
                self.assertEqual(payload["total"], 1)
                self.assertEqual(len(payload["results"]), 1)
                self.assertEqual(
                    payload["results"][0]["kind"],
                    "document_excerpt"
                )
                self.assertEqual(
                    payload["results"][0]["document_id"],
                    "customer-one"
                )

    def test_task_search_matches_title_description_assignee_status_and_priority(self):
        for query in (
            "Monthly Report",
            "monthly business",
            "Assigned user: Ahmed",
            "PENDING",
            "high"
        ):
            with self.subTest(query=query):
                response = self.search("/api/tasks/search", query)
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertTrue(payload["success"])
                self.assertEqual(payload["total"], 1)
                self.assertEqual(
                    payload["results"][0]["document_id"],
                    "task-one"
                )

    def test_search_is_unicode_case_insensitive(self):
        self.add_document(
            "unicode",
            "A record for Straße GmbH.",
            "2026-10-26T12:00:00+00:00"
        )
        response = self.search("/api/customers/search", "STRASSE")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 1)
        self.assertIn("Straße", response.json()["results"][0]["snippet"])

    def test_search_returns_a_limited_excerpt_around_the_match(self):
        self.add_document(
            "long-record",
            "PUBLICTERM " + ("unrelated " * 40) + "PRIVATE_ACCOUNT_BALANCE=1234",
            "2026-10-27T12:00:00+00:00"
        )
        response = self.search("/api/customers/search", "PUBLICTERM")
        self.assertEqual(response.status_code, 200, response.text)
        snippet = response.json()["results"][0]["snippet"]
        self.assertLessEqual(len(snippet), 320)
        self.assertIn("PUBLICTERM", snippet)
        self.assertNotIn("PRIVATE_ACCOUNT_BALANCE", snippet)

    def test_no_matches_return_empty_success_response(self):
        response = self.search("/api/tasks/search", "nonexistent phrase")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "success": True,
            "results": [],
            "total": 0,
            "limit": 20,
            "offset": 0
        })

    def test_search_deduplicates_chunks_and_supports_pagination(self):
        self.add_document(
            "customer-two",
            "Ahmed Khan has a second record.",
            "2026-10-21T12:00:00+00:00"
        )
        first_page = self.search(
            "/api/customers/search",
            "Ahmed",
            limit=1
        )
        second_page = self.search(
            "/api/customers/search",
            "Ahmed",
            limit=1,
            offset=1
        )

        self.assertEqual(first_page.status_code, 200, first_page.text)
        self.assertEqual(second_page.status_code, 200, second_page.text)
        self.assertEqual(first_page.json()["total"], 3)
        self.assertEqual(len(first_page.json()["results"]), 1)
        self.assertEqual(len(second_page.json()["results"]), 1)
        self.assertNotEqual(
            first_page.json()["results"][0]["document_id"],
            second_page.json()["results"][0]["document_id"]
        )

    def test_search_is_limited_to_authenticated_users_ready_documents(self):
        other_account = self.client.post("/api/auth/register", json={
            "email": "other-owner@example.com",
            "password": "a-secure-test-password"
        })
        self.assertEqual(other_account.status_code, 201)
        other_user_id = other_account.json()["user"]["id"]
        self.add_document(
            "other-customer",
            "Ahmed Khan private record.",
            "2026-10-25T12:00:00+00:00",
            user_id=other_user_id
        )
        response = self.search("/api/customers/search", "Ahmed")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 2)
        self.assertEqual(
            {item["document_id"] for item in response.json()["results"]},
            {"customer-one", "task-one"}
        )

    def test_search_requires_authentication(self):
        response = self.client.get("/api/customers/search", params={"q": "Ahmed"})
        self.assertEqual(response.status_code, 401)

    def test_empty_and_invalid_queries_are_rejected(self):
        blank = self.search("/api/customers/search", "   ")
        empty = self.client.get(
            "/api/tasks/search",
            params={"q": ""},
            headers=self.headers
        )
        too_long = self.search("/api/customers/search", "a" * 201)
        invalid_limit = self.search(
            "/api/tasks/search",
            "report",
            limit=51
        )

        self.assertEqual(blank.status_code, 422)
        self.assertEqual(empty.status_code, 422)
        self.assertEqual(too_long.status_code, 422)
        self.assertEqual(invalid_limit.status_code, 422)

    def test_database_errors_return_sanitized_service_unavailable(self):
        with patch.object(
            api,
            "search_document_excerpts",
            side_effect=sqlite3.OperationalError("private database detail")
        ):
            response = self.search("/api/customers/search", "Ahmed")

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private database detail", response.text)


if __name__ == "__main__":
    unittest.main()
