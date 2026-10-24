from django.contrib.auth import get_user_model
from rest_framework import serializers
from chat.models import Thread, Message, UploadedFile, GeneratedFile

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer for authenticated user details."""
    class Meta:
        model = User
        fields = ["id", "username", "email"]

class ThreadSerializer(serializers.ModelSerializer):
    """Serializer for conversation threads."""
    class Meta:
        model = Thread
        fields = ["id", "title", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

class MessageSerializer(serializers.ModelSerializer):
    """Serializer for thread messages."""
    class Meta:
        model = Message
        fields = [
            "id",
            "thread",
            "role",
            "content",
            "status",
            "input_tokens",
            "output_tokens",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class UploadedFileSerializer(serializers.ModelSerializer):
    """Serializer for uploaded files."""
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = [
            "id",
            "thread",
            "message",
            "name",
            "mime",
            "size",
            "path",
            "parsed_path",
            "summary",
            "status",
            "error",
            "download_url",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_download_url(self, obj):
        return f"/api/files/{obj.id}/download/"

class GeneratedFileSerializer(serializers.ModelSerializer):
    """Serializer for agent-generated files."""
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = GeneratedFile
        fields = [
            "id",
            "thread",
            "name",
            "kind",
            "version",
            "parent",
            "spec",
            "path",
            "download_url",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_download_url(self, obj):
        return f"/api/generated/{obj.id}/download/"
