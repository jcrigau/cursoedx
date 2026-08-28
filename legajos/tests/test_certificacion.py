"""La certificación de servicios: contenido, permisos y aislamiento."""

from datetime import date

import pytest

from core.models import Membresia, RegistroAuditoria, Rol, Usuario
from legajos.models import Cargo, FuentePago, Legajo, MotivoBaja, SituacionRevista, TipoCargo


@pytest.fixture
def legajo_con_servicios(institucion, db):
    legajo = Legajo.objects.create(
        institucion=institucion,
        apellido="Molina",
        nombre="Carla",
        cuil="27-32456789-1",
    )
    Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.CARGO_BASE,
        denominacion="Preceptor/a",
        jornada_completa=True,
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=date(2020, 3, 1),
    )
    Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.CARGO_BASE,
        denominacion="Bibliotecario/a",
        situacion_revista=SituacionRevista.SUPLENTE,
        fuente_pago=FuentePago.INTERNO,
        fecha_alta=date(2019, 3, 1),
        fecha_baja=date(2019, 12, 31),
        motivo_baja=MotivoBaja.FIN_SUPLENCIA,
    )
    return legajo


def url_de(legajo, formato=None):
    base = f"/legajos/{legajo.pk}/certificacion/"
    return f"{base}?formato={formato}" if formato else base


@pytest.mark.django_db
class TestPermisos:
    def test_exige_login(self, client, legajo_con_servicios):
        respuesta = client.get(url_de(legajo_con_servicios))
        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_un_usuario_sin_permiso_no_accede(self, client, institucion, legajo_con_servicios):
        docente = Usuario.objects.create_user(
            email="docente@uno.edu.ar", password="x", nombre="Luis", apellido="Paz"
        )
        Membresia.objects.create(usuario=docente, institucion=institucion, rol=Rol.DOCENTE)
        client.force_login(docente)
        assert client.get(url_de(legajo_con_servicios)).status_code == 403

    def test_no_se_puede_certificar_un_legajo_de_otra_escuela(
        self, client, secretaria, otra_institucion
    ):
        """El aislamiento también rige acá: el legajo ajeno ni siquiera existe."""
        ajeno = Legajo.objects.create(
            institucion=otra_institucion, apellido="Ajeno", nombre="Juan", cuil="20-30111222-3"
        )
        client.force_login(secretaria)
        assert client.get(url_de(ajeno)).status_code == 404


@pytest.mark.django_db
class TestContenido:
    def test_muestra_cada_periodo_con_su_situacion_de_revista(
        self, client, secretaria, legajo_con_servicios
    ):
        client.force_login(secretaria)
        contenido = client.get(url_de(legajo_con_servicios, "html")).content.decode()

        assert "Molina" in contenido and "Carla" in contenido
        assert "27-32456789-1" in contenido  # el CUIL identifica a la persona
        assert "Titular" in contenido
        assert "Suplente" in contenido
        assert "Preceptor/a" in contenido
        assert "continúa" in contenido  # el cargo sin baja sigue vigente

    def test_informa_la_antiguedad(self, client, secretaria, legajo_con_servicios):
        client.force_login(secretaria)
        contenido = client.get(url_de(legajo_con_servicios, "html")).content.decode()
        assert "Antigüedad en este establecimiento" in contenido

    def test_genera_un_pdf(self, client, secretaria, legajo_con_servicios):
        client.force_login(secretaria)
        respuesta = client.get(url_de(legajo_con_servicios))
        assert respuesta.status_code == 200
        assert respuesta["Content-Type"] == "application/pdf"
        assert respuesta.content.startswith(b"%PDF")

    def test_queda_registrada_en_la_auditoria(self, client, secretaria, legajo_con_servicios):
        client.force_login(secretaria)
        client.get(url_de(legajo_con_servicios))

        registro = RegistroAuditoria.objects.filter(accion="EXPORTACION").first()
        assert registro is not None
        assert registro.usuario == secretaria
        assert "Molina" in registro.descripcion

    def test_un_legajo_sin_cargos_no_falla(self, client, secretaria, institucion):
        vacio = Legajo.objects.create(
            institucion=institucion, apellido="Nuevo", nombre="Ana", cuil="27-40111222-3"
        )
        client.force_login(secretaria)
        contenido = client.get(url_de(vacio, "html")).content.decode()
        assert "no registra cargos" in contenido
