"""Darle acceso a alguien de la escuela.

Lo que importa: que el rol quede en la escuela correcta —un rol en la escuela
equivocada es acceso a datos laborales de otro colegio— y que se pueda correr
dos veces sin duplicar a nadie.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Institucion, Membresia, Rol, Usuario


class TestCrearUsuario:
    def test_crea_la_persona_con_su_rol(self, institucion, capsys):
        call_command("crear_usuario", "ana@uno.edu.ar", rol="secretaria", nombre="Ana")

        usuario = Usuario.objects.get(email="ana@uno.edu.ar")
        assert usuario.is_staff
        assert Membresia.objects.get(usuario=usuario).rol == Rol.SECRETARIA
        assert "Contraseña" in capsys.readouterr().out

    def test_el_docente_no_entra_al_panel(self, institucion):
        call_command("crear_usuario", "profe@uno.edu.ar", rol="docente")

        assert not Usuario.objects.get(email="profe@uno.edu.ar").is_staff

    def test_correrlo_de_nuevo_agrega_el_rol_y_no_duplica(self, institucion):
        call_command("crear_usuario", "ana@uno.edu.ar", rol="secretaria")
        call_command("crear_usuario", "ana@uno.edu.ar", rol="directivo")

        assert Usuario.objects.filter(email="ana@uno.edu.ar").count() == 1
        assert Membresia.objects.count() == 2

    def test_con_dos_escuelas_exige_decir_cual(self, institucion, otra_institucion):
        with pytest.raises(CommandError, match="más de una escuela"):
            call_command("crear_usuario", "ana@uno.edu.ar", rol="secretaria")

    def test_elige_la_escuela_por_nombre(self, institucion, otra_institucion):
        call_command("crear_usuario", "ana@dos.edu.ar", rol="secretaria", institucion="Escuela Dos")

        assert Membresia.objects.get().institucion == otra_institucion

    def test_un_rol_que_no_existe_se_explica(self, institucion):
        with pytest.raises(CommandError, match="no es un rol"):
            call_command("crear_usuario", "ana@uno.edu.ar", rol="portero")

    def test_se_puede_vincular_al_legajo(self, institucion):
        from legajos.models import Legajo

        Legajo.objects.create(institucion=institucion, apellido="Ochoa", nombre="Ramiro", cuil="")

        call_command("crear_usuario", "r@uno.edu.ar", rol="docente", legajo="Ochoa, Ramiro")

        assert Legajo.objects.get().usuario.email == "r@uno.edu.ar"

    def test_un_legajo_que_no_esta_se_avisa(self, institucion):
        with pytest.raises(CommandError, match="No hay ningún legajo"):
            call_command("crear_usuario", "r@uno.edu.ar", rol="docente", legajo="Nadie, Nadie")

    def test_sin_escuelas_no_hay_a_quien_darle_acceso(self, db):
        assert not Institucion.objects.exists()
        with pytest.raises(CommandError, match="ninguna escuela"):
            call_command("crear_usuario", "ana@uno.edu.ar", rol="secretaria")
