"""Los roles tienen que traducirse en permisos reales del panel."""

import pytest

from core.models import Membresia, Rol, Usuario
from core.permisos import grupo_de, sincronizar_permisos


@pytest.fixture
def permisos_sincronizados(db):
    return sincronizar_permisos()


class TestSincronizacion:
    def test_la_secretaria_puede_administrar_la_estructura(self, permisos_sincronizados):
        codigos = set(grupo_de(Rol.SECRETARIA).permissions.values_list("codename", flat=True))
        assert {"add_curso", "change_curso", "delete_curso", "view_curso"} <= codigos
        assert "add_bloquehorario" in codigos

    def test_el_directivo_solo_consulta(self, permisos_sincronizados):
        codigos = set(grupo_de(Rol.DIRECTIVO).permissions.values_list("codename", flat=True))
        assert "view_curso" in codigos
        assert "add_curso" not in codigos
        assert "delete_curso" not in codigos

    def test_nadie_puede_editar_la_auditoria(self, permisos_sincronizados):
        for rol in (Rol.SECRETARIA, Rol.DIRECTIVO):
            codigos = set(grupo_de(rol).permissions.values_list("codename", flat=True))
            assert "change_registroauditoria" not in codigos
            assert "delete_registroauditoria" not in codigos

    def test_es_idempotente(self, db):
        primera = sincronizar_permisos()
        segunda = sincronizar_permisos()
        assert primera == segunda
        assert grupo_de(Rol.SECRETARIA).permissions.count() == primera[Rol.SECRETARIA]


class TestAltaYBajaDeRoles:
    def test_dar_de_alta_otorga_permisos_y_acceso_al_panel(self, db, institucion):
        usuaria = Usuario.objects.create_user(
            email="nueva@uno.edu.ar", password="x", nombre="Nueva", apellido="Secre"
        )
        assert not usuaria.is_staff

        Membresia.objects.create(usuario=usuaria, institucion=institucion, rol=Rol.SECRETARIA)

        usuaria.refresh_from_db()
        assert usuaria.is_staff
        assert usuaria.has_perm("estructura.add_curso")

    def test_el_docente_no_entra_al_panel(self, db, institucion):
        docente = Usuario.objects.create_user(
            email="docente@uno.edu.ar", password="x", nombre="Juan", apellido="Gómez"
        )
        Membresia.objects.create(usuario=docente, institucion=institucion, rol=Rol.DOCENTE)

        docente.refresh_from_db()
        assert not docente.is_staff
        assert not docente.has_perm("estructura.view_curso")

    def test_la_baja_quita_los_permisos(self, db, institucion, secretaria):
        assert secretaria.has_perm("estructura.add_curso")

        Membresia.objects.filter(usuario=secretaria).delete()

        secretaria = Usuario.objects.get(pk=secretaria.pk)
        assert not secretaria.has_perm("estructura.add_curso")
        assert not secretaria.is_staff

    def test_conserva_permisos_si_sigue_teniendo_el_rol_en_otra_escuela(
        self, db, institucion, otra_institucion, secretaria
    ):
        Membresia.objects.create(
            usuario=secretaria, institucion=otra_institucion, rol=Rol.SECRETARIA
        )
        Membresia.objects.filter(usuario=secretaria, institucion=institucion).delete()

        secretaria = Usuario.objects.get(pk=secretaria.pk)
        assert secretaria.has_perm("estructura.add_curso")
        assert secretaria.is_staff

    def test_desactivar_la_membresia_equivale_a_darla_de_baja(self, db, secretaria):
        membresia = secretaria.membresias.first()
        membresia.activa = False
        membresia.save()

        secretaria = Usuario.objects.get(pk=secretaria.pk)
        assert not secretaria.has_perm("estructura.add_curso")
