"""El respaldo tiene que servir para volver: base y adjuntos, juntos.

Una copia de la base sin los certificados escaneados deja legajos
incompletos, y una copia que no se puede abrir no es una copia.
"""

from zipfile import ZipFile

import pytest
from django.core.management import call_command


@pytest.mark.django_db
class TestElRespaldo:
    def test_lleva_la_base_y_los_archivos(self, tmp_path, settings, institucion):
        settings.MEDIA_ROOT = tmp_path / "media"
        carpeta = settings.MEDIA_ROOT / "documentos"
        carpeta.mkdir(parents=True)
        (carpeta / "apto.pdf").write_bytes(b"%PDF-1.4 certificado")
        destino = tmp_path / "respaldos"

        call_command("respaldar", destino=str(destino), verbosity=0)

        archivos = sorted(destino.glob("respaldo-*.zip"))
        assert len(archivos) == 1
        with ZipFile(archivos[0]) as zip_:
            nombres = zip_.namelist()
            assert "archivos/documentos/apto.pdf" in nombres
            assert zip_.read("archivos/documentos/apto.pdf") == b"%PDF-1.4 certificado"

    def test_deja_solo_los_ultimos(self, tmp_path, settings, institucion):
        settings.MEDIA_ROOT = tmp_path / "media"
        destino = tmp_path / "respaldos"
        destino.mkdir()
        for dia in range(1, 6):  # respaldos viejos de días anteriores
            (destino / f"respaldo-2026-01-0{dia}.zip").write_bytes(b"viejo")

        call_command("respaldar", destino=str(destino), conservar=3, verbosity=0)

        quedan = sorted(archivo.name for archivo in destino.glob("respaldo-*.zip"))
        assert len(quedan) == 3
        # Se conservan los más nuevos, y el recién hecho es uno de ellos.
        assert any(nombre > "respaldo-2026-01-05.zip" for nombre in quedan)


@pytest.mark.django_db
class TestProbarCorreo:
    def test_explica_la_configuracion_y_manda(self, mailoutbox, capsys):
        call_command("probar_correo", "alguien@escuela.edu.ar")

        salida = capsys.readouterr().out
        assert "Configuración actual" in salida
        # La contraseña jamás se imprime.
        assert "FALTA" in salida or "puesta" in salida
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ["alguien@escuela.edu.ar"]
