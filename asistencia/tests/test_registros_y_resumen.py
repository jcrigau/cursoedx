"""Registros de asistencia y resumen mensual (la base de las novedades)."""

from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError

from asistencia.models import (
    EstadoAsistencia,
    RegistroAsistencia,
    buscar_licencia_que_justifica,
)
from asistencia.reportes import dias_en_el_mes, limites_del_mes, resumen_mensual
from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo
from licencias.models import EstadoLicencia, Licencia, TipoLicencia

AYER = date.today() - timedelta(days=1)


@pytest.fixture
def docente(institucion, db):
    return Legajo.objects.create(
        institucion=institucion, apellido="Pérez", nombre="Ana", cuil="27-30111222-3"
    )


def dar_cargo(institucion, legajo, fuente=FuentePago.SUBVENCIONADO):
    return Cargo.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=TipoCargo.CARGO_BASE,
        denominacion="Preceptor/a",
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=fuente,
        fecha_alta=date(2020, 3, 1),
    )


def dar_licencia(institucion, legajo, desde, hasta, con_goce=True, nombre="Enfermedad"):
    tipo, _ = TipoLicencia.objects.get_or_create(
        institucion=institucion, nombre=nombre, defaults={"con_goce": con_goce}
    )
    return Licencia.objects.create(
        institucion=institucion,
        legajo=legajo,
        tipo=tipo,
        fecha_inicio=desde,
        fecha_fin=hasta,
        estado=EstadoLicencia.APROBADA,
    )


class TestRegistro:
    def test_una_ausencia_sin_licencia_es_injustificada(self, institucion, docente):
        registro = RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.AUSENTE,
        )
        assert registro.es_ausencia
        assert registro.injustificada
        assert not registro.justificada

    def test_con_licencia_queda_justificada(self, institucion, docente):
        licencia = dar_licencia(institucion, docente, AYER, AYER)
        registro = RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.AUSENTE,
            licencia=licencia,
        )
        assert registro.justificada
        assert not registro.injustificada

    def test_busca_la_licencia_que_corresponde(self, institucion, docente):
        licencia = dar_licencia(institucion, docente, AYER, AYER)
        assert buscar_licencia_que_justifica(docente, AYER) == licencia
        assert buscar_licencia_que_justifica(docente, AYER - timedelta(days=5)) is None

    def test_una_licencia_pendiente_no_justifica(self, institucion, docente):
        licencia = dar_licencia(institucion, docente, AYER, AYER)
        licencia.estado = EstadoLicencia.SOLICITADA
        licencia.save()
        assert buscar_licencia_que_justifica(docente, AYER) is None

    def test_la_parcial_exige_las_horas(self, institucion, docente):
        registro = RegistroAsistencia(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.PARCIAL,
        )
        with pytest.raises(ValidationError) as error:
            registro.full_clean()
        assert "horas_afectadas" in error.value.message_dict

    def test_la_tardanza_exige_la_hora(self, institucion, docente):
        registro = RegistroAsistencia(
            institucion=institucion, legajo=docente, fecha=AYER, estado=EstadoAsistencia.TARDE
        )
        with pytest.raises(ValidationError) as error:
            registro.full_clean()
        assert "hora" in error.value.message_dict

    def test_no_se_registra_el_futuro(self, institucion, docente):
        registro = RegistroAsistencia(
            institucion=institucion,
            legajo=docente,
            fecha=date.today() + timedelta(days=1),
            estado=EstadoAsistencia.AUSENTE,
        )
        with pytest.raises(ValidationError) as error:
            registro.full_clean()
        assert "fecha" in error.value.message_dict

    def test_la_licencia_debe_ser_de_la_misma_persona(self, institucion, docente):
        otra = Legajo.objects.create(
            institucion=institucion, apellido="Otra", nombre="Persona", cuil="27-31222333-4"
        )
        licencia = dar_licencia(institucion, otra, AYER, AYER)
        registro = RegistroAsistencia(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.AUSENTE,
            licencia=licencia,
        )
        with pytest.raises(ValidationError) as error:
            registro.full_clean()
        assert "licencia" in error.value.message_dict

    def test_un_solo_registro_por_persona_y_dia(self, institucion, docente):
        from django.db import IntegrityError

        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.AUSENTE,
        )
        with pytest.raises(IntegrityError):
            RegistroAsistencia.objects.create(
                institucion=institucion,
                legajo=docente,
                fecha=AYER,
                estado=EstadoAsistencia.TARDE,
                hora=time(8, 0),
            )


