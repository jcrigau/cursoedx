"""Las decisiones de cobertura, tomadas donde aparece el problema.

Lo que se prueba acá no es que el dato se guarde —eso ya lo cubre el admin—
sino que la vía rápida haga exactamente lo mismo que el camino largo, y que
no deje pasar lo que el modelo no permite.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia


@pytest.fixture
def con_licencia(escuela, secretaria):
    """Una licencia aprobada sobre un cargo, sin cobertura decidida."""
    from horarios.tests.conftest import (
        crear_curso,
        crear_docente,
        crear_esquema,
        crear_materia,
        designar,
    )

    institucion = escuela["institucion"]
    esquema = crear_esquema(escuela)
    curso = crear_curso(escuela, esquema)
    materia = crear_materia(escuela, "Matemática")
    docente = crear_docente(escuela, "Titular", 1)
    cargo = designar(escuela, docente, materia, curso)

    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    licencia = Licencia.objects.create(
        institucion=institucion,
        legajo=docente,
        tipo=tipo,
        fecha_inicio=date.today(),
        fecha_fin=date.today() + timedelta(days=5),
        estado=EstadoLicencia.APROBADA,
    )
    return {"licencia": licencia, "cargo": cargo, "docente": docente, "escuela": escuela}


class TestDejarSinCubrir:
    def test_registra_la_decision_de_no_cubrir(self, client, con_licencia, secretaria):
        client.force_login(secretaria)

        respuesta = client.post(
            reverse("dejar_sin_cobertura"),
            {"licencia": con_licencia["licencia"].pk, "cargo": con_licencia["cargo"].pk},
        )

        assert respuesta.status_code == 302
        cobertura = Cobertura.objects.get()
        assert cobertura.tipo == TipoCobertura.SIN_COBERTURA
        assert cobertura.cargo == con_licencia["cargo"]
        # Cubre toda la licencia, que es lo que se decidió.
        assert cobertura.fecha_inicio == con_licencia["licencia"].fecha_inicio
        assert cobertura.fecha_fin == con_licencia["licencia"].fecha_fin

    def test_no_duplica_si_ya_estaba_decidida(self, client, con_licencia, secretaria):
        client.force_login(secretaria)
        datos = {"licencia": con_licencia["licencia"].pk, "cargo": con_licencia["cargo"].pk}
        client.post(reverse("dejar_sin_cobertura"), datos)

        client.post(reverse("dejar_sin_cobertura"), datos)

        assert Cobertura.objects.count() == 1

    def test_no_es_publica(self, client, con_licencia, db):
        respuesta = client.post(
            reverse("dejar_sin_cobertura"),
            {"licencia": con_licencia["licencia"].pk, "cargo": con_licencia["cargo"].pk},
        )
        assert respuesta.status_code in (302, 403)
        assert not Cobertura.objects.exists()


@pytest.fixture
def con_suplente(con_licencia):
    from legajos.models import Legajo

    licencia = con_licencia["licencia"]
    suplente = Legajo.objects.create(
        institucion=licencia.institucion,
        apellido="Suplente",
        nombre="Ana",
        cuil="27-30000999-1",
        fecha_ingreso=date.today(),
    )
    cobertura = Cobertura.objects.create(
        institucion=licencia.institucion,
        licencia=licencia,
        cargo=con_licencia["cargo"],
        tipo=TipoCobertura.SUPLENTE,
        suplente=suplente,
        fecha_inicio=licencia.fecha_inicio,
        fecha_fin=licencia.fecha_inicio + timedelta(days=2),
    )
    cobertura.designar_cargo_del_suplente()
    return cobertura


class TestSuplencias:
    def test_extender_corre_tambien_la_baja_del_cargo(self, client, con_suplente, secretaria):
        client.force_login(secretaria)
        nueva = con_suplente.licencia.fecha_fin

        client.post(
            reverse("extender_suplencia", args=[con_suplente.pk]),
            {"hasta": nueva.isoformat()},
        )

        con_suplente.refresh_from_db()
        assert con_suplente.fecha_fin == nueva
        # El cargo del suplente tiene que acompañar, o queda dado de baja antes
        # de terminar de trabajar.
        assert con_suplente.cargo_suplente.fecha_baja == nueva

    def test_no_deja_extender_mas_alla_de_la_licencia(self, client, con_suplente, secretaria):
        client.force_login(secretaria)
        antes = con_suplente.fecha_fin

        client.post(
            reverse("extender_suplencia", args=[con_suplente.pk]),
            {"hasta": (con_suplente.licencia.fecha_fin + timedelta(days=10)).isoformat()},
        )

        con_suplente.refresh_from_db()
        assert con_suplente.fecha_fin == antes

    def test_cesar_da_de_baja_el_cargo_con_su_motivo(self, client, con_suplente, secretaria):
        from legajos.models import MotivoBaja

        client.force_login(secretaria)

        client.post(reverse("cesar_suplencia", args=[con_suplente.pk]))

        con_suplente.refresh_from_db()
        cargo = con_suplente.cargo_suplente
        assert cargo.fecha_baja == date.today()
        assert cargo.motivo_baja == MotivoBaja.FIN_SUPLENCIA
