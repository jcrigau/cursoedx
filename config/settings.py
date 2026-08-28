"""Configuración de Django para el SGE.

Todo lo que cambia entre entornos se lee de variables de entorno (prefijo
``SGE_``), de modo que la misma imagen sirva para desarrollo y producción.
Ver ``.env.example`` para la lista completa.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(nombre: str, por_defecto: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return por_defecto
    return valor.strip().lower() in {"1", "true", "yes", "on", "si", "sí"}


def env_list(nombre: str, por_defecto: str = "") -> list[str]:
    crudo = os.environ.get(nombre, por_defecto)
    return [item.strip() for item in crudo.split(",") if item.strip()]


DEBUG = env_bool("SGE_DEBUG", False)

SECRET_KEY = os.environ.get("SGE_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "clave-insegura-solo-para-desarrollo"
    else:
        raise RuntimeError(
            "Falta SGE_SECRET_KEY. Generá una con: "
            'python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )

ALLOWED_HOSTS = env_list("SGE_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Detrás de un proxy (Caddy, Cloudflare Tunnel) los formularios necesitan
# saber desde qué origen se los sirve.
CSRF_TRUSTED_ORIGINS = env_list("SGE_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "estructura",
    "legajos",
    "horarios",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.InstitucionActualMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.institucion_actual",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


MOTORES = {
    "postgres": "django.db.backends.postgresql",
    "postgresql": "django.db.backends.postgresql",
    # MySQL es lo que ofrecen varios hospedajes económicos (PythonAnywhere,
    # entre otros). Requiere instalar mysqlclient.
    "mysql": "django.db.backends.mysql",
}


def configurar_base_de_datos() -> dict:
    """SQLite por defecto; PostgreSQL o MySQL según ``SGE_DATABASE_URL``."""
    url = os.environ.get("SGE_DATABASE_URL", "").strip()
    if not url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    partes = urlparse(url)
    motor = MOTORES.get(partes.scheme)
    if motor is None:
        raise RuntimeError(
            f"Esquema de base de datos no soportado: {partes.scheme!r}. "
            "Usá postgres://, mysql://, o dejá SGE_DATABASE_URL vacío para SQLite."
        )
    return {
        "ENGINE": motor,
        "NAME": partes.path.lstrip("/"),
        "USER": partes.username or "",
        "PASSWORD": partes.password or "",
        "HOST": partes.hostname or "",
        "PORT": str(partes.port or ""),
        "CONN_MAX_AGE": 60,
    }


DATABASES = {"default": configurar_base_de_datos()}

AUTH_USER_MODEL = "core.Usuario"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "es-ar"
TIME_ZONE = os.environ.get("SGE_TIME_ZONE", "America/Argentina/San_Luis")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Adjuntos de legajos y certificados. En producción conviene un volumen
# persistente con backup (ver REQUERIMIENTOS.md §6).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Endurecimiento para producción; en desarrollo estorbaría (no hay HTTPS).
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SGE_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = "DENY"
