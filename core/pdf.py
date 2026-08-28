"""Generación de PDF, con salida alternativa si el servidor no puede componerlos.

WeasyPrint necesita librerías del sistema (pango) que no están en todos los
hospedajes. Cuando faltan, en lugar de romper la pantalla se devuelve el mismo
documento en HTML: el navegador lo imprime o lo guarda como PDF igual de bien.
"""

from django.http import HttpResponse
from django.utils.text import slugify


def responder_pdf(html: str, request, nombre: str) -> HttpResponse:
    """Devuelve el documento en PDF, o en HTML si WeasyPrint no está disponible."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        # OSError: la librería de Python está, pero faltan las del sistema.
        return HttpResponse(html)

    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    archivo = slugify(nombre) or "documento"
    return HttpResponse(
        pdf,
        content_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{archivo}.pdf"'},
    )
