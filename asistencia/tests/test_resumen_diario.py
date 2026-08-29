"""El correo de las 7:00: qué dice y a quién le llega."""

import pytest
from django.core import mail
from django.core.management import call_command

from core.models import Membresia, Rol, Usuario
from core.tenancy import usar_institucion

from .conftest import dar_licencia, fecha_con_clases  # noqa: F401


@pytest.fixture
def con_secretaria_con_email(con_horario_publicado):
    institucion = con_horario_publicado["escuela"]["institucion"]
    usuaria = Usuario.objects.create_user(
        email="sec@escuela.edu.ar", password="x", nombre="Sec", apellido="Retaria"
    )
    Membresia.objects.create(usuario=usuaria, institucion=institucion, rol=Rol.SECRETARIA)
    return con_horario_publicado


class TestResumenDiario:
    def test_el_texto_cuenta_lo_que_importa(self, con_secretaria_con_email, monkeypatch):
        """Se arma para un día con clases y nombra a quien está de licencia."""
        from asistencia.management.commands.enviar_resumen_diario import Command

        datos = con_secretaria_con_email
        institucion = datos["escuela"]["institucion"]
        dar_licencia(datos, desde=datos["fecha"], hasta=datos["fecha"])

        with usar_institucion(institucion):
            cuerpo = Command()._resumen(institucion, datos["fecha"])

        assert cuerpo is not None
        assert datos["docente"].nombre_completo in cuerpo
        assert "sin decidir" in cuerpo or "sin docente" in cuerpo

    def test_un_dia_sin_clases_no_manda_nada(self, con_secretaria_con_email):
        from asistencia.management.commands.enviar_resumen_diario import Command

        datos = con_secretaria_con_email
        institucion = datos["escuela"]["institucion"]

        with usar_institucion(institucion):
            assert Command()._resumen(institucion, datos["fecha_libre"]) is None

    def test_llega_a_secretaria_y_direccion(self, con_secretaria_con_email):
        from asistencia.management.commands.enviar_resumen_diario import Command

        institucion = con_secretaria_con_email["escuela"]["institucion"]
        destinos = Command()._destinatarios(institucion)

        assert "sec@escuela.edu.ar" in destinos

    def test_probar_no_envia(self, con_secretaria_con_email, monkeypatch):
        from datetime import date as fecha_real

        import asistencia.management.commands.enviar_resumen_diario as modulo

        class FechaFija(fecha_real):
            @classmethod
            def today(cls):
                return con_secretaria_con_email["fecha"]

        monkeypatch.setattr(modulo, "date", FechaFija)

        call_command("enviar_resumen_diario", "--probar", verbosity=0)

        assert len(mail.outbox) == 0
