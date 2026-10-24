import datetime
from unittest.mock import MagicMock, patch
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import exceptions, status
from rest_framework.test import APIClient
import jwt

from chat.authentication import authenticate_token, aauthenticate_token
from chat.models import Thread, Message, UploadedFile
from chat.validators import validate_safe_filename

User = get_user_model()

# Generate an RSA key pair for testing token signing and verification
TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()

class MockSigningKey:
    """Mock PyJWK signing key wrapper holding the public key."""
    def __init__(self, key):
        self.key = key

def make_test_token(
    sub="test-user-sub-1",
    email="user1@example.com",
    iss=None,
    azp=None,
    expires_in_seconds=3600,
    key=TEST_PRIVATE_KEY,
):
    """Generate a signed RS256 JWT for testing."""
    iss = iss or settings.KEYCLOAK_PUBLIC_URL
    azp = azp or settings.KEYCLOAK_CLIENT_ID
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": sub,
        "email": email,
        "iss": iss,
        "azp": azp,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-kid"})

class KeycloakAuthAndApiTests(TestCase):
    """Unit and integration tests for Keycloak JWT auth, threads CRUD, and user isolation."""

    def setUp(self):
        self.client = APIClient()

        # Mock the JWKS client to return the test public key
        self.mock_jwks = MagicMock()
        self.mock_jwks.get_signing_key_from_jwt.return_value = MockSigningKey(TEST_PUBLIC_KEY)
        self.patcher = patch("chat.authentication.get_jwks_client", return_value=self.mock_jwks)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_valid_token_accepted(self):
        """A valid Keycloak token authenticates the user and creates a local Django User."""
        token = make_test_token(sub="keycloak-user-1", email="user1@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "keycloak-user-1")
        self.assertEqual(response.data["email"], "user1@example.com")

        # Verify Django user was created in DB
        self.assertTrue(User.objects.filter(username="keycloak-user-1").exists())

    def test_expired_token_rejected(self):
        """Expired tokens must be rejected with HTTP 401."""
        expired_token = make_test_token(expires_in_seconds=-120)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")

        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_issuer_rejected(self):
        """Tokens with an unexpected issuer claim must be rejected with HTTP 401."""
        bad_issuer_token = make_test_token(iss="http://malicious-idp.example.com/realms/fake")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {bad_issuer_token}")

        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_wrong_azp_rejected(self):
        """Tokens with an unauthorized party (azp) not matching the client ID must be rejected."""
        bad_azp_token = make_test_token(azp="unauthorized-client-app")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {bad_azp_token}")

        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_b_gets_404_on_user_a_thread(self):
        """User B must receive 404 Not Found when trying to access or manipulate User A's thread."""
        token_a = make_test_token(sub="user-a", email="a@example.com")
        token_b = make_test_token(sub="user-b", email="b@example.com")

        # User A creates a thread
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        create_resp = self.client.post("/api/threads/", {"title": "User A Private Thread"})
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        thread_id = create_resp.data["id"]

        # Add a message to User A's thread
        thread_obj = Thread.objects.get(id=thread_id)
        Message.objects.create(thread=thread_obj, role="user", content="Hello from User A")

        # User B tries to retrieve User A's thread
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_b}")
        detail_resp = self.client.get(f"/api/threads/{thread_id}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_404_NOT_FOUND)

        # User B tries to list messages in User A's thread
        messages_resp = self.client.get(f"/api/threads/{thread_id}/messages/")
        self.assertEqual(messages_resp.status_code, status.HTTP_404_NOT_FOUND)

        # User B tries to update User A's thread
        update_resp = self.client.put(f"/api/threads/{thread_id}/", {"title": "Hacked Title"})
        self.assertEqual(update_resp.status_code, status.HTTP_404_NOT_FOUND)

        # User B tries to delete User A's thread
        delete_resp = self.client.delete(f"/api/threads/{thread_id}/")
        self.assertEqual(delete_resp.status_code, status.HTTP_404_NOT_FOUND)

        # Confirm thread still exists with original title
        thread_obj.refresh_from_db()
        self.assertEqual(thread_obj.title, "User A Private Thread")

    def test_threads_crud_and_messages_listing(self):
        """Authenticated user can create, read, update, list messages, and delete their threads."""
        token = make_test_token(sub="crud-user", email="crud@example.com")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 1. Create thread
        resp_create = self.client.post("/api/threads/", {"title": "Research LangGraph"})
        self.assertEqual(resp_create.status_code, status.HTTP_201_CREATED)
        thread_id = resp_create.data["id"]

        # 2. List threads
        resp_list = self.client.get("/api/threads/")
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_list.data), 1)

        # 3. Retrieve detail
        resp_detail = self.client.get(f"/api/threads/{thread_id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_detail.data["title"], "Research LangGraph")

        # 4. Partial update (PATCH)
        resp_patch = self.client.patch(f"/api/threads/{thread_id}/", {"title": "LangGraph Notes"})
        self.assertEqual(resp_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_patch.data["title"], "LangGraph Notes")

        # 5. Add messages and verify listing
        thread_obj = Thread.objects.get(id=thread_id)
        Message.objects.create(thread=thread_obj, role="user", content="How does LangGraph work?")
        Message.objects.create(thread=thread_obj, role="assistant", content="It creates stateful graphs.")

        resp_messages = self.client.get(f"/api/threads/{thread_id}/messages/")
        self.assertEqual(resp_messages.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_messages.data), 2)
        self.assertEqual(resp_messages.data[0]["role"], "user")
        self.assertEqual(resp_messages.data[1]["role"], "assistant")

        # 6. Delete thread
        resp_delete = self.client.delete(f"/api/threads/{thread_id}/")
        self.assertEqual(resp_delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Thread.objects.filter(id=thread_id).exists())

    def test_authenticate_token_function_reusability(self):
        """Reusable authenticate_token function returns (user, payload) for valid tokens."""
        token = make_test_token(sub="direct-func-user", email="func@example.com")
        user, payload = authenticate_token(token)
        self.assertEqual(user.username, "direct-func-user")
        self.assertEqual(user.email, "func@example.com")
        self.assertEqual(payload["sub"], "direct-func-user")

    async def test_async_authenticate_token_wrapper(self):
        """Reusable aauthenticate_token function works in async views and coroutines."""
        token = make_test_token(sub="async-func-user", email="async@example.com")
        user, payload = await aauthenticate_token(token)
        self.assertEqual(user.username, "async-func-user")
        self.assertEqual(payload["sub"], "async-func-user")

    def test_filename_validator_rejects_path_traversal(self):
        """Filename validator rejects directory traversal attacks."""
        with self.assertRaises(ValidationError):
            validate_safe_filename("../../../etc/passwd")
        with self.assertRaises(ValidationError):
            validate_safe_filename("subfolder/file.txt")
        with self.assertRaises(ValidationError):
            validate_safe_filename("..")
        self.assertEqual(validate_safe_filename("document.pdf"), "document.pdf")
