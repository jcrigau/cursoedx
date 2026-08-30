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


def _aviso_sin_responder(situacion) -> Pendiente:
    """El docente avisó y nadie le contestó todavía.

    Aparece en cuanto llega el aviso (además del correo que se manda en el
    momento): es la comunicación recibida pendiente de contestar.
    """
    return Pendiente(
        titulo="Avisos de docentes sin responder",
        cantidad=situacion["avisos_sin_responder"],
        detalle=(
            "Avisaron desde el portal que faltan. Marcarlo visto les confirma "
            "que la escuela ya lo sabe; también se puede responder por WhatsApp "
            "o correo con el mensaje ya escrito."
        ),
        url=reverse("avisos_recibidos"),
        accion="Responder",
        urgente=True,
    )


def _del_directivo(institucion, situacion) -> list[Pendiente]:
    """Lo que solo el directivo puede destrabar."""
    from licencias.models import EstadoLicencia, Licencia

    a_aprobar = Licencia.objects.filter(
        institucion=institucion, estado=EstadoLicencia.SOLICITADA
    ).count()

    return [
        _aviso_sin_responder(situacion),
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
            detalle=(
                "Hay que designar suplente o dejar constancia de que el curso queda "
                "libre. Se resuelven todos los cargos de una licencia de una vez."
            ),
            url=(reverse("admin:licencias_licencia_changelist") + "?estado__exact=APROBADA"),
            accion="Decidir",
            urgente=True,
        ),
    ]


def _avisos_sin_licencia(institucion, hoy) -> int:
    """Avisos de hace dos días o más cuyo certificado nunca llegó.

    Es el único punto del circuito donde algo se pierde en silencio: el
    docente avisó, se lo marcó ausente, y la licencia no se cargó nunca. Sin
    licencia, esa ausencia queda injustificada en el mes y nadie la persigue.
    Un aviso con licencia cargada —aunque esté sin aprobar— ya no es un cabo
    suelto: lo está persiguiendo el directivo.
    """
    from datetime import timedelta

    from licencias.models import EstadoLicencia, Licencia
    from portal.models import AvisoInasistencia, EstadoAviso

    viejos = AvisoInasistencia.objects.filter(
        institucion=institucion, fecha__lte=hoy - timedelta(days=2)
    ).exclude(estado=EstadoAviso.ANULADO)

    sueltos = 0
    for aviso in viejos.select_related("legajo"):
        cubierto = (
            Licencia.objects.filter(
                legajo=aviso.legajo,
                fecha_inicio__lte=aviso.fecha,
                fecha_fin__gte=aviso.fecha,
            )
            .exclude(estado__in=[EstadoLicencia.RECHAZADA, EstadoLicencia.CANCELADA])
            .exists()
        )
        if not cubierto:
            sueltos += 1
    return sueltos


def _de_secretaria(institucion, situacion, documentos_vencidos) -> list[Pendiente]:
    """El trabajo del día y el cierre del mes."""
    hoy = date.today()
    return [
        _aviso_sin_responder(situacion),
        Pendiente(
            titulo="Avisos viejos sin licencia cargada",
            cantidad=_avisos_sin_licencia(institucion, hoy),
            detalle=(
                "Avisaron hace más de dos días y el certificado nunca se cargó: esas "
                "ausencias van a quedar injustificadas en el mes."
            ),
            url=reverse("admin:portal_avisoinasistencia_changelist"),
            accion="Revisar y cargar",
            urgente=True,
        ),
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
            detalle=(
                "Hay que designar suplente o dejar constancia de que el curso queda "
                "libre. Se resuelven todos los cargos de una licencia de una vez."
            ),
            url=(reverse("admin:licencias_licencia_changelist") + "?estado__exact=APROBADA"),
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
        _legajos_sin_cuil(institucion),
        Pendiente(
            titulo="Documentación vencida",
            cantidad=len(documentos_vencidos),
            detalle="Hay que reclamarla y reemplazarla en el legajo.",
            url=reverse("admin:legajos_documentolegajo_changelist"),
            accion="Ver los legajos",
        ),
        _el_mes(institucion, hoy),
    ]


def _legajos_sin_cuil(institucion) -> Pendiente:
    """El dato que falta y nadie ve no se completa nunca.

    Una escuela recién cargada arranca con la lista de apellidos: sin CUIL no
    se puede liquidar ni certificar servicios, así que conviene tenerlo a la
    vista hasta que esté completo.
    """
    from legajos.models import EstadoLegajo, Legajo

    faltan = Legajo.objects.filter(
        institucion=institucion, estado=EstadoLegajo.ACTIVO, cuil=""
    ).count()
    return Pendiente(
        titulo="Legajos sin CUIL",
        cantidad=faltan,
        detalle=(
            "Sin CUIL no se puede liquidar ni certificar servicios. Se completan en "
            "el legajo, o subiendo de nuevo la planilla del personal con la columna "
            "cargada."
        ),
        url=(reverse("admin:legajos_legajo_changelist") + "?faltan=cuil"),
        accion="Completar",
    )


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
