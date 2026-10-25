import json
import os
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from chat.authentication import aauthenticate_token
from chat.models import Thread, Message
from chat.serializers import ThreadSerializer, MessageSerializer, UserSerializer
from chat.streaming import acquire_stream_lock, release_stream_lock, stream_chat_turn
from filesvc.throttles import ChatRateThrottle

@method_decorator(csrf_exempt, name="dispatch")
class MeView(APIView):
    """Return profile details for the currently authenticated user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

@method_decorator(csrf_exempt, name="dispatch")
class ThreadViewSet(viewsets.ModelViewSet):
    """CRUD operations on conversation threads, strictly scoped to request.user."""
    serializer_class = ThreadSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ChatRateThrottle]

    def get_queryset(self):
        return Thread.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_destroy(self, instance):
        """Clean up disk files and checkpoints when a thread is deleted to prevent bloat."""
        for uf in instance.uploaded_files.all():
            if uf.path and os.path.exists(uf.path):
                try:
                    os.remove(uf.path)
                except Exception:
                    pass
            if uf.parsed_path and os.path.exists(uf.parsed_path):
                try:
                    os.remove(uf.parsed_path)
                except Exception:
                    pass

        for gf in instance.generated_files.all():
            if gf.path and os.path.exists(gf.path):
                try:
                    os.remove(gf.path)
                except Exception:
                    pass

        from agent.checkpointer import delete_thread_checkpoints
        delete_thread_checkpoints(str(instance.id))
        instance.delete()

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        thread = self.get_object()
        messages = thread.messages.all()
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

async def _authenticate_async_request(request):
    """Extract Bearer token and authenticate asynchronously."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        user, _ = await aauthenticate_token(parts[1])
        return user
    except Exception:
        return None

@csrf_exempt
async def stream_thread_view(request, id):
    """Async SSE streaming view for thread conversations."""
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)

    user = await _authenticate_async_request(request)
    if not user:
        return HttpResponse(json.dumps({"detail": "Unauthorized"}), status=401, content_type="application/json")

    request.user = user
    throttle = ChatRateThrottle()
    if not throttle.allow_request(request, view=None):
        return HttpResponse(json.dumps({"detail": "Request was throttled."}), status=429, content_type="application/json")

    try:
        thread = await Thread.objects.aget(id=id)
    except (Thread.DoesNotExist, ValueError):
        return HttpResponse(json.dumps({"detail": "Thread not found."}), status=404, content_type="application/json")

    if thread.user_id != user.id:
        return HttpResponse(json.dumps({"detail": "Thread not found."}), status=404, content_type="application/json")

    # Enforce single concurrent stream per thread
    if not await acquire_stream_lock(str(thread.id)):
        return HttpResponse(
            json.dumps({"detail": "A stream is already active on this thread."}),
            status=409,
            content_type="application/json",
        )

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        await release_stream_lock(str(thread.id))
        return HttpResponse(json.dumps({"detail": "Invalid JSON."}), status=400, content_type="application/json")

    user_content = body.get("message", "").strip()
    if not user_content:
        await release_stream_lock(str(thread.id))
        return HttpResponse(json.dumps({"detail": "Message cannot be empty."}), status=400, content_type="application/json")

    max_len = int(os.getenv("MAX_MESSAGE_LENGTH", "32000"))
    if len(user_content) > max_len:
        await release_stream_lock(str(thread.id))
        return HttpResponse(
            json.dumps({"detail": f"Message exceeds maximum allowed length of {max_len} characters."}),
            status=400,
            content_type="application/json",
        )

    attached_file_ids = body.get("files", [])

    # Save user message to database
    user_msg = await Message.objects.acreate(thread=thread, role="user", content=user_content, status="complete")

    # Link attached files belonging to this thread to prevent orphaned uploads
    if attached_file_ids and isinstance(attached_file_ids, list):
        from chat.models import UploadedFile
        await UploadedFile.objects.filter(
            id__in=attached_file_ids,
            thread=thread,
            message__isnull=True,
        ).aupdate(message=user_msg)

    # Auto-generate thread title from first message
    msg_count = await Message.objects.filter(thread=thread).acount()
    if msg_count <= 1 or thread.title in ("New Thread", ""):
        thread.title = user_content[:50].strip()
        await thread.asave(update_fields=["title"])

    response = StreamingHttpResponse(
        stream_chat_turn(thread=thread, user_prompt=user_content),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response

@csrf_exempt
async def regenerate_thread_view(request, id):
    """Async endpoint to prune last assistant turn from checkpoint and re-run from last user message."""
    if request.method != "POST":
        return HttpResponse("Method Not Allowed", status=405)

    user = await _authenticate_async_request(request)
    if not user:
        return HttpResponse(json.dumps({"detail": "Unauthorized"}), status=401, content_type="application/json")

    request.user = user
    throttle = ChatRateThrottle()
    if not throttle.allow_request(request, view=None):
        return HttpResponse(json.dumps({"detail": "Request was throttled."}), status=429, content_type="application/json")

    try:
        thread = await Thread.objects.aget(id=id)
    except (Thread.DoesNotExist, ValueError):
        return HttpResponse(json.dumps({"detail": "Thread not found."}), status=404, content_type="application/json")

    if thread.user_id != user.id:
        return HttpResponse(json.dumps({"detail": "Thread not found."}), status=404, content_type="application/json")

    # Enforce single concurrent stream per thread
    if not await acquire_stream_lock(str(thread.id)):
        return HttpResponse(
            json.dumps({"detail": "A stream is already active on this thread."}),
            status=409,
            content_type="application/json",
        )

    last_assistant = await Message.objects.filter(thread=thread, role="assistant").order_by("-created_at").afirst()
    if not last_assistant:
        await release_stream_lock(str(thread.id))
        return HttpResponse(json.dumps({"detail": "No assistant message to regenerate."}), status=400, content_type="application/json")

    response = StreamingHttpResponse(
        stream_chat_turn(
            thread=thread,
            is_regenerate=True,
            existing_assistant_message=last_assistant,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
