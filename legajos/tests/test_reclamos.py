"""El sistema reclama la documentación; la escuela deja de perseguir.

Lo importante: que le llegue a la persona (no solo a secretaría), que la
copia quede en la escuela, y que no se convierta en un correo diario.
"""

from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.models import Membresia, Rol, Usuario
from legajos.models import DocumentoLegajo, Legajo, TipoDocumento


@pytest.fixture
def con_documento_vencido(institucion):
    legajo = Legajo.objects.create(
        institucion=institucion,
        apellido="Benítez",
        nombre="Ana",
        cuil="27-30000001-1",
        email="ana@escuela.edu.ar",
        fecha_ingreso=date.today(),
    )
    tipo = TipoDocumento.objects.create(
        institucion=institucion, nombre="Apto psicofísico", dias_preaviso=30
    )
    documento = DocumentoLegajo.objects.create(
        legajo=legajo,
        tipo=tipo,
        fecha_emision=date.today() - timedelta(days=400),
        fecha_vencimiento=date.today() - timedelta(days=10),
    )
    directivo = Usuario.objects.create_user(
        email="direccion@escuela.edu.ar", password="x", nombre="Dire", apellido="Ctivo"
    )
    Membresia.objects.create(usuario=directivo, institucion=institucion, rol=Rol.DIRECTIVO)
    return {"legajo": legajo, "documento": documento}


@pytest.mark.django_db
class TestElReclamo:
    def test_le_llega_a_la_persona_con_copia_a_la_escuela(self, con_documento_vencido, mailoutbox):
        call_command("reclamar_documentacion", verbosity=0)

        assert len(mailoutbox) == 1
        correo = mailoutbox[0]
        assert correo.to == ["ana@escuela.edu.ar"]
        assert "direccion@escuela.edu.ar" in correo.cc
        assert "Apto psicofísico" in correo.body
        assert "venció" in correo.body

    def test_no_insiste_todos_los_dias(self, con_documento_vencido, mailoutbox):
        call_command("reclamar_documentacion", verbosity=0)
        call_command("reclamar_documentacion", verbosity=0)

        assert len(mailoutbox) == 1
        con_documento_vencido["documento"].refresh_from_db()
        assert con_documento_vencido["documento"].reclamado_en is not None

    def test_vuelve_a_reclamar_pasadas_dos_semanas(self, con_documento_vencido, mailoutbox):
        documento = con_documento_vencido["documento"]
        documento.reclamado_en = timezone.now() - timedelta(days=20)
        documento.save()

        call_command("reclamar_documentacion", verbosity=0)

        assert len(mailoutbox) == 1

    def test_probar_no_manda_ni_marca(self, con_documento_vencido, mailoutbox):
        call_command("reclamar_documentacion", "--probar", verbosity=0)

        assert not mailoutbox
        con_documento_vencido["documento"].refresh_from_db()
        assert con_documento_vencido["documento"].reclamado_en is None

    def test_lo_que_esta_al_dia_no_molesta_a_nadie(self, con_documento_vencido, mailoutbox):
        documento = con_documento_vencido["documento"]
        documento.fecha_vencimiento = date.today() + timedelta(days=300)
        documento.save()

        call_command("reclamar_documentacion", verbosity=0)

        assert not mailoutbox
