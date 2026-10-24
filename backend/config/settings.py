import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Base directory for the backend project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from repo root or backend directory if present
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "insecure-dev-secret-key-change-in-production")
DEBUG = os.getenv("DEBUG", "1").lower() in ("1", "true", "yes")

allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,backend,testserver")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts_str.split(",") if host.strip()]
if "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "chat.apps.ChatConfig",
    "filesvc.apps.FilesvcConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database configuration: support PostgreSQL via DATABASE_URL with SQLite fallback
use_sqlite = os.getenv("USE_SQLITE", "0").lower() in ("1", "true")
db_url = os.getenv("DATABASE_URL")
if db_url and not use_sqlite:
    parsed = urlparse(db_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": parsed.port or 5432,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "chat.authentication.KeycloakJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        "user": "1000/day",
        "upload": os.getenv("THROTTLE_RATE_UPLOAD", "60/minute"),
        "chat": os.getenv("THROTTLE_RATE_CHAT", "60/minute"),
    },
}

# CORS settings for frontend communication
cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

# Keycloak OpenID Connect endpoints and client ID
KEYCLOAK_INTERNAL_URL = os.getenv(
    "KEYCLOAK_INTERNAL_URL",
    "http://keycloak:8080/realms/chat/protocol/openid-connect/certs",
)
KEYCLOAK_PUBLIC_URL = os.getenv(
    "KEYCLOAK_PUBLIC_URL",
    "http://localhost:8080/realms/chat",
)
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "chat-web")

# File storage and upload limits
media_env = os.getenv("MEDIA_ROOT")
if media_env and not (os.name == "nt" and media_env.startswith("/")):
    MEDIA_ROOT = media_env
else:
    MEDIA_ROOT = str(BASE_DIR / "media")
MEDIA_URL = "/media/"
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", str(25 * 1024 * 1024)))
MAX_REQUEST_SIZE_BYTES = int(os.getenv("MAX_REQUEST_SIZE_BYTES", str(100 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_REQUEST_SIZE_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_FILE_SIZE_BYTES
MAX_ZIP_MEMBERS = int(os.getenv("MAX_ZIP_MEMBERS", "100"))
MAX_ZIP_UNCOMPRESSED_SIZE = int(os.getenv("MAX_ZIP_UNCOMPRESSED_SIZE", str(50 * 1024 * 1024)))
