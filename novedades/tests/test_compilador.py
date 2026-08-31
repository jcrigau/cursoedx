"""Compilación de las novedades del mes.

Lo que más importa acá es el ruteo: cada línea tiene que ir a la planilla del
cargo que la originó. Un error de ruteo se traduce en un sueldo mal liquidado.
"""

from datetime import date, time, timedelta

import pytest

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from legajos.models import FuentePago, Legajo, MotivoBaja
from licencias.models import Cobertura, TipoCobertura
from novedades.compilador import SIN_REEMPLAZO, compilar
from novedades.models import Destino, Novedad, Origen, TipoNovedad

from .conftest import ANIO, MES, dar_cargo, dar_licencia, dar_materia


class TestAltasYBajas:
    def test_un_alta_del_mes_genera_novedad(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), horas=5, nivel=nivel)
        compilar(periodo)

        novedad = periodo.novedades.get()
        assert novedad.tipo == TipoNovedad.ALTA
        assert novedad.fecha == date(ANIO, MES, 4)
        assert novedad.horas == 5

    def test_el_alta_incluye_los_datos_que_pide_el_liquidador(
        self, institucion, periodo, docente, nivel
    ):
        """CUIL, obra social y antigüedad: hoy se tipean a mano en observaciones."""
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)

        observaciones = periodo.novedades.get().observaciones
        assert docente.cuil in observaciones
        assert "OSDE" in observaciones
        assert "Antigüedad" in observaciones
        assert "Titular" in observaciones

    def test_una_baja_por_renuncia_se_distingue_del_cese(
        self, institucion, periodo, docente, nivel
    ):
        dar_cargo(
            institucion,
            docente,
            alta=date(2024, 3, 1),
            baja=date(ANIO, MES, 20),
            motivo_baja=MotivoBaja.RENUNCIA,
            nivel=nivel,
        )
        otro = Legajo.objects.create(
            institucion=institucion, apellido="Paz", nombre="Ana", cuil="27-31456789-3"
        )
        dar_cargo(
            institucion,
            otro,
            alta=date(2024, 3, 1),
            baja=date(ANIO, MES, 22),
            motivo_baja=MotivoBaja.CESE,
            nivel=nivel,
        )
        compilar(periodo)

        tipos = set(periodo.novedades.values_list("tipo", flat=True))
        assert tipos == {TipoNovedad.RENUNCIA, TipoNovedad.CESE}

    def test_un_cargo_de_otro_mes_no_aparece(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, alta=date(ANIO, 3, 1), nivel=nivel)
        compilar(periodo)
        assert periodo.novedades.count() == 0

    def test_una_designacion_a_termino_marca_tiempo_determinado(
        self, institucion, periodo, docente, nivel
    ):
        dar_cargo(
            institucion,
            docente,
            alta=date(ANIO, MES, 4),
            baja=date(ANIO, MES, 30),
            motivo_baja=MotivoBaja.FIN_SUPLENCIA,
            nivel=nivel,
        )
        compilar(periodo)

        alta = periodo.novedades.get(tipo=TipoNovedad.ALTA)
        assert alta.tiempo_determinado
        assert alta.fecha_fin == date(ANIO, MES, 30)


class TestRuteoAPlanillas:
    def test_un_cargo_del_estado_va_a_la_oficial(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        assert periodo.novedades.get().destino == Destino.OFICIAL

    def test_un_cargo_de_la_escuela_va_a_la_interna(self, institucion, periodo, docente, nivel):
        dar_cargo(
            institucion, docente, alta=date(ANIO, MES, 4), fuente=FuentePago.INTERNO, nivel=nivel
        )
        compilar(periodo)
        assert periodo.novedades.get().destino == Destino.INTERNA

    def test_el_personal_mixto_genera_una_linea_por_planilla(
        self, institucion, periodo, docente, nivel
    ):
        """El caso que hoy se rutea a mano y se equivoca."""
        matematica = dar_materia(institucion, nivel, "Matemática")
        taller = dar_materia(institucion, nivel, "Taller")
        dar_cargo(institucion, docente, materia=matematica, horas=5, nivel=nivel)
        dar_cargo(
            institucion,
            docente,
            materia=taller,
            horas=2,
            fuente=FuentePago.INTERNO,
            nivel=nivel,
        )
        dar_licencia(institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 6), con_goce=False)

        compilar(periodo)

        destinos = sorted(periodo.novedades.values_list("destino", flat=True))
        assert destinos == [Destino.INTERNA, Destino.OFICIAL]
        # Cada línea lleva su propio espacio curricular.
        espacios = set(periodo.novedades.values_list("espacio", flat=True))
        assert espacios == {"Matemática", "Taller"}


