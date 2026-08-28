"""Vistas base: tablero de inicio y cambio de institución."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .middleware import CLAVE_SESION


@login_required
def inicio(request):
    """Tablero de entrada.

    Hoy resume la estructura cargada; a medida que avancen las fases va a
    mostrar también vencimientos, licencias en curso y novedades pendientes
    (módulo M7 del documento de requerimientos).
    """
    institucion = request.institucion
    if institucion is None:
        return render(request, "core/sin_institucion.html", status=403)

    # Import local: el tablero cruza módulos y va a sumar más apps por fase.
    from estructura.models import (
        BloqueHorario,
        CicloLectivo,
        Curso,
        EstadoCiclo,
        Materia,
        Nivel,
        TipoBloque,
    )

    ciclo = (
        CicloLectivo.objects.del_contexto().filter(estado=EstadoCiclo.ACTIVO).first()
        or CicloLectivo.objects.del_contexto().first()
    )
    cursos = Curso.objects.del_contexto()
    if ciclo is not None:
        cursos = cursos.filter(ciclo_lectivo=ciclo)

    contexto = {
        "ciclo": ciclo,
        "cantidad_niveles": Nivel.objects.del_contexto().count(),
        "cantidad_cursos": cursos.count(),
        "cantidad_materias": Materia.objects.del_contexto().count(),
        "periodos": list(ciclo.periodos.all()) if ciclo else [],
        "tiene_grilla": BloqueHorario.objects.filter(
            esquema__institucion=institucion, tipo=TipoBloque.CLASE
        ).exists(),
        "cursos": cursos.select_related("nivel", "turno", "esquema_horario")[:12],
    }
    contexto.update(_resumen_de_personal(institucion))
    return render(request, "core/inicio.html", contexto)


def _resumen_de_personal(institucion) -> dict:
    """Personal activo y estado de la documentación (módulo de legajos)."""
    from legajos.models import DocumentoLegajo, EstadoLegajo, FuentePago, Legajo

    activos = Legajo.objects.del_contexto().filter(estado=EstadoLegajo.ACTIVO)

    # Los documentos con vencimiento son pocos (unos cientos): se revisan en
    # Python porque cada tipo tiene su propia ventana de preaviso.
    documentos = (
        DocumentoLegajo.objects.filter(
            legajo__institucion=institucion, fecha_vencimiento__isnull=False
        )
        .select_related("tipo", "legajo")
        .order_by("fecha_vencimiento")
    )
    vencidos = [documento for documento in documentos if documento.esta_vencido]
    por_vencer = [documento for documento in documentos if documento.por_vencer]

    return {
        "cantidad_personal": activos.count(),
        "personal_por_fuente": {
            "subvencionado": activos.filter(
                cargos__fuente_pago=FuentePago.SUBVENCIONADO, cargos__fecha_baja__isnull=True
            )
            .distinct()
            .count(),
            "interno": activos.filter(
                cargos__fuente_pago=FuentePago.INTERNO, cargos__fecha_baja__isnull=True
            )
            .distinct()
            .count(),
        },
        "documentos_vencidos": vencidos,
        "documentos_por_vencer": por_vencer,
    }


@require_POST
@login_required
def cambiar_institucion(request):
    """Cambia la escuela activa, validando que el usuario tenga acceso."""
    institucion_id = request.POST.get("institucion")
    destino = request.POST.get("siguiente") or reverse("inicio")

    elegida = request.user.instituciones().filter(pk=institucion_id).first()
    if elegida is None:
        messages.error(request, "No tenés acceso a esa institución.")
        return HttpResponseRedirect(destino)

    request.session[CLAVE_SESION] = elegida.pk
    messages.success(request, f"Trabajando en {elegida}.")
    return HttpResponseRedirect(destino)
