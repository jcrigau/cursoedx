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
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST

from legajos.models import MotivoBaja

from .models import Cobertura, Licencia, TipoCobertura

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
