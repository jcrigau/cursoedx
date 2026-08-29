"""La versión tiene que verse siempre, y no puede romper nada si falta git.

El dato es de diagnóstico: sirve para saber qué está corriendo en cada lado.
Justamente por eso no puede tumbar una pantalla cuando el entorno no lo
provee —un despliegue sin repositorio, una imagen sin git—, que es la forma
más tonta de que un sistema se caiga.
"""

import pytest
from django.urls import reverse

from core import version as modulo_version


@pytest.fixture(autouse=True)
def sin_cache():
    """Cada prueba arranca sin la revisión ya resuelta."""
    modulo_version.revision.cache_clear()
    modulo_version.fecha_revision.cache_clear()
    yield
    modulo_version.revision.cache_clear()
    modulo_version.fecha_revision.cache_clear()


def test_la_revision_sale_del_entorno_si_esta(monkeypatch):
    monkeypatch.setenv("SGE_REVISION", "abc123def456789")
    assert modulo_version.revision() == "abc123def456"


def test_sin_git_ni_entorno_la_revision_no_explota(monkeypatch, tmp_path, settings):
    """Un despliegue sin repositorio informa «desconocida», no falla."""
    monkeypatch.delenv("SGE_REVISION", raising=False)
    settings.BASE_DIR = tmp_path  # carpeta vacía: ni REVISION ni .git
    assert modulo_version.revision() == modulo_version.SIN_DATO
    assert modulo_version.etiqueta() == f"SGE {modulo_version.VERSION}"


def test_la_etiqueta_incluye_la_revision(monkeypatch):
    monkeypatch.setenv("SGE_REVISION", "a1b2c3d")
    assert modulo_version.etiqueta() == f"SGE {modulo_version.VERSION} · a1b2c3d"


def test_informacion_reporta_las_dependencias_opcionales():
    datos = modulo_version.informacion()
    nombres = {dependencia["nombre"] for dependencia in datos["opcionales"]}
    assert nombres == {"OR-Tools", "WeasyPrint", "openpyxl"}
    for dependencia in datos["opcionales"]:
        assert isinstance(dependencia["disponible"], bool)


def test_la_version_aparece_al_pie_de_las_pantallas(client, secretaria, institucion):
    client.force_login(secretaria)
    respuesta = client.get(reverse("inicio"))
    assert modulo_version.VERSION in respuesta.content.decode()


def test_el_estado_del_sistema_lo_ve_quien_administra(client, secretaria, institucion):
    client.force_login(secretaria)
    respuesta = client.get(reverse("estado_del_sistema"))
    assert respuesta.status_code == 200
    cuerpo = respuesta.content.decode()
    assert modulo_version.VERSION in cuerpo
    assert "OR-Tools" in cuerpo


def test_el_estado_del_sistema_no_es_publico(client, db):
    """Dice qué hay instalado y con qué base corre: no va sin permiso."""
    from core.models import Usuario

    ajeno = Usuario.objects.create_user(
        email="ajeno@otra.edu.ar", password="clave-de-prueba-123", nombre="Juan", apellido="Gómez"
    )
    client.force_login(ajeno)
    assert client.get(reverse("estado_del_sistema")).status_code == 403


class TestIdentidadVisual:
    """El color y el emblema son de la escuela activa, no del sistema.

    Es lo que evita cargar datos reales en la escuela de prueba: mientras se
    trabaja en una, todas las pantallas están pintadas de su color. Sin escuela
    activa —el superusuario mirando algo que no es de ninguna— no se pinta nada.
    """

    def test_el_color_de_la_escuela_se_aplica_a_la_pantalla(self, client, secretaria, institucion):
        institucion.color = "#c2560f"
        institucion.emblema = "🍊"
        institucion.save()

        client.force_login(secretaria)
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "--acento: #c2560f" in cuerpo
        assert "🍊" in cuerpo

    def test_sin_color_la_pantalla_queda_neutra(self, client, secretaria, institucion):
        client.force_login(secretaria)
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "--acento:" not in cuerpo

    def test_el_emblema_sirve_de_icono_sin_archivos(self, institucion):
        institucion.emblema = "🍊"
        assert institucion.icono_svg.startswith("data:image/svg+xml,")

    def test_sin_emblema_no_hay_icono(self, institucion):
        assert institucion.icono_svg == ""
