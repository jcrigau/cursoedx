"""La pantalla de ingreso, con freno y con memoria.

Django trae la suya, que anda bien; esta le agrega dos cosas que una escuela
expuesta a internet necesita: que un intento fallido quede registrado, y que
probar contraseñas al voleo deje de servir después de unos cuantos errores.
"""

from django.contrib.auth import views as vistas_django

from . import seguridad


class IngresoView(vistas_django.LoginView):
    """Igual que la de Django, pero cuenta los intentos."""

    template_name = "registration/login.html"

    def form_valid(self, form):
        seguridad.registrar_intento(form.cleaned_data.get("username", ""), self._ip(), exito=True)
        return super().form_valid(form)

    def form_invalid(self, form):
        # Se registra acá y no en la señal de Django para tener la IP a mano.
        seguridad.registrar_intento(form.data.get("username", ""), self._ip(), exito=False)
        return super().form_invalid(form)

    def post(self, request, *args, **kwargs):
        espera = seguridad.minutos_de_espera(request.POST.get("username", ""), self._ip())
        if espera:
            self._avisar_del_bloqueo(request)
            # El mensaje va aparte del formulario: el de credenciales es a
            # propósito genérico —no dice si el email existe— y este tiene que
            # poder explicarse.
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_form(),
                    bloqueado=(
                        f"Demasiados intentos fallidos. Probá de nuevo en {espera} minuto(s). "
                        "Si no te acordás la contraseña, pedile a secretaría que te la cambie."
                    ),
                )
            )
        return super().post(request, *args, **kwargs)

    def _ip(self):
        return seguridad.ip_de(self.request)

    def _avisar_del_bloqueo(self, request):
        """Un bloqueo queda en la bitácora: puede ser el rastro de un ataque."""
        from .models import AccionAuditada, registrar_auditoria

        registrar_auditoria(
            AccionAuditada.BLOQUEO,
            descripcion=(
                f"Ingreso bloqueado por intentos fallidos "
                f"({request.POST.get('username', '')} desde {self._ip() or 'IP desconocida'})"
            ),
            modelo="IntentoDeAcceso",
        )
