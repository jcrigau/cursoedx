"""Certificación de servicios: el documento que la escuela emite y firma."""

from datetime import date

from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils.text import slugify

from core.models import AccionAuditada, registrar_auditoria

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

    pdf = _a_pdf(html, request)
    registrar_auditoria(
        AccionAuditada.EXPORTACION,
        legajo,
        usuario=request.user,
        descripcion=f"Certificación de servicios de {legajo.nombre_completo}",
    )
    nombre = slugify(f"certificacion-servicios-{legajo.apellido}-{legajo.nombre}")
    return HttpResponse(
        pdf,
        content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}.pdf"'},
    )


def _a_pdf(html: str, request) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as error:  # pragma: no cover - depende del entorno
        raise Http404(
            "Falta WeasyPrint para generar el PDF. Mientras tanto se puede ver la "
            "certificación con ?formato=html e imprimirla desde el navegador."
        ) from error
    return HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
