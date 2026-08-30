"""Cómo viene el ausentismo, mes a mes.

El resumen mensual responde «¿qué le pasó a cada uno este mes?». Esta otra
pregunta es de dirección y no la contestaba nadie: **¿esto es mucho o es lo
normal?**. Sin los meses anteriores al lado, un mes con seis ausencias no dice
nada.

Se separan dos cosas que no son lo mismo aunque las dos dejen un curso sin su
docente: los **días de licencia** (avisados, con su artículo y su certificado)
y las **inasistencias sin licencia** (las que quedan injustificadas si nadie
carga nada). La segunda es la que hay que mirar.
"""

from dataclasses import dataclass
from datetime import date

from licencias.models import EstadoLicencia, Licencia

from .models import EstadoAsistencia, RegistroAsistencia
from .reportes import dias_en_el_mes, limites_del_mes

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


@dataclass
class MesDeAusentismo:
    anio: int
    mes: int
    con_licencia: int = 0
    sin_licencia: int = 0

    @property
    def total(self) -> int:
        return self.con_licencia + self.sin_licencia

    @property
    def etiqueta(self) -> str:
        return MESES[self.mes - 1][:3]

    @property
    def nombre_largo(self) -> str:
        return f"{MESES[self.mes - 1]} de {self.anio}"


def _mes_anterior(anio: int, mes: int) -> tuple[int, int]:
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def por_mes(institucion, hasta: date, cantidad: int = 12) -> list[MesDeAusentismo]:
    """Los últimos ``cantidad`` meses, del más viejo al más nuevo."""
    meses: list[MesDeAusentismo] = []
    anio, mes = hasta.year, hasta.month
    for _ in range(cantidad):
        meses.append(MesDeAusentismo(anio=anio, mes=mes))
        anio, mes = _mes_anterior(anio, mes)
    meses.reverse()

    if not meses:
        return []

    desde_todo, _ = limites_del_mes(meses[0].anio, meses[0].mes)
    _, hasta_todo = limites_del_mes(meses[-1].anio, meses[-1].mes)

    licencias = Licencia.objects.filter(
        institucion=institucion,
        estado=EstadoLicencia.APROBADA,
        fecha_inicio__lte=hasta_todo,
        fecha_fin__gte=desde_todo,
    )
    ausencias = RegistroAsistencia.objects.filter(
        institucion=institucion,
        estado=EstadoAsistencia.AUSENTE,
        fecha__gte=desde_todo,
        fecha__lte=hasta_todo,
    ).values_list("fecha", flat=True)

    por_clave = {(mes_.anio, mes_.mes): mes_ for mes_ in meses}
    for licencia in licencias:
        for mes_ in meses:
            mes_.con_licencia += dias_en_el_mes(
                licencia.fecha_inicio, licencia.fecha_fin, mes_.anio, mes_.mes
            )
    for fecha in ausencias:
        mes_ = por_clave.get((fecha.year, fecha.month))
        if mes_ is not None:
            mes_.sin_licencia += 1
    return meses


def por_motivo(institucion, meses: list[MesDeAusentismo]) -> list[tuple[str, int]]:
    """Qué motivos explican esos días, de mayor a menor."""
    if not meses:
        return []
    desde, _ = limites_del_mes(meses[0].anio, meses[0].mes)
    _, hasta = limites_del_mes(meses[-1].anio, meses[-1].mes)

    conteo: dict[str, int] = {}
    licencias = Licencia.objects.filter(
        institucion=institucion,
        estado=EstadoLicencia.APROBADA,
        fecha_inicio__lte=hasta,
        fecha_fin__gte=desde,
    ).select_related("tipo")
    for licencia in licencias:
        dias = sum(
            dias_en_el_mes(licencia.fecha_inicio, licencia.fecha_fin, mes_.anio, mes_.mes)
            for mes_ in meses
        )
        if dias:
            conteo[str(licencia.tipo)] = conteo.get(str(licencia.tipo), 0) + dias

    sin_licencia = sum(mes_.sin_licencia for mes_ in meses)
    if sin_licencia:
        conteo["Inasistencia sin licencia"] = sin_licencia

    return sorted(conteo.items(), key=lambda par: -par[1])
