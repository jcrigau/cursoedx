"""El parte diario: cruce del horario vigente con licencias y coberturas.

Es la pantalla que la secretaría abre todas las mañanas, así que lo que se
prueba acá es que el cruce salga bien: el titular de licencia no aparece, el
suplente ocupa su lugar y las horas que nadie cubre quedan a la vista.
"""

from datetime import date, time, timedelta

import pytest

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from asistencia.parte import coberturas_pendientes, parte_diario, version_vigente
from horarios.generador import Parametros, generar
from horarios.models import EstadoVersion
from horarios.tests.conftest import (
    crear_curso,
    crear_docente,
    crear_esquema,
    crear_materia,
    crear_plan,
    crear_version,
    designar,
)
from legajos.models import Legajo
from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia


def fecha_con_clases(escuela, version) -> date:
    """Una fecha del período en la que efectivamente hay clases.

    No se puede fijar un día de antemano: el generador concentra las horas en
    los días que le convienen, así que la fecha se deduce del horario generado.
    """
    dias = sorted({a.dia_semana for a in version.asignaciones.all()})
    fecha = escuela["periodo"].fecha_inicio
    while fecha.weekday() not in dias:
        fecha += timedelta(days=1)
    return fecha


def fecha_sin_clases(escuela, version) -> date:
    """Un día del período en el que no hay ninguna clase."""
    dias = {a.dia_semana for a in version.asignaciones.all()}
    fecha = escuela["periodo"].fecha_inicio
    while fecha.weekday() in dias:
        fecha += timedelta(days=1)
    return fecha


@pytest.fixture
def con_horario_publicado(escuela):
    """Una escuela con horario vigente: un curso, una materia, una docente."""
    esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    crear_plan(curso, materia, 4)
    docente = crear_docente(escuela, "Titular", 1)
    cargo = designar(escuela, docente, materia, curso)

    version = crear_version(escuela)
    generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=5))
    version.publicar()

    return {
        "escuela": escuela,
        "curso": curso,
        "materia": materia,
        "docente": docente,
        "cargo": cargo,
        "version": version,
        "fecha": fecha_con_clases(escuela, version),
        "fecha_libre": fecha_sin_clases(escuela, version),
    }


def dar_licencia(datos, desde=None, hasta=None):
    escuela = datos["escuela"]
    tipo = TipoLicencia.objects.create(
        institucion=escuela["institucion"], nombre="Enfermedad", codigo="Art. 76"
    )
    return Licencia.objects.create(
        institucion=escuela["institucion"],
        legajo=datos["docente"],
        tipo=tipo,
        fecha_inicio=desde or datos["fecha"],
        fecha_fin=hasta or datos["fecha"],
        estado=EstadoLicencia.APROBADA,
    )


class TestArmadoDelParte:
    def test_lista_a_quien_debe_venir(self, con_horario_publicado):
        parte = parte_diario(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )
        assert parte.hay_clases
        assert len(parte.lineas) == 1
        linea = parte.lineas[0]
        assert linea.legajo == con_horario_publicado["docente"]
        assert linea.horas >= 1
        assert str(con_horario_publicado["curso"]) in linea.detalle_cursos

    def test_avisa_si_no_hay_horario_publicado(self, escuela):
        """Un borrador sin publicar no sirve para armar el parte."""
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 3)
        designar(escuela, crear_docente(escuela, "Pérez", 1), materia, curso)
        version = crear_version(escuela)
        generar(version, Parametros(segundos_limite=5))
        assert version.estado == EstadoVersion.BORRADOR

        parte = parte_diario(escuela["institucion"], fecha_con_clases(escuela, version))
        assert not parte.hay_clases
        assert "horario vigente" in parte.aviso

    def test_avisa_si_la_fecha_esta_fuera_del_ciclo(self, con_horario_publicado):
        parte = parte_diario(con_horario_publicado["escuela"]["institucion"], date(2030, 5, 4))
        assert "fuera del ciclo" in parte.aviso

    def test_un_dia_sin_clases_no_tiene_lineas(self, con_horario_publicado):
        parte = parte_diario(
            con_horario_publicado["escuela"]["institucion"],
            con_horario_publicado["fecha_libre"],
        )
        assert parte.lineas == []
        assert "No hay clases" in parte.aviso

    def test_encuentra_la_version_vigente(self, con_horario_publicado):
        vigente = version_vigente(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )
        assert vigente == con_horario_publicado["version"]


