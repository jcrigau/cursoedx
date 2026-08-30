"""Decisiones de cobertura que se toman en un clic.

Cada una de estas se podía hacer desde el panel de administración, pero eran
tres o cuatro pantallas para algo que la escuela resuelve en el momento: «este
curso queda libre», «el suplente sigue una semana más», «se termina hoy».
Puestas donde la decisión aparece —el parte, el tablero— dejan de ser trámite.
"""

from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.models import AccionAuditada, registrar_auditoria
from horarios.models import AsignacionHoraria
from legajos.models import Legajo, MotivoBaja

from . import avisos
from . import candidatos as buscador
from .models import Cobertura, Licencia, TipoCobertura, ViaAviso

PERMISO = "licencias.change_cobertura"


@login_required
@permission_required(PERMISO, raise_exception=True)
def cubrir_licencia(request, pk):
    """Resolver de una vez todos los cargos que deja libres una licencia.

    Una licencia sobre un profesor con seis horas cátedra son seis cargos, y
    hasta ahora cada uno era un formulario aparte. Acá se tildan los que se le
    dan a la misma persona y se designa una sola vez, con el sistema
    revisando que no le queden dos cursos a la misma hora.
    """
    from .models import EstadoLicencia, Licencia, TipoCobertura
    from .superposicion import hay_horario, revisar

    licencia = get_object_or_404(
        Licencia.objects.del_contexto().select_related("legajo", "tipo"), pk=pk
    )
    ya_resueltos = {
        cobertura.cargo_id: cobertura
        for cobertura in licencia.coberturas.select_related("suplente")
    }
    cargos = list(licencia.cargos_afectados().select_related("materia", "curso"))

    if request.method == "POST":
        resultado = _guardar_la_cobertura(request, licencia, cargos, ya_resueltos)
        if resultado is not None:
            return resultado

    return render(
        request,
        "licencias/cubrir_licencia.html",
        {
            "licencia": licencia,
            "cargos": [
                {"cargo": cargo, "cobertura": ya_resueltos.get(cargo.id)} for cargo in cargos
            ],
            "pendientes": [cargo for cargo in cargos if cargo.id not in ya_resueltos],
            "posibles": _posibles_suplentes(licencia, cargos),
            "hay_horario": hay_horario(request.institucion, licencia.fecha_inicio),
            "aprobada": licencia.estado == EstadoLicencia.APROBADA,
            "tipos": TipoCobertura.choices,
            "choques": getattr(request, "_choques", []),
            "elegidos": [int(c) for c in request.POST.getlist("cargos") if c.isdigit()],
            "revisar": revisar,  # se usa solo en las pruebas de la vista
        },
    )


def _posibles_suplentes(licencia, cargos):
    """Personal que puede tomar esos cargos, primero quien da esas materias."""
    from legajos.models import PLANTELES_SIN_CLASES, EstadoLegajo, Legajo

    materias = {cargo.materia_id for cargo in cargos if cargo.materia_id}
    gente = (
        Legajo.objects.filter(institucion=licencia.institucion, estado=EstadoLegajo.ACTIVO)
        .exclude(pk=licencia.legajo_id)
        .exclude(plantel__in=PLANTELES_SIN_CLASES)
        .prefetch_related("cargos", "materias_que_puede_dar")
        .order_by("apellido", "nombre")
    )
    con_la_materia, el_resto = [], []
    for legajo in gente:
        suyas = {cargo.materia_id for cargo in legajo.cargos.all() if cargo.materia_id}
        suyas |= {materia.id for materia in legajo.materias_que_puede_dar.all()}
        (con_la_materia if materias & suyas else el_resto).append(legajo)
    return {"con_la_materia": con_la_materia, "el_resto": el_resto}


