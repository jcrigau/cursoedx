"""«¿A quién llamo?»: la búsqueda de reemplazo y el aviso.

Lo que importa acá es el criterio: que la lista ponga primero a quien
realmente conviene llamar, que explique por qué alguien no puede, y que
designar deje al suplente con su cargo —de donde sale su alta en el mes—.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from horarios.models import AsignacionHoraria
from legajos.models import Legajo
from licencias import avisos
from licencias.candidatos import buscar
from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia


@pytest.fixture
def hora_sin_docente(escuela):
    """Un curso con una hora cuyo titular está de licencia."""
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

    institucion = escuela["institucion"]
    esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    crear_plan(curso, materia, 4)
    titular = crear_docente(escuela, "Titular", 1)
    cargo = designar(escuela, titular, materia, curso)

    version = crear_version(escuela)
    generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=5))
    version.publicar()

    asignacion = version.asignaciones.order_by("dia_semana", "hora_inicio").first()
    fecha = escuela["periodo"].fecha_inicio
    while fecha.weekday() != asignacion.dia_semana:
        fecha += timedelta(days=1)

    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    licencia = Licencia.objects.create(
        institucion=institucion,
        legajo=titular,
        tipo=tipo,
        fecha_inicio=fecha,
        fecha_fin=fecha + timedelta(days=3),
        estado=EstadoLicencia.APROBADA,
    )
    return {
        "escuela": escuela,
        "asignacion": asignacion,
        "fecha": fecha,
        "licencia": licencia,
        "cargo": cargo,
        "materia": materia,
        "titular": titular,
    }


def otra_persona(escuela, apellido, cuil, **datos):
    return Legajo.objects.create(
        institucion=escuela["institucion"],
        apellido=apellido,
        nombre="Prueba",
        cuil=cuil,
        fecha_ingreso=date.today(),
        **datos,
    )


class TestAQuienLlamo:
    def test_el_titular_no_se_ofrece_a_si_mismo(self, hora_sin_docente):
        candidatos = buscar(
            hora_sin_docente["escuela"]["institucion"],
            hora_sin_docente["asignacion"],
            hora_sin_docente["fecha"],
        )
        assert hora_sin_docente["titular"] not in [c.legajo for c in candidatos]

    def test_explica_por_que_alguien_no_puede(self, hora_sin_docente):
        """Saber el motivo evita volver a preguntarse lo mismo mañana."""
        de_licencia = otra_persona(hora_sin_docente["escuela"], "Enferma", "27-30000777-1")
        Licencia.objects.create(
            institucion=de_licencia.institucion,
            legajo=de_licencia,
            tipo=hora_sin_docente["licencia"].tipo,
            fecha_inicio=hora_sin_docente["fecha"],
            fecha_fin=hora_sin_docente["fecha"],
            estado=EstadoLicencia.APROBADA,
        )

        candidatos = buscar(
            de_licencia.institucion, hora_sin_docente["asignacion"], hora_sin_docente["fecha"]
        )
        suya = next(c for c in candidatos if c.legajo == de_licencia)

        assert not suya.disponible
        assert suya.por_que_no == "está de licencia"

    def test_los_disponibles_van_primero(self, hora_sin_docente):
        libre = otra_persona(hora_sin_docente["escuela"], "Libre", "27-30000778-1")
        ocupada = otra_persona(hora_sin_docente["escuela"], "Ocupada", "27-30000779-1")
        # A la ocupada se le pone una clase justo a esa hora.
        AsignacionHoraria.objects.filter(
            version=hora_sin_docente["asignacion"].version,
            dia_semana=hora_sin_docente["asignacion"].dia_semana,
            hora_inicio=hora_sin_docente["asignacion"].hora_inicio,
        ).exclude(pk=hora_sin_docente["asignacion"].pk).update(legajo=ocupada)

        candidatos = buscar(
            libre.institucion, hora_sin_docente["asignacion"], hora_sin_docente["fecha"]
        )
        orden = [c.legajo for c in candidatos]

        assert orden.index(libre) < orden.index(ocupada) or not any(
            c.legajo == ocupada and not c.disponible for c in candidatos
        )

    def test_el_personal_que_no_da_clases_no_aparece(self, hora_sin_docente):
        """Un ordenanza o una administrativa no son reemplazo para un curso."""
        from legajos.models import Plantel

        otra_persona(
            hora_sin_docente["escuela"], "Ordenanza", "20-30000782-1", plantel=Plantel.MAESTRANZA
        )
        otra_persona(
            hora_sin_docente["escuela"],
            "Administrativa",
            "27-30000783-1",
            plantel=Plantel.ADMINISTRATIVO,
        )
        preceptor = otra_persona(
            hora_sin_docente["escuela"], "Preceptor", "20-30000784-1", plantel=Plantel.PRECEPTOR
        )

        candidatos = buscar(
            hora_sin_docente["escuela"]["institucion"],
            hora_sin_docente["asignacion"],
            hora_sin_docente["fecha"],
        )
        apellidos = [c.legajo.apellido for c in candidatos]

        assert "Ordenanza" not in apellidos
        assert "Administrativa" not in apellidos
        # El preceptor sí: puede estar habilitado para dar la materia.
        assert preceptor in [c.legajo for c in candidatos]

    def test_la_pantalla_lista_a_los_candidatos(self, client, hora_sin_docente, secretaria):
        otra_persona(hora_sin_docente["escuela"], "Candidata", "27-30000780-1")
        client.force_login(secretaria)

        respuesta = client.get(
            reverse("cubrir_ahora", args=[hora_sin_docente["asignacion"].pk]),
            {"fecha": hora_sin_docente["fecha"].isoformat(), "solo_disponibles": "0"},
        )

        assert respuesta.status_code == 200
        assert "Candidata" in respuesta.content.decode()


class TestDesignarDesdeAhi:
    def test_designar_crea_la_cobertura_y_el_cargo(self, client, hora_sin_docente, secretaria):
        suplente = otra_persona(hora_sin_docente["escuela"], "Suplente", "27-30000781-1")
        client.force_login(secretaria)

        client.post(
            reverse("designar_suplente", args=[hora_sin_docente["asignacion"].pk]),
            {"fecha": hora_sin_docente["fecha"].isoformat(), "suplente": suplente.pk},
        )

        cobertura = Cobertura.objects.get()
        assert cobertura.tipo == TipoCobertura.SUPLENTE
        assert cobertura.suplente == suplente
        # El cargo es lo que después se convierte en alta al compilar el mes.
        assert cobertura.cargo_suplente is not None
        assert cobertura.cargo_suplente.legajo == suplente

    def test_sin_licencia_detras_no_inventa_una_suplencia(
        self, client, hora_sin_docente, secretaria
    ):
        """Una suplencia se apoya en la licencia que la justifica."""
        hora_sin_docente["licencia"].delete()
        suplente = otra_persona(hora_sin_docente["escuela"], "Suplente", "27-30000782-1")
        client.force_login(secretaria)

        client.post(
            reverse("designar_suplente", args=[hora_sin_docente["asignacion"].pk]),
            {"fecha": hora_sin_docente["fecha"].isoformat(), "suplente": suplente.pk},
        )

        assert not Cobertura.objects.exists()


class TestElAviso:
    def test_el_numero_queda_como_lo_espera_whatsapp(self):
        assert avisos.telefono_para_whatsapp("02664-15-123456") == "542664123456"
        assert avisos.telefono_para_whatsapp("") == ""

    def test_el_mensaje_dice_lo_necesario(self, hora_sin_docente):
        suplente = otra_persona(
            hora_sin_docente["escuela"], "Suplente", "27-30000783-1", telefono="2664123456"
        )
        cobertura = Cobertura.objects.create(
            institucion=suplente.institucion,
            licencia=hora_sin_docente["licencia"],
            cargo=hora_sin_docente["cargo"],
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=hora_sin_docente["fecha"],
            fecha_fin=hora_sin_docente["fecha"],
        )

        mensaje = avisos.mensaje_para(cobertura)

        assert hora_sin_docente["titular"].nombre_completo in mensaje
        assert f"{cobertura.fecha_inicio:%d/%m/%Y}" in mensaje
        assert avisos.link_de_whatsapp(cobertura).startswith("https://wa.me/54")

    def test_queda_registrado_quien_avisó_y_cuándo(self, client, hora_sin_docente, secretaria):
        suplente = otra_persona(hora_sin_docente["escuela"], "Suplente", "27-30000784-1")
        cobertura = Cobertura.objects.create(
            institucion=suplente.institucion,
            licencia=hora_sin_docente["licencia"],
            cargo=hora_sin_docente["cargo"],
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=hora_sin_docente["fecha"],
            fecha_fin=hora_sin_docente["fecha"],
        )
        client.force_login(secretaria)

        client.post(reverse("avisar_suplencia", args=[cobertura.pk]), {"via": "WHATSAPP"})

        cobertura.refresh_from_db()
        assert cobertura.notificada_en is not None
        assert cobertura.notificada_por == "WHATSAPP"
