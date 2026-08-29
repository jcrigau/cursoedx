"""El tablero muestra lo que cada puesto tiene para hacer, y nada más.

La idea es que nadie tenga que saber dónde vive cada cosa en el panel de
administración: entra, ve lo suyo, y el link lo lleva al lugar exacto.
"""

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.models import Institucion, Membresia, Rol, Usuario


@pytest.fixture
def escuela_cargada(db):
    call_command("cargar_piloto", verbosity=0)
    return Institucion.objects.get()


def crear(escuela, rol, email):
    usuario = Usuario.objects.create_user(
        email=email, password="clave-de-prueba-123", nombre="Prueba", apellido="Puesto"
    )
    Membresia.objects.create(usuario=usuario, institucion=escuela, rol=rol)
    return usuario


class TestQueVeCadaPuesto:
    def test_el_directivo_ve_las_licencias_a_aprobar(self, client, escuela_cargada):
        from legajos.models import Legajo
        from licencias.models import EstadoLicencia, Licencia, TipoLicencia

        tipo = TipoLicencia.objects.filter(institucion=escuela_cargada).first()
        Licencia.objects.create(
            institucion=escuela_cargada,
            legajo=Legajo.objects.filter(institucion=escuela_cargada).first(),
            tipo=tipo,
            fecha_inicio="2026-08-31",
            fecha_fin="2026-09-02",
            estado=EstadoLicencia.SOLICITADA,
        )

        client.force_login(crear(escuela_cargada, Rol.DIRECTIVO, "dir@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Licencias esperando aprobación" in cuerpo
        # Y el link lleva al listado ya filtrado, no al panel a secas.
        assert "estado__exact=SOLICITADA" in cuerpo

    def test_el_liquidador_no_ve_el_trabajo_de_la_secretaria(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.LIQUIDADOR, "liq@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Documentación vencida" not in cuerpo
        assert "sin marcar en el parte" not in cuerpo

    def test_la_secretaria_ve_su_trabajo(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "sec@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Lo que tenés para resolver" in cuerpo
        assert "El mes está sin compilar" in cuerpo

    def test_el_docente_va_derecho_al_portal(self, client, escuela_cargada):
        """No trabaja sobre el tablero de la escuela: lo suyo está en el portal."""
        client.force_login(crear(escuela_cargada, Rol.DOCENTE, "doc@uno.edu.ar"))

        respuesta = client.get(reverse("inicio"))

        assert respuesta.status_code == 302
        assert respuesta.url == reverse("portal_inicio")


class TestAislamiento:
    def test_los_pendientes_son_de_la_escuela_activa(self, client, escuela_cargada, db):
        """Una licencia de otra escuela no puede aparecer acá."""
        from legajos.models import Legajo
        from licencias.models import EstadoLicencia, Licencia, TipoLicencia

        otra = Institucion.objects.create(nombre="Escuela dos", nombre_corto="Dos")
        legajo = Legajo.objects.create(
            institucion=otra, apellido="Ajeno", nombre="Juan", cuil="20-11111111-1"
        )
        tipo = TipoLicencia.objects.create(institucion=otra, nombre="Enfermedad", codigo="Art. 76")
        Licencia.objects.create(
            institucion=otra,
            legajo=legajo,
            tipo=tipo,
            fecha_inicio="2026-08-31",
            fecha_fin="2026-09-02",
            estado=EstadoLicencia.SOLICITADA,
        )

        client.force_login(crear(escuela_cargada, Rol.DIRECTIVO, "dir2@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Licencias esperando aprobación" not in cuerpo
