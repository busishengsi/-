import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import app as backend


class ApiFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        root = Path(self.temp_directory.name)
        backend.DATABASE = root / "test.db"
        backend.UPLOAD_DIR = root / "uploads"
        backend.UPLOAD_DIR.mkdir()
        backend.init_db()
        backend.app.config["TESTING"] = True
        self.client = backend.app.test_client()

    def tearDown(self):
        self.temp_directory.cleanup()

    def register(self, username):
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123", "nickname": username},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["data"]["token"]

    def make_admin(self, username="admin"):
        token = self.register(username)
        connection = backend.connect_db()
        connection.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
        connection.commit()
        connection.close()
        return token

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def test_complete_claim_flow(self):
        owner_token = self.register("owner")
        applicant_token = self.register("applicant")

        created = self.client.post(
            "/api/items",
            headers=self.auth(owner_token),
            json={
                "type": "found",
                "title": "黑色雨伞",
                "category": "daily",
                "description": "教学楼门口捡到",
                "location": "一号教学楼",
            },
        )
        self.assertEqual(created.status_code, 201)
        item_id = created.get_json()["data"]["id"]

        admin_token = self.make_admin()
        reviewed_item = self.client.patch(
            f"/api/admin/items/{item_id}/audit",
            headers=self.auth(admin_token),
            json={"action": "approve"},
        )
        self.assertEqual(reviewed_item.status_code, 200)

        listing = self.client.get("/api/items?page=bad&page_size=bad")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.get_json()["data"]["total"], 1)

        claim = self.client.post(
            f"/api/items/{item_id}/claims",
            headers=self.auth(applicant_token),
            json={"description": "伞柄上贴有姓名缩写", "proof": "AB"},
        )
        self.assertEqual(claim.status_code, 201)
        claim_id = claim.get_json()["data"]["id"]

        reviewed = self.client.patch(
            f"/api/claims/{claim_id}/review",
            headers=self.auth(owner_token),
            json={"action": "approve", "note": "信息一致"},
        )
        self.assertEqual(reviewed.status_code, 200)

        detail = self.client.get(f"/api/items/{item_id}").get_json()["data"]
        self.assertEqual(detail["status"], "claimed")

        messages = self.client.get("/api/messages", headers=self.auth(applicant_token))
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(messages.get_json()["data"]["total"], 1)

    def test_image_recognition(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (300, 200), (25, 25, 25)).save(image_bytes, "PNG")
        image_bytes.seek(0)

        response = self.client.post(
            "/api/ai/recognize",
            data={"image": (image_bytes, "sample.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["category"], "digital")

    def test_system_status_and_health_headers(self):
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json()["database"], "ready")
        self.assertEqual(health.headers["X-App-Version"], backend.APP_VERSION)
        self.assertIn("X-Process-Time-Ms", health.headers)

        status = self.client.get("/api/system/status")
        self.assertEqual(status.status_code, 200)
        data = status.get_json()["data"]
        self.assertGreater(data["runtime"]["process_id"], 0)
        self.assertIn("operating_system", data["runtime"])
        self.assertEqual(data["storage"]["records"]["users"], 0)

    def test_database_backup_is_readable(self):
        self.register("backup_user")
        destination = Path(self.temp_directory.name) / "backup.db"
        backup = backend.create_database_backup(destination)

        self.assertTrue(backup.exists())
        connection = sqlite3.connect(backup)
        try:
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_item_audit_permissions_and_visibility(self):
        owner_token = self.register("publisher")
        created = self.client.post(
            "/api/items",
            headers=self.auth(owner_token),
            json={"type": "lost", "title": "学生证", "category": "card"},
        )
        item = created.get_json()["data"]
        self.assertEqual(item["audit_status"], "pending")
        self.assertEqual(self.client.get("/api/items").get_json()["data"]["total"], 0)

        forbidden = self.client.patch(
            f"/api/admin/items/{item['id']}/audit",
            headers=self.auth(owner_token),
            json={"action": "approve"},
        )
        self.assertEqual(forbidden.status_code, 403)

        admin_token = self.make_admin("reviewer")
        pending = self.client.get(
            "/api/admin/items?audit_status=pending", headers=self.auth(admin_token)
        )
        self.assertEqual(pending.get_json()["data"]["total"], 1)

        approved = self.client.patch(
            f"/api/admin/items/{item['id']}/audit",
            headers=self.auth(admin_token),
            json={"action": "approve", "note": "信息完整"},
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(self.client.get("/api/items").get_json()["data"]["total"], 1)

    def test_frontend_pages_are_served_by_flask(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("校园失物招领平台", home.get_data(as_text=True))
        for page in ("index.html", "list.html", "detail.html", "publish.html", "audit.html", "login.html"):
            response = self.client.get(f"/{page}")
            self.assertEqual(response.status_code, 200, page)
            self.assertIn('src="app.js"', response.get_data(as_text=True))
            response.close()
        script = self.client.get("/app.js")
        self.assertEqual(script.status_code, 200)
        script.close()
        home.close()


if __name__ == "__main__":
    unittest.main()
