"""El control «grilla vs. planta»: lo designado contra lo que se da.

Lo que no puede quedar sin explicación es un cargo subvencionado sin
resolución: ahí se cobra algo cuyo respaldo no está en el sistema.
"""

from datetime import date

import pytest
from django.urls import reverse

from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo
from legajos.planta import resumen, revisar


@pytest.fixture
def con_cargos(institucion):
    from estructura.models import Materia, Nivel, TipoNivel

    nivel = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    materia = Materia.objects.create(institucion=institucion, nivel=nivel, nombre="Matemática")
    legajo = Legajo.objects.create(
        institucion=institucion,
        apellido="Benítez",
        nombre="Ana",
        cuil="27-30000001-1",
        fecha_ingreso=date(2020, 3, 1),
    )
    cargo = Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.HORAS_CATEDRA,
        materia=materia,
        horas_semanales=10,
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=date(2020, 3, 1),
    )
    return {"institucion": institucion, "legajo": legajo, "cargo": cargo}


@pytest.mark.django_db
class TestElControl:
    def test_marca_el_cargo_subvencionado_sin_resolucion(self, con_cargos):
        lineas = revisar(con_cargos["institucion"])

        linea = lineas[0]
        assert linea.cargos_sin_resolucion == [con_cargos["cargo"]]
        assert linea.hay_que_mirarla

    def test_con_la_resolucion_cargada_queda_en_orden(self, con_cargos):
        cargo = con_cargos["cargo"]
        cargo.resolucion_numero = "1234/25"
        cargo.save()

        linea = revisar(con_cargos["institucion"])[0]

        assert linea.cargos_sin_resolucion == []

    def test_un_cargo_interno_no_necesita_resolucion(self, con_cargos):
        """La resolución respalda lo que paga el estado, no lo que paga la escuela."""
        cargo = con_cargos["cargo"]
        cargo.fuente_pago = FuentePago.INTERNO
        cargo.save()

        linea = revisar(con_cargos["institucion"])[0]

        assert linea.cargos_sin_resolucion == []

    def test_cuenta_las_horas_designadas(self, con_cargos):
        lineas = revisar(con_cargos["institucion"])

        assert lineas[0].horas_designadas == 10
        # Sin horario publicado no hay con qué comparar: cero, y se avisa.
        assert lineas[0].horas_en_el_horario == 0
        assert resumen(lineas)["horas_designadas"] == 10

    def test_la_pantalla_se_ve(self, client, con_cargos, secretaria):
        client.force_login(secretaria)

        cuerpo = client.get(reverse("control_de_planta")).content.decode()

        assert "Control de la planta" in cuerpo
        assert "Benítez" in cuerpo
        assert "Sin resolución" in cuerpo

    def test_no_es_publica(self, client, con_cargos):
        assert client.get(reverse("control_de_planta")).status_code in (302, 403)
