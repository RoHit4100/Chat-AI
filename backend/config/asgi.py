"""ASGI config for config project."""
import os
from django.core.asgi import get_asgi_application

# Set settings module for ASGI entrypoint
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
