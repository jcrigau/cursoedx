"""Portal del docente: lo suyo y nada más.

Todas las pantallas arrancan por el legajo vinculado al usuario. Si no hay
vínculo no hay portal: es la garantía de que nadie ve datos de otra persona,
por más que cambie un número en la dirección.
"""

from datetime import date, datetime, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from asistencia.parte import version_vigente
from core.bienvenida import para as bienvenida_para
from horarios.models import AsignacionHoraria
from horarios.vistas_grilla import grilla_de_docente
from legajos.antiguedad import calcular_antiguedad
from legajos.models import Legajo
from licencias.models import EstadoLicencia, Licencia, TipoLicencia

from .models import AvisoInasistencia, EstadoAviso, Fichada, MotivoAviso, TipoFichada


def legajo_del_usuario(request) -> Legajo | None:
    """El legajo de quien está conectado, dentro de la institución activa."""
    if request.institucion is None:
        return None
    return (
        Legajo.objects.del_contexto()
        .filter(usuario=request.user)
        .select_related("institucion")
        .first()
    )


def con_legajo(vista):
    """Deja el legajo propio en la vista, o explica por qué no hay portal."""

    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        legajo = legajo_del_usuario(request)
        if legajo is None:
            return render(request, "portal/sin_legajo.html", status=403)
        return vista(request, legajo, *args, **kwargs)

    return envoltura


def _clases_de(legajo, fecha: date):
    """Las clases que le tocan ese día según el horario vigente."""
    version = version_vigente(legajo.institucion, fecha)
    if version is None:
        return None, []
    clases = (
        AsignacionHoraria.objects.filter(version=version, legajo=legajo, dia_semana=fecha.weekday())
        .select_related("curso", "materia")
        .order_by("hora_inicio")
    )
    return version, list(clases)


@con_legajo
def inicio(request, legajo):
    """Lo de hoy: clases, fichada, aviso y licencias en curso."""
    hoy = date.today()
    version, clases = _clases_de(legajo, hoy)

    licencia = (
        legajo.licencias.filter(
            estado=EstadoLicencia.APROBADA, fecha_inicio__lte=hoy, fecha_fin__gte=hoy
        )
        .select_related("tipo")
        .first()
    )
    contexto = {
        "legajo": legajo,
        "hoy": hoy,
        "clases": clases,
        "hay_horario": version is not None,
        "fichada": legajo.fichadas.filter(fecha=hoy, tipo=TipoFichada.ENTRADA).first(),
        "salida": legajo.fichadas.filter(fecha=hoy, tipo=TipoFichada.SALIDA).first(),
        "aviso": legajo.avisos.filter(fecha=hoy).exclude(estado=EstadoAviso.ANULADO).first(),
        "licencia": licencia,
        "puede_fichar": legajo.institucion.latitud is not None,
        "documentos_por_vencer": [
            documento
            for documento in legajo.documentos.select_related("tipo")
            if documento.por_vencer or documento.esta_vencido
        ],
    }
    contexto["seccion"] = "inicio"
    contexto["bienvenida"] = bienvenida_para(request.user, legajo.institucion)
    return render(request, "portal/inicio.html", contexto)


@con_legajo
def mi_horario(request, legajo):
    hoy = date.today()
    version = version_vigente(legajo.institucion, hoy)
    grilla = grilla_de_docente(version, legajo) if version else None
    return render(
        request,
        "portal/horario.html",
        {"legajo": legajo, "grilla": grilla, "version": version, "seccion": "horario"},
    )


@con_legajo
def mi_legajo(request, legajo):
    """Los datos que la escuela tiene de la persona."""
    return render(
        request,
        "portal/legajo.html",
        {
            "legajo": legajo,
            "cargos": legajo.cargos.select_related("materia", "curso").order_by("-fecha_alta"),
            "documentos": legajo.documentos.select_related("tipo").order_by("fecha_vencimiento"),
            "titulos": legajo.titulos.all(),
            "antiguedad": calcular_antiguedad(legajo),
            "seccion": "legajo",
        },
    )


@con_legajo
def mis_licencias(request, legajo):
    """Historial de licencias y solicitud de una nueva."""
    if request.method == "POST":
        return _solicitar_licencia(request, legajo)

    return render(
        request,
        "portal/licencias.html",
        {
            "legajo": legajo,
            "licencias": legajo.licencias.select_related("tipo").order_by("-fecha_inicio"),
            "tipos": TipoLicencia.objects.del_contexto().filter(activo=True),
            "hoy": date.today(),
            "seccion": "licencias",
        },
    )