class TestLicencias:
    def test_cuenta_solo_los_dias_del_mes(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, nivel=nivel)
        # Del 25 de abril al 5 de mayo: en mayo son 5 días.
        dar_licencia(institucion, docente, date(ANIO, 4, 25), date(ANIO, MES, 5), con_goce=False)
        compilar(periodo)

        novedad = periodo.novedades.get()
        assert novedad.dias == 5
        assert novedad.fecha == date(ANIO, MES, 1)  # se recorta al inicio del mes

    def test_la_licencia_con_goce_no_se_informa(self, institucion, periodo, docente, nivel):
        """Regla del liquidador: solo lo que genera descuento o pago adicional."""
        dar_cargo(institucion, docente, nivel=nivel)
        dar_licencia(institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 6), con_goce=True)
        compilar(periodo)

        novedad = periodo.novedades.get()
        assert not novedad.impacta_haberes
        assert periodo.resumen()["a_informar"] == 0

    def test_la_licencia_sin_goce_si_se_informa(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, nivel=nivel)
        dar_licencia(
            institucion,
            docente,
            date(ANIO, MES, 4),
            date(ANIO, MES, 6),
            nombre="Sin goce",
            con_goce=False,
        )
        compilar(periodo)
        assert periodo.resumen()["a_informar"] == 1

    def test_una_licencia_pendiente_no_se_compila(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, nivel=nivel)
        dar_licencia(
            institucion,
            docente,
            date(ANIO, MES, 4),
            date(ANIO, MES, 6),
            con_goce=False,
            aprobada=False,
        )
        compilar(periodo)
        assert periodo.novedades.count() == 0

    def test_informa_quien_cubre(self, institucion, periodo, docente, nivel):
        cargo = dar_cargo(institucion, docente, nivel=nivel)
        licencia = dar_licencia(
            institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 20), con_goce=False
        )
        suplente = Legajo.objects.create(
            institucion=institucion, apellido="Vega", nombre="Julieta", cuil="27-38999111-2"
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia,
            cargo=cargo,
            tipo=TipoCobertura.SUPLENTE,
            suplente=suplente,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )
        compilar(periodo)
        assert periodo.novedades.get().reemplazante == "Vega, Julieta"

    def test_deja_constancia_de_que_no_hubo_reemplazo(self, institucion, periodo, docente, nivel):
        cargo = dar_cargo(institucion, docente, nivel=nivel)
        licencia = dar_licencia(
            institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 6), con_goce=False
        )
        Cobertura.objects.create(
            institucion=institucion,
            licencia=licencia,
            cargo=cargo,
            tipo=TipoCobertura.SIN_COBERTURA,
            fecha_inicio=licencia.fecha_inicio,
            fecha_fin=licencia.fecha_fin,
        )
        compilar(periodo)
        assert periodo.novedades.get().reemplazante == SIN_REEMPLAZO

    def test_avisa_si_no_se_puede_rutear(self, institucion, periodo, docente):
        """Sin cargos vigentes no hay planilla a la cual informar."""
        dar_licencia(institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 6), con_goce=False)
        resultado = compilar(periodo)
        assert periodo.novedades.count() == 0
        assert any("qué planilla" in aviso for aviso in resultado.avisos)


