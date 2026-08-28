"""Escuela mínima para probar el generador.

Se arma a mano y bien chica para que cada prueba corra en menos de un segundo:
lo que se verifica son las reglas, no el tamaño.
"""

from datetime import date, time

import pytest

from estructura.models import (
    BloqueHorario,
    CicloLectivo,
    Curso,
    EsquemaHorario,
    Materia,
    MateriaPlan,
    Nivel,
    PeriodoAcademico,
    TipoBloque,
    TipoNivel,
    Turno,
)
from horarios.models import VersionHorario
from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo


@pytest.fixture
def escuela(institucion, db):
    nivel = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    ciclo = CicloLectivo.objects.create(
        institucion=institucion,
        anio=2026,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 15),
    )
    periodo = PeriodoAcademico.objects.create(
        ciclo=ciclo,
        nombre="1er cuatrimestre",
        orden=1,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 7, 31),
    )
    turno = Turno.objects.create(
        institucion=institucion,
        nivel=nivel,
        nombre="Mañana",
        hora_inicio=time(8, 0),
        hora_fin=time(12, 0),
    )
    return {
        "institucion": institucion,
        "nivel": nivel,
        "ciclo": ciclo,
        "periodo": periodo,
        "turno": turno,
    }


def crear_esquema(escuela, nombre="Común", horas_por_dia=4, dias=3, inicio=time(8, 0)):
    """Grilla rectangular: ``dias`` días con ``horas_por_dia`` horas de 40'."""
    esquema = EsquemaHorario.objects.create(
        institucion=escuela["institucion"], turno=escuela["turno"], nombre=nombre
    )
    for dia in range(dias):
        momento = inicio
        for orden in range(1, horas_por_dia + 1):
            fin_minutos = (momento.hour * 60 + momento.minute + 40) % (24 * 60)
            fin = time(fin_minutos // 60, fin_minutos % 60)
            BloqueHorario.objects.create(
                esquema=esquema,
                dia_semana=dia,
                orden=orden,
                tipo=TipoBloque.CLASE,
                hora_inicio=momento,
                hora_fin=fin,
                etiqueta=f"{orden}ª hora",
            )
            momento = fin
    return esquema


def crear_curso(escuela, esquema, anio=1, division="A"):
    return Curso.objects.create(
        institucion=escuela["institucion"],
        ciclo_lectivo=escuela["ciclo"],
        nivel=escuela["nivel"],
        anio_estudio=anio,
        division=division,
        turno=escuela["turno"],
        esquema_horario=esquema,
    )


def crear_materia(escuela, nombre):
    return Materia.objects.create(
        institucion=escuela["institucion"], nivel=escuela["nivel"], nombre=nombre
    )


def crear_plan(curso, materia, horas, periodo=None):
    from estructura.models import Vigencia

    return MateriaPlan.objects.create(
        curso=curso,
        materia=materia,
        horas_semanales=horas,
        vigencia=Vigencia.PERIODO if periodo else Vigencia.ANUAL,
        periodo=periodo,
    )


def crear_docente(escuela, apellido, cuil_sufijo):
    return Legajo.objects.create(
        institucion=escuela["institucion"],
        apellido=apellido,
        nombre="Docente",
        cuil=f"27-3000{cuil_sufijo:04d}-1",
    )


def designar(escuela, docente, materia, curso=None, horas=4):
    """Le da al docente el cargo de esa materia (y curso, si se indica)."""
    return Cargo.objects.create(
        institucion=escuela["institucion"],
        legajo=docente,
        tipo=TipoCargo.HORAS_CATEDRA,
        nivel=escuela["nivel"],
        materia=materia,
        curso=curso,
        horas_semanales=horas,
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=date(2026, 3, 1),
    )


def crear_version(escuela, nombre="Borrador"):
    return VersionHorario.objects.create(
        institucion=escuela["institucion"], periodo=escuela["periodo"], nombre=nombre
    )
