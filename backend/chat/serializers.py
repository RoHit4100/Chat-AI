from django.db import models
from django.contrib.auth import get_user_model
from rest_framework import serializers
from chat.models import Thread, Message, UploadedFile, GeneratedFile

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer for authenticated user details."""
    class Meta:
        model = User
        fields = ["id", "username", "email"]

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

class MessageSerializer(serializers.ModelSerializer):
    """Serializer for thread messages, including attached uploaded files."""
    files = UploadedFileSerializer(source="uploaded_files", many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "thread",
            "role",
            "content",
            "files",
            "status",
            "input_tokens",
            "output_tokens",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

class ThreadSerializer(serializers.ModelSerializer):
    """Serializer for conversation threads with aggregate token totals exposed."""
    total_input_tokens = serializers.SerializerMethodField()
    total_output_tokens = serializers.SerializerMethodField()
    total_tokens = serializers.SerializerMethodField()

    class Meta:
        model = Thread
        fields = [
            "id",
            "title",
            "total_input_tokens",
            "total_output_tokens",
            "total_tokens",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_total_input_tokens(self, obj):
        agg = obj.messages.aggregate(val=models.Sum("input_tokens"))
        return agg["val"] or 0

    def get_total_output_tokens(self, obj):
        agg = obj.messages.aggregate(val=models.Sum("output_tokens"))
        return agg["val"] or 0

    def get_total_tokens(self, obj):
        agg = obj.messages.aggregate(
            inp=models.Sum("input_tokens"),
            out=models.Sum("output_tokens"),
        )
        return (agg["inp"] or 0) + (agg["out"] or 0)

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
