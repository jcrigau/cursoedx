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


class TestVolverAlTablero:
    """Desde cualquier pantalla se tiene que poder volver, sin buscar."""

    def test_la_barra_tiene_el_inicio(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "vuelta@uno.edu.ar"))
        cuerpo = client.get(reverse("parte_diario")).content.decode()
        assert "volver-al-inicio" in cuerpo

    def test_el_admin_tiene_el_camino_de_vuelta(self, client, escuela_cargada):
        """Django solo ofrece «Ver sitio», que ni se ve ni dice a dónde lleva."""
        usuario = crear(escuela_cargada, Rol.SECRETARIA, "vuelta2@uno.edu.ar")
        client.force_login(usuario)
        cuerpo = client.get(reverse("admin:index")).content.decode()
        assert "Volver al tablero" in cuerpo
        assert f'href="{reverse("inicio")}"' in cuerpo


class TestCabosSueltos:
    """El aviso viejo sin licencia es el único punto donde algo se pierde solo."""

    def test_un_aviso_viejo_sin_licencia_aparece(self, client, escuela_cargada):
        from datetime import date, timedelta

        from legajos.models import Legajo
        from portal.models import AvisoInasistencia, MotivoAviso

        sin_licencias = (
            Legajo.objects.filter(institucion=escuela_cargada, licencias__isnull=True)
            .order_by("apellido")
            .first()
        )
        AvisoInasistencia.objects.create(
            institucion=escuela_cargada,
            legajo=sin_licencias,
            fecha=date.today() - timedelta(days=3),
            motivo=MotivoAviso.ENFERMEDAD,
        )

        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "cabo@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Avisos viejos sin licencia cargada" in cuerpo

    def test_con_la_licencia_cargada_deja_de_ser_un_cabo(self, client, escuela_cargada):
        from datetime import date, timedelta

        from legajos.models import Legajo
        from licencias.models import EstadoLicencia, Licencia, TipoLicencia
        from portal.models import AvisoInasistencia, MotivoAviso

        legajo = (
            Legajo.objects.filter(institucion=escuela_cargada, licencias__isnull=True)
            .order_by("apellido")
            .first()
        )
        fecha = date.today() - timedelta(days=3)
        AvisoInasistencia.objects.create(
            institucion=escuela_cargada,
            legajo=legajo,
            fecha=fecha,
            motivo=MotivoAviso.ENFERMEDAD,
        )
        # La licencia existe aunque todavía no esté aprobada: ya la está
        # persiguiendo el directivo, no es un cabo suelto.
        Licencia.objects.create(
            institucion=escuela_cargada,
            legajo=legajo,
            tipo=TipoLicencia.objects.filter(institucion=escuela_cargada).first(),
            fecha_inicio=fecha,
            fecha_fin=fecha,
            estado=EstadoLicencia.SOLICITADA,
        )

        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "cabo2@uno.edu.ar"))
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert "Avisos viejos sin licencia cargada" not in cuerpo


class TestLaSemana:
    def test_muestra_los_siete_dias(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "sem@uno.edu.ar"))
        respuesta = client.get(reverse("semana"))
        assert respuesta.status_code == 200

    def test_una_licencia_que_empieza_aparece_en_su_dia(self, client, escuela_cargada):
        from datetime import date, timedelta

        from legajos.models import Legajo
        from licencias.models import EstadoLicencia, Licencia, TipoLicencia

        Licencia.objects.create(
            institucion=escuela_cargada,
            legajo=Legajo.objects.filter(institucion=escuela_cargada).first(),
            tipo=TipoLicencia.objects.filter(institucion=escuela_cargada).first(),
            fecha_inicio=date.today() + timedelta(days=2),
            fecha_fin=date.today() + timedelta(days=9),
            estado=EstadoLicencia.APROBADA,
        )

        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "sem2@uno.edu.ar"))
        cuerpo = client.get(reverse("semana")).content.decode()

        assert "empieza" in cuerpo
