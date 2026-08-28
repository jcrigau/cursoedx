"""Cómputo de antigüedad: lo que se certifica y lo que después usa quien liquida.

El error clásico —y el que estas pruebas cuidan— es contar dos veces el tiempo
de alguien que tuvo varios cargos simultáneos.
"""

from datetime import date

import pytest

from legajos.antiguedad import (
    antiguedad_en_la_institucion,
    calcular_antiguedad,
    desglosar,
    dias_de,
    unir_periodos,
)
from legajos.models import (
    Cargo,
    FuentePago,
    Legajo,
    ServicioAnterior,
    SituacionRevista,
    TipoCargo,
)


@pytest.fixture
def legajo(institucion, db):
    return Legajo.objects.create(
        institucion=institucion, apellido="Gómez", nombre="Ana", cuil="27-30123456-4"
    )


def crear_cargo(legajo, desde, hasta=None, horas=4, denominacion="Preceptor/a"):
    return Cargo.objects.create(
        institucion=legajo.institucion,
        legajo=legajo,
        tipo=TipoCargo.CARGO_BASE,
        denominacion=denominacion,
        horas_semanales=horas,
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=desde,
        fecha_baja=hasta,
        motivo_baja="CESE" if hasta else "",
    )


class TestUnirPeriodos:
    def test_periodos_separados_se_mantienen(self):
        periodos = [(date(2020, 1, 1), date(2020, 3, 31)), (date(2021, 1, 1), date(2021, 3, 31))]
        assert unir_periodos(periodos) == periodos

    def test_periodos_superpuestos_se_funden(self):
        unidos = unir_periodos(
            [(date(2020, 3, 1), date(2020, 6, 30)), (date(2020, 5, 1), date(2020, 8, 31))]
        )
        assert unidos == [(date(2020, 3, 1), date(2020, 8, 31))]

    def test_periodos_contiguos_se_funden(self):
        # Uno termina el 30 y el otro empieza el 31: es tiempo continuo.
        unidos = unir_periodos(
            [(date(2020, 3, 1), date(2020, 3, 30)), (date(2020, 3, 31), date(2020, 4, 30))]
        )
        assert unidos == [(date(2020, 3, 1), date(2020, 4, 30))]

    def test_uno_contenido_en_otro(self):
        unidos = unir_periodos(
            [(date(2020, 1, 1), date(2020, 12, 31)), (date(2020, 5, 1), date(2020, 6, 30))]
        )
        assert unidos == [(date(2020, 1, 1), date(2020, 12, 31))]

    def test_no_importa_el_orden_de_entrada(self):
        desordenados = [
            (date(2021, 1, 1), date(2021, 3, 31)),
            (date(2020, 1, 1), date(2020, 3, 31)),
        ]
        assert unir_periodos(desordenados)[0][0] == date(2020, 1, 1)

    def test_sin_periodos(self):
        assert unir_periodos([]) == []

    def test_cuenta_ambos_extremos(self):
        # Del 1 al 31 de enero se trabajaron 31 días, no 30.
        assert dias_de([(date(2020, 1, 1), date(2020, 1, 31))]) == 31


class TestDesglose:
    def test_un_anio_exacto(self):
        antiguedad = desglosar(365)
        assert (antiguedad.anios, antiguedad.meses, antiguedad.dias) == (1, 0, 0)

    def test_anios_meses_y_dias(self):
        antiguedad = desglosar(365 * 2 + 30 * 3 + 5)
        assert (antiguedad.anios, antiguedad.meses, antiguedad.dias) == (2, 3, 5)

    def test_texto_legible(self):
        assert str(desglosar(365 * 2 + 30 * 3 + 5)) == "2 años, 3 meses y 5 días"
        assert str(desglosar(365)) == "1 año"
        assert str(desglosar(0)) == "0 días"

    def test_un_solo_mes(self):
        assert str(desglosar(30)) == "1 mes"


class TestAntiguedadDelLegajo:
    def test_cargo_cerrado(self, legajo):
        crear_cargo(legajo, date(2020, 1, 1), date(2020, 12, 31))
        antiguedad = calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1))
        assert antiguedad.total_dias == 366  # 2020 fue bisiesto

    def test_cargo_abierto_cuenta_hasta_la_fecha(self, legajo):
        crear_cargo(legajo, date(2023, 1, 1))
        antiguedad = calcular_antiguedad(legajo, a_fecha=date(2023, 12, 31))
        assert antiguedad.total_dias == 365

    def test_cargos_simultaneos_se_cuentan_una_sola_vez(self, legajo):
        """El caso que más se equivoca a mano: tres cargos a la vez, un solo tiempo."""
        crear_cargo(legajo, date(2023, 1, 1), date(2023, 12, 31), denominacion="Preceptor/a")
        crear_cargo(legajo, date(2023, 1, 1), date(2023, 12, 31), denominacion="Bibliotecario/a")
        crear_cargo(legajo, date(2023, 3, 1), date(2023, 6, 30), denominacion="Tutor/a")

        antiguedad = calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1))
        assert antiguedad.total_dias == 365  # y no 365 + 365 + 122

    def test_cargos_en_anios_distintos_se_suman(self, legajo):
        crear_cargo(legajo, date(2020, 1, 1), date(2020, 12, 31))
        crear_cargo(legajo, date(2022, 1, 1), date(2022, 12, 31))
        antiguedad = calcular_antiguedad(legajo, a_fecha=date(2023, 1, 1))
        assert antiguedad.total_dias == 366 + 365

    def test_ignora_cargos_que_todavia_no_empezaron(self, legajo):
        crear_cargo(legajo, date(2030, 1, 1))
        assert calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1)).total_dias == 0

    def test_suma_los_servicios_anteriores(self, legajo):
        crear_cargo(legajo, date(2023, 1, 1), date(2023, 12, 31))
        ServicioAnterior.objects.create(
            legajo=legajo,
            institucion_nombre="Escuela anterior",
            desde=date(2020, 1, 1),
            hasta=date(2020, 12, 31),
        )
        antiguedad = calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1))
        assert antiguedad.total_dias == 365 + 366

    def test_servicio_anterior_superpuesto_no_duplica(self, legajo):
        # Alguien que trabajaba en dos escuelas a la vez tiene una sola antigüedad.
        crear_cargo(legajo, date(2023, 1, 1), date(2023, 12, 31))
        ServicioAnterior.objects.create(
            legajo=legajo,
            institucion_nombre="Otra escuela",
            desde=date(2023, 3, 1),
            hasta=date(2023, 6, 30),
        )
        assert calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1)).total_dias == 365

    def test_servicio_no_docente_se_puede_excluir(self, legajo):
        ServicioAnterior.objects.create(
            legajo=legajo,
            institucion_nombre="Empresa privada",
            desde=date(2018, 1, 1),
            hasta=date(2018, 12, 31),
            es_docente=False,
        )
        assert calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1)).total_dias == 0
        con_todo = calcular_antiguedad(legajo, a_fecha=date(2024, 1, 1), solo_docente=False)
        assert con_todo.total_dias == 365

    def test_antiguedad_en_la_institucion_ignora_lo_anterior(self, legajo):
        crear_cargo(legajo, date(2023, 1, 1), date(2023, 12, 31))
        ServicioAnterior.objects.create(
            legajo=legajo,
            institucion_nombre="Escuela anterior",
            desde=date(2020, 1, 1),
            hasta=date(2020, 12, 31),
        )
        assert antiguedad_en_la_institucion(legajo, date(2024, 1, 1)).total_dias == 365

    def test_legajo_sin_cargos(self, legajo):
        assert calcular_antiguedad(legajo).total_dias == 0