class TestAsistencia:
    def test_una_inasistencia_injustificada_se_informa(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, nivel=nivel)
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.AUSENTE,
        )
        compilar(periodo)

        novedad = periodo.novedades.get()
        assert novedad.tipo == TipoNovedad.INASISTENCIA
        assert novedad.dias == 1

    def test_una_falta_se_informa_una_vez_por_planilla(self, institucion, periodo, docente, nivel):
        """Tres cargos de la misma planilla no son tres descuentos: es un día."""
        for numero in range(3):
            dar_cargo(institucion, docente, nivel=nivel, horas=5, denominacion=f"Cargo {numero}")
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.AUSENTE,
        )

        compilar(periodo)

        novedad = periodo.novedades.get()  # una sola
        assert novedad.dias == 1
        # Y sin horas: la planilla toma las horas si están, y las semanales del
        # cargo no tienen nada que ver con lo que faltó ese día.
        assert novedad.horas is None

    def test_las_horas_de_una_ausencia_parcial_no_se_multiplican(
        self, institucion, periodo, docente, nivel
    ):
        """El error que se veía en pantalla: 2 horas informadas tres veces."""
        for numero in range(3):
            dar_cargo(institucion, docente, nivel=nivel, horas=5, denominacion=f"Cargo {numero}")
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.PARCIAL,
            horas_afectadas=2,
        )

        compilar(periodo)

        novedades = list(periodo.novedades.all())
        assert len(novedades) == 1
        assert novedades[0].horas == 2
        assert sum(novedad.horas or 0 for novedad in novedades) == 2

    def test_cargos_de_distinta_fuente_sí_generan_dos_lineas(
        self, institucion, periodo, docente, nivel
    ):
        """Son dos planillas distintas: ahí la separación es correcta."""
        dar_cargo(institucion, docente, nivel=nivel, fuente=FuentePago.SUBVENCIONADO, horas=5)
        dar_cargo(institucion, docente, nivel=nivel, fuente=FuentePago.INTERNO, horas=3)
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.AUSENTE,
        )

        compilar(periodo)

        destinos = {novedad.destino for novedad in periodo.novedades.all()}
        assert len(destinos) == 2

    def test_una_ausencia_parcial_mixta_no_se_duplica_y_se_avisa(
        self, institucion, periodo, docente, nivel
    ):
        """El error real: 2 horas parciales de alguien "mixto" salían como 4.

        Acá, a diferencia del día entero, "horas" es de un cargo puntual y el
        parte diario no dice de cuál: repartirlas es inventar el dato, así que
        no se genera ninguna línea automática y se avisa para cargarla a mano.
        """
        dar_cargo(institucion, docente, nivel=nivel, fuente=FuentePago.SUBVENCIONADO, horas=5)
        dar_cargo(institucion, docente, nivel=nivel, fuente=FuentePago.INTERNO, horas=3)
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.PARCIAL,
            horas_afectadas=2,
        )

        resultado = compilar(periodo)

        assert periodo.novedades.filter(tipo=TipoNovedad.INASISTENCIA).count() == 0
        assert any("las dos fuentes" in aviso for aviso in resultado.avisos)

    def test_recompilar_limpia_las_lineas_que_ya_no_corresponden(
        self, institucion, periodo, docente, nivel
    ):
        """Al anular el hecho, su novedad automática se va."""
        dar_cargo(institucion, docente, nivel=nivel, horas=5)
        registro = RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.AUSENTE,
        )
        compilar(periodo)
        assert periodo.novedades.count() == 1

        registro.delete()  # se corrigió: no había faltado
        resultado = compilar(periodo)

        assert periodo.novedades.count() == 0
        assert resultado.eliminadas == 1

    def test_no_borra_lo_cargado_a_mano(self, institucion, periodo, docente, nivel):
        from novedades.models import Novedad, Origen, TipoNovedad

        cargo = dar_cargo(institucion, docente, nivel=nivel, horas=5)
        Novedad.objects.create(
            institucion=institucion,
            periodo=periodo,
            legajo=docente,
            cargo=cargo,
            tipo=TipoNovedad.OTRA,
            fecha=date(ANIO, MES, 7),
            origen=Origen.MANUAL,
            motivo="Cargada a mano",
        )

        compilar(periodo)

        assert periodo.novedades.filter(origen=Origen.MANUAL).count() == 1

    def test_una_ausencia_justificada_no_genera_inasistencia(
        self, institucion, periodo, docente, nivel
    ):
        dar_cargo(institucion, docente, nivel=nivel)
        licencia = dar_licencia(
            institucion, docente, date(ANIO, MES, 6), date(ANIO, MES, 6), con_goce=True
        )
        RegistroAsistencia.objects.create(
            institucion=institucion,
            legajo=docente,
            fecha=date(ANIO, MES, 6),
            estado=EstadoAsistencia.AUSENTE,
            licencia=licencia,
        )
        compilar(periodo)
        assert not periodo.novedades.filter(tipo=TipoNovedad.INASISTENCIA).exists()

    def test_las_tardanzas_se_informan_agrupadas(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, nivel=nivel)
        for dia in (5, 12, 19):
            RegistroAsistencia.objects.create(
                institucion=institucion,
                legajo=docente,
                fecha=date(ANIO, MES, dia),
                estado=EstadoAsistencia.TARDE,
                hora=time(8, 20),
            )
        compilar(periodo)

        novedad = periodo.novedades.get(tipo=TipoNovedad.TARDANZA)
        assert novedad.dias == 3
        assert "3 llegadas tarde" in novedad.motivo


