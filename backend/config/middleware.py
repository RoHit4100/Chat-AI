import time
import uuid
import logging

logger = logging.getLogger("django.request")

class RequestLoggingMiddleware:
    """Middleware that assigns a request_id and emits structured logs for incoming HTTP requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id

        start_time = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        user_id = str(getattr(request.user, "id", "anonymous")) if getattr(request, "user", None) and request.user.is_authenticated else "anonymous"

        extra = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
        }

        # Don't clutter logs with heartbeat or static health pings
        if not request.path.startswith("/static/"):
            logger.info(
                "%s %s %s (%sms)",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                extra=extra,
            )

        response["X-Request-ID"] = request_id
        return response