class TestLicenciasYCoberturas:
    def test_el_titular_de_licencia_no_aparece_y_sus_horas_quedan_sin_cubrir(
        self, con_horario_publicado
    ):
        dar_licencia(con_horario_publicado)
        parte = parte_diario(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )

        assert parte.lineas == []
        assert parte.sin_cobertura
        primera = parte.sin_cobertura[0]
        assert primera.titular == con_horario_publicado["docente"]
        # Nadie decidió todavía qué hacer con esas horas.
        assert primera.decidida is False

    def test_el_suplente_ocupa_el_lugar_del_titular(self, con_horario_publicado):
        escuela = con_horario_publicado["escuela"]
        licencia = dar_licencia(con_horario_publicado)
        suplente = Legajo.objects.create(
            institucion=escuela["institucion"],
            apellido="Suplente",
            nombre="Marta",
            cuil="27-39888777-6",
        )
        Cobertura.objects.create(
            institucion=escuela["institucion"],
            licencia=licencia,
            cargo=con_horario_publicado["cargo"],
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )

        parte = parte_diario(escuela["institucion"], con_horario_publicado["fecha"])

        assert parte.sin_cobertura == []
        assert len(parte.lineas) == 1
        linea = parte.lineas[0]
        assert linea.legajo == suplente
        assert linea.es_suplente
        assert linea.titular == con_horario_publicado["docente"]

    def test_sin_cobertura_deja_constancia_de_que_fue_decidido(self, con_horario_publicado):
        escuela = con_horario_publicado["escuela"]
        licencia = dar_licencia(con_horario_publicado)
        Cobertura.objects.create(
            institucion=escuela["institucion"],
            licencia=licencia,
            cargo=con_horario_publicado["cargo"],
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )

        parte = parte_diario(escuela["institucion"], con_horario_publicado["fecha"])
        assert parte.lineas == []
        assert all(hora.decidida for hora in parte.sin_cobertura)

    def test_la_licencia_de_otro_dia_no_afecta(self, con_horario_publicado):
        otro_dia = con_horario_publicado["fecha"] + timedelta(days=7)
        dar_licencia(con_horario_publicado, desde=otro_dia, hasta=otro_dia)

        parte = parte_diario(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )
        assert len(parte.lineas) == 1

    def test_avisa_las_coberturas_sin_resolver(self, con_horario_publicado):
        dar_licencia(con_horario_publicado)
        pendientes = coberturas_pendientes(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )
        assert len(pendientes) == 1
        _licencia, cargo = pendientes[0]
        assert cargo == con_horario_publicado["cargo"]


class TestRegistrosEnElParte:
    def test_muestra_lo_ya_registrado(self, con_horario_publicado):
        escuela = con_horario_publicado["escuela"]
        RegistroAsistencia.objects.create(
            institucion=escuela["institucion"],
            legajo=con_horario_publicado["docente"],
            fecha=con_horario_publicado["fecha"],
            estado=EstadoAsistencia.TARDE,
            hora=time(8, 30),
        )
        parte = parte_diario(escuela["institucion"], con_horario_publicado["fecha"])
        assert parte.lineas[0].estado == "Llegada tarde"
        assert parte.sin_registrar == 0

    def test_cuenta_los_que_faltan_registrar(self, con_horario_publicado):
        parte = parte_diario(
            con_horario_publicado["escuela"]["institucion"], con_horario_publicado["fecha"]
        )
        assert parte.sin_registrar == 1
