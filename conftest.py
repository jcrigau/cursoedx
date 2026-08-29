"""Fixtures compartidas por las pruebas."""

import pytest

from core.models import Institucion, Membresia, Rol, Usuario


@pytest.fixture(autouse=True)
def media_en_temporal(settings, tmp_path):
    """Los archivos subidos en las pruebas van a un directorio descartable.

    Sin esto, cargar_piloto (que ahora adjunta fotos) y cualquier prueba que
    suba un archivo dejarían basura en el media/ real del proyecto.
    """
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def institucion(db):
    return Institucion.objects.create(nombre="Escuela Uno", nombre_corto="Uno")


@pytest.fixture
def otra_institucion(db):
    return Institucion.objects.create(nombre="Escuela Dos", nombre_corto="Dos")


@pytest.fixture
def secretaria(db, institucion):
    """Usuaria de secretaría con acceso solo a la primera institución."""
    usuaria = Usuario.objects.create_user(
        email="secretaria@uno.edu.ar",
        password="clave-de-prueba-123",
        nombre="Ana",
        apellido="Pérez",
        is_staff=True,
    )
    Membresia.objects.create(usuario=usuaria, institucion=institucion, rol=Rol.SECRETARIA)
    return usuaria
