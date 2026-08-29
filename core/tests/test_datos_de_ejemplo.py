"""La escuela de ejemplo se puede recargar sin miedo.

Es la que se usa para mostrar el sistema y para probar en el servidor, así que
se corre más de una vez sobre la misma base: al actualizar, al agregar algo,
al mostrarle el sistema a otra escuela. Volver a cargarla tiene que reencontrar
lo que ya está, no inventar una segunda planta docente al lado.
"""

import pytest
from django.core.management import call_command

from core.management.commands.cargar_piloto import (
    COLOR_ESCUELA_DE_PRUEBA,
    EMBLEMA_ESCUELA_DE_PRUEBA,
    NOMBRE_ESCUELA_DE_PRUEBA,
    NOMBRES_ANTERIORES,
)
from core.models import Institucion, Membresia, Rol, Usuario
from legajos.models import Cargo, Legajo


def contar():
    return {
        "escuelas": Institucion.objects.count(),
        "legajos": Legajo.objects.count(),
        "cargos": Cargo.objects.count(),
    }


@pytest.mark.django_db
def test_cargar_el_piloto_dos_veces_no_duplica_nada():
    call_command("cargar_piloto", verbosity=0)
    primera = contar()

    call_command("cargar_piloto", verbosity=0)

    assert contar() == primera
    assert primera["legajos"] > 20  # la planta se llegó a armar


@pytest.mark.django_db
def test_la_escuela_de_ejemplo_se_distingue_a_la_vista():
    call_command("cargar_piloto", verbosity=0)

    escuela = Institucion.objects.get()
    assert escuela.nombre == NOMBRE_ESCUELA_DE_PRUEBA
    assert escuela.color == COLOR_ESCUELA_DE_PRUEBA
    assert escuela.emblema == EMBLEMA_ESCUELA_DE_PRUEBA


@pytest.mark.django_db
def test_una_instalacion_vieja_se_renombra_en_lugar_de_duplicarse():
    """La que ya venía andando con el nombre anterior tiene que quedar al día."""
    Institucion.objects.create(nombre=NOMBRES_ANTERIORES[0], nombre_corto="Instituto")

    call_command("cargar_piloto", verbosity=0)

    escuela = Institucion.objects.get()  # una sola, no dos
    assert escuela.nombre == NOMBRE_ESCUELA_DE_PRUEBA
    assert escuela.emblema == EMBLEMA_ESCUELA_DE_PRUEBA


@pytest.mark.django_db
def test_el_escenario_se_puede_recargar():
    """Volver a armarlo tiene que replantar lo mismo, no acumular situaciones.

    Se corre sin el generador de horarios: acá lo que se prueba es que los
    usuarios y las situaciones no se dupliquen, no el horario.
    """
    call_command("cargar_piloto", verbosity=0)
    call_command("cargar_escenario", "--sin-demo", verbosity=0)
    primera = contar()
    usuarios = Usuario.objects.count()

    call_command("cargar_escenario", "--sin-demo", verbosity=0)

    assert contar() == primera
    assert Usuario.objects.count() == usuarios


@pytest.mark.django_db
def test_el_escenario_crea_un_usuario_por_puesto():
    call_command("cargar_piloto", verbosity=0)
    call_command("cargar_escenario", "--sin-demo", verbosity=0)

    institucion = Institucion.objects.get()
    roles = set(Membresia.objects.filter(institucion=institucion).values_list("rol", flat=True))
    assert roles == {Rol.SECRETARIA, Rol.DIRECTIVO, Rol.DOCENTE, Rol.LIQUIDADOR}