class TestRecompilacion:
    def test_no_duplica_al_volver_a_compilar(self, institucion, periodo, docente, nivel):
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        resultado = compilar(periodo)

        assert periodo.novedades.count() == 1
        assert resultado.creadas == 0
        assert resultado.actualizadas == 1

    def test_conserva_lo_que_ya_se_informo(self, institucion, periodo, docente, nivel, secretaria):
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        novedad = periodo.novedades.get()
        novedad.marcar_informada(usuario=secretaria)

        compilar(periodo)

        novedad.refresh_from_db()
        assert novedad.informada
        assert novedad.informada_por == secretaria

    def test_no_pisa_las_novedades_cargadas_a_mano(self, institucion, periodo, docente, nivel):
        cargo = dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        manual = Novedad.objects.create(
            institucion=institucion,
            periodo=periodo,
            legajo=docente,
            cargo=cargo,
            tipo=TipoNovedad.OTRA,
            destino=Destino.OFICIAL,
            fecha=date(ANIO, MES, 10),
            motivo="Pago adicional acordado",
            origen=Origen.MANUAL,
        )
        compilar(periodo)

        manual.refresh_from_db()
        assert manual.motivo == "Pago adicional acordado"
        assert manual.origen == Origen.MANUAL
        assert periodo.novedades.count() == 2

    def test_refleja_una_correccion_posterior(self, institucion, periodo, docente, nivel):
        cargo = dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), horas=5, nivel=nivel)
        compilar(periodo)

        cargo.horas_semanales = 8
        cargo.save()
        compilar(periodo)

        assert periodo.novedades.get().horas == 8


class TestCierre:
    def test_cerrar_congela_las_novedades(self, institucion, periodo, docente, nivel, secretaria):
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        periodo.cerrar(usuario=secretaria)

        novedad = periodo.novedades.get()
        assert novedad.congelada
        assert periodo.esta_cerrado
        assert periodo.cerrado_por == secretaria

    def test_una_novedad_congelada_no_se_modifica(
        self, institucion, periodo, docente, nivel, secretaria
    ):
        from django.core.exceptions import ValidationError

        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        periodo.cerrar(usuario=secretaria)

        novedad = periodo.novedades.get()
        novedad.dias = 99
        with pytest.raises(ValidationError):
            novedad.save(update_fields=["dias"])

    def test_se_puede_marcar_informada_con_el_periodo_cerrado(
        self, institucion, periodo, docente, nivel, secretaria
    ):
        """Marcar el traspaso no cambia el dato liquidado."""
        dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
        compilar(periodo)
        periodo.cerrar(usuario=secretaria)

        novedad = periodo.novedades.get()
        novedad.marcar_informada(usuario=secretaria)
        assert novedad.informada

    def test_no_se_compila_un_periodo_cerrado(
        self, institucion, periodo, docente, nivel, secretaria
    ):
        periodo.cerrar(usuario=secretaria)
        resultado = compilar(periodo)
        assert resultado.total == 0
        assert any("cerrado" in aviso for aviso in resultado.avisos)

    def test_la_reapertura_queda_auditada(self, institucion, periodo, secretaria):
        from core.models import RegistroAuditoria

        periodo.cerrar(usuario=secretaria)
        periodo.reabrir("Faltaba cargar una licencia", usuario=secretaria)

        assert periodo.editable
        registro = RegistroAuditoria.objects.filter(accion="REAPERTURA_PERIODO").first()
        assert registro is not None
        assert "Faltaba cargar" in registro.descripcion

    def test_el_cierre_queda_auditado(self, institucion, periodo, secretaria):
        from core.models import RegistroAuditoria

        periodo.cerrar(usuario=secretaria)
        registro = RegistroAuditoria.objects.filter(accion="CIERRE_PERIODO").first()
        assert registro is not None
        assert registro.usuario == secretaria