def _guardar_la_cobertura(request, licencia, cargos, ya_resueltos):
    """Crea las coberturas tildadas. Devuelve None si hay que volver a mostrar."""
    from .models import Cobertura, TipoCobertura
    from .superposicion import revisar

    elegidos = [int(valor) for valor in request.POST.getlist("cargos") if valor.isdigit()]
    seleccionados = [
        cargo for cargo in cargos if cargo.id in elegidos and cargo.id not in ya_resueltos
    ]
    if not seleccionados:
        messages.error(request, "Tildá al menos un cargo para cubrir.")
        return None

    desde = _fecha(request.POST.get("desde")) or licencia.fecha_inicio
    hasta = _fecha(request.POST.get("hasta")) or licencia.fecha_fin
    if desde < licencia.fecha_inicio or hasta > licencia.fecha_fin:
        messages.error(
            request,
            "Las fechas de la cobertura tienen que estar dentro de la licencia "
            f"({licencia.fecha_inicio:%d/%m} al {licencia.fecha_fin:%d/%m}).",
        )
        return None

    tipo = request.POST.get("tipo", TipoCobertura.SUPLENTE)
    suplente = None
    if tipo == TipoCobertura.SUPLENTE:
        suplente = Legajo.objects.del_contexto().filter(pk=request.POST.get("suplente")).first()
        if suplente is None:
            messages.error(request, "Elegí a quién se le asignan esos cargos.")
            return None

        choques = revisar(request.institucion, suplente, seleccionados, desde, hasta)
        if choques:
            # No se guarda nada: es el error que después aparece con dos cursos
            # esperando a la misma persona.
            request._choques = choques
            messages.error(
                request,
                f"{suplente.nombre_completo} no puede tomar todo eso: hay "
                f"{len(choques)} hora(s) que se le pisan con lo que ya tiene.",
            )
            return None

    creadas = 0
    for cargo in seleccionados:
        cobertura, creada = Cobertura.objects.get_or_create(
            institucion=licencia.institucion,
            licencia=licencia,
            cargo=cargo,
            defaults={
                "tipo": tipo,
                "suplente": suplente,
                "fecha_inicio": desde,
                "fecha_fin": hasta,
            },
        )
        if creada:
            cobertura.designar_cargo_del_suplente()
            creadas += 1

    registrar_auditoria(
        AccionAuditada.CREACION,
        licencia,
        usuario=request.user,
        descripcion=(
            f"{creadas} cargo(s) de {licencia.legajo.nombre_completo} "
            + (f"cubiertos por {suplente.nombre_completo}" if suplente else "sin cobertura")
        ),
    )
    messages.success(
        request,
        f"Listo: {creadas} cargo(s) resueltos"
        + (f" con {suplente.nombre_completo}." if suplente else " sin cobertura."),
    )
    return HttpResponseRedirect(reverse("cubrir_licencia", args=[licencia.pk]))


@login_required
@permission_required("licencias.view_licencia", raise_exception=True)
def calendario(request):
    """El mes completo: quién falta cada día, de un vistazo.

    El parte mira un día y «La semana» los próximos siete. Para decidir si se
    puede autorizar una licencia más hay que ver cómo se apilan: tres personas
    el mismo martes es un problema aunque cada licencia por separado sea
    razonable.
    """
    import calendar as calendario_py

    from .models import EstadoLicencia

    hoy = date.today()
    anio = _entero(request.GET.get("anio"), hoy.year)
    mes = _entero(request.GET.get("mes"), hoy.month)
    if not 1 <= mes <= 12:
        anio, mes = hoy.year, hoy.month

    primero = date(anio, mes, 1)
    ultimo = date(anio, mes, calendario_py.monthrange(anio, mes)[1])

    # Una licencia solicitada todavía no descuenta a nadie, pero hay que verla:
    # es justo la que se está por decidir.
    licencias = list(
        Licencia.objects.filter(
            institucion=request.institucion,
            estado__in=[EstadoLicencia.APROBADA, EstadoLicencia.SOLICITADA],
            fecha_inicio__lte=ultimo,
            fecha_fin__gte=primero,
        ).select_related("legajo", "tipo")
    )

    semanas = []
    for semana_py in calendario_py.Calendar(firstweekday=0).monthdatescalendar(anio, mes):
        fila = []
        for dia in semana_py:
            del_dia = [
                licencia
                for licencia in licencias
                if licencia.fecha_inicio <= dia <= licencia.fecha_fin
            ]
            fila.append(
                {
                    "fecha": dia,
                    "del_mes": dia.month == mes,
                    "es_hoy": dia == hoy,
                    "fin_de_semana": dia.weekday() >= 5,
                    "licencias": sorted(del_dia, key=lambda lic: lic.legajo.apellido),
                    "aprobadas": sum(1 for lic in del_dia if lic.estado == EstadoLicencia.APROBADA),
                }
            )
        semanas.append(fila)

    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (ultimo + timedelta(days=1)).replace(day=1)
    return render(
        request,
        "licencias/calendario.html",
        {
            "semanas": semanas,
            "mes": primero,
            "anterior": anterior,
            "siguiente": siguiente,
            "personas": len({licencia.legajo_id for licencia in licencias}),
            "cantidad": len(licencias),
        },
    )


