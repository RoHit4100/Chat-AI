from django.conf import settings
from django.contrib.auth import get_user_model
import jwt
from jwt import PyJWKClient
from rest_framework import authentication, exceptions
from asgiref.sync import sync_to_async

# Global cached JWKS client instance across requests
_jwks_client = None

def get_jwks_client() -> PyJWKClient:
    """Return a singleton instance of PyJWKClient configured with key caching."""
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            uri=settings.KEYCLOAK_INTERNAL_URL,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=3600,
        )
    return _jwks_client

def authenticate_token(token: str):
    """Validate a Keycloak JWT token, return (user, payload) or raise AuthenticationFailed."""
    if not token or not isinstance(token, str):
        raise exceptions.AuthenticationFailed("Token is missing or invalid.")

    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.KEYCLOAK_PUBLIC_URL,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
            },
        )
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed("Token has expired.")
    except jwt.InvalidIssuerError:
        raise exceptions.AuthenticationFailed("Token issuer is invalid.")
    except Exception as exc:
        raise exceptions.AuthenticationFailed(f"Token validation failed: {exc}")

    # Validate azp (Authorized Party) matches client ID
    if payload.get("azp") != settings.KEYCLOAK_CLIENT_ID:
        raise exceptions.AuthenticationFailed("Token azp does not match client ID.")

    sub = payload.get("sub")
    if not sub:
        raise exceptions.AuthenticationFailed("Token is missing required sub claim.")

    email = payload.get("email", "") or ""

    # Get or create local Django User mapped to Keycloak sub claim
    User = get_user_model()
    user, created = User.objects.get_or_create(username=sub, defaults={"email": email})
    if not created and email and user.email != email:
        user.email = email
        user.save(update_fields=["email"])

    return user, payload

# Reusable asynchronous wrapper for async views
aauthenticate_token = sync_to_async(authenticate_token, thread_sensitive=True)

class KeycloakJWTAuthentication(authentication.BaseAuthentication):
    """DRF Authentication class for Keycloak JWT tokens."""

    def authenticate_header(self, request):
        # Return Bearer to ensure DRF responds with HTTP 401 Unauthorized on auth failures
        return "Bearer"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        token = parts[1]
        user, payload = authenticate_token(token)
        return (user, payload)
