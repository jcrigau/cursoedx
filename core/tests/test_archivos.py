"""Los archivos subidos se ven —y solo los ve quien está conectado—.

En producción Django no sirve MEDIA_ROOT por su cuenta, así que las fotos y
los certificados del legajo quedaban guardados pero daban 404. Se sirven desde
la app, detrás de login: en esa carpeta hay aptos psicofísicos y certificados
de antecedentes.
"""

import pytest


@pytest.fixture
def un_archivo(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    carpeta = tmp_path / "fotos"
    carpeta.mkdir()
    (carpeta / "carnet.jpg").write_bytes(b"una foto de prueba")
    return "/media/fotos/carnet.jpg"


@pytest.mark.django_db
class TestLosAdjuntos:
    def test_quien_esta_conectado_los_abre(self, client, un_archivo, secretaria):
        client.force_login(secretaria)

        respuesta = client.get(un_archivo)

        assert respuesta.status_code == 200
        assert b"".join(respuesta.streaming_content) == b"una foto de prueba"

    def test_un_desconocido_no(self, client, un_archivo):
        """Son datos de salud y personales: no pueden quedar públicos."""
        respuesta = client.get(un_archivo)

        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_no_se_puede_salir_de_la_carpeta(self, client, secretaria, settings, tmp_path):
        """La ruta se resuelve contra MEDIA_ROOT, no contra el disco entero."""
        settings.MEDIA_ROOT = tmp_path
        client.force_login(secretaria)

        respuesta = client.get("/media/../config/settings.py")

        assert respuesta.status_code in (400, 403, 404)
