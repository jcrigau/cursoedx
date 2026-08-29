"""Fixtures del módulo de asistencia.

La escuela de prueba se reutiliza de horarios: el parte diario y el cuadro por
curso se apoyan en el horario vigente, así que necesitan exactamente la misma
estructura y no tiene sentido construir otra distinta.
"""

from datetime import date, timedelta

import pytest

from horarios.generador import Parametros, generar
from horarios.tests.conftest import (  # noqa: F401  (escuela se reexporta como fixture)
    crear_curso,
    crear_docente,
    crear_esquema,
    crear_materia,
    crear_plan,
    crear_version,
    designar,
    escuela,
)
from licencias.models import EstadoLicencia, Licencia, TipoLicencia


def fecha_con_clases(escuela, version) -> date:
    """Una fecha del período en la que efectivamente hay clases.

    No se puede fijar un día de antemano: el generador concentra las horas en
    los días que le convienen, así que la fecha se deduce del horario generado.
    """
    dias = sorted({a.dia_semana for a in version.asignaciones.all()})
    fecha = escuela["periodo"].fecha_inicio
    while fecha.weekday() not in dias:
        fecha += timedelta(days=1)
    return fecha


def fecha_sin_clases(escuela, version) -> date:
    """Un día del período en el que no hay ninguna clase."""
    dias = {a.dia_semana for a in version.asignaciones.all()}
    fecha = escuela["periodo"].fecha_inicio
    while fecha.weekday() in dias:
        fecha += timedelta(days=1)
    return fecha


@pytest.fixture
def con_horario_publicado(escuela):
    """Una escuela con horario vigente: un curso, una materia, una docente."""
    esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    crear_plan(curso, materia, 4)
    docente = crear_docente(escuela, "Titular", 1)
    cargo = designar(escuela, docente, materia, curso)

    version = crear_version(escuela)
    generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=5))
    version.publicar()

    return {
        "escuela": escuela,
        "curso": curso,
        "materia": materia,
        "docente": docente,
        "cargo": cargo,
        "version": version,
        "fecha": fecha_con_clases(escuela, version),
        "fecha_libre": fecha_sin_clases(escuela, version),
    }


def dar_licencia(datos, desde=None, hasta=None):
    """Una licencia aprobada para la docente de la escuela de prueba."""
    institucion = datos["escuela"]["institucion"]
    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    return Licencia.objects.create(
        institucion=institucion,
        legajo=datos["docente"],
        tipo=tipo,
        fecha_inicio=desde or datos["fecha"],
        fecha_fin=hasta or datos["fecha"],
        estado=EstadoLicencia.APROBADA,
    )
