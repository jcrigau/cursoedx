"""Probar contraseñas al voleo tiene que dejar de servir.

Sin freno, cualquiera con tiempo prueba claves contra la dirección del sistema
hasta acertar. Con freno, después de unos cuantos errores hay que esperar.
Lo que no puede pasar es dejar afuera a quien se equivocó y después acertó.
"""

import pytest
from django.urls import reverse

from core.models import AccionAuditada, IntentoDeAcceso, RegistroAuditoria, Usuario
from core.seguridad import INTENTOS_MAXIMOS


@pytest.fixture
def usuaria(db):
    return Usuario.objects.create_user(
        email="secre@escuela.edu.ar",
        password="una-clave-larga-y-buena",
        nombre="Ana",
        apellido="Pérez",
    )


def intentar(client, email, clave):
    return client.post(reverse("login"), {"username": email, "password": clave})


@pytest.mark.django_db
class TestElFreno:
    def test_los_intentos_quedan_registrados(self, client, usuaria):
        intentar(client, usuaria.email, "no-es")
        intentar(client, usuaria.email, "una-clave-larga-y-buena")

        intentos = list(IntentoDeAcceso.objects.order_by("creado_en"))
        assert [intento.exito for intento in intentos] == [False, True]
        # Nunca se guarda la contraseña probada.
        assert not any("clave" in (intento.email or "") for intento in intentos)

    def test_despues_de_varios_errores_hay_que_esperar(self, client, usuaria):
        for _ in range(INTENTOS_MAXIMOS):
            intentar(client, usuaria.email, "no-es")

        # Ahora ni siquiera con la clave correcta entra: está frenado.
        respuesta = intentar(client, usuaria.email, "una-clave-larga-y-buena")

        assert respuesta.status_code == 200  # vuelve al formulario
        assert "Demasiados intentos" in respuesta.content.decode()
        assert not respuesta.wsgi_request.user.is_authenticated

    def test_el_bloqueo_queda_en_la_bitacora(self, client, usuaria):
        for _ in range(INTENTOS_MAXIMOS + 1):
            intentar(client, usuaria.email, "no-es")

        assert RegistroAuditoria.objects.filter(accion=AccionAuditada.BLOQUEO).exists()

    def test_equivocarse_y_despues_acertar_no_arrastra_nada(self, client, usuaria):
        """Los fallos se cuentan desde el último ingreso bueno, no desde siempre."""
        for _ in range(INTENTOS_MAXIMOS - 1):
            intentar(client, usuaria.email, "no-es")
        intentar(client, usuaria.email, "una-clave-larga-y-buena")  # entra
        client.logout()

        for _ in range(INTENTOS_MAXIMOS - 1):
            intentar(client, usuaria.email, "no-es")
        respuesta = intentar(client, usuaria.email, "una-clave-larga-y-buena")

        assert respuesta.status_code == 302  # entró: no quedó frenada
        assert respuesta.url == reverse("inicio")

    def test_el_mensaje_no_dice_si_el_email_existe(self, client, usuaria):
        """Decirlo le regala al atacante la mitad del trabajo."""
        conocido = intentar(client, usuaria.email, "no-es").content.decode()
        inventado = intentar(client, "nadie@ninguna.edu.ar", "no-es").content.decode()

        assert "no existe" not in inventado.lower()
        assert ("Correo electrónico" in conocido) == ("Correo electrónico" in inventado)


@pytest.mark.django_db
class TestLosBorrados:
    """El respaldo permite recuperar; la bitácora permite darse cuenta."""

    def test_borrar_desde_el_panel_queda_registrado(self, client, institucion, secretaria):
        from datetime import date

        from legajos.models import Legajo

        secretaria.is_superuser = True
        secretaria.save()
        legajo = Legajo.objects.create(
            institucion=institucion,
            apellido="Benítez",
            nombre="Ana",
            cuil="27-30000001-1",
            fecha_ingreso=date.today(),
        )
        client.force_login(secretaria)

        client.post(
            reverse("admin:legajos_legajo_delete", args=[legajo.pk]), {"post": "yes"}, follow=True
        )

        assert not Legajo.objects.filter(pk=legajo.pk).exists()
        rastro = RegistroAuditoria.objects.filter(accion=AccionAuditada.BAJA).last()
        assert rastro is not None
        assert "Benítez" in rastro.descripcion
        assert rastro.usuario_id == secretaria.pk


@pytest.mark.django_db
class TestLasCabeceras:
    def test_el_navegador_solo_acepta_contenido_propio(self, client, usuaria):
        client.force_login(usuaria)

        respuesta = client.get(reverse("login"))

        politica = respuesta["Content-Security-Policy"]
        assert "default-src 'self'" in politica
        # Nada de meter el sistema en un iframe ajeno ni mandar un formulario
        # a otro servidor.
        assert "frame-ancestors 'none'" in politica
        assert "form-action 'self'" in politica

    def test_las_claves_cortas_no_se_aceptan(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            validate_password("Escuela1")  # ocho caracteres

        validate_password("Sombrilla-Verde-71")  # no levanta

    def test_la_sesion_no_dura_para_siempre(self, settings):
        assert settings.SESSION_COOKIE_AGE <= 12 * 60 * 60
        assert settings.SESSION_SAVE_EVERY_REQUEST is True
