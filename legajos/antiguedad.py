"""Cómputo de antigüedad docente.

El punto fino: una persona puede tener varios cargos a la vez (horas de dos
materias, un cargo y horas), y ese tiempo se trabaja **una sola vez**. Por eso
los períodos se unen antes de contar, en lugar de sumar la duración de cada
cargo por separado — sumarlos daría el doble o el triple de la antigüedad real.

El desglose en años, meses y días usa la convención administrativa habitual
(año de 365 días, mes de 30). El dato exacto y no opinable es ``total_dias``:
es el que conviene mirar ante cualquier diferencia con el organismo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Antiguedad:
    """Resultado del cómputo, en días exactos y en su desglose habitual."""

    total_dias: int
    anios: int
    meses: int
    dias: int

    def __str__(self) -> str:
        partes = []
        if self.anios:
            partes.append(f"{self.anios} año{'s' if self.anios != 1 else ''}")
        if self.meses:
            partes.append(f"{self.meses} mes{'es' if self.meses != 1 else ''}")
        if self.dias or not partes:
            partes.append(f"{self.dias} día{'s' if self.dias != 1 else ''}")
        if len(partes) == 1:
            return partes[0]
        return f"{', '.join(partes[:-1])} y {partes[-1]}"


def unir_periodos(periodos: Iterable[tuple[date, date]]) -> list[tuple[date, date]]:
    """Une los períodos que se superponen o son contiguos.

    Dos cargos que van del 1/3 al 30/6 y del 1/5 al 31/8 son, en total, del 1/3
    al 31/8: cuatro meses no se convierten en siete por estar designado dos
    veces.
    """
    ordenados = sorted((desde, hasta) for desde, hasta in periodos if desde <= hasta)
    if not ordenados:
        return []

    unidos = [ordenados[0]]
    for desde, hasta in ordenados[1:]:
        ultimo_desde, ultimo_hasta = unidos[-1]
        # +1 día: dos períodos que se tocan (uno termina el 30 y el otro empieza
        # el 31) son continuos, no dos tramos separados.
        if (desde - ultimo_hasta).days <= 1:
            unidos[-1] = (ultimo_desde, max(ultimo_hasta, hasta))
        else:
            unidos.append((desde, hasta))
    return unidos


def dias_de(periodos: Iterable[tuple[date, date]]) -> int:
    """Días trabajados, contando inicio y fin inclusive."""
    return sum((hasta - desde).days + 1 for desde, hasta in periodos)


def desglosar(total_dias: int) -> Antiguedad:
    """Pasa de días a años, meses y días según la convención administrativa."""
    anios, resto = divmod(max(total_dias, 0), 365)
    meses, dias = divmod(resto, 30)
    return Antiguedad(total_dias=max(total_dias, 0), anios=anios, meses=meses, dias=dias)


def periodos_en_la_institucion(legajo, a_fecha: date | None = None) -> list[tuple[date, date]]:
    """Períodos trabajados en esta escuela, tomados de los cargos."""
    a_fecha = a_fecha or date.today()
    periodos = []
    for cargo in legajo.cargos.all():
        if cargo.fecha_alta > a_fecha:
            continue
        fin = min(cargo.fecha_baja or a_fecha, a_fecha)
        periodos.append((cargo.fecha_alta, fin))
    return periodos


def periodos_anteriores(
    legajo, a_fecha: date | None = None, solo_docente: bool = True
) -> list[tuple[date, date]]:
    """Períodos declarados en otras instituciones."""
    a_fecha = a_fecha or date.today()
    servicios = legajo.servicios_anteriores.all()
    if solo_docente:
        servicios = [servicio for servicio in servicios if servicio.es_docente]
    return [
        (servicio.desde, min(servicio.hasta, a_fecha))
        for servicio in servicios
        if servicio.desde <= a_fecha
    ]


def calcular_antiguedad(
    legajo,
    a_fecha: date | None = None,
    incluir_anteriores: bool = True,
    solo_docente: bool = True,
) -> Antiguedad:
    """Antigüedad total del legajo a una fecha.

    El porcentaje que corresponde por antigüedad lo aplica quien liquida: acá
    solo se informa el tiempo de servicio.
    """
    a_fecha = a_fecha or date.today()
    periodos = periodos_en_la_institucion(legajo, a_fecha)
    if incluir_anteriores:
        periodos += periodos_anteriores(legajo, a_fecha, solo_docente)
    return desglosar(dias_de(unir_periodos(periodos)))


def antiguedad_en_la_institucion(legajo, a_fecha: date | None = None) -> Antiguedad:
    """Solo lo trabajado en esta escuela (sin servicios anteriores)."""
    return calcular_antiguedad(legajo, a_fecha, incluir_anteriores=False)
