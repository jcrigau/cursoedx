"""Parte diario: quién tiene que estar hoy, y qué pasó con cada uno.

Se arma solo, cruzando el horario vigente con las licencias y las coberturas
del día. Ese cruce es lo que le ahorra el trabajo a la secretaría: en lugar de
mirar el horario en papel, restar los que están de licencia y acordarse de qué
suplente entró, abre el parte y solo marca las novedades.

Las horas de un titular de licencia se muestran según lo que la escuela haya
decidido: pasan al suplente designado, o quedan marcadas como sin cobertura
—los alumnos quedan libres—, incluida la situación de que todavía nadie haya
decidido nada.
"""

from dataclasses import dataclass, field
from datetime import date

from estructura.models import PeriodoAcademico
from horarios.models import AsignacionHoraria, EstadoVersion, VersionHorario
from legajos.models import Legajo
from licencias.models import Cobertura, TipoCobertura, coberturas_vigentes, licencias_vigentes
from portal.models import AvisoInasistencia, EstadoAviso, Fichada, TipoFichada

from .models import RegistroAsistencia


@dataclass
class LineaParte:
    """Una persona que debía trabajar hoy."""

    legajo: Legajo
    horas: int = 0
    cursos: list[str] = field(default_factory=list)
    licencia = None
    es_suplente: bool = False
    titular: Legajo | None = None
    registro: RegistroAsistencia | None = None
    aviso = None  # el docente avisó que no venía (portal)
    fichada = None  # marcó su entrada desde el celular (portal)

    @property
    def detalle_cursos(self) -> str:
        return ", ".join(sorted(set(self.cursos)))

    @property
    def estado(self) -> str:
        if self.registro:
            return self.registro.get_estado_display()
        return "Sin registrar"


@dataclass
class HoraSinCobertura:
    """Una hora que queda sin docente: el curso no tiene clase."""

    curso: str
    materia: str
    titular: Legajo
    hora_inicio: object
    decidida: bool  # False si nadie resolvió todavía qué hacer


@dataclass
class ParteDiario:
    fecha: date
    version: VersionHorario | None = None
    lineas: list[LineaParte] = field(default_factory=list)
    sin_cobertura: list[HoraSinCobertura] = field(default_factory=list)
    aviso: str = ""

    @property
    def hay_clases(self) -> bool:
        return self.version is not None and bool(self.lineas or self.sin_cobertura)

    @property
    def sin_registrar(self) -> int:
        return sum(1 for linea in self.lineas if linea.registro is None)


def periodo_de(institucion, fecha: date) -> PeriodoAcademico | None:
    """Período académico que contiene esa fecha."""
    return (
        PeriodoAcademico.objects.filter(
            ciclo__institucion=institucion, fecha_inicio__lte=fecha, fecha_fin__gte=fecha
        )
        .select_related("ciclo")
        .first()
    )


def version_vigente(institucion, fecha: date) -> VersionHorario | None:
    """Horario publicado para el período de esa fecha."""
    periodo = periodo_de(institucion, fecha)
    if periodo is None:
        return None
    return VersionHorario.objects.filter(
        institucion=institucion, periodo=periodo, estado=EstadoVersion.VIGENTE
    ).first()


def parte_diario(institucion, fecha: date) -> ParteDiario:
    """Arma el parte de un día."""
    parte = ParteDiario(fecha=fecha)

    if periodo_de(institucion, fecha) is None:
        parte.aviso = "La fecha está fuera del ciclo lectivo."
        return parte

    version = version_vigente(institucion, fecha)
    if version is None:
        parte.aviso = (
            "No hay un horario vigente para este período. Publicá una versión de "
            "horario para que el parte se arme solo."
        )
        return parte
    parte.version = version

    asignaciones = list(
        AsignacionHoraria.objects.filter(version=version, dia_semana=fecha.weekday())
        .select_related("curso", "materia", "legajo", "cargo")
        .order_by("hora_inicio")
    )
    if not asignaciones:
        parte.aviso = "No hay clases este día según el horario vigente."
        return parte

    licencias = {
        licencia.legajo_id: licencia for licencia in licencias_vigentes(institucion, fecha)
    }
    coberturas = {
        cobertura.cargo_id: cobertura for cobertura in coberturas_vigentes(institucion, fecha)
    }

    lineas: dict[int, LineaParte] = {}

    for asignacion in asignaciones:
        if asignacion.legajo_id is None:
            continue  # hora sin docente designado: es tema del horario, no del parte

        licencia = licencias.get(asignacion.legajo_id)
        if licencia is None:
            _sumar(lineas, asignacion.legajo, asignacion)
            continue

        cobertura = coberturas.get(asignacion.cargo_id)
        if cobertura is not None and cobertura.tipo == TipoCobertura.SUPLENTE:
            linea = _sumar(lineas, cobertura.suplente, asignacion)
            linea.es_suplente = True
            linea.titular = asignacion.legajo
            continue

        parte.sin_cobertura.append(
            HoraSinCobertura(
                curso=str(asignacion.curso),
                materia=asignacion.materia.nombre,
                titular=asignacion.legajo,
                hora_inicio=asignacion.hora_inicio,
                decidida=cobertura is not None,
            )
        )

    registros = {
        registro.legajo_id: registro
        for registro in RegistroAsistencia.objects.filter(
            institucion=institucion, fecha=fecha
        ).select_related("licencia")
    }
    # Lo que los propios docentes informaron desde el portal (F5).
    avisos = {
        aviso.legajo_id: aviso
        for aviso in AvisoInasistencia.objects.filter(institucion=institucion, fecha=fecha).exclude(
            estado=EstadoAviso.ANULADO
        )
    }
    fichadas = {
        fichada.legajo_id: fichada
        for fichada in Fichada.objects.filter(
            institucion=institucion, fecha=fecha, tipo=TipoFichada.ENTRADA
        )
    }

    for legajo_id, linea in lineas.items():
        linea.registro = registros.get(legajo_id)
        linea.licencia = licencias.get(legajo_id)
        linea.aviso = avisos.get(legajo_id)
        linea.fichada = fichadas.get(legajo_id)

    parte.lineas = sorted(lineas.values(), key=lambda linea: linea.legajo.nombre_completo)
    return parte


def _sumar(lineas: dict, legajo, asignacion) -> LineaParte:
    linea = lineas.get(legajo.id)
    if linea is None:
        linea = LineaParte(legajo=legajo)
        lineas[legajo.id] = linea
    linea.horas += 1
    linea.cursos.append(str(asignacion.curso))
    return linea


def coberturas_pendientes(institucion, fecha: date) -> list[Cobertura]:
    """Cargos con licencia vigente sobre los que todavía no se decidió nada."""
    pendientes = []
    for licencia in licencias_vigentes(institucion, fecha):
        decididos = {
            cobertura.cargo_id
            for cobertura in licencia.coberturas.filter(
                fecha_inicio__lte=fecha, fecha_fin__gte=fecha
            )
        }
        for cargo in licencia.cargos_afectados():
            if cargo.id not in decididos:
                pendientes.append((licencia, cargo))
    return pendientes