def _solicitar_licencia(request, legajo):
    """Crea la solicitud. Queda pendiente hasta que la resuelva el directivo."""
    tipo = get_object_or_404(
        TipoLicencia.objects.del_contexto(), pk=request.POST.get("tipo"), activo=True
    )
    try:
        desde = datetime.strptime(request.POST["desde"], "%Y-%m-%d").date()
        hasta = datetime.strptime(request.POST["hasta"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        messages.error(request, "Revisá las fechas de la licencia.")
        return HttpResponseRedirect(reverse("portal_licencias"))

    licencia = Licencia(
        institucion=legajo.institucion,
        legajo=legajo,
        tipo=tipo,
        fecha_inicio=desde,
        fecha_fin=hasta,
        estado=EstadoLicencia.SOLICITADA,
        observaciones=request.POST.get("observaciones", "")[:500],
        certificado=request.FILES.get("certificado"),
    )

    excesos = licencia.excesos()
    if excesos and not tipo.extensible_con_aval:
        for exceso in excesos:
            messages.error(request, exceso)
        return HttpResponseRedirect(reverse("portal_licencias"))

    if licencia.fecha_fin < licencia.fecha_inicio:
        messages.error(request, "La fecha de fin no puede ser anterior a la de inicio.")
        return HttpResponseRedirect(reverse("portal_licencias"))

    licencia.save()
    for exceso in excesos:
        messages.warning(request, f"Se envió igual, pero tené en cuenta: {exceso}")
    messages.success(
        request, "Solicitud enviada. Queda pendiente hasta que la apruebe la dirección."
    )
    return HttpResponseRedirect(reverse("portal_licencias"))


@con_legajo
def avisar(request, legajo):
    """Avisar que no se va a poder asistir."""
    if request.method == "POST":
        return _guardar_aviso(request, legajo)

    hoy = date.today()
    return render(
        request,
        "portal/avisar.html",
        {
            "legajo": legajo,
            "hoy": hoy,
            "manana": hoy + timedelta(days=1),
            "motivos": MotivoAviso.choices,
            "avisos": legajo.avisos.exclude(estado=EstadoAviso.ANULADO).order_by("-fecha")[:10],
            "seccion": "avisar",
        },
    )


def _guardar_aviso(request, legajo):
    try:
        fecha = datetime.strptime(request.POST["fecha"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        messages.error(request, "Revisá la fecha.")
        return HttpResponseRedirect(reverse("portal_avisar"))

    if fecha < date.today():
        messages.error(request, "El aviso es para hoy o para un día que viene.")
        return HttpResponseRedirect(reverse("portal_avisar"))

    aviso, creado = AvisoInasistencia.objects.update_or_create(
        legajo=legajo,
        fecha=fecha,
        defaults={
            "institucion": legajo.institucion,
            "motivo": request.POST.get("motivo", MotivoAviso.OTRO),
            "detalle": request.POST.get("detalle", "")[:300],
            "estado": EstadoAviso.ENVIADO,
        },
    )
    messages.success(
        request,
        "Aviso enviado a secretaría." if creado else "Se actualizó el aviso de ese día.",
    )
    return HttpResponseRedirect(reverse("portal_avisar"))


@require_POST
@con_legajo
def anular_aviso(request, legajo, pk: int):
    aviso = get_object_or_404(AvisoInasistencia, pk=pk, legajo=legajo)
    if not aviso.anulable:
        raise PermissionDenied("Ese aviso ya no se puede anular.")
    aviso.estado = EstadoAviso.ANULADO
    aviso.save(update_fields=["estado", "actualizado_en"])
    messages.info(request, "Aviso anulado.")
    return HttpResponseRedirect(reverse("portal_avisar"))


@require_POST
@con_legajo
def fichar(request, legajo):
    """Registra la entrada o la salida, con la ubicación que manda el celular.

    Se guarda siempre: si la ubicación no llega o cae lejos, queda marcado para
    que la escuela lo revise, pero nunca se pierde la constancia.
    """
    tipo = request.POST.get("tipo", TipoFichada.ENTRADA)
    if tipo not in TipoFichada.values:
        tipo = TipoFichada.ENTRADA

    ahora = timezone.localtime()
    if legajo.fichadas.filter(fecha=ahora.date(), tipo=tipo).exists():
        return JsonResponse(
            {"ok": False, "mensaje": f"Ya registraste tu {tipo.lower()} de hoy."}, status=409
        )

    def numero(clave):
        try:
            return float(request.POST[clave])
        except (KeyError, TypeError, ValueError):
            return None

    fichada = Fichada(
        institucion=legajo.institucion,
        legajo=legajo,
        fecha=ahora.date(),
        hora=ahora.time().replace(microsecond=0),
        tipo=tipo,
        latitud=numero("latitud"),
        longitud=numero("longitud"),
        precision_metros=int(numero("precision") or 0) or None,
    )
    fichada.save()

    if fichada.latitud is None:
        mensaje = "Registrado sin ubicación: avisale a secretaría si hace falta."
    elif fichada.en_la_escuela:
        mensaje = f"{fichada.get_tipo_display()} registrada a las {fichada.hora:%H:%M}."
    else:
        mensaje = (
            f"Registrado a las {fichada.hora:%H:%M}, pero a {fichada.distancia_metros} m "
            "de la escuela. Va a quedar marcado para revisar."
        )

    return JsonResponse(
        {
            "ok": True,
            "mensaje": mensaje,
            "hora": f"{fichada.hora:%H:%M}",
            "en_la_escuela": fichada.en_la_escuela,
        }
    )