def _entero(crudo, por_defecto: int) -> int:
    try:
        return int(crudo)
    except (TypeError, ValueError):
        return por_defecto


def _volver(request, por_defecto="inicio"):
    """Vuelve a la pantalla desde donde se decidió, no a una genérica."""
    return HttpResponseRedirect(request.POST.get("siguiente") or reverse(por_defecto))


def _fecha(crudo):
    try:
        return datetime.strptime(crudo, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@require_POST
@login_required
@permission_required("licencias.add_cobertura", raise_exception=True)
def dejar_sin_cobertura(request):
    """Registra que un cargo de licencia no se cubre: los alumnos quedan libres.

    Es la decisión más frecuente y la que menos se registraba, justamente
    porque «no hacer nada» y «decidir no cubrir» se parecen en la práctica.
    En el sistema son distintas: una queda como pendiente y la otra como
    constancia de por qué el curso no tuvo clase.
    """
    licencia = get_object_or_404(Licencia.objects.del_contexto(), pk=request.POST.get("licencia"))
    cargo = get_object_or_404(licencia.legajo.cargos, pk=request.POST.get("cargo"))

    if licencia.coberturas.filter(cargo=cargo).exists():
        messages.info(request, "Ese cargo ya tenía la cobertura decidida.")
        return _volver(request, "parte_diario")

    Cobertura.objects.create(
        institucion=licencia.institucion,
        licencia=licencia,
        cargo=cargo,
        tipo=TipoCobertura.SIN_COBERTURA,
        fecha_inicio=licencia.fecha_inicio,
        fecha_fin=licencia.fecha_fin,
        observaciones=request.POST.get("observaciones", "").strip(),
    )
    messages.success(
        request,
        f"{cargo.descripcion}: queda sin cubrir. Esos cursos figuran sin clase en el parte.",
    )
    return _volver(request, "parte_diario")


@require_POST
@login_required
@permission_required(PERMISO, raise_exception=True)
def extender_suplencia(request, pk: int):
    """Corre la fecha de fin de una suplencia, y la del cargo del suplente."""
    cobertura = get_object_or_404(Cobertura.objects.del_contexto(), pk=pk)
    hasta = _fecha(request.POST.get("hasta"))

    if hasta is None:
        messages.error(request, "Indicá hasta qué fecha se extiende.")
        return _volver(request)
    if hasta <= cobertura.fecha_fin:
        messages.error(request, "La fecha nueva tiene que ser posterior a la actual.")
        return _volver(request)
    if hasta > cobertura.licencia.fecha_fin:
        # La cobertura no puede pasarse de la licencia que la origina: si el
        # titular sigue de licencia, primero hay que prorrogarla a ella.
        messages.error(
            request,
            f"La licencia de {cobertura.licencia.legajo.nombre_completo} termina el "
            f"{cobertura.licencia.fecha_fin:%d/%m/%Y}. Primero hay que extenderla a ella.",
        )
        return _volver(request)

    cobertura.fecha_fin = hasta
    cobertura.save(update_fields=["fecha_fin", "actualizado_en"])
    if cobertura.cargo_suplente_id:
        cargo = cobertura.cargo_suplente
        cargo.fecha_baja = hasta
        cargo.save(update_fields=["fecha_baja", "actualizado_en"])

    messages.success(
        request,
        f"{cobertura.suplente.nombre_completo} sigue hasta el {hasta:%d/%m/%Y}.",
    )
    return _volver(request)


@require_POST
@login_required
@permission_required(PERMISO, raise_exception=True)
def cesar_suplencia(request, pk: int):
    """Termina una suplencia hoy: da de baja el cargo del suplente.

    De esa baja sale sola la novedad del mes, sin cargarla a mano.
    """
    cobertura = get_object_or_404(Cobertura.objects.del_contexto(), pk=pk)
    hoy = date.today()
    hasta = max(hoy, cobertura.fecha_inicio)

    cobertura.fecha_fin = hasta
    cobertura.save(update_fields=["fecha_fin", "actualizado_en"])
    if cobertura.cargo_suplente_id:
        cargo = cobertura.cargo_suplente
        cargo.fecha_baja = hasta
        cargo.motivo_baja = MotivoBaja.FIN_SUPLENCIA
        cargo.save(update_fields=["fecha_baja", "motivo_baja", "actualizado_en"])

    messages.success(
        request,
        f"Suplencia de {cobertura.suplente.nombre_completo} terminada el {hasta:%d/%m/%Y}. "
        "La baja va a aparecer al compilar el mes.",
    )
    return _volver(request)


@login_required
@permission_required("licencias.add_cobertura", raise_exception=True)
def cubrir_ahora(request, pk: int):
    """A quién llamar para una hora que quedó sin docente.

    Cruza lo que el sistema ya sabe —quién está hoy en el edificio, quién da
    esa materia, quién tiene esa hora libre— y lo deja filtrable. Es la
    pregunta urgente de la escuela cuando un curso se queda sin clase.
    """
    asignacion = get_object_or_404(
        AsignacionHoraria.objects.select_related("version", "curso", "materia", "legajo", "cargo"),
        pk=pk,
        version__institucion=request.institucion,
    )
    fecha = _fecha(request.GET.get("fecha")) or date.today()

    filtros = {
        "en_la_escuela": request.GET.get("en_la_escuela") == "1",
        "misma_materia": request.GET.get("misma_materia") == "1",
        "solo_disponibles": request.GET.get("solo_disponibles", "1") == "1",
    }
    todos = buscador.buscar(request.institucion, asignacion, fecha)
    licencia = buscador.licencia_de_la_hora(request.institucion, asignacion, fecha)

    return render(
        request,
        "licencias/cubrir.html",
        {
            "asignacion": asignacion,
            "fecha": fecha,
            "licencia": licencia,
            "candidatos": buscador.filtrar(todos, **filtros),
            "total": len(todos),
            "filtros": filtros,
            "cobertura": licencia.coberturas.filter(cargo=asignacion.cargo).first()
            if licencia
            else None,
        },
    )


@require_POST
@login_required
@permission_required("licencias.add_cobertura", raise_exception=True)
def designar_suplente(request, pk: int):
    """Designa a alguien para cubrir la licencia sobre ese cargo.

    Le crea además el cargo que va a ocupar, copiado del titular: de ahí sale
    su alta en las novedades del mes, sin cargarla a mano.
    """
    asignacion = get_object_or_404(
        AsignacionHoraria.objects.select_related("cargo"),
        pk=pk,
        version__institucion=request.institucion,
    )
    fecha = _fecha(request.POST.get("fecha")) or date.today()
    licencia = buscador.licencia_de_la_hora(request.institucion, asignacion, fecha)

    if licencia is None:
        messages.error(
            request,
            "Esa hora no tiene una licencia detrás. Cargá primero la licencia del "
            "titular: la suplencia se apoya en ella y es lo que después la convierte "
            "en alta para la liquidación.",
        )
        return _volver(request, "cursos_del_dia")

    suplente = get_object_or_404(Legajo.objects.del_contexto(), pk=request.POST.get("suplente"))
    if asignacion.cargo_id is None:
        messages.error(request, "Esa hora no está asociada a un cargo del titular.")
        return _volver(request, "cursos_del_dia")

    cobertura, creada = Cobertura.objects.get_or_create(
        institucion=request.institucion,
        licencia=licencia,
        cargo=asignacion.cargo,
        defaults={
            "tipo": TipoCobertura.SUPLENTE,
            "suplente": suplente,
            "fecha_inicio": licencia.fecha_inicio,
            "fecha_fin": licencia.fecha_fin,
        },
    )
    if not creada:
        cobertura.tipo = TipoCobertura.SUPLENTE
        cobertura.suplente = suplente
        cobertura.save(update_fields=["tipo", "suplente", "actualizado_en"])
    cobertura.designar_cargo_del_suplente()
    registrar_auditoria(
        AccionAuditada.CREACION,
        cobertura,
        usuario=request.user,
        descripcion=(
            f"Designó a {suplente.nombre_completo} como suplente de "
            f"{asignacion.cargo.legajo.nombre_completo} ({asignacion.cargo.descripcion})"
        ),
    )

    messages.success(
        request,
        f"{suplente.nombre_completo} cubre {asignacion.cargo.descripcion} "
        f"del {cobertura.fecha_inicio:%d/%m} al {cobertura.fecha_fin:%d/%m}. "
        "Falta avisarle.",
    )
    return HttpResponseRedirect(
        reverse("cubrir_ahora", args=[asignacion.pk]) + f"?fecha={fecha:%Y-%m-%d}"
    )


@login_required
@permission_required("licencias.change_cobertura", raise_exception=True)
def avisar_suplencia(request, pk: int):
    """El aviso al suplente: el mismo mensaje, por email o por WhatsApp."""
    cobertura = get_object_or_404(
        Cobertura.objects.del_contexto().select_related(
            "suplente", "cargo__legajo", "cargo__curso", "licencia"
        ),
        pk=pk,
    )
    if cobertura.suplente_id is None:
        messages.error(request, "Esa cobertura no tiene suplente designado.")
        return _volver(request)

    if request.method == "POST":
        return _mandar_el_aviso(request, cobertura)

    return render(
        request,
        "licencias/avisar.html",
        {
            "cobertura": cobertura,
            "mensaje": avisos.mensaje_para(cobertura),
            "asunto": avisos.asunto_para(cobertura),
            "link_whatsapp": avisos.link_de_whatsapp(cobertura),
        },
    )


def _mandar_el_aviso(request, cobertura):
    via = request.POST.get("via")

    if via == ViaAviso.EMAIL:
        if avisos.enviar_por_email(cobertura):
            _registrar_aviso(cobertura, ViaAviso.EMAIL)
            messages.success(request, f"Aviso enviado a {cobertura.suplente.email}.")
        else:
            messages.error(
                request,
                "No se pudo enviar el correo. Puede ser que la persona no tenga "
                "email cargado, o que este servidor todavía no tenga configurado "
                "el envío. Queda la opción de WhatsApp o el llamado.",
            )
    elif via in (ViaAviso.WHATSAPP, ViaAviso.OTRO):
        # WhatsApp y el llamado los hace una persona; el sistema solo deja
        # registrado que se avisó, para que nadie llame dos veces ni ninguna.
        _registrar_aviso(cobertura, via)
        messages.success(request, f"Anotado: {cobertura.suplente.nombre_completo} fue avisado/a.")
    else:
        messages.error(request, "No se indicó por dónde se avisó.")

    return HttpResponseRedirect(reverse("avisar_suplencia", args=[cobertura.pk]))


def _registrar_aviso(cobertura, via):
    from django.utils import timezone

    cobertura.notificada_en = timezone.now()
    cobertura.notificada_por = via
    cobertura.save(update_fields=["notificada_en", "notificada_por", "actualizado_en"])
