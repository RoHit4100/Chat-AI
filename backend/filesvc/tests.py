import datetime
import io
import json
import os
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from agent.tools import read_file
from chat.models import Thread, UploadedFile
from filesvc.storage import storage
from filesvc.throttles import UploadRateThrottle, ChatRateThrottle

User = get_user_model()

# Key pair for testing JWTs
TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()

class MockSigningKey:
    def __init__(self, key):
        self.key = key

def make_test_token(sub="test-user-sub-1", email="user1@example.com"):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "iss": settings.KEYCLOAK_PUBLIC_URL,
        "azp": settings.KEYCLOAK_CLIENT_ID,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(seconds=3600)).timestamp()),
    }
    return jwt.encode(payload, TEST_PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-kid"})

class FileServiceTests(TestCase):
    """Comprehensive test suite for file uploading, parsing, security, download, and tools."""

    def setUp(self):
        self.client = APIClient()

        # Mock JWKS for Keycloak authentication
        self.mock_jwks = MagicMock()
        self.mock_jwks.get_signing_key_from_jwt.return_value = MockSigningKey(TEST_PUBLIC_KEY)
        self.patcher = patch("chat.authentication.get_jwks_client", return_value=self.mock_jwks)
        self.patcher.start()

        self.token_user1 = make_test_token(sub="sub-user-1", email="user1@example.com")
        self.token_user2 = make_test_token(sub="sub-user-2", email="user2@example.com")

        self.user1 = User.objects.create(username="sub-user-1", email="user1@example.com")
        self.user2 = User.objects.create(username="sub-user-2", email="user2@example.com")

        self.thread1 = Thread.objects.create(user=self.user1, title="Thread 1")
        self.thread2 = Thread.objects.create(user=self.user2, title="Thread 2")

        self.sample_dir = Path(__file__).resolve().parent.parent / "sample_files"

    def tearDown(self):
        self.patcher.stop()

    def test_upload_endpoint_requires_auth(self):
        """Unauthenticated requests to upload endpoint return 401."""
        url = f"/api/threads/{self.thread1.id}/files/"
        response = self.client.post(url, {}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_upload_fixtures_all_types(self):
        """Upload and parse one fixture per type: pdf, docx, xlsx, csv, pptx, image, txt, py, json, zip."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        fixtures = [
            "sample.pdf",
            "sample.docx",
            "sample.xlsx",
            "sample.csv",
            "sample.pptx",
            "sample.png",
            "sample.txt",
            "sample.py",
            "sample.json",
            "sample.zip",
        ]

        for fname in fixtures:
            fpath = self.sample_dir / fname
            self.assertTrue(fpath.exists(), f"Sample file {fname} must exist.")
            with open(fpath, "rb") as f:
                uploaded = SimpleUploadedFile(fname, f.read())

            res = self.client.post(url, {"files": uploaded}, format="multipart")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, f"Failed uploading {fname}: {res.data}")
            self.assertEqual(len(res.data), 1)
            record = res.data[0]
            self.assertEqual(record["status"], "ready", f"File {fname} parsing failed: {record.get('error')}")
            self.assertTrue(record["summary"], f"File {fname} should have a summary.")
            self.assertTrue(record["parsed_path"], f"File {fname} should have a parsed_path.")

            # Validate Image dimension storage
            if fname == "sample.png":
                parsed = storage.read_parsed(record["parsed_path"])
                self.assertIn("image_info", parsed)
                self.assertEqual(parsed["image_info"]["width"], 32)
                self.assertEqual(parsed["image_info"]["height"], 32)

    def test_multipart_many_files_per_request(self):
        """Upload multiple files in a single request."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        f1 = SimpleUploadedFile("batch1.txt", b"First batch text content.")
        f2 = SimpleUploadedFile("batch2.json", b'{"key": "value"}')

        res = self.client.post(url, {"files": [f1, f2]}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data), 2)
        self.assertTrue(all(item["status"] == "ready" for item in res.data))

    def test_corrupt_file_handling(self):
        """Corrupt files get status failed with a clear message."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        corrupt_pdf = SimpleUploadedFile("corrupt.pdf", b"%PDF-1.4 corrupt junk data not a real pdf body")
        res = self.client.post(url, {"files": corrupt_pdf}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        record = res.data[0]
        self.assertEqual(record["status"], "failed")
        self.assertIn("Parsing failed", record["error"])

    def test_wrong_extension_handling(self):
        """Executable disguised with .pdf extension gets status failed."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        # DOS / Windows executable header
        fake_pdf = SimpleUploadedFile("evil.pdf", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff")
        res = self.client.post(url, {"files": fake_pdf}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        record = res.data[0]
        self.assertEqual(record["status"], "failed")
        self.assertTrue("MIME type" in record["error"] or "not permitted" in record["error"])

    def test_oversized_file_handling(self):
        """File exceeding MAX_FILE_SIZE_BYTES receives failed status."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        with patch("filesvc.validators.MAX_FILE_SIZE_BYTES", 100):
            big_file = SimpleUploadedFile("too_big.txt", b"A" * 500)
            res = self.client.post(url, {"files": big_file}, format="multipart")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            record = res.data[0]
            self.assertEqual(record["status"], "failed")
            self.assertIn("exceeds limit", record["error"])

    def test_oversized_request_handling(self):
        """Total request size exceeding MAX_REQUEST_SIZE_BYTES returns 400 Bad Request."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        with patch("filesvc.views.MAX_REQUEST_SIZE_BYTES", 200):
            f1 = SimpleUploadedFile("f1.txt", b"A" * 150)
            f2 = SimpleUploadedFile("f2.txt", b"B" * 150)
            res = self.client.post(url, {"files": [f1, f2]}, format="multipart")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("Total request size", res.data["detail"])

    def test_zip_safety_traversal(self):
        """ZIP archives with path traversal are rejected with status failed."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0:")
        buf.seek(0)

        traversal_zip = SimpleUploadedFile("traversal.zip", buf.read())
        res = self.client.post(url, {"files": traversal_zip}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        record = res.data[0]
        self.assertEqual(record["status"], "failed")
        self.assertIn("traversal", record["error"])

    def test_zip_safety_bomb_and_nested_archive(self):
        """ZIP bomb exceeding uncompressed limit and nested archives are rejected."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")
        url = f"/api/threads/{self.thread1.id}/files/"

        # Nested archive check
        buf_nested = io.BytesIO()
        with zipfile.ZipFile(buf_nested, "w") as zf:
            zf.writestr("inner.zip", b"PK\x05\x06" + b"\x00" * 18)
        buf_nested.seek(0)

        nested_zip = SimpleUploadedFile("nested.zip", buf_nested.read())
        res = self.client.post(url, {"files": nested_zip}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data[0]["status"], "failed")
        self.assertIn("nested archive", res.data[0]["error"].lower())

        # Uncompressed size limit check
        with patch("filesvc.validators.MAX_ZIP_UNCOMPRESSED_SIZE", 50):
            buf_big = io.BytesIO()
            with zipfile.ZipFile(buf_big, "w") as zf:
                zf.writestr("big.txt", b"X" * 200)
            buf_big.seek(0)

            bomb_zip = SimpleUploadedFile("bomb.zip", buf_big.read())
            res = self.client.post(url, {"files": bomb_zip}, format="multipart")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(res.data[0]["status"], "failed")
            self.assertIn("exceeds limit", res.data[0]["error"])

    def test_cross_user_access_returns_404(self):
        """Cross-user upload, list, and download return 404."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user2}")

        # User 2 attempts to upload to User 1's thread
        upload_url = f"/api/threads/{self.thread1.id}/files/"
        f = SimpleUploadedFile("test.txt", b"Hello")
        res = self.client.post(upload_url, {"files": f}, format="multipart")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # User 2 attempts to list User 1's thread files
        res = self.client.get(upload_url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # User 1 creates a file
        uf = UploadedFile.objects.create(
            thread=self.thread1,
            name="private.txt",
            mime="text/plain",
            size=11,
            path=str(self.sample_dir / "sample.txt"),
            status="ready",
        )

        # User 2 attempts to download User 1's file
        download_url = f"/api/files/{uf.id}/download/"
        res = self.client.get(download_url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_endpoint_security_headers_and_sanitization(self):
        """Download endpoint sets nosniff, sanitizes filename, and never renders HTML/SVG inline."""
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_user1}")

        # Normal text download
        uf_text = UploadedFile.objects.create(
            thread=self.thread1,
            name="my\"document\r\n.txt",
            mime="text/plain",
            size=10,
            path=str(self.sample_dir / "sample.txt"),
            status="ready",
        )
        res = self.client.get(f"/api/files/{uf_text.id}/download/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        disposition = res.headers.get("Content-Disposition", "")
        self.assertIn("attachment", disposition)
        self.assertNotIn("\r", disposition)
        self.assertNotIn("\n", disposition)
        self.assertNotIn('""', disposition)

        # HTML file must NEVER be served inline or as text/html
        html_path = self.sample_dir / "sample_html.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write("<script>alert('xss')</script>")

        uf_html = UploadedFile.objects.create(
            thread=self.thread1,
            name="test.html",
            mime="text/html",
            size=30,
            path=str(html_path),
            status="ready",
        )
        res_html = self.client.get(f"/api/files/{uf_html.id}/download/")
        self.assertEqual(res_html.status_code, status.HTTP_200_OK)
        self.assertEqual(res_html.headers.get("Content-Type"), "application/octet-stream")
        self.assertIn("attachment", res_html.headers.get("Content-Disposition", ""))

        # SVG file must NEVER be served inline
        svg_path = self.sample_dir / "sample_svg.svg"
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write("<svg onload='alert(1)'></svg>")

        uf_svg = UploadedFile.objects.create(
            thread=self.thread1,
            name="vector.svg",
            mime="image/svg+xml",
            size=30,
            path=str(svg_path),
            status="ready",
        )
        res_svg = self.client.get(f"/api/files/{uf_svg.id}/download/")
        self.assertEqual(res_svg.status_code, status.HTTP_200_OK)
        self.assertEqual(res_svg.headers.get("Content-Type"), "application/octet-stream")

    def test_tool_read_file(self):
        """Test tool read_file for spreadsheets, images, truncation, and cross-user verification."""
        # 1. Spreadsheet reading (schema + sample by default)
        uf_csv = UploadedFile.objects.create(
            thread=self.thread1,
            name="sample.csv",
            mime="text/csv",
            size=77,
            path=str(self.sample_dir / "sample.csv"),
            status="ready",
        )
        from filesvc.service import file_service
        file_service.parse_file_sync(uf_csv.id)
        uf_csv.refresh_from_db()

        config_user1 = {"configurable": {"thread_id": str(self.thread1.id), "user_id": str(self.user1.id)}}
        res_default = read_file.invoke({"file_id": str(uf_csv.id)}, config=config_user1)
        self.assertIn("Total Rows", res_default)
        self.assertIn("Schema", res_default)

        # 2. Spreadsheet row range request
        res_range = read_file.invoke({"file_id": str(uf_csv.id), "row_start": 1, "row_end": 2}, config=config_user1)
        self.assertIn("Tokyo", res_range)
        self.assertIn("Rows 1 to 2", res_range)

        # 3. Image dimensions and vision payload
        uf_img = UploadedFile.objects.create(
            thread=self.thread1,
            name="sample.png",
            mime="image/png",
            size=116,
            path=str(self.sample_dir / "sample.png"),
            status="ready",
        )
        file_service.parse_file_sync(uf_img.id)
        uf_img.refresh_from_db()

        res_img = read_file.invoke({"file_id": str(uf_img.id)}, config=config_user1)
        self.assertIn("Dimensions 32x32 px", res_img)
        self.assertIn("Vision Model Payload ready", res_img)

        # 4. Bounded output with truncation
        large_txt_path = self.sample_dir / "large.txt"
        with open(large_txt_path, "w", encoding="utf-8") as f:
            f.write("Line of content.\n" * 500)

        uf_large = UploadedFile.objects.create(
            thread=self.thread1,
            name="large.txt",
            mime="text/plain",
            size=5000,
            path=str(large_txt_path),
            status="ready",
        )
        file_service.parse_file_sync(uf_large.id)
        uf_large.refresh_from_db()

        res_large = read_file.invoke({"file_id": str(uf_large.id)}, config=config_user1)
        self.assertIn("... [output truncated: remaining content omitted for safety]", res_large)

        # 5. Cross-user verification
        config_user2 = {"configurable": {"thread_id": str(self.thread2.id), "user_id": str(self.user2.id)}}
        res_cross = read_file.invoke({"file_id": str(uf_csv.id)}, config=config_user2)
        self.assertIn("Error:", res_cross)
        self.assertIn("does not belong", res_cross)

    def test_throttling_classes(self):
        """Verify DRF throttling classes for upload and chat are properly scoped."""
        upload_throttle = UploadRateThrottle()
        chat_throttle = ChatRateThrottle()
        self.assertEqual(upload_throttle.scope, "upload")
        self.assertEqual(chat_throttle.scope, "chat")
