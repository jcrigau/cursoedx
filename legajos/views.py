"""Certificación de servicios: el documento que la escuela emite y firma."""

from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from core.models import AccionAuditada, registrar_auditoria
from core.pdf import responder_pdf
from licencias.models import licencias_vigentes

from .antiguedad import antiguedad_en_la_institucion, calcular_antiguedad
from .models import Legajo


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def certificacion_servicios(request, pk):
    """Genera la certificación de servicios de un legajo.

    Sale en PDF; con ``?formato=html`` se ve en pantalla, que es cómodo para
    revisarla antes de imprimirla.
    """
    legajo = get_object_or_404(Legajo.objects.del_contexto().select_related("institucion"), pk=pk)
    a_fecha = date.today()

    cargos = list(legajo.cargos.select_related("materia", "curso", "nivel").order_by("fecha_alta"))
    contexto = {
        "legajo": legajo,
        "institucion": legajo.institucion,
        "cargos": cargos,
        "servicios_anteriores": list(legajo.servicios_anteriores.order_by("desde")),
        "antiguedad_institucion": antiguedad_en_la_institucion(legajo, a_fecha),
        "antiguedad_total": calcular_antiguedad(legajo, a_fecha),
        "fecha": a_fecha,
        "emitido_por": request.user,
    }
    html = render_to_string("legajos/certificacion.html", contexto, request=request)

    if request.GET.get("formato") == "html":
        return HttpResponse(html)

    registrar_auditoria(
        AccionAuditada.EXPORTACION,
        legajo,
        usuario=request.user,
        descripcion=f"Certificación de servicios de {legajo.nombre_completo}",
    )
    return responder_pdf(
        html, request, f"certificacion-servicios-{legajo.apellido}-{legajo.nombre}"
    )


@login_required
@permission_required("legajos.view_legajo", raise_exception=True)
def buscar(request):
    """Buscar una persona por apellido, nombre o CUIL.

    La secretaría piensa en personas —«¿qué pasa con Herrera?»— y hasta ahora
    para llegar a alguien había que saber en qué pantalla estaba lo que se
    quería ver. Acá se escribe el apellido y sale la persona con todo lo suyo
    a un clic: sus cargos, si está de licencia hoy, y qué documentación debe.
    """
    consulta = request.GET.get("q", "").strip()
    encontrados = []

    if consulta:
        encontrados = list(
            Legajo.objects.del_contexto()
            .filter(
                Q(apellido__icontains=consulta)
                | Q(nombre__icontains=consulta)
                | Q(cuil__icontains=consulta)
            )
            .prefetch_related("cargos")
            .order_by("apellido", "nombre")[:25]
        )

    hoy = date.today()
    de_licencia = {
        licencia.legajo_id: licencia for licencia in licencias_vigentes(request.institucion, hoy)
    }
    for legajo in encontrados:
        legajo.licencia_de_hoy = de_licencia.get(legajo.id)

    return render(
        request,
        "legajos/buscar.html",
        {"consulta": consulta, "encontrados": encontrados, "hoy": hoy},
    )
