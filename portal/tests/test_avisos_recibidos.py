"""El aviso del docente llega con ruido y se responde con un toque.

Antes el aviso quedaba esperando a que alguien entrara a mirar el parte. Ahora
al llegar manda un correo a secretaría y dirección, queda al frente del
tablero como comunicación sin responder, y responder es un clic: visto (que el
docente ve en su portal), WhatsApp o correo con el mensaje escrito.
"""

from datetime import date

import pytest
from django.core import mail
from django.urls import reverse

from core.models import Membresia, Rol, Usuario
from portal.models import AvisoInasistencia, EstadoAviso, MotivoAviso

HOY = date.today()


def con_rol(institucion, rol, email):
    usuario = Usuario.objects.create_user(
        email=email, password="clave-de-prueba-123", nombre="Alguien", apellido="De Gestión"
    )
    Membresia.objects.create(usuario=usuario, institucion=institucion, rol=rol)
    return usuario


@pytest.fixture
def gestion(escuela_ubicada):
    institucion = escuela_ubicada["institucion"]
    return {
        "institucion": institucion,
        "secretaria": con_rol(institucion, Rol.SECRETARIA, "secretaria@uno.edu.ar"),
        "directivo": con_rol(institucion, Rol.DIRECTIVO, "directivo@uno.edu.ar"),
    }


def avisar(client, docente_con_portal, motivo=MotivoAviso.ENFERMEDAD):
    client.force_login(docente_con_portal["usuario"])
    client.post(
        "/portal/avisar/",
        {"fecha": f"{HOY:%Y-%m-%d}", "motivo": motivo, "detalle": "Gripe"},
    )
    client.logout()
    return AvisoInasistencia.objects.get()


@pytest.mark.django_db
class TestElAvisoLlega:
    def test_sale_el_correo_a_secretaria_y_direccion(self, client, docente_con_portal, gestion):
        avisar(client, docente_con_portal)

        assert len(mail.outbox) == 1
        correo = mail.outbox[0]
        assert sorted(correo.to) == ["directivo@uno.edu.ar", "secretaria@uno.edu.ar"]
        assert "Suárez" in correo.subject
        assert "enfermedad" in correo.subject.lower()

    def test_sin_emails_de_gestion_no_rompe_nada(self, client, docente_con_portal):
        aviso = avisar(client, docente_con_portal)
        assert aviso.estado == EstadoAviso.ENVIADO
        assert len(mail.outbox) == 0

    def test_queda_al_frente_del_tablero(self, client, docente_con_portal, gestion):
        avisar(client, docente_con_portal)

        client.force_login(gestion["directivo"])
        cuerpo = client.get(reverse("inicio")).content.decode()

        # La tarjeta de comunicaciones y el pendiente urgente, con su link.
        assert "Comunicaciones sin responder" in cuerpo
        assert "Avisos de docentes sin responder" in cuerpo
        assert reverse("avisos_recibidos") in cuerpo

    def test_respondido_ya_no_es_pendiente(self, client, docente_con_portal, gestion):
        aviso = avisar(client, docente_con_portal)
        aviso.marcar_visto()

        client.force_login(gestion["secretaria"])
        cuerpo = client.get(reverse("inicio")).content.decode()
        assert "Avisos de docentes sin responder" not in cuerpo


@pytest.mark.django_db
class TestResponder:
    def test_la_pantalla_lista_lo_que_llego(self, client, docente_con_portal, gestion):
        avisar(client, docente_con_portal)
        client.force_login(gestion["secretaria"])

        cuerpo = client.get(reverse("avisos_recibidos")).content.decode()

        assert "Suárez" in cuerpo
        assert "Gripe" in cuerpo
        assert "Cargar la licencia" in cuerpo

    def test_el_whatsapp_sale_con_el_numero_listo(self, client, docente_con_portal, gestion):
        legajo = docente_con_portal["legajo"]
        legajo.telefono = "02664-15-123456"
        legajo.save()
        avisar(client, docente_con_portal)
        client.force_login(gestion["secretaria"])

        cuerpo = client.get(reverse("avisos_recibidos")).content.decode()

        assert "wa.me/542664123456" in cuerpo
        # El recordatorio del certificado va en el mensaje de enfermedad.
        assert "certificado" in cuerpo

    def test_visto_es_la_respuesta_por_la_app(self, client, docente_con_portal, gestion):
        aviso = avisar(client, docente_con_portal)
        client.force_login(gestion["secretaria"])

        client.post(reverse("responder_aviso", args=[aviso.pk]))

        aviso.refresh_from_db()
        assert aviso.estado == EstadoAviso.VISTO
        # Y el docente lo ve en su portal.
        client.force_login(docente_con_portal["usuario"])
        cuerpo = client.get("/portal/avisar/").content.decode()
        assert "visto por secretaría" in cuerpo.lower()

    def test_el_directivo_tambien_responde(self, client, docente_con_portal, gestion):
        aviso = avisar(client, docente_con_portal)
        client.force_login(gestion["directivo"])

        client.post(reverse("responder_aviso", args=[aviso.pk]))

        aviso.refresh_from_db()
        assert aviso.estado == EstadoAviso.VISTO

    def test_el_docente_no_entra_a_esta_pantalla(self, client, docente_con_portal):
        client.force_login(docente_con_portal["usuario"])
        assert client.get(reverse("avisos_recibidos")).status_code == 403

    def test_no_se_responde_lo_de_otra_escuela(
        self, client, docente_con_portal, gestion, otra_institucion
    ):
        from legajos.models import Legajo

        ajeno = Legajo.objects.create(
            institucion=otra_institucion, apellido="Ajeno", nombre="Juan", cuil="20-30999888-7"
        )
        aviso = AvisoInasistencia.objects.create(
            institucion=otra_institucion, legajo=ajeno, fecha=HOY, motivo=MotivoAviso.OTRO
        )
        client.force_login(gestion["secretaria"])

        assert "Ajeno" not in client.get(reverse("avisos_recibidos")).content.decode()
        assert client.post(reverse("responder_aviso", args=[aviso.pk])).status_code == 404