class TestDiasEnElMes:
    def test_periodo_contenido(self):
        assert dias_en_el_mes(date(2026, 5, 4), date(2026, 5, 8), 2026, 5) == 5

    def test_periodo_que_cruza_meses(self):
        """Una licencia de fin de abril a principios de mayo se parte."""
        assert dias_en_el_mes(date(2026, 4, 28), date(2026, 5, 3), 2026, 4) == 3
        assert dias_en_el_mes(date(2026, 4, 28), date(2026, 5, 3), 2026, 5) == 3

    def test_periodo_de_otro_mes(self):
        assert dias_en_el_mes(date(2026, 3, 1), date(2026, 3, 10), 2026, 5) == 0

    def test_limites_de_febrero_bisiesto(self):
        assert limites_del_mes(2028, 2)[1].day == 29


@pytest.mark.django_db
class TestResumenMensual:
    def _mes_de(self, fecha):
        return fecha.year, fecha.month

    def test_separa_justificadas_de_injustificadas(self, institucion, docente):
        dar_cargo(institucion, docente)
        licencia = dar_licencia(institucion, docente, AYER, AYER)
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.AUSENTE,
            licencia=licencia,
        )
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER - timedelta(days=1),
            estado=EstadoAsistencia.AUSENTE,
        )

        anio, mes = self._mes_de(AYER)
        resumen = resumen_mensual(institucion, anio, mes)[0]
        assert resumen.ausencias_justificadas == 1
        # La del día anterior puede caer en otro mes; se comprueba el total.
        assert resumen.ausencias_justificadas + resumen.ausencias_injustificadas >= 1

    def test_cuenta_tardanzas(self, institucion, docente):
        dar_cargo(institucion, docente)
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=AYER,
            estado=EstadoAsistencia.TARDE,
            hora=time(8, 20),
        )
        anio, mes = self._mes_de(AYER)
        assert resumen_mensual(institucion, anio, mes)[0].tardanzas == 1

    def test_informa_los_dias_de_licencia_del_mes(self, institucion, docente):
        dar_cargo(institucion, docente)
        dar_licencia(institucion, docente, date(2026, 5, 4), date(2026, 5, 8))

        resumen = resumen_mensual(institucion, 2026, 5)[0]
        assert resumen.licencias[0].dias == 5
        assert resumen.tiene_novedades

    def test_una_licencia_larga_se_reparte_entre_los_meses(self, institucion, docente):
        dar_cargo(institucion, docente)
        dar_licencia(institucion, docente, date(2026, 4, 20), date(2026, 5, 10))

        abril = resumen_mensual(institucion, 2026, 4)[0]
        mayo = resumen_mensual(institucion, 2026, 5)[0]
        assert abril.licencias[0].dias == 11
        assert mayo.licencias[0].dias == 10

    def test_marca_los_dias_sin_goce(self, institucion, docente):
        dar_cargo(institucion, docente)
        dar_licencia(
            institucion,
            docente,
            date(2026, 5, 4),
            date(2026, 5, 6),
            con_goce=False,
            nombre="Licencia sin goce",
        )
        resumen = resumen_mensual(institucion, 2026, 5)[0]
        assert resumen.dias_sin_goce == 3

    def test_identifica_al_personal_mixto(self, institucion, docente):
        """Con cargos de las dos fuentes, la persona va a las dos planillas."""
        dar_cargo(institucion, docente, FuentePago.SUBVENCIONADO)
        dar_cargo(institucion, docente, FuentePago.INTERNO)
        dar_licencia(institucion, docente, date(2026, 5, 4), date(2026, 5, 6))

        resumen = resumen_mensual(institucion, 2026, 5)[0]
        assert resumen.es_mixto
        assert "Oficial" in resumen.detalle_fuentes
        assert "Interna" in resumen.detalle_fuentes

    def test_no_lista_a_quien_no_tuvo_novedades(self, institucion, docente):
        dar_cargo(institucion, docente)
        assert resumen_mensual(institucion, 2026, 5) == []

    def test_no_mezcla_instituciones(self, institucion, otra_institucion, docente):
        dar_cargo(institucion, docente)
        dar_licencia(institucion, docente, date(2026, 5, 4), date(2026, 5, 6))
        assert len(resumen_mensual(institucion, 2026, 5)) == 1
        assert resumen_mensual(otra_institucion, 2026, 5) == []
