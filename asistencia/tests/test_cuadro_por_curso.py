"""El día visto por curso: qué se dicta en cada hora y quién la da.

El parte responde "quién falta"; este cuadro responde "qué cursos se quedan
sin clase, y a qué hora". Son los mismos datos, así que lo importante es que
no puedan contradecirse: si el parte dice que alguien está ausente, acá esa
hora tiene que salir marcada.
"""

import pytest

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from asistencia.parte import EstadoHora, cuadro_del_dia, parte_diario
from legajos.models import Legajo
from licencias.models import Cobertura, TipoCobertura

from .conftest import dar_licencia


def horas_del_unico_curso(datos, fecha=None):
    cuadros = cuadro_del_dia(datos["escuela"]["institucion"], fecha or datos["fecha"])
    assert len(cuadros) == 1
    return cuadros[0]


class TestCuadroPorCurso:
    def test_muestra_cada_hora_con_su_materia_y_docente(self, con_horario_publicado):
        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert cuadro.curso == con_horario_publicado["curso"]
        assert cuadro.horas
        for hora in cuadro.horas:
            assert hora.materia == con_horario_publicado["materia"].nombre
            assert hora.docente == con_horario_publicado["docente"]
            assert hora.estado == EstadoHora.NORMAL
        assert not cuadro.tiene_problemas

    def test_un_dia_sin_clases_no_devuelve_cursos(self, con_horario_publicado):
        assert (
            cuadro_del_dia(
                con_horario_publicado["escuela"]["institucion"],
                con_horario_publicado["fecha_libre"],
            )
            == []
        )

    def test_marca_las_horas_del_docente_ausente(self, con_horario_publicado):
        """Lo que se pidió: que salte a la vista qué cursos quedan sin clase."""
        RegistroAsistencia.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            legajo=con_horario_publicado["docente"],
            fecha=con_horario_publicado["fecha"],
            estado=EstadoAsistencia.AUSENTE,
        )

        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert cuadro.tiene_problemas
        assert cuadro.sin_clase == len(cuadro.horas)
        for hora in cuadro.horas:
            assert hora.estado == EstadoHora.AUSENTE
            assert hora.sin_clase

    def test_una_tardanza_se_señala_pero_no_deja_al_curso_sin_clase(self, con_horario_publicado):
        RegistroAsistencia.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            legajo=con_horario_publicado["docente"],
            fecha=con_horario_publicado["fecha"],
            estado=EstadoAsistencia.TARDE,
            hora="08:10",
        )

        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert not cuadro.tiene_problemas
        assert all(hora.estado == EstadoHora.CON_NOVEDAD for hora in cuadro.horas)

    def test_la_licencia_cubierta_muestra_al_suplente(self, con_horario_publicado):
        licencia = dar_licencia(con_horario_publicado)
        suplente = Legajo.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            apellido="Suplente",
            nombre="Ana",
            cuil="27-30000999-1",
            fecha_ingreso=con_horario_publicado["fecha"],
        )
        Cobertura.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            licencia=licencia,
            cargo=con_horario_publicado["cargo"],
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )

        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert not cuadro.tiene_problemas
        for hora in cuadro.horas:
            assert hora.estado == EstadoHora.SUPLENTE
            assert hora.docente == suplente
            assert hora.titular == con_horario_publicado["docente"]

    def test_la_licencia_sin_cubrir_deja_el_curso_libre(self, con_horario_publicado):
        licencia = dar_licencia(con_horario_publicado)
        Cobertura.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            licencia=licencia,
            cargo=con_horario_publicado["cargo"],
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )

        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert cuadro.sin_clase == len(cuadro.horas)
        for hora in cuadro.horas:
            assert hora.estado == EstadoHora.SIN_DOCENTE
            assert hora.docente is None

    def test_la_licencia_sin_decidir_queda_como_sin_resolver(self, con_horario_publicado):
        """Distinta de «alumnos libres»: es una tarea pendiente, no una decisión."""
        dar_licencia(con_horario_publicado)

        cuadro = horas_del_unico_curso(con_horario_publicado)

        for hora in cuadro.horas:
            assert hora.estado == EstadoHora.SIN_RESOLVER

    def test_dos_licencias_superpuestas_no_esconden_al_suplente(self, con_horario_publicado):
        """La misma superposición que se prueba en el parte, vista por curso."""
        from licencias.models import EstadoLicencia, Licencia, TipoLicencia

        institucion = con_horario_publicado["escuela"]["institucion"]
        fecha = con_horario_publicado["fecha"]
        cargo = con_horario_publicado["cargo"]

        con_suplente = dar_licencia(con_horario_publicado)
        suplente = Legajo.objects.create(
            institucion=institucion, apellido="Suplente", nombre="Marta", cuil="27-39888777-6"
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=con_suplente,
            cargo=cargo,
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=con_suplente.fecha_inicio,
            fecha_fin=con_suplente.fecha_fin,
        )

        otro_tipo = TipoLicencia.objects.create(
            institucion=institucion, nombre="Trámite personal", codigo="Art. 93.4"
        )
        sin_suplente = Licencia.objects.create(
            institucion=institucion,
            legajo=con_horario_publicado["docente"],
            tipo=otro_tipo,
            fecha_inicio=fecha,
            fecha_fin=fecha,
            estado=EstadoLicencia.APROBADA,
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=sin_suplente,
            cargo=cargo,
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )

        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert not cuadro.tiene_problemas
        for hora in cuadro.horas:
            assert hora.estado == EstadoHora.SUPLENTE
            assert hora.docente == suplente

    def test_no_contradice_al_parte(self, con_horario_publicado):
        """Las dos pantallas salen del mismo cruce: tienen que coincidir."""
        licencia = dar_licencia(con_horario_publicado)
        Cobertura.objects.create(
            institucion=con_horario_publicado["escuela"]["institucion"],
            licencia=licencia,
            cargo=con_horario_publicado["cargo"],
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )

        institucion = con_horario_publicado["escuela"]["institucion"]
        fecha = con_horario_publicado["fecha"]
        parte = parte_diario(institucion, fecha)
        cuadro = horas_del_unico_curso(con_horario_publicado)

        assert len(parte.sin_cobertura) == cuadro.sin_clase


@pytest.mark.django_db
class TestVista:
    def test_la_pantalla_muestra_los_cursos(self, client, con_horario_publicado, secretaria):
        client.force_login(secretaria)
        respuesta = client.get(
            "/asistencia/cursos/", {"fecha": con_horario_publicado["fecha"].isoformat()}
        )
        assert respuesta.status_code == 200
        assert str(con_horario_publicado["curso"]) in respuesta.content.decode()

    def test_no_es_publica(self, client, db):
        assert client.get("/asistencia/cursos/").status_code in (302, 403)
