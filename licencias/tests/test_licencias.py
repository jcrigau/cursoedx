"""Licencias: topes del régimen, flujo de aprobación y cobertura de las horas."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from legajos.models import Cargo, FuentePago, Legajo, SituacionRevista, TipoCargo
from licencias.models import (
    Cobertura,
    EstadoLicencia,
    Licencia,
    TipoCobertura,
    TipoLicencia,
    coberturas_vigentes,
    licencias_vigentes,
    suplencias_por_vencer,
)


@pytest.fixture
def docente(institucion, db):
    return Legajo.objects.create(
        institucion=institucion, apellido="Molina", nombre="Ana", cuil="27-30111222-3"
    )


@pytest.fixture
def cargo(institucion, docente):
    return Cargo.objects.create(
        institucion=institucion,
        legajo=docente,
        tipo=TipoCargo.CARGO_BASE,
        denominacion="Preceptor/a",
        situacion_revista=SituacionRevista.TITULAR,
        fuente_pago=FuentePago.SUBVENCIONADO,
        fecha_alta=date(2024, 3, 1),
    )


def crear_tipo(institucion, nombre="Razones particulares", **extra):
    datos = {"codigo": "Art. 93.4", "con_goce": True}
    datos.update(extra)
    return TipoLicencia.objects.create(institucion=institucion, nombre=nombre, **datos)


def crear_licencia(institucion, docente, tipo, desde, hasta, **extra):
    return Licencia(
        institucion=institucion,
        legajo=docente,
        tipo=tipo,
        fecha_inicio=desde,
        fecha_fin=hasta,
        **extra,
    )


class TestDuracion:
    def test_cuenta_los_dos_extremos(self, institucion, docente):
        tipo = crear_tipo(institucion)
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 4), date(2026, 5, 6))
        assert licencia.dias == 3

    def test_un_solo_dia(self, institucion, docente):
        tipo = crear_tipo(institucion)
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 4), date(2026, 5, 4))
        assert licencia.dias == 1

    def test_rechaza_fechas_invertidas(self, institucion, docente):
        tipo = crear_tipo(institucion)
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 6), date(2026, 5, 4))
        with pytest.raises(ValidationError):
            licencia.full_clean()


class TestTopes:
    def test_tope_por_caso(self, institucion, docente):
        """Matrimonio: 12 días por caso."""
        tipo = crear_tipo(institucion, "Matrimonio", codigo="Art. 93.1", tope_dias_por_caso=12)
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 1), date(2026, 5, 20))
        with pytest.raises(ValidationError, match="máximo de 12 por caso"):
            licencia.full_clean()

    def test_dentro_del_tope_por_caso(self, institucion, docente):
        tipo = crear_tipo(institucion, "Matrimonio", codigo="Art. 93.1", tope_dias_por_caso=12)
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 1), date(2026, 5, 12))
        licencia.full_clean()  # 12 justos: no levanta

    def test_tope_anual_acumulado(self, institucion, docente):
        """Razones particulares: 5 días al año, sumando las ya tomadas."""
        tipo = crear_tipo(institucion, tope_dias_anual=5)
        Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 3, 2),
            fecha_fin=date(2026, 3, 5),
            estado=EstadoLicencia.APROBADA,
        )  # 4 días
        segunda = crear_licencia(
            institucion, docente, tipo, date(2026, 8, 10), date(2026, 8, 11)
        )  # 2 más: 6 en el año
        with pytest.raises(ValidationError, match="tope es de 5"):
            segunda.full_clean()

    def test_las_solicitudes_pendientes_no_consumen_tope(self, institucion, docente):
        tipo = crear_tipo(institucion, tope_dias_anual=5)
        Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 3, 2),
            fecha_fin=date(2026, 3, 5),
            estado=EstadoLicencia.SOLICITADA,
        )
        segunda = crear_licencia(institucion, docente, tipo, date(2026, 8, 10), date(2026, 8, 11))
        segunda.full_clean()  # todavía no consumió nada

    def test_el_tope_es_por_año(self, institucion, docente):
        tipo = crear_tipo(institucion, tope_dias_anual=5)
        Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2025, 3, 2),
            fecha_fin=date(2025, 3, 6),
            estado=EstadoLicencia.APROBADA,
        )
        nueva = crear_licencia(institucion, docente, tipo, date(2026, 3, 2), date(2026, 3, 6))
        nueva.full_clean()  # es otro año

    def test_tope_de_dias_consecutivos(self, institucion, docente):
        """Exámenes: 20 al año, pero no más de 5 seguidos."""
        tipo = crear_tipo(
            institucion,
            "Exámenes",
            codigo="Art. 94.1",
            tope_dias_anual=20,
            tope_dias_consecutivos=5,
        )
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 5, 4), date(2026, 5, 11))
        with pytest.raises(ValidationError, match="5 consecutivos"):
            licencia.full_clean()

    def test_enfermedad_se_extiende_con_aval(self, institucion, docente):
        """Enfermedad: 60 días al año, extensibles con junta médica."""
        tipo = crear_tipo(
            institucion,
            "Enfermedad",
            codigo="Art. 76",
            tope_dias_anual=60,
            extensible_con_aval=True,
        )
        larga = crear_licencia(institucion, docente, tipo, date(2026, 3, 1), date(2026, 6, 30))

        with pytest.raises(ValidationError, match="adjuntando el aval"):
            larga.full_clean()

        larga.aval = SimpleUploadedFile("junta.pdf", b"acta de junta medica")
        larga.full_clean()  # con el aval, sigue

    def test_sin_topes_no_hay_excesos(self, institucion, docente):
        tipo = crear_tipo(institucion, "Congresos", codigo="Art. 97")
        licencia = crear_licencia(institucion, docente, tipo, date(2026, 3, 1), date(2026, 4, 30))
        assert licencia.excesos() == []


class TestFlujo:
    def test_aprobar_registra_quien_y_cuando(self, institucion, docente, secretaria):
        tipo = crear_tipo(institucion)
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 5),
        )
        licencia.aprobar(usuario=secretaria)

        licencia.refresh_from_db()
        assert licencia.estado == EstadoLicencia.APROBADA
        assert licencia.resuelta_por == secretaria
        assert licencia.resuelta_en == date.today()

    def test_rechazar_guarda_el_motivo(self, institucion, docente):
        tipo = crear_tipo(institucion)
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 5),
        )
        licencia.rechazar(motivo="Sin certificado")

        assert licencia.estado == EstadoLicencia.RECHAZADA
        assert licencia.motivo_rechazo == "Sin certificado"

    def test_solo_las_aprobadas_estan_vigentes(self, institucion, docente):
        tipo = crear_tipo(institucion)
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 8),
        )
        assert not licencia.vigente_en(date(2026, 5, 5))
        licencia.aprobar()
        assert licencia.vigente_en(date(2026, 5, 5))
        assert not licencia.vigente_en(date(2026, 5, 9))

    def test_licencias_vigentes_de_la_institucion(self, institucion, docente):
        tipo = crear_tipo(institucion)
        Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 8),
            estado=EstadoLicencia.APROBADA,
        )
        assert licencias_vigentes(institucion, date(2026, 5, 6)).count() == 1
        assert licencias_vigentes(institucion, date(2026, 5, 9)).count() == 0

    def test_por_defecto_afecta_todos_los_cargos_vigentes(self, institucion, docente, cargo):
        tipo = crear_tipo(institucion)
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=date(2026, 5, 4),
            fecha_fin=date(2026, 5, 8),
        )
        assert list(licencia.cargos_afectados()) == [cargo]


@pytest.fixture
def licencia_aprobada(institucion, docente, cargo):
    tipo = crear_tipo(institucion, "Enfermedad", codigo="Art. 76")
    return Licencia.objects.create(
        institucion=institucion,
        legajo=docente,
        tipo=tipo,
        fecha_inicio=date(2026, 5, 4),
        fecha_fin=date(2026, 5, 29),
        estado=EstadoLicencia.APROBADA,
    )


@pytest.fixture
def suplente(institucion, db):
    return Legajo.objects.create(
        institucion=institucion, apellido="Reemplazo", nombre="Luis", cuil="20-33444555-6"
    )


class TestCobertura:
    def test_designar_suplente_le_crea_el_cargo(
        self, institucion, licencia_aprobada, cargo, suplente
    ):
        cobertura = Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=licencia_aprobada.fecha_inicio,
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        nuevo = cobertura.designar_cargo_del_suplente()

        assert nuevo.legajo == suplente
        assert nuevo.situacion_revista == SituacionRevista.SUPLENTE
        # Hereda la fuente de pago del titular: la novedad va a la misma planilla.
        assert nuevo.fuente_pago == cargo.fuente_pago
        assert nuevo.fecha_alta == licencia_aprobada.fecha_inicio
        assert nuevo.fecha_baja == licencia_aprobada.fecha_fin

    def test_no_duplica_la_designacion(self, institucion, licencia_aprobada, cargo, suplente):
        cobertura = Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            suplente=suplente,
            fecha_inicio=licencia_aprobada.fecha_inicio,
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        primero = cobertura.designar_cargo_del_suplente()
        segundo = cobertura.designar_cargo_del_suplente()
        assert primero == segundo
        assert Cargo.objects.filter(legajo=suplente).count() == 1

    def test_sin_cobertura_no_crea_cargo(self, institucion, licencia_aprobada, cargo):
        """Los alumnos quedan libres: se registra la decisión, nada más."""
        cobertura = Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=licencia_aprobada.fecha_inicio,
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        assert cobertura.designar_cargo_del_suplente() is None
        assert "sin cobertura" in str(cobertura)

    def test_suplente_obligatorio(self, institucion, licencia_aprobada, cargo):
        cobertura = Cobertura(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            tipo=TipoCobertura.SUPLENTE,
            fecha_inicio=licencia_aprobada.fecha_inicio,
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        with pytest.raises(ValidationError) as error:
            cobertura.full_clean()
        assert "suplente" in error.value.message_dict

    def test_no_puede_cubrirse_a_si_mismo(self, institucion, licencia_aprobada, cargo, docente):
        cobertura = Cobertura(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            suplente=docente,
            fecha_inicio=licencia_aprobada.fecha_inicio,
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        with pytest.raises(ValidationError) as error:
            cobertura.full_clean()
        assert "sí misma" in str(error.value)

    def test_debe_estar_dentro_de_la_licencia(
        self, institucion, licencia_aprobada, cargo, suplente
    ):
        cobertura = Cobertura(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            suplente=suplente,
            fecha_inicio=date(2026, 5, 1),  # antes de que empiece la licencia
            fecha_fin=licencia_aprobada.fecha_fin,
        )
        with pytest.raises(ValidationError, match="dentro del período de la licencia"):
            cobertura.full_clean()

    def test_cobertura_parcial_es_valida(self, institucion, licencia_aprobada, cargo, suplente):
        """Se puede cubrir solo una parte: pasa cuando el suplente entra después."""
        cobertura = Cobertura(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            suplente=suplente,
            fecha_inicio=date(2026, 5, 10),
            fecha_fin=date(2026, 5, 29),
        )
        cobertura.full_clean()

    def test_coberturas_vigentes_por_fecha(self, institucion, licencia_aprobada, cargo, suplente):
        Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia_aprobada,
            cargo=cargo,
            suplente=suplente,
            fecha_inicio=date(2026, 5, 10),
            fecha_fin=date(2026, 5, 20),
        )
        assert coberturas_vigentes(institucion, date(2026, 5, 15)).count() == 1
        assert coberturas_vigentes(institucion, date(2026, 5, 25)).count() == 0

    def test_avisa_las_suplencias_por_vencer(self, institucion, docente, cargo, suplente):
        from datetime import timedelta

        tipo = crear_tipo(institucion, "Enfermedad larga", codigo="Art. 76")
        hoy = date.today()
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy + timedelta(days=3),
            estado=EstadoLicencia.APROBADA,
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia,
            cargo=cargo,
            suplente=suplente,
            fecha_inicio=hoy - timedelta(days=30),
            fecha_fin=hoy + timedelta(days=3),
        )
        assert suplencias_por_vencer(institucion).count() == 1


class TestColumnaDeCobertura:
    """La columna del listado de licencias tiene que distinguir "resuelta,
    sin suplente" de "todavía sin resolver": son estados distintos."""

    def _texto(self, licencia):
        from django.contrib import admin

        from licencias.admin import LicenciaAdmin
        from licencias.models import Licencia as LicenciaModel

        admin_de = LicenciaAdmin(LicenciaModel, admin.site)
        return str(admin_de.cobertura_resuelta(licencia))

    def test_todos_los_cargos_sin_cobertura_se_lee_como_resuelto(self, institucion, docente, cargo):
        tipo = crear_tipo(institucion)
        hoy = date.today()
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=hoy,
            fecha_fin=hoy,
            estado=EstadoLicencia.APROBADA,
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia,
            cargo=cargo,
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=hoy,
            fecha_fin=hoy,
        )

        texto = self._texto(licencia)

        assert "resuelta" in texto
        assert "faltan" not in texto

    def test_sin_decidir_nada_dice_faltan(self, institucion, docente, cargo):
        tipo = crear_tipo(institucion)
        hoy = date.today()
        licencia = Licencia.objects.create(
            institucion=institucion,
            legajo=docente,
            tipo=tipo,
            fecha_inicio=hoy,
            fecha_fin=hoy,
            estado=EstadoLicencia.APROBADA,
        )

        assert "faltan 1" in self._texto(licencia)
