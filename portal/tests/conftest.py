"""Escuela de prueba con un docente que tiene usuario del portal."""

from datetime import date

import pytest

from core.models import Membresia, Rol, Usuario
from horarios.tests.conftest import escuela  # noqa: F401  (fixture reexportada)
from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo

# Coordenadas de referencia para las pruebas de fichaje.
LATITUD_ESCUELA = -33.301726
LONGITUD_ESCUELA = -66.337752


@pytest.fixture
def escuela_ubicada(escuela):  # noqa: F811
    institucion = escuela["institucion"]
    institucion.latitud = LATITUD_ESCUELA
    institucion.longitud = LONGITUD_ESCUELA
    institucion.radio_fichaje_metros = 200
    institucion.save()
    return escuela


@pytest.fixture
def docente_con_portal(escuela_ubicada):
    """Un docente con legajo, cargo y usuario vinculado."""
    institucion = escuela_ubicada["institucion"]
    usuario = Usuario.objects.create_user(
        email="docente@uno.edu.ar", password="clave-larga-123", nombre="Ana", apellido="Suárez"
    )
    Membresia.objects.create(usuario=usuario, institucion=institucion, rol=Rol.DOCENTE)
    legajo = Legajo.objects.create(
        institucion=institucion,
        apellido="Suárez",
        nombre="Ana",
        cuil="27-30111222-3",
        usuario=usuario,
    )
    Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.CARGO_BASE,
        denominacion="Preceptor/a",
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=date(2024, 3, 1),
    )
    return {"escuela": escuela_ubicada, "usuario": usuario, "legajo": legajo}
