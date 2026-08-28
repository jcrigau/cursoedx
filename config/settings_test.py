"""Configuración para correr las pruebas.

Fija el entorno antes de importar la configuración real, así los tests no
dependen de que exista un ``.env`` ni de la base de datos de desarrollo.
"""

import os

os.environ.setdefault("SGE_DEBUG", "1")
os.environ["SGE_DATABASE_URL"] = ""  # SQLite en memoria, siempre

from .settings import *  # noqa: F403,E402

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}

# Hashear con PBKDF2 en cada test cuesta segundos; en pruebas no aporta nada.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

LANGUAGE_CODE = "es-ar"
