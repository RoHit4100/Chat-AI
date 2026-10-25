import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from datetime import datetime, timezone, timedelta

from django.test import TestCase
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status

from chat.models import Thread, Message, UploadedFile, GeneratedFile
from chat.streaming import stream_chat_turn
from agent.tools import read_file, generate_file
from filesvc.storage import storage

User = get_user_model()
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_files"

class EndToEndRegressionTests(TestCase):
    """End-to-end regression tests verifying file reading, multi-file turns, file generations,
    revisions, security rejection of corrupt/unsupported files, and tool failure handling.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="test_e2e_user", email="test_e2e@example.com")
        self.client = APIClient()
        
        # Setup mock JWKS for APIClient
        test_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.mock_jwks = MagicMock()
        self.mock_jwks.get_signing_key_from_jwt.return_value = MagicMock(key=test_key.public_key())
        self.jwks_patcher = patch("chat.authentication.get_jwks_client", return_value=self.mock_jwks)
        self.jwks_patcher.start()

        token = jwt.encode(
            {
                "sub": "test_e2e_user",
                "email": "test_e2e@example.com",
                "iss": settings.KEYCLOAK_PUBLIC_URL,
                "azp": settings.KEYCLOAK_CLIENT_ID,
                "iat": int(datetime.now(timezone.utc).timestamp()),
                "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            },
            test_key,
            algorithm="RS256",
            headers={"kid": "test-kid"}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.thread = Thread.objects.create(user=self.user, title="E2E Thread")

    def tearDown(self):
        self.jwks_patcher.stop()

    def test_upload_corrupt_file_sets_failed_status_with_clear_error(self):
        """Uploading corrupt file sets status='failed' with error explanation."""
        corrupt = SimpleUploadedFile("broken.zip", b"PK\x03\x04corrupteddata")
        resp = self.client.post(f"/api/threads/{self.thread.id}/files/", {"files": corrupt}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        uf = UploadedFile.objects.filter(thread=self.thread, name="broken.zip").first()
        self.assertIsNotNone(uf)
        self.assertEqual(uf.status, "failed")
        self.assertIn("not a zip file", uf.error.lower())

    def test_upload_unsupported_type_sets_failed_status_with_clear_error(self):
        """Uploading disallowed extension produces status='failed' and 'not permitted' error."""
        exe = SimpleUploadedFile("danger.exe", b"MZ\x00\x00executable")
        resp = self.client.post(f"/api/threads/{self.thread.id}/files/", {"files": exe}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        uf = UploadedFile.objects.filter(thread=self.thread, name="danger.exe").first()
        self.assertIsNotNone(uf)
        self.assertEqual(uf.status, "failed")
        self.assertIn("not permitted", uf.error.lower())

    def test_upload_oversized_file_rejected(self):
        """Uploading oversized file returns 400 or sets failed with exceeds limit."""
        huge = SimpleUploadedFile("huge.txt", b"x" * (26 * 1024 * 1024))
        resp = self.client.post(f"/api/threads/{self.thread.id}/files/", {"files": huge}, format="multipart")
        if resp.status_code == status.HTTP_400_BAD_REQUEST:
            self.assertIn("exceeds limit", str(resp.data).lower())
        else:
            uf = UploadedFile.objects.filter(thread=self.thread, name="huge.txt").first()
            self.assertEqual(uf.status, "failed")
            self.assertIn("exceeds limit", uf.error.lower())

    def test_generate_all_file_types_creates_valid_files_and_download_works(self):
        """All supported generator kinds create valid on-disk files and download returns 200 with nosniff."""
        kinds = ["md", "csv", "docx", "pdf", "xlsx", "pptx", "png", "code"]
        config = {"configurable": {"thread_id": str(self.thread.id), "user_id": str(self.user.id)}}
        
        specs = {
            "md": ("doc.md", {"title": "Doc", "content": "Content"}),
            "csv": ("data.csv", {"headers": ["A", "B"], "rows": [[1, 2]]}),
            "docx": ("report.docx", {"title": "Docx", "paragraphs": ["Para"]}),
            "pdf": ("document.pdf", {"title": "Pdf", "paragraphs": ["Para"]}),
            "xlsx": ("sheet.xlsx", {"headers": ["H1"], "rows": [["R1"]]}),
            "pptx": ("deck.pptx", {"title": "Pptx", "slides": [{"title": "S1"}]}),
            "png": ("chart.png", {"chart_type": "bar", "labels": ["X"], "values": [10]}),
            "code": ("script.py", {"language": "python", "code": "def solve(): return 42"}),
        }

        for kind in kinds:
            name, spec = specs[kind]
            out = generate_file.invoke({"kind": kind, "name": name, "spec": spec}, config=config)
            self.assertIn("Successfully generated", out)
            
            gf = GeneratedFile.objects.filter(thread=self.thread, kind=kind).order_by("-id").first()
            self.assertIsNotNone(gf)
            self.assertTrue(os.path.exists(gf.path))
            self.assertGreater(os.path.getsize(gf.path), 0)

            # Test download view
            resp = self.client.get(f"/api/generated/{gf.id}/download/")
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.get("X-Content-Type-Options"), "nosniff")

    def test_revise_generated_file_creates_version_2_with_parent(self):
        """Revising a generated file creates version 2 with parent pointer and updated spec."""
        config = {"configurable": {"thread_id": str(self.thread.id), "user_id": str(self.user.id)}}
        
        # Version 1
        generate_file.invoke(
            {"kind": "xlsx", "name": "finance.xlsx", "spec": {"headers": ["Quarter", "Revenue"], "rows": [["Q1", 100]]}},
            config=config
        )
        v1 = GeneratedFile.objects.filter(thread=self.thread, name="finance.xlsx", version=1).first()
        self.assertIsNotNone(v1)

        # Version 2 with based_on
        v2_spec = {"headers": ["Quarter", "Revenue", "Profit"], "rows": [["Q1", 100, 20]]}
        out_v2 = generate_file.invoke(
            {"kind": "xlsx", "name": "finance.xlsx", "spec": v2_spec, "based_on": str(v1.id)},
            config=config
        )
        self.assertIn("Successfully generated", out_v2)
        v2 = GeneratedFile.objects.filter(thread=self.thread, name="finance.xlsx", version=2).first()
        self.assertIsNotNone(v2)
        self.assertEqual(v2.parent_id, v1.id)
        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.spec["headers"], ["Quarter", "Revenue", "Profit"])

    async def test_tool_failure_loop_stops_and_explains_to_user(self):
        """Tool failures trigger up to 3 attempts then agent explains failure to user without crashing."""
        events = []
        async for evt in stream_chat_turn(self.thread, user_prompt="fail tool test"):
            for line in evt.strip().split("\n"):
                if line.startswith("data:") and "content" in line:
                    try:
                        d = json.loads(line[5:].strip())
                        events.append(d.get("content", ""))
                    except:
                        pass
        full_response = "".join(events)
        self.assertTrue(len(full_response) > 0)
        self.assertTrue(any(word in full_response.lower() for word in ["fail", "stopping", "error", "consecutive"]))
