"""Modelos de horario, control de choques al editar a mano, y vistas."""

from datetime import time

import pytest
from django.core.exceptions import ValidationError

from horarios.models import AsignacionHoraria, EstadoVersion, VersionHorario, se_superponen

from .conftest import (
    crear_curso,
    crear_docente,
    crear_esquema,
    crear_materia,
    crear_plan,
    crear_version,
    designar,
)


class TestSuperposicion:
    def test_franjas_que_se_pisan(self):
        assert se_superponen(time(8, 0), time(8, 40), time(8, 20), time(9, 0))

    def test_franjas_consecutivas_no_se_pisan(self):
        # Una termina justo cuando empieza la otra.
        assert not se_superponen(time(8, 0), time(8, 40), time(8, 40), time(9, 20))

    def test_una_contenida_en_otra(self):
        assert se_superponen(time(8, 0), time(10, 0), time(8, 30), time(9, 0))


@pytest.fixture
def con_horario(escuela):
    esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    crear_plan(curso, materia, 2)
    docente = crear_docente(escuela, "Pérez", 1)
    cargo = designar(escuela, docente, materia, curso)
    version = crear_version(escuela)
    return {
        "escuela": escuela,
        "esquema": esquema,
        "curso": curso,
        "materia": materia,
        "docente": docente,
        "cargo": cargo,
        "version": version,
    }


class TestAsignacion:
    def test_copia_el_horario_del_bloque(self, con_horario):
        bloque = con_horario["esquema"].bloques.first()
        asignacion = AsignacionHoraria.objects.create(
            version=con_horario["version"],
            curso=con_horario["curso"],
            bloque=bloque,
            materia=con_horario["materia"],
            cargo=con_horario["cargo"],
        )
        assert asignacion.dia_semana == bloque.dia_semana
        assert asignacion.hora_inicio == bloque.hora_inicio
        assert asignacion.legajo == con_horario["docente"]

    def test_avisa_si_el_curso_ya_tiene_clase_a_esa_hora(self, con_horario):
        bloque = con_horario["esquema"].bloques.first()
        AsignacionHoraria.objects.create(
            version=con_horario["version"],
            curso=con_horario["curso"],
            bloque=bloque,
            materia=con_horario["materia"],
            cargo=con_horario["cargo"],
        )
        otra_materia = crear_materia(con_horario["escuela"], "Lengua")
        repetida = AsignacionHoraria(
            version=con_horario["version"],
            curso=con_horario["curso"],
            bloque=bloque,
            materia=otra_materia,
        )
        with pytest.raises(ValidationError, match="ya tiene"):
            repetida.full_clean()

    def test_avisa_si_el_docente_ya_esta_en_otro_curso(self, con_horario):
        escuela = con_horario["escuela"]
        otro_esquema = crear_esquema(escuela, "Otro", horas_por_dia=4, dias=3)
        otro_curso = crear_curso(escuela, otro_esquema, anio=2, division="B")
        crear_plan(otro_curso, con_horario["materia"], 2)

        bloque = con_horario["esquema"].bloques.first()
        AsignacionHoraria.objects.create(
            version=con_horario["version"],
            curso=con_horario["curso"],
            bloque=bloque,
            materia=con_horario["materia"],
            cargo=con_horario["cargo"],
        )
        # Mismo día y hora en el otro esquema: es otro bloque, pero el docente
        # no puede estar en los dos lugares.
        bloque_gemelo = otro_esquema.bloques.get(
            dia_semana=bloque.dia_semana, hora_inicio=bloque.hora_inicio
        )
        chocada = AsignacionHoraria(
            version=con_horario["version"],
            curso=otro_curso,
            bloque=bloque_gemelo,
            materia=con_horario["materia"],
            cargo=con_horario["cargo"],
        )
        with pytest.raises(ValidationError, match="docente ya está"):
            chocada.full_clean()


