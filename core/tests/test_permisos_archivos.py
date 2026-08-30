"""Cada archivo se autoriza contra su dueño, no contra «estar conectado».

Los docentes tienen usuario del portal: si alcanzara el login, cualquiera
podría abrir el certificado médico de otro escribiendo la dirección. Acá se
prueba lo contrario, que es lo que hace utilizable el módulo de recibos de
sueldo y el de sanciones.
"""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse  # noqa: F401  (se usa al armar rutas legibles)

from core.models import Membresia, Rol, Usuario
from legajos.models import DocumentoLegajo, Legajo, TipoDocumento


def _usuario(email, institucion, rol):
    usuario = Usuario.objects.create_user(
        email=email, password="clave-de-prueba-123", nombre="Alguien", apellido="Prueba"
    )
    Membresia.objects.create(usuario=usuario, institucion=institucion, rol=rol)
    return usuario


@pytest.fixture
def con_certificados(institucion, settings, tmp_path):
    """Dos docentes, cada uno con su apto psicofísico subido."""
    settings.MEDIA_ROOT = tmp_path
    # Las pruebas guardan en memoria; acá hacen falta archivos de verdad,
    # porque lo que se prueba es justamente quién los puede descargar.
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    }
    tipo = TipoDocumento.objects.create(institucion=institucion, nombre="Apto psicofísico")

    gente = {}
    for nombre, email in [
        ("Benítez", "benitez@escuela.edu.ar"),
        ("Cabrera", "cabrera@escuela.edu.ar"),
    ]:
        usuario = _usuario(email, institucion, Rol.DOCENTE)
        legajo = Legajo.objects.create(
            institucion=institucion,
            apellido=nombre,
            nombre="Ana",
            cuil=f"27-3000000{len(gente)}-1",
            fecha_ingreso=date.today(),
            usuario=usuario,
        )
        documento = DocumentoLegajo.objects.create(
            legajo=legajo,
            tipo=tipo,
            archivo=SimpleUploadedFile(f"apto-{nombre}.pdf", b"%PDF-1.4 datos de salud"),
        )
        gente[nombre] = {"usuario": usuario, "legajo": legajo, "url": documento.archivo.url}
    return gente


@pytest.mark.django_db
class TestQuienAbreQue:
    def test_cada_uno_abre_lo_suyo(self, client, con_certificados):
        client.force_login(con_certificados["Benítez"]["usuario"])

        respuesta = client.get(con_certificados["Benítez"]["url"])

        assert respuesta.status_code == 200

    def test_nadie_abre_el_certificado_de_otro(self, client, con_certificados):
        """El caso que importa: un docente con usuario, probando direcciones."""
        client.force_login(con_certificados["Benítez"]["usuario"])

        respuesta = client.get(con_certificados["Cabrera"]["url"])

        # 404 y no 403: tampoco tiene por qué enterarse de que existe.
        assert respuesta.status_code == 404

    def test_secretaria_abre_los_de_su_escuela(self, client, con_certificados, secretaria):
        client.force_login(secretaria)

        assert client.get(con_certificados["Cabrera"]["url"]).status_code == 200

    def test_secretaria_de_otra_escuela_no(self, client, con_certificados, otra_institucion):
        """El permiso dice qué; la institución dice sobre qué datos."""
        ajena = _usuario("otra@escuela.edu.ar", otra_institucion, Rol.SECRETARIA)
        ajena.is_staff = True
        ajena.save()
        client.force_login(ajena)

        assert client.get(con_certificados["Benítez"]["url"]).status_code == 404

    def test_sin_sesion_va_al_login(self, client, con_certificados):
        respuesta = client.get(con_certificados["Benítez"]["url"])

        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_un_archivo_sin_dueño_no_se_entrega(self, client, con_certificados, secretaria):
        """Se falla cerrado: lo que no cuelga de un registro conocido, no sale."""
        client.force_login(secretaria)

        assert client.get("/media/documentos/suelto.pdf").status_code == 404
        assert client.get("/media/otra-cosa/archivo.pdf").status_code == 404

    def test_el_nombre_no_se_puede_adivinar(self, con_certificados):
        """La carpeta lleva un identificador al azar, no «documentos/apto.pdf»."""
        ruta = con_certificados["Benítez"]["url"]

        assert ruta.startswith("/media/documentos/")
        assert len(ruta.split("/")[3]) == 32  # el uuid de la carpeta

    def test_no_se_puede_salir_de_la_carpeta(self, client, con_certificados, secretaria):
        client.force_login(secretaria)

        assert client.get("/media/../config/settings.py").status_code in (400, 403, 404)


@pytest.mark.django_db
class TestQueSePuedeSubir:
    """Un adjunto es un papel escaneado o una foto. Nada más."""

    def _documento(self, institucion, nombre, contenido=b"x"):
        from django.core.exceptions import ValidationError

        legajo = Legajo.objects.create(
            institucion=institucion,
            apellido="Prueba",
            nombre="Ana",
            cuil="27-30000009-1",
            fecha_ingreso=date.today(),
        )
        tipo = TipoDocumento.objects.create(institucion=institucion, nombre="Un papel")
        documento = DocumentoLegajo(
            legajo=legajo, tipo=tipo, archivo=SimpleUploadedFile(nombre, contenido)
        )
        try:
            documento.full_clean()
        except ValidationError as error:
            return error
        return None

    def test_un_pdf_escaneado_entra(self, institucion):
        assert self._documento(institucion, "apto.pdf", b"%PDF-1.4") is None

    def test_una_pagina_web_no(self, institucion):
        """.html y .svg los ejecuta el navegador: servirían para robar sesiones."""
        error = self._documento(institucion, "trampa.html", b"<script>robar()</script>")

        assert error is not None
        assert "no se puede subir" in str(error)

    def test_un_ejecutable_tampoco(self, institucion):
        assert self._documento(institucion, "virus.exe", b"MZ") is not None

    def test_un_archivo_enorme_no(self, institucion):
        from core.archivos import MEGAS_MAXIMOS

        grande = b"0" * ((MEGAS_MAXIMOS + 1) * 1024 * 1024)
        error = self._documento(institucion, "escaneo.pdf", grande)

        assert error is not None
        assert "máximo" in str(error)


@pytest.mark.django_db
class TestComoSeEntrega:
    def test_el_navegador_no_adivina_el_tipo(self, client, con_certificados):
        client.force_login(con_certificados["Benítez"]["usuario"])

        respuesta = client.get(con_certificados["Benítez"]["url"])

        assert respuesta["X-Content-Type-Options"] == "nosniff"
        # Un PDF se puede abrir en el visor del navegador sin riesgo.
        assert "attachment" not in respuesta.get("Content-Disposition", "")
