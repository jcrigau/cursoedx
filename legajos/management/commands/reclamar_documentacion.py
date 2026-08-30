"""El sistema reclama la documentación en lugar de que la escuela persiga.

La secretaría ya veía en el tablero a quién se le vence el apto psicofísico,
pero después había que llamar a cada uno. Acá el aviso sale solo: le llega a
la persona —que es quien tiene que ir al médico— con copia a secretaría, para
que quede constancia de que se reclamó.

    python manage.py reclamar_documentacion --probar
    python manage.py reclamar_documentacion

Se programa junto al resumen diario (una vez por día alcanza: cada documento
se reclama como mucho una vez cada DIAS_ENTRE_RECLAMOS).
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.correo import emails_de_gestion
from core.models import Institucion
from legajos.models import DocumentoLegajo, EstadoLegajo

# Insistir todos los días es acoso, no un recordatorio: se espera dos semanas
# entre un reclamo y el siguiente por el mismo documento.
DIAS_ENTRE_RECLAMOS = 14


class Command(BaseCommand):
    help = "Le avisa a cada persona qué documentación se le vence, con copia a secretaría."

    def add_arguments(self, parser):
        parser.add_argument(
            "--probar",
            action="store_true",
            help="Mostrar los mensajes por pantalla sin enviarlos ni marcar nada.",
        )

    def handle(self, *args, **opciones):
        hoy = date.today()
        enviados = 0

        for institucion in Institucion.objects.filter(activa=True):
            for legajo, documentos in self._por_persona(institucion, hoy).items():
                if not legajo.email:
                    self.stdout.write(
                        self.style.WARNING(
                            f"{legajo}: sin email en el legajo, no se le pudo avisar."
                        )
                    )
                    continue

                asunto, cuerpo = self._mensaje(legajo, documentos, hoy)
                if opciones["probar"]:
                    self.stdout.write(f"\n--- {asunto} → {legajo.email} ---\n{cuerpo}")
                    continue

                # Con copia a la escuela: el reclamo tiene que quedar a la
                # vista de quien después lo va a reclamar en persona.
                EmailMessage(
                    subject=asunto,
                    body=cuerpo,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "") or None,
                    to=[legajo.email],
                    cc=emails_de_gestion(institucion),
                ).send(fail_silently=True)
                ahora = timezone.now()
                for documento in documentos:
                    documento.reclamado_en = ahora
                    documento.save(update_fields=["reclamado_en"])
                enviados += 1
                self.stdout.write(f"+ {legajo}: {len(documentos)} documento(s) reclamados.")

        if not opciones["probar"]:
            self.stdout.write(
                self.style.SUCCESS(f"Listo: {enviados} persona(s) recibieron el reclamo.")
            )

    def _por_persona(self, institucion, hoy) -> dict:
        """Lo vencido o por vencer de cada uno, sin repetir lo ya reclamado."""
        limite = timezone.now() - timedelta(days=DIAS_ENTRE_RECLAMOS)
        documentos = (
            DocumentoLegajo.objects.filter(
                legajo__institucion=institucion,
                legajo__estado=EstadoLegajo.ACTIVO,
                fecha_vencimiento__isnull=False,
            )
            .select_related("legajo", "tipo")
            .order_by("legajo__apellido", "fecha_vencimiento")
        )

        agrupados: dict = {}
        for documento in documentos:
            # La ventana de preaviso la define cada tipo de documento.
            if not (documento.esta_vencido or documento.por_vencer):
                continue
            if documento.reclamado_en and documento.reclamado_en > limite:
                continue
            agrupados.setdefault(documento.legajo, []).append(documento)
        return agrupados

    @staticmethod
    def _mensaje(legajo, documentos, hoy) -> tuple[str, str]:
        vencidos = [documento for documento in documentos if documento.esta_vencido]
        asunto = (
            f"{legajo.institucion}: tenés documentación vencida"
            if vencidos
            else f"{legajo.institucion}: se te vence documentación del legajo"
        )

        lineas = [f"Hola {legajo.nombre}:", ""]
        for documento in documentos:
            dias = documento.dias_para_vencer(hoy)
            cuando = (
                f"venció hace {abs(dias)} día(s)"
                if documento.esta_vencido
                else f"vence en {dias} día(s)"
            )
            lineas.append(
                f"  · {documento.tipo} — {cuando} ({documento.fecha_vencimiento:%d/%m/%Y})."
            )
        lineas += [
            "",
            "Acercale el comprobante nuevo a secretaría así lo cargamos en tu legajo.",
            "",
            "Este aviso lo manda el sistema de gestión de la escuela.",
        ]
        return asunto, "\n".join(lineas)