class TestVersion:
    def test_publicar_archiva_la_anterior(self, escuela):
        primera = crear_version(escuela, "Borrador 1")
        primera.publicar()
        segunda = crear_version(escuela, "Borrador 2")
        segunda.publicar()

        primera.refresh_from_db()
        assert primera.estado == EstadoVersion.HISTORICO
        assert segunda.estado == EstadoVersion.VIGENTE

    def test_publicar_no_toca_otros_periodos(self, escuela):
        from datetime import date

        from estructura.models import PeriodoAcademico

        segundo_periodo = PeriodoAcademico.objects.create(
            ciclo=escuela["ciclo"],
            nombre="2do cuatrimestre",
            orden=2,
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 12, 15),
        )
        del_primero = crear_version(escuela, "Primer cuatrimestre")
        del_primero.publicar()

        del_segundo = VersionHorario.objects.create(
            institucion=escuela["institucion"], periodo=segundo_periodo, nombre="Segundo"
        )
        del_segundo.publicar()

        del_primero.refresh_from_db()
        assert del_primero.estado == EstadoVersion.VIGENTE


@pytest.mark.django_db
class TestVistas:
    def _generar(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 3)
        docente = crear_docente(escuela, "Pérez", 1)
        designar(escuela, docente, materia, curso)
        version = crear_version(escuela)

        from horarios.generador import Parametros, generar

        generar(version, Parametros(segundos_limite=5))
        return version, curso, docente

    def test_exige_login(self, client, escuela):
        version = crear_version(escuela)
        respuesta = client.get(f"/horarios/{version.pk}/")
        assert respuesta.status_code == 302

    def test_muestra_la_grilla_del_curso(self, client, secretaria, escuela):
        version, curso, _docente = self._generar(escuela)
        client.force_login(secretaria)
        respuesta = client.get(f"/horarios/{version.pk}/curso/{curso.pk}/")
        assert respuesta.status_code == 200
        assert "Matemática" in respuesta.content.decode()

    def test_muestra_la_grilla_del_docente(self, client, secretaria, escuela):
        version, _curso, docente = self._generar(escuela)
        client.force_login(secretaria)
        respuesta = client.get(f"/horarios/{version.pk}/docente/{docente.pk}/")
        contenido = respuesta.content.decode()
        assert respuesta.status_code == 200
        assert "Pérez" in contenido
        assert "1°A" in contenido

    def test_el_indice_resume_dias_por_docente(self, client, secretaria, escuela):
        version, _curso, _docente = self._generar(escuela)
        client.force_login(secretaria)
        respuesta = client.get(f"/horarios/{version.pk}/")
        assert respuesta.status_code == 200
        assert respuesta.context["docentes"][0]["horas"] == 3

    def test_no_se_ve_el_horario_de_otra_escuela(
        self, client, secretaria, otra_institucion, escuela
    ):
        from datetime import date

        from estructura.models import CicloLectivo, PeriodoAcademico

        ciclo_ajeno = CicloLectivo.objects.create(
            institucion=otra_institucion,
            anio=2026,
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 12, 15),
        )
        periodo_ajeno = PeriodoAcademico.objects.create(
            ciclo=ciclo_ajeno,
            nombre="1er cuatrimestre",
            orden=1,
            fecha_inicio=date(2026, 3, 1),
            fecha_fin=date(2026, 7, 31),
        )
        version_ajena = VersionHorario.objects.create(
            institucion=otra_institucion, periodo=periodo_ajeno, nombre="Ajena"
        )
        client.force_login(secretaria)
        assert client.get(f"/horarios/{version_ajena.pk}/").status_code == 404

    def test_exporta_en_pdf(self, client, secretaria, escuela):
        version, curso, _docente = self._generar(escuela)
        client.force_login(secretaria)
        respuesta = client.get(f"/horarios/{version.pk}/curso/{curso.pk}/?formato=pdf")
        assert respuesta["Content-Type"] == "application/pdf"
        assert respuesta.content.startswith(b"%PDF")
