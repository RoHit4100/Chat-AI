import uuid
from django.conf import settings
from django.db import models
from chat.validators import validate_safe_filename

class Thread(models.Model):
    """Conversation thread associated with an authenticated user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="threads")
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.title} ({self.id})"

class Message(models.Model):
    """Message belonging to a conversation thread."""
    STATUS_CHOICES = [
        ("complete", "complete"),
        ("failed", "failed"),
        ("stopped", "stopped"),
    ]

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=32)
    content = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="complete")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:30]}"

class UploadedFile(models.Model):
    """File uploaded by a user within a conversation thread."""
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("ready", "ready"),
        ("failed", "failed"),
    ]

    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="uploaded_files")
    message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_files")
    name = models.CharField(max_length=255, validators=[validate_safe_filename])
    mime = models.CharField(max_length=128)
    size = models.PositiveBigIntegerField()
    path = models.CharField(max_length=1024)
    parsed_path = models.CharField(max_length=1024, blank=True, default="")
    summary = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.status})"

class GeneratedFile(models.Model):
    """File generated during agent execution within a thread."""
    thread = models.ForeignKey(Thread, on_delete=models.CASCADE, related_name="generated_files")
    name = models.CharField(max_length=255, validators=[validate_safe_filename])
    kind = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    spec = models.JSONField(default=dict, blank=True)
    path = models.CharField(max_length=1024)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} v{self.version} ({self.kind})"
