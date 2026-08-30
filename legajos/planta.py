"""El control que evita un rechazo en el contralor.

La escuela cobra los cargos subvencionados contra resoluciones: cada cargo
aprobado tiene la suya. Dos cosas se desalinean solas a lo largo del año y
nadie las mira hasta que el organismo las devuelve:

1. **Horas que se dan sin estar designadas** (o al revés): el horario le
   asigna a alguien más —o menos— horas de las que dicen sus cargos.
2. **Cargos subvencionados sin resolución cargada**: se está cobrando algo
   cuyo respaldo no está en el sistema.

Las dos salen de datos que ya existen; solo faltaba cruzarlos.
"""

from dataclasses import dataclass, field
from datetime import date

from horarios.models import AsignacionHoraria
from legajos.models import EstadoLegajo, FuentePago, Legajo, TipoCargo


@dataclass
class LineaDePlanta:
    """Una persona, con lo designado y lo que realmente da."""

    legajo: Legajo
    horas_designadas: int
    horas_en_el_horario: int
    cargos_sin_resolucion: list = field(default_factory=list)

    @property
    def diferencia(self) -> int:
        """Positiva: da más de lo designado. Negativa: le sobran horas."""
        return self.horas_en_el_horario - self.horas_designadas

    @property
    def hay_que_mirarla(self) -> bool:
        return bool(self.diferencia) or bool(self.cargos_sin_resolucion)

    @property
    def que_pasa(self) -> str:
        if self.diferencia > 0:
            return f"da {self.diferencia} hora(s) más de las designadas"
        if self.diferencia < 0:
            return f"tiene {abs(self.diferencia)} hora(s) designadas que no da"
        return ""


def revisar(institucion, version=None, a_fecha: date | None = None) -> list[LineaDePlanta]:
    """Cruza cargos vigentes contra el horario publicado, persona por persona.

    ``version`` es la versión de horario a comparar; sin ella se compara solo
    contra los cargos (que igual sirve para el control de resoluciones).
    """
    a_fecha = a_fecha or date.today()

    en_el_horario: dict[int, int] = {}
    if version is not None:
        for asignacion in AsignacionHoraria.objects.filter(version=version).exclude(legajo=None):
            en_el_horario[asignacion.legajo_id] = en_el_horario.get(asignacion.legajo_id, 0) + 1

    lineas = []
    personas = (
        Legajo.objects.filter(institucion=institucion, estado=EstadoLegajo.ACTIVO)
        .prefetch_related("cargos")
        .order_by("apellido", "nombre")
    )
    for legajo in personas:
        vigentes = [cargo for cargo in legajo.cargos.all() if cargo.vigente_en(a_fecha)]
        # Solo se comparan horas cátedra: un cargo de jornada (preceptor,
        # secretaria) no ocupa bloques del horario de clases.
        designadas = sum(
            cargo.horas_semanales or 0
            for cargo in vigentes
            if cargo.tipo == TipoCargo.HORAS_CATEDRA
        )
        linea = LineaDePlanta(
            legajo=legajo,
            horas_designadas=designadas,
            horas_en_el_horario=en_el_horario.get(legajo.id, 0),
            cargos_sin_resolucion=[
                cargo
                for cargo in vigentes
                if cargo.fuente_pago == FuentePago.SUBVENCIONADO and not cargo.resolucion_numero
            ],
        )
        if linea.hay_que_mirarla or linea.horas_designadas or linea.horas_en_el_horario:
            lineas.append(linea)

    # Primero lo que hay que resolver.
    return sorted(lineas, key=lambda linea: (not linea.hay_que_mirarla, linea.legajo.apellido))


def resumen(lineas: list[LineaDePlanta]) -> dict:
    sin_resolucion = [linea for linea in lineas if linea.cargos_sin_resolucion]
    return {
        "personas": len(lineas),
        "con_diferencia": sum(1 for linea in lineas if linea.diferencia),
        "sin_resolucion": len(sin_resolucion),
        "cargos_sin_resolucion": sum(len(linea.cargos_sin_resolucion) for linea in sin_resolucion),
        "horas_designadas": sum(linea.horas_designadas for linea in lineas),
        "horas_en_el_horario": sum(linea.horas_en_el_horario for linea in lineas),
    }
