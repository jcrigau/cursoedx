"""Quién puede cubrir una hora que quedó sin docente.

Cuando un curso se queda sin clase, la pregunta de la escuela es concreta y
urgente: «¿a quién llamo?». La respuesta está toda en el sistema —el horario
dice quién está en el edificio, los cargos dicen quién da esa materia, las
licencias y las DDJJ dicen quién no puede— pero hasta ahora había que cruzarla
de memoria, con el horario en papel al lado.

Se ordena por lo que sirve: primero alguien que ya está acá, que da la materia
y que tiene esa hora libre. Después, lo que se le vaya pareciendo.
"""

from dataclasses import dataclass
from datetime import date

from estructura.models import PeriodoAcademico
from horarios.models import AsignacionHoraria, FranjaNoDisponible, se_superponen
from legajos.models import EstadoLegajo, Legajo
from licencias.models import licencias_vigentes


@dataclass
class Candidato:
    """Una persona que podría cubrir la hora, con lo que hay que saber de ella."""

    legajo: Legajo
    da_la_materia: bool
    esta_en_la_escuela: bool
    tiene_clase_a_esa_hora: bool
    de_licencia: bool
    bloqueado_por_ddjj: bool
    horas_hoy: int
    otras_materias: list[str]

    @property
    def disponible(self) -> bool:
        """Se lo puede llamar: ni ocupado, ni de licencia, ni bloqueado."""
        return not (self.tiene_clase_a_esa_hora or self.de_licencia or self.bloqueado_por_ddjj)

    @property
    def por_que_no(self) -> str:
        if self.de_licencia:
            return "está de licencia"
        if self.tiene_clase_a_esa_hora:
            return "tiene clase a esa hora"
        if self.bloqueado_por_ddjj:
            return "lo declaró no disponible en su DDJJ"
        return ""

    @property
    def como_avisarle(self) -> list[str]:
        vias = []
        if self.legajo.email:
            vias.append("email")
        if self.legajo.telefono:
            vias.append("WhatsApp")
        return vias

    @property
    def puntaje(self) -> tuple:
        """Para ordenar: lo mejor primero.

        Alguien que ya está en la escuela, da la materia y tiene la hora libre
        es el reemplazo ideal —no hay que hacerlo venir ni improvisar la clase—
        y así se ordena.
        """
        return (
            not self.disponible,
            not self.da_la_materia,
            not self.esta_en_la_escuela,
            -self.horas_hoy,
            self.legajo.apellido,
        )


def buscar(institucion, asignacion: AsignacionHoraria, fecha: date) -> list[Candidato]:
    """Los posibles reemplazos para esa hora, ordenados por conveniencia."""
    version = asignacion.version
    dia = fecha.weekday()

    del_dia = list(
        AsignacionHoraria.objects.filter(version=version, dia_semana=dia)
        .exclude(legajo=None)
        .select_related("legajo")
    )
    # Quién está en el edificio hoy, y quién no puede porque ya está dando clase.
    en_la_escuela = {a.legajo_id for a in del_dia}
    horas_por_persona: dict[int, int] = {}
    ocupados = set()
    for otra in del_dia:
        horas_por_persona[otra.legajo_id] = horas_por_persona.get(otra.legajo_id, 0) + 1
        if se_superponen(
            asignacion.hora_inicio, asignacion.hora_fin, otra.hora_inicio, otra.hora_fin
        ):
            ocupados.add(otra.legajo_id)

    de_licencia = {licencia.legajo_id for licencia in licencias_vigentes(institucion, fecha)}
    bloqueados = _bloqueados_por_ddjj(institucion, asignacion, fecha)

    personas = (
        Legajo.objects.filter(institucion=institucion, estado=EstadoLegajo.ACTIVO)
        .exclude(pk=asignacion.legajo_id)
        .prefetch_related("cargos__materia")
    )

    candidatos = []
    for legajo in personas:
        materias = {
            cargo.materia.nombre for cargo in legajo.cargos.all() if cargo.materia_id is not None
        }
        candidatos.append(
            Candidato(
                legajo=legajo,
                da_la_materia=asignacion.materia.nombre in materias,
                esta_en_la_escuela=legajo.id in en_la_escuela,
                tiene_clase_a_esa_hora=legajo.id in ocupados,
                de_licencia=legajo.id in de_licencia,
                bloqueado_por_ddjj=legajo.id in bloqueados,
                horas_hoy=horas_por_persona.get(legajo.id, 0),
                otras_materias=sorted(materias - {asignacion.materia.nombre})[:3],
            )
        )

    return sorted(candidatos, key=lambda candidato: candidato.puntaje)


def _bloqueados_por_ddjj(institucion, asignacion, fecha: date) -> set[int]:
    """Quiénes declararon que esa franja no la pueden tomar.

    Solo cuentan las franjas duras: una preferencia se puede pisar si hace
    falta, un impedimento real —otra escuela, un estudio— no.
    """
    periodo = (
        PeriodoAcademico.objects.filter(
            ciclo__institucion=institucion, fecha_inicio__lte=fecha, fecha_fin__gte=fecha
        )
        .values_list("pk", flat=True)
        .first()
    )
    if periodo is None:
        return set()

    franjas = FranjaNoDisponible.objects.filter(
        declaracion__institucion=institucion,
        declaracion__periodo_id=periodo,
        dia_semana=asignacion.dia_semana,
        es_preferencia=False,
    ).select_related("declaracion")

    return {
        franja.declaracion.legajo_id
        for franja in franjas
        if se_superponen(
            asignacion.hora_inicio, asignacion.hora_fin, franja.hora_desde, franja.hora_hasta
        )
    }


def filtrar(
    candidatos: list[Candidato], *, en_la_escuela: bool, misma_materia: bool, solo_disponibles: bool
) -> list[Candidato]:
    """Aplica los filtros que eligió la secretaría."""
    resultado = candidatos
    if en_la_escuela:
        resultado = [c for c in resultado if c.esta_en_la_escuela]
    if misma_materia:
        resultado = [c for c in resultado if c.da_la_materia]
    if solo_disponibles:
        resultado = [c for c in resultado if c.disponible]
    return resultado


def licencia_de_la_hora(institucion, asignacion, fecha: date):
    """La licencia que dejó esa hora sin docente, si la hay.

    Una suplencia se apoya siempre en una licencia: es lo que la justifica y
    lo que después la convierte en alta en las novedades. Si el docente
    faltó sin licencia todavía, no hay dónde registrar el reemplazo —hay que
    cargarla primero.
    """
    if asignacion.legajo_id is None:
        return None
    return next(
        (
            licencia
            for licencia in licencias_vigentes(institucion, fecha)
            if licencia.legajo_id == asignacion.legajo_id
        ),
        None,
    )
