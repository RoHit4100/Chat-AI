from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from chat.models import Thread
from chat.serializers import ThreadSerializer, MessageSerializer, UserSerializer

class MeView(APIView):
    """Return profile details for the currently authenticated user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class ThreadViewSet(viewsets.ModelViewSet):
    """CRUD operations on conversation threads, strictly scoped to request.user."""
    serializer_class = ThreadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Filter all queries by request.user
        return Thread.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # Assign thread owner on creation
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        # get_object() automatically applies get_queryset(), returning 404 if not owned
        thread = self.get_object()
        messages = thread.messages.all()
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)
