"""Fixtures compartidas por las pruebas."""

import pytest

from core.models import Institucion, Membresia, Rol, Usuario


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
