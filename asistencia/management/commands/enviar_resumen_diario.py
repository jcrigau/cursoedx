"""El día de la escuela, por correo, antes de salir de casa.

Se programa en el hosting (en PythonAnywhere: pestaña Tasks) para las 7:00 y
le manda a secretaría y dirección un resumen de lo que los espera: quiénes
faltan y por qué, cuántas horas quedan sin cubrir, y qué hay para resolver.

    python manage.py enviar_resumen_diario
    python manage.py enviar_resumen_diario --a alguien@escuela.edu.ar --probar
"""

from datetime import date

from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from asistencia.parte import coberturas_pendientes, parte_diario
from core.models import Institucion, Membresia, Rol
from core.tenancy import usar_institucion
from licencias.models import EstadoLicencia, Licencia

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


class Command(BaseCommand):
    help = "Manda a secretaría y dirección el resumen del día por correo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--a",
            action="append",
            default=None,
            help=(
                "Mandar solo a esta dirección (repetible). Sin esto, va a "
                "secretaría y dirección de cada escuela."
            ),
        )
        parser.add_argument(
            "--probar",
            action="store_true",
            help="Mostrar el mensaje por pantalla en lugar de enviarlo.",
        )

    def handle(self, *args, **opciones):
        hoy = date.today()
        enviados = 0

        for institucion in Institucion.objects.filter(activa=True):
            with usar_institucion(institucion):
                cuerpo = self._resumen(institucion, hoy)
            if cuerpo is None:
                self.stdout.write(f"{institucion}: sin clases hoy, no se envía.")
                continue

            destinos = opciones["a"] or self._destinatarios(institucion)
            if not destinos:
                self.stdout.write(
                    self.style.WARNING(
                        f"{institucion}: nadie de secretaría o dirección tiene email."
                    )
                )
                continue

            asunto = f"{institucion} · el día de hoy, {hoy:%d/%m}"
            if opciones["probar"]:
                self.stdout.write(f"\n--- {asunto} → {', '.join(destinos)} ---\n{cuerpo}")
                continue

            enviados += send_mail(
                subject=asunto,
                message=cuerpo,
                from_email=None,  # usa el remitente configurado
                recipient_list=destinos,
                fail_silently=False,
            )
            self.stdout.write(f"{institucion}: enviado a {', '.join(destinos)}.")

        if enviados:
            self.stdout.write(self.style.SUCCESS(f"{enviados} resumen(es) enviados."))

    def _destinatarios(self, institucion) -> list[str]:
        return sorted(
            {
                membresia.usuario.email
                for membresia in Membresia.objects.filter(
                    institucion=institucion,
                    activa=True,
                    rol__in=[Rol.SECRETARIA, Rol.DIRECTIVO],
                ).select_related("usuario")
                if membresia.usuario.email
            }
        )

    def _resumen(self, institucion, hoy) -> str | None:
        """El texto del correo, o nada si hoy no hay clases."""
        parte = parte_diario(institucion, hoy)
        if not parte.hay_clases:
            return None

        lineas = [f"Buen día. Así viene el {DIAS[hoy.weekday()]} {hoy:%d/%m} en {institucion}:", ""]

        suplentes = [linea for linea in parte.lineas if linea.es_suplente]
        de_licencia = list(
            Licencia.objects.filter(
                institucion=institucion,
                estado=EstadoLicencia.APROBADA,
                fecha_inicio__lte=hoy,
                fecha_fin__gte=hoy,
            ).select_related("legajo", "tipo")
        )

        if de_licencia:
            lineas.append("De licencia:")
            for licencia in de_licencia:
                lineas.append(
                    f"  - {licencia.legajo.nombre_completo}: {licencia.tipo.codigo}, "
                    f"hasta el {licencia.fecha_fin:%d/%m}"
                )
            for linea in suplentes:
                lineas.append(f"  - Cubre {linea.legajo.nombre_completo} (suplente)")
            lineas.append("")

        if parte.sin_cobertura:
            cursos = sorted({hora.curso for hora in parte.sin_cobertura})
            lineas.append(
                f"OJO: {len(parte.sin_cobertura)} hora(s) sin docente en "
                f"{', '.join(cursos)}. Resolver en «Cursos de hoy»."
            )
            lineas.append("")

        pendientes = coberturas_pendientes(institucion, hoy)
        if pendientes:
            lineas.append(f"Coberturas sin decidir: {len(pendientes)}.")
        solicitadas = Licencia.objects.filter(
            institucion=institucion, estado=EstadoLicencia.SOLICITADA
        ).count()
        if solicitadas:
            lineas.append(f"Licencias esperando aprobación: {solicitadas}.")

        lineas.append("")
        lineas.append(f"{len(parte.lineas)} persona(s) en el parte de hoy.")
        lineas.append("El detalle, en el sistema: Parte diario y Cursos de hoy.")
        return "\n".join(lineas)
