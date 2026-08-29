"""Resumen mensual de asistencia y licencias.

Es el paso previo a las novedades de liquidación (F4): responde, para un mes,
qué le pasó a cada persona y sobre qué cargos, separando lo que paga el estado
de lo que paga la escuela.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date

from legajos.models import FuentePago, Legajo
from licencias.models import EstadoLicencia, Licencia

from .models import EstadoAsistencia, RegistroAsistencia


def limites_del_mes(anio: int, mes: int) -> tuple[date, date]:
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def dias_en_el_mes(desde: date, hasta: date, anio: int, mes: int) -> int:
    """Cuántos días de un período caen dentro del mes."""
    inicio_mes, fin_mes = limites_del_mes(anio, mes)
    desde_real = max(desde, inicio_mes)
    hasta_real = min(hasta, fin_mes)
    if hasta_real < desde_real:
        return 0
    return (hasta_real - desde_real).days + 1


@dataclass
class LicenciaDelMes:
    licencia: Licencia
    dias: int

    @property
    def tipo(self) -> str:
        return str(self.licencia.tipo)

    @property
    def con_goce(self) -> bool:
        return self.licencia.tipo.con_goce


@dataclass
class ResumenDocente:
    """Lo que hay que informar de una persona en el mes."""

    legajo: Legajo
    ausencias_justificadas: int = 0
    ausencias_injustificadas: int = 0
    tardanzas: int = 0
    retiros: int = 0
    horas_no_dictadas: int = 0
    licencias: list[LicenciaDelMes] = field(default_factory=list)
    fuentes: set = field(default_factory=set)
    # Los registros del parte que suman a cada número: son la respuesta a
    # «¿3 inasistencias? ¿qué días?» sin salir de la pantalla.
    registros: list = field(default_factory=list)

    @property
    def tiene_novedades(self) -> bool:
        """Si no pasó nada, no hay nada que informar a quien liquida."""
        return bool(
            self.ausencias_justificadas
            or self.ausencias_injustificadas
            or self.tardanzas
            or self.retiros
            or self.horas_no_dictadas
            or self.licencias
        )

    @property
    def dias_sin_goce(self) -> int:
        """Días de licencia que generan descuento."""
        return sum(item.dias for item in self.licencias if not item.con_goce)

    @property
    def es_mixto(self) -> bool:
        return len(self.fuentes) > 1

    @property
    def detalle_fuentes(self) -> str:
        etiquetas = {
            FuentePago.SUBVENCIONADO: "Oficial",
            FuentePago.INTERNO: "Interna",
        }
        return ", ".join(sorted(etiquetas[fuente] for fuente in self.fuentes))


def resumen_mensual(institucion, anio: int, mes: int) -> list[ResumenDocente]:
    """Arma el resumen del mes, una fila por persona con algo para informar."""
    inicio, fin = limites_del_mes(anio, mes)
    resumenes: dict[int, ResumenDocente] = {}

    def fila(legajo) -> ResumenDocente:
        if legajo.id not in resumenes:
            resumenes[legajo.id] = ResumenDocente(legajo=legajo)
        return resumenes[legajo.id]

    registros = RegistroAsistencia.objects.filter(
        institucion=institucion, fecha__gte=inicio, fecha__lte=fin
    ).select_related("legajo", "licencia")

    for registro in registros:
        actual = fila(registro.legajo)
        actual.registros.append(registro)
        if registro.estado == EstadoAsistencia.AUSENTE:
            if registro.justificada:
                actual.ausencias_justificadas += 1
            else:
                actual.ausencias_injustificadas += 1
        elif registro.estado == EstadoAsistencia.PARCIAL:
            actual.horas_no_dictadas += registro.horas_afectadas or 0
            if not registro.justificada:
                actual.ausencias_injustificadas += 0  # la parcial no suma un día entero
        elif registro.estado == EstadoAsistencia.TARDE:
            actual.tardanzas += 1
        elif registro.estado == EstadoAsistencia.RETIRO:
            actual.retiros += 1

    licencias = Licencia.objects.filter(
        institucion=institucion,
        estado=EstadoLicencia.APROBADA,
        fecha_inicio__lte=fin,
        fecha_fin__gte=inicio,
    ).select_related("legajo", "tipo")

    for licencia in licencias:
        dias = dias_en_el_mes(licencia.fecha_inicio, licencia.fecha_fin, anio, mes)
        if dias:
            fila(licencia.legajo).licencias.append(LicenciaDelMes(licencia=licencia, dias=dias))

    # La fuente de pago sale de los cargos vigentes: define a qué planilla va
    # cada novedad (Oficial o Interna).
    for resumen in resumenes.values():
        resumen.fuentes = {cargo.fuente_pago for cargo in resumen.legajo.cargos_vigentes(inicio)}

    return sorted(
        (r for r in resumenes.values() if r.tiene_novedades),
        key=lambda r: r.legajo.nombre_completo,
    )
