"""¿Al suplente le entra esta suplencia en su horario?

Designar a alguien que a esa hora ya está dando clase en otro curso es el
error que después aparece el lunes a las 7:45, con dos cursos esperando a la
misma persona. El sistema tiene todos los datos para verlo antes: el horario
vigente dice qué da cada uno, y las coberturas dicen qué está supliendo.

Se comparan **horarios reales**, nunca identidad de bloque: dos cursos con
esquemas distintos tienen bloques distintos a la misma hora del reloj.
"""

from dataclasses import dataclass
from datetime import date

from horarios.models import AsignacionHoraria, se_superponen

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


@dataclass(frozen=True)
class Choque:
    """Una hora que se pisa con otra que la persona ya tiene."""

    dia: int
    hora_inicio: object
    hora_fin: object
    lo_nuevo: str
    lo_que_ya_tiene: str

    def __str__(self) -> str:
        return (
            f"{DIAS[self.dia].capitalize()} {self.hora_inicio:%H:%M}–{self.hora_fin:%H:%M}: "
            f"{self.lo_nuevo} se pisa con {self.lo_que_ya_tiene}"
        )


def _asignaciones_de(version, cargo):
    """Las horas del horario que corresponden a un cargo."""
    consulta = AsignacionHoraria.objects.filter(version=version, legajo=cargo.legajo_id)
    if cargo.materia_id:
        consulta = consulta.filter(materia=cargo.materia_id)
    if cargo.curso_id:
        consulta = consulta.filter(curso=cargo.curso_id)
    return consulta.select_related("materia", "curso")


def _etiqueta(asignacion) -> str:
    return f"{asignacion.materia} · {asignacion.curso}"


def ocupacion_de(institucion, legajo, desde: date, hasta: date, version) -> list[tuple]:
    """Qué tiene esa persona ocupado: lo suyo y lo que ya está supliendo."""
    from .models import Cobertura, TipoCobertura

    ocupado = [
        (asignacion.dia_semana, asignacion.hora_inicio, asignacion.hora_fin, _etiqueta(asignacion))
        for asignacion in AsignacionHoraria.objects.filter(
            version=version, legajo=legajo
        ).select_related("materia", "curso")
    ]

    # Y lo que ya se comprometió a cubrir en esas mismas fechas.
    otras = Cobertura.objects.filter(
        institucion=institucion,
        suplente=legajo,
        tipo=TipoCobertura.SUPLENTE,
        fecha_inicio__lte=hasta,
        fecha_fin__gte=desde,
    ).select_related("cargo__legajo", "cargo__materia", "cargo__curso")
    for cobertura in otras:
        for asignacion in _asignaciones_de(version, cobertura.cargo):
            ocupado.append(
                (
                    asignacion.dia_semana,
                    asignacion.hora_inicio,
                    asignacion.hora_fin,
                    f"{_etiqueta(asignacion)} (suplencia de {cobertura.cargo.legajo.apellido})",
                )
            )
    return ocupado


def revisar(institucion, suplente, cargos, desde: date, hasta: date) -> list[Choque]:
    """Los choques de horario que tendría el suplente con esos cargos.

    Sin horario publicado devuelve vacío: no hay con qué comparar, y frenar la
    designación por eso sería peor —la escuela igual tiene que cubrir el
    curso—. La pantalla avisa que no se pudo verificar.
    """
    from asistencia.parte import version_vigente

    version = version_vigente(institucion, desde)
    if version is None:
        return []

    ocupado = ocupacion_de(institucion, suplente, desde, hasta, version)
    choques = []
    for cargo in cargos:
        for nueva in _asignaciones_de(version, cargo):
            for dia, inicio, fin, que_es in ocupado:
                if dia == nueva.dia_semana and se_superponen(
                    nueva.hora_inicio, nueva.hora_fin, inicio, fin
                ):
                    choques.append(
                        Choque(
                            dia=dia,
                            hora_inicio=nueva.hora_inicio,
                            hora_fin=nueva.hora_fin,
                            lo_nuevo=_etiqueta(nueva),
                            lo_que_ya_tiene=que_es,
                        )
                    )
    return choques


def hay_horario(institucion, fecha: date) -> bool:
    from asistencia.parte import version_vigente

    return version_vigente(institucion, fecha) is not None


def revisar_varios(institucion, legajos, cargos, desde: date, hasta: date) -> dict:
    """Los choques de cada candidato, resolviendo el horario una sola vez.

    La pantalla necesita saber, antes de que la secretaría elija, a quién le
    entra y a quién no. Hacerlo persona por persona serían dos consultas por
    cada una; acá se trae el horario y las coberturas una vez y se compara en
    memoria, que para una escuela es instantáneo.
    """
    from asistencia.parte import version_vigente

    from .models import Cobertura, TipoCobertura

    version = version_vigente(institucion, desde)
    if version is None or not cargos:
        return {legajo.id: [] for legajo in legajos}

    # Lo que hay que cubrir.
    a_cubrir = []
    for cargo in cargos:
        for asignacion in _asignaciones_de(version, cargo):
            a_cubrir.append(asignacion)

    # Lo que cada uno ya tiene: sus horas del horario…
    ocupacion: dict[int, list] = {legajo.id: [] for legajo in legajos}
    for asignacion in AsignacionHoraria.objects.filter(
        version=version, legajo__in=[legajo.id for legajo in legajos]
    ).select_related("materia", "curso"):
        ocupacion[asignacion.legajo_id].append(
            (
                asignacion.dia_semana,
                asignacion.hora_inicio,
                asignacion.hora_fin,
                _etiqueta(asignacion),
            )
        )

    # …y lo que ya se comprometió a suplir en esas fechas.
    otras = Cobertura.objects.filter(
        institucion=institucion,
        suplente__in=[legajo.id for legajo in legajos],
        tipo=TipoCobertura.SUPLENTE,
        fecha_inicio__lte=hasta,
        fecha_fin__gte=desde,
    ).select_related("cargo__legajo", "cargo__materia", "cargo__curso")
    for cobertura in otras:
        for asignacion in _asignaciones_de(version, cobertura.cargo):
            ocupacion.setdefault(cobertura.suplente_id, []).append(
                (
                    asignacion.dia_semana,
                    asignacion.hora_inicio,
                    asignacion.hora_fin,
                    f"{_etiqueta(asignacion)} (suplencia de {cobertura.cargo.legajo.apellido})",
                )
            )

    choques: dict[int, list] = {}
    for legajo in legajos:
        propios = []
        for nueva in a_cubrir:
            for dia, inicio, fin, que_es in ocupacion.get(legajo.id, []):
                if dia == nueva.dia_semana and se_superponen(
                    nueva.hora_inicio, nueva.hora_fin, inicio, fin
                ):
                    propios.append(
                        Choque(
                            dia=dia,
                            hora_inicio=nueva.hora_inicio,
                            hora_fin=nueva.hora_fin,
                            lo_nuevo=_etiqueta(nueva),
                            lo_que_ya_tiene=que_es,
                        )
                    )
        choques[legajo.id] = propios
    return choques
