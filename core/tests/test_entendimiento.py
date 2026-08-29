"""Lo que ayuda a entender el sistema sin leer el manual.

El circuito, la ayuda de cada pantalla y la bienvenida del primer ingreso no
cambian ningún dato: lo que hay que probar es que aparezcan donde tienen que
aparecer, y que la bienvenida no vuelva una vez cerrada.
"""

import pytest
from django.core.management import call_command
from django.urls import reverse

from core.bienvenida import para as bienvenida_para
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


class TestElCircuito:
    def test_dibuja_el_camino_completo(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "circ@uno.edu.ar"))
        cuerpo = client.get(reverse("circuito")).content.decode()

        for paso in ("Avisa que no viene", "Decide la cobertura", "Cierra el mes"):
            assert paso in cuerpo

    def test_no_es_publico(self, client, db):
        assert client.get(reverse("circuito")).status_code == 302


class TestLaAyudaDeCadaPantalla:
    def test_el_parte_explica_lo_que_no_se_marca(self, client, escuela_cargada):
        client.force_login(crear(escuela_cargada, Rol.SECRETARIA, "ayuda@uno.edu.ar"))
        cuerpo = client.get(reverse("parte_diario")).content.decode()
        assert "se toma como presente" in cuerpo


class TestLaBienvenida:
    def test_cada_puesto_recibe_la_suya(self, escuela_cargada):
        directivo = crear(escuela_cargada, Rol.DIRECTIVO, "b1@uno.edu.ar")
        liquidador = crear(escuela_cargada, Rol.LIQUIDADOR, "b2@uno.edu.ar")

        assert "aprobación" in str(bienvenida_para(directivo, escuela_cargada))
        assert "cierre" in str(bienvenida_para(liquidador, escuela_cargada))

    def test_con_dos_roles_gana_el_que_mas_trabajo_tiene(self, escuela_cargada):
        usuario = crear(escuela_cargada, Rol.DIRECTIVO, "b3@uno.edu.ar")
        Membresia.objects.create(usuario=usuario, institucion=escuela_cargada, rol=Rol.SECRETARIA)

        assert bienvenida_para(usuario, escuela_cargada) == bienvenida_para(
            crear(escuela_cargada, Rol.SECRETARIA, "b4@uno.edu.ar"), escuela_cargada
        )

    def test_una_vez_cerrada_no_vuelve(self, client, escuela_cargada):
        usuario = crear(escuela_cargada, Rol.SECRETARIA, "b5@uno.edu.ar")
        client.force_login(usuario)
        assert "no mostrar más" in client.get(reverse("inicio")).content.decode()

        client.post(reverse("ocultar_bienvenida"), {"siguiente": reverse("inicio")})

        usuario.refresh_from_db()
        assert usuario.vio_la_bienvenida
        assert "no mostrar más" not in client.get(reverse("inicio")).content.decode()


class TestLaPuestaEnMarcha:
    def test_cada_paso_pendiente_lleva_a_su_formulario(self, client, db, institucion, secretaria):
        """Una escuela vacía se arma siguiendo la lista, sin saber dónde está cada cosa."""
        client.force_login(secretaria)
        cuerpo = client.get(reverse("inicio")).content.decode()

        assert reverse("admin:estructura_nivel_add") in cuerpo
