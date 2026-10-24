"""WSGI config for config project."""
import os
from django.core.wsgi import get_wsgi_application

# Set settings module for WSGI entrypoint
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