class TestResumen:
    def test_cuenta_por_planilla_y_pendientes(
        self, institucion, periodo, docente, nivel, secretaria
    ):
        matematica = dar_materia(institucion, nivel, "Matemática")
        dar_cargo(
            institucion, docente, alta=date(ANIO, MES, 4), materia=matematica, horas=5, nivel=nivel
        )
        otro = Legajo.objects.create(
            institucion=institucion, apellido="Paz", nombre="Ana", cuil="27-31456789-3"
        )
        dar_cargo(
            institucion,
            otro,
            alta=date(ANIO, MES, 5),
            fuente=FuentePago.INTERNO,
            nivel=nivel,
        )
        compilar(periodo)

        resumen = periodo.resumen()
        assert resumen["a_informar"] == 2
        assert resumen["oficial"] == 1
        assert resumen["interna"] == 1
        assert resumen["pendientes"] == 2

        periodo.novedades.first().marcar_informada(usuario=secretaria)
        assert periodo.resumen()["informadas"] == 1


@pytest.mark.django_db
def test_no_mezcla_instituciones(institucion, otra_institucion, periodo, docente, nivel):
    """Una novedad de otra escuela no puede colarse en este período."""
    dar_cargo(institucion, docente, alta=date(ANIO, MES, 4), nivel=nivel)
    ajeno = Legajo.objects.create(
        institucion=otra_institucion, apellido="Ajeno", nombre="Juan", cuil="20-30111222-3"
    )
    dar_cargo(otra_institucion, ajeno, alta=date(ANIO, MES, 4))

    compilar(periodo)

    assert periodo.novedades.count() == 1
    assert periodo.novedades.get().legajo == docente


@pytest.mark.django_db
def test_el_alta_del_suplente_sale_sola(institucion, periodo, docente, nivel, secretaria):
    """Al designar un suplente, su alta aparece en la planilla correcta.

    Es la cadena completa: licencia → cobertura → cargo del suplente → novedad.
    """
    cargo = dar_cargo(institucion, docente, fuente=FuentePago.INTERNO, nivel=nivel, horas=4)
    licencia = dar_licencia(
        institucion, docente, date(ANIO, MES, 4), date(ANIO, MES, 20), con_goce=False
    )
    suplente = Legajo.objects.create(
        institucion=institucion, apellido="Vega", nombre="Julieta", cuil="27-38999111-2"
    )
    cobertura = Cobertura.objects.create(
        institucion=institucion,
        licencia=licencia,
        cargo=cargo,
        tipo=TipoCobertura.SUPLENTE,
        suplente=suplente,
        fecha_inicio=licencia.fecha_inicio,
        fecha_fin=licencia.fecha_fin,
    )
    cobertura.designar_cargo_del_suplente()

    compilar(periodo)

    alta = periodo.novedades.get(legajo=suplente, tipo=TipoNovedad.ALTA)
    # Hereda la planilla del cargo que cubre, no la del suplente.
    assert alta.destino == Destino.INTERNA
    assert alta.tiempo_determinado
    assert "Suplencia de" in alta.observaciones

    cese = periodo.novedades.filter(legajo=suplente, tipo=TipoNovedad.CESE).first()
    assert cese is not None
    assert cese.fecha == licencia.fecha_fin + timedelta(days=0)
