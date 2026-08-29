"""Decisiones de cobertura que se toman en un clic.

Cada una de estas se podía hacer desde el panel de administración, pero eran
tres o cuatro pantallas para algo que la escuela resuelve en el momento: «este
curso queda libre», «el suplente sigue una semana más», «se termina hoy».
Puestas donde la decisión aparece —el parte, el tablero— dejan de ser trámite.
"""

from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from horarios.models import AsignacionHoraria
from legajos.models import Legajo, MotivoBaja

from . import avisos
from . import candidatos as buscador
from .models import Cobertura, Licencia, TipoCobertura, ViaAviso

PERMISO = "licencias.change_cobertura"


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
