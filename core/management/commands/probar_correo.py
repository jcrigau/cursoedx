"""¿El correo del sistema está bien configurado? Averiguarlo en un comando.

Varias cosas dependen del correo —el aviso de inasistencia que llega a
secretaría, el resumen de las 7:00, el reclamo de documentación— y hasta ahora
la única forma de saber si andaban era esperar a que pasara algo real. Acá se
manda un mensaje de prueba y se dice qué falta, sin mostrar nunca la clave.

    python manage.py probar_correo vos@gmail.com
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Manda un correo de prueba y revisa la configuración."

    def add_arguments(self, parser):
        parser.add_argument("destino", help="A qué dirección mandar la prueba.")

    def handle(self, *args, **opciones):
        destino = opciones["destino"]
        self._mostrar_la_configuracion()

        if "console" in settings.EMAIL_BACKEND:
            self.stdout.write(
                self.style.WARNING(
                    "\nNo hay servidor de correo configurado: los mensajes se "
                    "escriben en pantalla y nunca salen de la máquina.\n"
                    "Para activarlo, agregá al archivo .env del servidor:\n"
                    "  SGE_EMAIL_HOST=smtp.gmail.com\n"
                    "  SGE_EMAIL_USUARIO=la.cuenta@gmail.com\n"
                    "  SGE_EMAIL_CLAVE=la-contraseña-de-aplicación\n"
                    "  SGE_EMAIL_REMITENTE=la.cuenta@gmail.com\n"
                    "Con Gmail no va la contraseña de la cuenta: hay que crear "
                    "una «contraseña de aplicación» en la configuración de Google."
                )
            )

        self.stdout.write(f"\nMandando la prueba a {destino}…")
        try:
            enviados = send_mail(
                subject="Prueba del sistema de gestión escolar",
                message=(
                    "Si estás leyendo esto, el correo del sistema quedó bien "
                    "configurado: van a llegar los avisos de inasistencia, el "
                    "resumen del día y los reclamos de documentación."
                ),
                from_email=None,  # usa el remitente configurado
                recipient_list=[destino],
                fail_silently=False,
            )
        except Exception as error:  # noqa: BLE001 — hay que explicarlo, no propagarlo
            raise CommandError(f"{self._explicar(error)}\n\nDetalle técnico: {error}") from error

        if enviados:
            self.stdout.write(
                self.style.SUCCESS(
                    "Enviado. Revisá la bandeja (y la carpeta de correo no deseado)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING("El servidor no rechazó nada, pero tampoco envió.")
            )

    def _mostrar_la_configuracion(self):
        clave = "puesta" if settings.EMAIL_HOST_PASSWORD else self.style.WARNING("FALTA")
        self.stdout.write("Configuración actual:")
        for etiqueta, valor in [
            ("Servidor", settings.EMAIL_HOST or self.style.WARNING("sin configurar")),
            ("Puerto", settings.EMAIL_PORT),
            ("Usuario", settings.EMAIL_HOST_USER or self.style.WARNING("sin configurar")),
            ("Contraseña", clave),  # nunca se imprime el valor
            ("TLS", "sí" if settings.EMAIL_USE_TLS else "no"),
            ("Remitente", settings.DEFAULT_FROM_EMAIL),
        ]:
            self.stdout.write(f"  {etiqueta}: {valor}")

    @staticmethod
    def _explicar(error) -> str:
        """Traduce los errores típicos a algo accionable."""
        texto = str(error).lower()
        if "authentication" in texto or "username and password" in texto:
            return (
                "El servidor rechazó el usuario o la clave. Con Gmail hay que usar "
                "una «contraseña de aplicación», no la de la cuenta."
            )
        if "name or service not known" in texto or "getaddrinfo" in texto:
            return "No se pudo resolver el servidor: revisá SGE_EMAIL_HOST."
        if "timed out" in texto or "connection refused" in texto:
            return (
                "No hubo respuesta del servidor. En hospedajes gratuitos suele estar "
                "bloqueado el correo saliente: revisá el puerto o el plan."
            )
        return "No se pudo enviar."
