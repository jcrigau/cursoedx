"""El mes entero: para decidir si se puede autorizar una licencia más."""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from legajos.models import Legajo
from licencias.models import EstadoLicencia, Licencia, TipoLicencia


@pytest.fixture
def con_licencias(institucion):
    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    primero = date.today().replace(day=1)
    for numero, (apellido, estado) in enumerate(
        [("Benítez", EstadoLicencia.APROBADA), ("Cabrera", EstadoLicencia.SOLICITADA)]
    ):
        legajo = Legajo.objects.create(
            institucion=institucion,
            apellido=apellido,
            nombre="Prueba",
            cuil=f"27-3000000{numero}-1",
            fecha_ingreso=date.today(),
        )
        Licencia.objects.create(
            institucion=institucion,
            legajo=legajo,
            tipo=tipo,
            fecha_inicio=primero,
            fecha_fin=primero + timedelta(days=3),
            estado=estado,
        )
    return institucion


@pytest.mark.django_db
class TestElCalendario:
    def test_muestra_el_mes_con_sus_licencias(self, client, con_licencias, secretaria):
        client.force_login(secretaria)

        cuerpo = client.get(reverse("calendario_licencias")).content.decode()

        assert "Benítez" in cuerpo
        # La solicitada también se ve: es justo la que hay que decidir.
        assert "Cabrera" in cuerpo
        assert "sin-decidir" in cuerpo

    def test_se_puede_ir_a_otro_mes(self, client, con_licencias, secretaria):
        client.force_login(secretaria)
        hoy = date.today()

        respuesta = client.get(reverse("calendario_licencias"), {"anio": 2027, "mes": 3})

        assert respuesta.status_code == 200
        assert "marzo" in respuesta.content.decode().lower()
        assert hoy.year == date.today().year  # no toca nada

    def test_un_mes_imposible_cae_en_el_actual(self, client, con_licencias, secretaria):
        client.force_login(secretaria)

        respuesta = client.get(reverse("calendario_licencias"), {"anio": 2026, "mes": 77})

        assert respuesta.status_code == 200

    def test_no_muestra_licencias_de_otra_escuela(
        self, client, con_licencias, otra_institucion, secretaria
    ):
        ajeno = Legajo.objects.create(
            institucion=otra_institucion, apellido="Ajeno", nombre="Juan", cuil="20-99999999-1"
        )
        tipo = TipoLicencia.objects.create(
            institucion=otra_institucion, nombre="Enfermedad", codigo="Art. 76"
        )
        Licencia.objects.create(
            institucion=otra_institucion,
            legajo=ajeno,
            tipo=tipo,
            fecha_inicio=date.today(),
            fecha_fin=date.today(),
            estado=EstadoLicencia.APROBADA,
        )
        client.force_login(secretaria)

        assert "Ajeno" not in client.get(reverse("calendario_licencias")).content.decode()
