"""Lo que cada puesto tiene para hacer, en la primera pantalla.

El tablero mostraba lo mismo para todos, y lo pendiente había que ir a
buscarlo al panel de administración sabiendo dónde estaba. Pero cada puesto
entra a resolver cosas distintas: el directivo aprueba licencias, la
secretaría marca el parte y cierra el mes, el liquidador descarga lo cerrado.

Cada pendiente trae el link al lugar exacto donde se resuelve. La idea es que
nadie tenga que aprender el mapa del sistema para hacer su trabajo.
"""

from dataclasses import dataclass
from datetime import date

from django.urls import reverse

from .models import Rol


@dataclass
class Pendiente:
    """Algo por resolver, con el link a donde se resuelve."""

    titulo: str
    cantidad: int
    detalle: str
    url: str
    accion: str
    # Lo que deja a un curso sin clase o frena la liquidación va en rojo.
    urgente: bool = False


def pendientes_de(institucion, usuario, *, situacion, documentos_vencidos) -> list[Pendiente]:
    """Los pendientes del usuario según su rol en la escuela activa.

    ``situacion`` y ``documentos_vencidos`` vienen ya calculados por el
    tablero: son consultas que no conviene repetir.
    """
    roles = usuario.roles_en(institucion)
    if usuario.is_superuser:
        # Quien administra el producto ve todo, sin necesitar membresía.
        roles = {Rol.SECRETARIA, Rol.DIRECTIVO, Rol.LIQUIDADOR}

    pendientes: list[Pendiente] = []
    if Rol.DIRECTIVO in roles:
        pendientes += _del_directivo(institucion, situacion)
    if Rol.SECRETARIA in roles:
        pendientes += _de_secretaria(institucion, situacion, documentos_vencidos)
    if Rol.LIQUIDADOR in roles:
        pendientes += _del_liquidador(institucion)

    # Puede haber repetidos si alguien tiene dos roles en la misma escuela.
    vistos, unicos = set(), []
    for pendiente in pendientes:
        if pendiente.titulo in vistos:
            continue
        vistos.add(pendiente.titulo)
        unicos.append(pendiente)
    return [pendiente for pendiente in unicos if pendiente.cantidad]


def _del_directivo(institucion, situacion) -> list[Pendiente]:
    """Lo que solo el directivo puede destrabar."""
    from licencias.models import EstadoLicencia, Licencia

    a_aprobar = Licencia.objects.filter(
        institucion=institucion, estado=EstadoLicencia.SOLICITADA
    ).count()

    return [
        Pendiente(
            titulo="Licencias esperando aprobación",
            cantidad=a_aprobar,
            detalle="Mientras no se resuelvan, esas personas siguen figurando en el parte.",
            url=(
                reverse("admin:licencias_licencia_changelist")
                + f"?estado__exact={EstadoLicencia.SOLICITADA}"
            ),
            accion="Aprobar o rechazar",
            urgente=True,
        ),
        Pendiente(
            titulo="Licencias sin decidir la cobertura",
            cantidad=situacion["coberturas_pendientes"],
            detalle="Hay que designar suplente o dejar constancia de que el curso queda libre.",
            url=reverse("admin:licencias_cobertura_add"),
            accion="Decidir",
            urgente=True,
        ),
    ]


def _de_secretaria(institucion, situacion, documentos_vencidos) -> list[Pendiente]:
    """El trabajo del día y el cierre del mes."""
    hoy = date.today()
    return [
        Pendiente(
            titulo="Horas sin docente hoy",
            cantidad=situacion["horas_sin_cobertura"],
            detalle="Esos cursos se quedan sin clase.",
            url=reverse("cursos_del_dia"),
            accion="Ver los cursos",
            urgente=True,
        ),
        Pendiente(
            titulo="Licencias sin decidir la cobertura",
            cantidad=situacion["coberturas_pendientes"],
            detalle="Hay que designar suplente o dejar constancia de que el curso queda libre.",
            url=reverse("admin:licencias_cobertura_add"),
            accion="Decidir",
            urgente=True,
        ),
        Pendiente(
            titulo="Personas sin marcar en el parte",
            cantidad=situacion["parte_sin_registrar"],
            detalle="Lo que quede sin marcar se toma como presente.",
            url=reverse("parte_diario"),
            accion="Abrir el parte",
        ),
        Pendiente(
            titulo="Documentación vencida",
            cantidad=len(documentos_vencidos),
            detalle="Hay que reclamarla y reemplazarla en el legajo.",
            url=reverse("admin:legajos_documentolegajo_changelist"),
            accion="Ver los legajos",
        ),
        _el_mes(institucion, hoy),
    ]


def _el_mes(institucion, hoy) -> Pendiente:
    """En qué punto del cierre mensual está la secretaría."""
    from novedades.models import PeriodoNovedades

    url = reverse("novedades_detalle", args=[hoy.year, hoy.month])
    periodo = PeriodoNovedades.objects.filter(
        institucion=institucion, anio=hoy.year, mes=hoy.month
    ).first()

    if periodo is None or periodo.compilado_en is None:
        return Pendiente(
            titulo="El mes está sin compilar",
            cantidad=1,
            detalle="Compilar arma las novedades desde altas, bajas, licencias e inasistencias.",
            url=url,
            accion="Compilar el mes",
        )

    resumen = periodo.resumen()
    if resumen["pendientes"]:
        return Pendiente(
            titulo="Novedades sin informar",
            cantidad=resumen["pendientes"],
            detalle=f"De {resumen['a_informar']} que hay que pasarle al liquidador.",
            url=url,
            accion="Revisar el mes",
        )

    if not periodo.esta_cerrado:
        return Pendiente(
            titulo="El mes está sin cerrar",
            cantidad=1,
            detalle="Hasta que no se cierre, el liquidador no puede ver ni descargar nada.",
            url=url,
            accion="Cerrar el mes",
        )

    return Pendiente(titulo="", cantidad=0, detalle="", url=url, accion="")


def _del_liquidador(institucion) -> list[Pendiente]:
    """Lo único que le toca: descargar lo que ya está cerrado."""
    from novedades.models import EstadoPeriodo, PeriodoNovedades

    cerrados = PeriodoNovedades.objects.filter(
        institucion=institucion, estado=EstadoPeriodo.CERRADO
    ).count()

    return [
        Pendiente(
            titulo="Meses cerrados para liquidar",
            cantidad=cerrados,
            detalle="Ya revisados por la escuela. Se descargan en Excel, CSV o PDF.",
            url=reverse("novedades_periodos"),
            accion="Ver y descargar",
        )
    ]
