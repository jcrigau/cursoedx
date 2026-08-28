"""Las pantallas de asistencia: permisos y carga del parte."""

from datetime import date

import pytest

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from core.models import Membresia, Rol, Usuario
from horarios.generador import Parametros, generar
from horarios.tests.conftest import (
    crear_curso,
    crear_docente,
    crear_esquema,
    crear_materia,
    crear_plan,
    crear_version,
    designar,
)
from licencias.models import EstadoLicencia, Licencia, TipoLicencia

from .test_parte import fecha_con_clases


@pytest.fixture
def escuela_con_parte(escuela):
    """Escuela con horario publicado y una fecha pasada en la que hubo clases."""
    esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    crear_plan(curso, materia, 4)
    docente = crear_docente(escuela, "Titular", 1)
    designar(escuela, docente, materia, curso)

    version = crear_version(escuela)
    generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=5))
    version.publicar()

    # El período de prueba es de 2026; se corre la fecha al pasado si hiciera
    # falta, porque no se puede registrar asistencia de un día que no pasó.
    fecha = fecha_con_clases(escuela, version)
    return {"escuela": escuela, "docente": docente, "version": version, "fecha": fecha}


@pytest.mark.django_db
class TestParteDiario:
    def test_exige_login(self, client):
        respuesta = client.get("/asistencia/")
        assert respuesta.status_code == 302
        assert "/cuentas/login/" in respuesta["Location"]

    def test_el_docente_no_accede(self, client, institucion):
        docente = Usuario.objects.create_user(
            email="doc@uno.edu.ar", password="x", nombre="Luis", apellido="Paz"
        )
        Membresia.objects.create(usuario=docente, institucion=institucion, rol=Rol.DOCENTE)
        client.force_login(docente)
        assert client.get("/asistencia/").status_code == 403

    def test_muestra_el_parte_del_dia(self, client, secretaria, escuela_con_parte):
        client.force_login(secretaria)
        fecha = escuela_con_parte["fecha"]
        respuesta = client.get(f"/asistencia/?fecha={fecha:%Y-%m-%d}")

        assert respuesta.status_code == 200
        parte = respuesta.context["parte"]
        assert len(parte.lineas) == 1
        assert parte.lineas[0].legajo == escuela_con_parte["docente"]

    def test_una_fecha_invalida_cae_en_hoy(self, client, secretaria, escuela_con_parte):
        client.force_login(secretaria)
        respuesta = client.get("/asistencia/?fecha=cualquier-cosa")
        assert respuesta.context["fecha"] == date.today()

    def test_guarda_una_ausencia(self, client, secretaria, escuela_con_parte):
        client.force_login(secretaria)
        fecha = escuela_con_parte["fecha"]
        docente = escuela_con_parte["docente"]

        client.post(
            "/asistencia/",
            {
                "fecha": f"{fecha:%Y-%m-%d}",
                f"estado_{docente.id}": EstadoAsistencia.AUSENTE,
                f"obs_{docente.id}": "Avisó por teléfono",
            },
        )

        registro = RegistroAsistencia.objects.get(legajo=docente, fecha=fecha)
        assert registro.estado == EstadoAsistencia.AUSENTE
        assert registro.observaciones == "Avisó por teléfono"
        assert registro.registrado_por == secretaria
        assert registro.injustificada

    def test_el_certificado_que_llega_despues_justifica_la_falta(
        self, client, secretaria, escuela_con_parte, institucion
    ):
        """Caso frecuente: primero se marca la falta, después trae el certificado.

        Al aprobarse la licencia, la ausencia ya cargada tiene que quedar
        justificada sola; si no, el mes cerraría con un descuento indebido.
        """
        fecha = escuela_con_parte["fecha"]
        docente = escuela_con_parte["docente"]

        client.force_login(secretaria)
        client.post(
            "/asistencia/",
            {"fecha": f"{fecha:%Y-%m-%d}", f"estado_{docente.id}": EstadoAsistencia.AUSENTE},
        )
        registro = RegistroAsistencia.objects.get(legajo=docente, fecha=fecha)
        assert registro.injustificada

        tipo = TipoLicencia.objects.create(
            institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
        )
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )
        licencia.aprobar(usuario=secretaria)

        registro.refresh_from_db()
        assert registro.licencia == licencia
        assert registro.justificada

    def test_una_licencia_rechazada_no_justifica_nada(
        self, client, secretaria, escuela_con_parte, institucion
    ):
        fecha = escuela_con_parte["fecha"]
        docente = escuela_con_parte["docente"]
        client.force_login(secretaria)
        client.post(
            "/asistencia/",
            {"fecha": f"{fecha:%Y-%m-%d}", f"estado_{docente.id}": EstadoAsistencia.AUSENTE},
        )

        tipo = TipoLicencia.objects.create(institucion=institucion, nombre="Particulares")
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=fecha,
            fecha_fin=fecha,
        )
        licencia.rechazar(motivo="Sin respaldo")

        registro = RegistroAsistencia.objects.get(legajo=docente, fecha=fecha)
        assert registro.injustificada

    def test_dejar_en_blanco_borra_el_registro(self, client, secretaria, escuela_con_parte):
        fecha = escuela_con_parte["fecha"]
        docente = escuela_con_parte["docente"]
        RegistroAsistencia.objects.create(
            institucion=escuela_con_parte["escuela"]["institucion"],
            legajo=docente,
            fecha=fecha,
            estado=EstadoAsistencia.AUSENTE,
        )

        client.force_login(secretaria)
        client.post("/asistencia/", {"fecha": f"{fecha:%Y-%m-%d}", f"estado_{docente.id}": ""})

        assert not RegistroAsistencia.objects.filter(legajo=docente, fecha=fecha).exists()


@pytest.mark.django_db
class TestResumenMensual:
    def test_muestra_el_mes_pedido(self, client, secretaria, institucion, escuela_con_parte):
        docente = escuela_con_parte["docente"]
        tipo = TipoLicencia.objects.create(
            institucion=institucion, nombre="Sin goce", con_goce=False
        )
        Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 6),
            estado=EstadoLicencia.APROBADA,
        )

        client.force_login(secretaria)
        respuesta = client.get("/asistencia/resumen/?anio=2026&mes=5")

        assert respuesta.status_code == 200
        resumenes = respuesta.context["resumenes"]
        assert len(resumenes) == 1
        assert resumenes[0].dias_sin_goce == 3

    def test_un_mes_sin_novedades_queda_vacio(self, client, secretaria, escuela_con_parte):
        client.force_login(secretaria)
        respuesta = client.get("/asistencia/resumen/?anio=2026&mes=9")
        assert respuesta.context["resumenes"] == []

    def test_un_mes_invalido_no_rompe(self, client, secretaria, escuela_con_parte):
        client.force_login(secretaria)
        respuesta = client.get("/asistencia/resumen/?anio=2026&mes=99")
        assert respuesta.status_code == 200
        assert respuesta.context["mes"] == 12
