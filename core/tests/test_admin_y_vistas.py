"""El admin es la interfaz de carga de la F0: tiene que estar acotado también."""

from datetime import date, time

import pytest
from django.contrib.admin.sites import AdminSite

from core.admin import MembresiaAdmin, filtrar_por_institucion
from core.middleware import CLAVE_SESION
from core.models import Membresia, Rol
from estructura.admin import CursoAdmin
from estructura.models import (
    CicloLectivo,
    Curso,
    EsquemaHorario,
    EstadoCiclo,
    Nivel,
    TipoNivel,
    Turno,
)


def crear_estructura(institucion, division="A"):
    """Mínimo necesario para tener un curso: nivel, ciclo, turno y esquema."""
    nivel = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    ciclo = CicloLectivo.objects.create(
        institucion=institucion,
        anio=2026,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 15),
        estado=EstadoCiclo.ACTIVO,
    )
    turno = Turno.objects.create(
        institucion=institucion,
        nivel=nivel,
        nombre="Mañana",
        hora_inicio=time(7, 45),
        hora_fin=time(13, 0),
    )
    esquema = EsquemaHorario.objects.create(
        institucion=institucion, turno=turno, nombre="Sin almuerzo"
    )
    curso = Curso.objects.create(
        institucion=institucion,
        ciclo_lectivo=ciclo,
        nivel=nivel,
        anio_estudio=1,
        division=division,
        turno=turno,
        esquema_horario=esquema,
    )
    return {"nivel": nivel, "ciclo": ciclo, "turno": turno, "esquema": esquema, "curso": curso}


class TestFiltradoDelAdmin:
    def test_filtra_modelos_con_institucion_propia(self, institucion, otra_institucion):
        propia = crear_estructura(institucion)
        crear_estructura(otra_institucion)
        assert list(filtrar_por_institucion(Curso.objects.all(), institucion)) == [propia["curso"]]

    def test_filtra_modelos_que_llegan_por_relacion(self, institucion, otra_institucion):
        # BloqueHorario no guarda institución: se llega por esquema__institucion.
        from estructura.models import BloqueHorario

        propia = crear_estructura(institucion)
        ajena = crear_estructura(otra_institucion)
        mio = BloqueHorario.objects.create(
            esquema=propia["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        BloqueHorario.objects.create(
            esquema=ajena["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        assert list(filtrar_por_institucion(BloqueHorario.objects.all(), institucion)) == [mio]

    def test_sin_institucion_activa_no_lista_nada(self, institucion):
        crear_estructura(institucion)
        assert filtrar_por_institucion(Curso.objects.all(), None).count() == 0

    def test_queryset_del_admin_respeta_la_institucion(
        self, rf, secretaria, institucion, otra_institucion
    ):
        propia = crear_estructura(institucion)
        crear_estructura(otra_institucion)
        peticion = rf.get("/admin/")
        peticion.user = secretaria
        peticion.institucion = institucion

        admin = CursoAdmin(Curso, AdminSite())
        assert list(admin.get_queryset(peticion)) == [propia["curso"]]

    def test_los_desplegables_solo_ofrecen_datos_propios(
        self, rf, secretaria, institucion, otra_institucion
    ):
        propia = crear_estructura(institucion)
        crear_estructura(otra_institucion)
        peticion = rf.get("/admin/")
        peticion.user = secretaria
        peticion.institucion = institucion

        admin = CursoAdmin(Curso, AdminSite())
        campo = Curso._meta.get_field("turno")
        formfield = admin.formfield_for_foreignkey(campo, peticion)
        assert list(formfield.queryset) == [propia["turno"]]

    def test_asigna_la_institucion_al_crear(self, rf, secretaria, institucion):
        peticion = rf.post("/admin/")
        peticion.user = secretaria
        peticion.institucion = institucion

        admin = MembresiaAdmin(Membresia, AdminSite())
        membresia = Membresia(usuario=secretaria, rol=Rol.DIRECTIVO)
        admin.save_model(peticion, membresia, form=None, change=False)
        assert membresia.institucion == institucion


@pytest.mark.django_db
class TestVistas:
    def test_el_inicio_exige_login(self, client):
        respuesta = client.get("/")
        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_el_inicio_muestra_la_estructura(self, client, secretaria, institucion):
        crear_estructura(institucion)
        client.force_login(secretaria)
        respuesta = client.get("/")
        assert respuesta.status_code == 200
        assert respuesta.context["cantidad_cursos"] == 1
        assert respuesta.context["ciclo"].anio == 2026

    def test_usuario_sin_institucion_recibe_aviso(self, client, db):
        from core.models import Usuario

        suelto = Usuario.objects.create_user(
            email="nadie@ejemplo.com", password="x", nombre="Sin", apellido="Escuela"
        )
        client.force_login(suelto)
        respuesta = client.get("/")
        assert respuesta.status_code == 403

    def test_no_se_puede_cambiar_a_una_institucion_ajena(
        self, client, secretaria, institucion, otra_institucion
    ):
        client.force_login(secretaria)
        respuesta = client.post(
            "/institucion/cambiar/", {"institucion": otra_institucion.pk}, follow=True
        )
        assert client.session.get(CLAVE_SESION) != otra_institucion.pk
        assert b"No ten" in respuesta.content  # "No tenés acceso a esa institución."

    def test_se_puede_cambiar_a_una_institucion_propia(self, client, secretaria, otra_institucion):
        Membresia.objects.create(
            usuario=secretaria, institucion=otra_institucion, rol=Rol.SECRETARIA
        )
        client.force_login(secretaria)
        client.post("/institucion/cambiar/", {"institucion": otra_institucion.pk})
        assert client.session[CLAVE_SESION] == otra_institucion.pk
