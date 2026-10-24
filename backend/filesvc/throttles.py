from rest_framework.throttling import UserRateThrottle

class UploadRateThrottle(UserRateThrottle):
    """Throttle for file upload operations."""
    scope = "upload"

class ChatRateThrottle(UserRateThrottle):
    """Throttle for chat messaging and streaming requests."""
    scope = "chat"
