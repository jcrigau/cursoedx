"""Armado de las grillas que se muestran e imprimen.

Una grilla es una tabla de horas (filas) por días (columnas). Se construye a
partir de los horarios reales y no de los bloques, para que la vista del
docente —que puede dar clase en cursos con esquemas distintos— salga alineada.
"""

from dataclasses import dataclass, field
from datetime import time

from estructura.models import BloqueHorario, DiaSemana, TipoBloque


@dataclass
class Celda:
    principal: str = ""
    secundario: str = ""
    tipo: str = ""  # clase, recreo, almuerzo o vacío
    vacia: bool = True


@dataclass
class Fila:
    inicio: time
    fin: time
    etiqueta: str = ""
    celdas: list[Celda] = field(default_factory=list)


@dataclass
class Grilla:
    titulo: str
    subtitulo: str
    dias: list[tuple[int, str]]
    filas: list[Fila]
    sin_asignar: int = 0


def _dias_legibles(dias: list[int]) -> list[tuple[int, str]]:
    etiquetas = dict(DiaSemana.choices)
    return [(dia, etiquetas[dia]) for dia in dias]


def grilla_de_curso(version, curso) -> Grilla:
    """Horario de un curso: qué materia y con qué docente en cada hora."""
    bloques = list(
        BloqueHorario.objects.filter(esquema_id=curso.esquema_horario_id).order_by(
            "dia_semana", "hora_inicio"
        )
    )
    asignaciones = {
        (asignacion.dia_semana, asignacion.hora_inicio): asignacion
        for asignacion in version.asignaciones.filter(curso=curso).select_related(
            "materia", "legajo"
        )
    }

    dias = sorted({bloque.dia_semana for bloque in bloques})
    horas = sorted({(bloque.hora_inicio, bloque.hora_fin) for bloque in bloques})
    por_dia_hora = {(bloque.dia_semana, bloque.hora_inicio): bloque for bloque in bloques}

    filas, sin_asignar = [], 0
    for inicio, fin in horas:
        fila = Fila(inicio=inicio, fin=fin)
        for dia in dias:
            bloque = por_dia_hora.get((dia, inicio))
            if bloque is None:
                fila.celdas.append(Celda())
                continue
            if bloque.tipo != TipoBloque.CLASE:
                fila.celdas.append(
                    Celda(
                        principal=bloque.get_tipo_display(), tipo=bloque.tipo.lower(), vacia=False
                    )
                )
                continue
            asignacion = asignaciones.get((dia, inicio))
            if asignacion is None:
                sin_asignar += 1
                fila.celdas.append(Celda(tipo="clase"))
                continue
            fila.celdas.append(
                Celda(
                    principal=asignacion.materia.nombre,
                    secundario=(
                        asignacion.legajo.nombre_completo if asignacion.legajo else "sin docente"
                    ),
                    tipo="clase",
                    vacia=False,
                )
            )
            fila.etiqueta = fila.etiqueta or (bloque.etiqueta or "")
        if not fila.etiqueta:
            referencia = next(
                (por_dia_hora[(dia, inicio)] for dia in dias if (dia, inicio) in por_dia_hora), None
            )
            fila.etiqueta = referencia.etiqueta if referencia else ""
        filas.append(fila)

    return Grilla(
        titulo=str(curso),
        subtitulo=f"{curso.nivel} · turno {curso.turno.nombre} · {version.periodo}",
        dias=_dias_legibles(dias),
        filas=filas,
        sin_asignar=sin_asignar,
    )


def grilla_de_docente(version, legajo) -> Grilla:
    """Horario de un docente: en qué curso está cada hora y cuándo tiene libre."""
    asignaciones = list(
        version.asignaciones.filter(legajo=legajo).select_related("curso", "materia")
    )
    dias = sorted({asignacion.dia_semana for asignacion in asignaciones})
    horas = sorted({(a.hora_inicio, a.hora_fin) for a in asignaciones})
    por_dia_hora = {(a.dia_semana, a.hora_inicio): a for a in asignaciones}

    filas = []
    for inicio, fin in horas:
        fila = Fila(inicio=inicio, fin=fin)
        for dia in dias:
            asignacion = por_dia_hora.get((dia, inicio))
            if asignacion is None:
                fila.celdas.append(Celda(tipo="libre"))
                continue
            fila.celdas.append(
                Celda(
                    principal=str(asignacion.curso),
                    secundario=asignacion.materia.nombre,
                    tipo="clase",
                    vacia=False,
                )
            )
        filas.append(fila)

    return Grilla(
        titulo=legajo.nombre_completo,
        subtitulo=(
            f"{len(asignaciones)} horas · {len(dias)} día{'s' if len(dias) != 1 else ''} "
            f"por semana · {version.periodo}"
        ),
        dias=_dias_legibles(dias),
        filas=filas,
    )
