"""Genera el manual de la secretaría en PDF.

El manual vive como plantilla dentro del proyecto (``templates/docs/``), así
que se versiona con el código y sale siempre con el número de versión de lo
que está instalado. Un manual que no acompaña al sistema envejece mal.

    python manage.py generar_manual
    python manage.py generar_manual --salida /tmp/manual.pdf
"""

from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from core.version import FASE, VERSION

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class Command(BaseCommand):
    help = "Genera el manual de uso de la secretaría en PDF."

    def add_arguments(self, parser):
        parser.add_argument(
            "--salida",
            default="",
            help="Dónde escribirlo. Por defecto, manual-sge-VERSION.pdf en la raíz.",
        )
        parser.add_argument(
            "--html",
            action="store_true",
            help="Escribir el HTML en vez del PDF, para revisarlo en el navegador.",
        )

    def handle(self, *args, **opciones):
        hoy = date.today()
        contexto = {
            "version": VERSION,
            "fase": FASE,
            "fecha": f"{hoy.day} de {MESES[hoy.month - 1]} de {hoy.year}",
        }
        html = render_to_string("docs/manual.html", contexto)

        if opciones["html"]:
            destino = Path(opciones["salida"] or Path(settings.BASE_DIR) / "manual-sge.html")
            destino.write_text(html, encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"Manual en HTML: {destino}"))
            return

        try:
            from weasyprint import HTML
        except (ImportError, OSError) as error:
            # Igual que el resto de los documentos del sistema: sin las
            # librerías de composición, queda el HTML y se imprime desde el
            # navegador con Ctrl+P.
            destino = Path(settings.BASE_DIR) / "manual-sge.html"
            destino.write_text(html, encoding="utf-8")
            self.stdout.write(
                self.style.WARNING(
                    f"WeasyPrint no está disponible en este equipo ({error}). "
                    f"Se escribió el manual en HTML: {destino}\n"
                    "Se convierte a PDF abriéndolo en el navegador con Ctrl+P → "
                    "Guardar como PDF."
                )
            )
            return

        destino = Path(opciones["salida"] or Path(settings.BASE_DIR) / f"manual-sge-{VERSION}.pdf")
        HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(destino)
        self.stdout.write(self.style.SUCCESS(f"Manual generado: {destino}"))
        self.stdout.write(f"  versión {VERSION} — {FASE}")
