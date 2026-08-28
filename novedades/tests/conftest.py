"""Datos mínimos para probar la compilación de novedades."""

from datetime import date

import pytest

from estructura.models import Materia, Nivel, TipoNivel
from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo
from licencias.models import EstadoLicencia, Licencia, TipoLicencia
from novedades.models import PeriodoNovedades

# Mes de referencia de las pruebas.
ANIO, MES = 2026, 5
INICIO = date(ANIO, MES, 1)


@pytest.fixture
def nivel(institucion, db):
    return Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)


@pytest.fixture
def periodo(institucion, db):
    return PeriodoNovedades.objects.create(institucion=institucion, anio=ANIO, mes=MES)


@pytest.fixture
def docente(institucion, db):
    return Legajo.objects.create(
        institucion=institucion,
        apellido="Ríos",
        nombre="Elena",
        cuil="27-30456789-2",
        obra_social="OSDE",
    )


def dar_cargo(
    institucion,
    legajo,
    *,
    fuente=FuentePago.SUBVENCIONADO,
    alta=date(2024, 3, 1),
    baja=None,
    motivo_baja="",
    denominacion="Preceptor/a",
    materia=None,
    horas=None,
    nivel=None,
):
    return Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.HORAS_CATEDRA if materia else TipoCargo.CARGO_BASE,
        denominacion="" if materia else denominacion,
        materia=materia,
        nivel=nivel,
        horas_semanales=horas,
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=fuente,
        fecha_alta=alta,
        fecha_baja=baja,
        motivo_baja=motivo_baja,
    )


def dar_materia(institucion, nivel, nombre="Matemática"):
    return Materia.objects.create(institucion=institucion, nivel=nivel, nombre=nombre)


def dar_licencia(
    institucion,
    legajo,
    desde,
    hasta,
    *,
    nombre="Enfermedad",
    con_goce=True,
    impacta=None,
    aprobada=True,
):
    tipo, _creado = TipoLicencia.objects.get_or_create(
        institucion=institucion,
        nombre=nombre,
        defaults={
            "con_goce": con_goce,
            "impacta_haberes": (not con_goce) if impacta is None else impacta,
        },
    )
    return Licencia.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=tipo,
        fecha_inicio=desde,
        fecha_fin=hasta,
        estado=EstadoLicencia.APROBADA if aprobada else EstadoLicencia.SOLICITADA,
    )
