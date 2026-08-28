"""Reglas de los legajos, cargos y documentación."""

from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError

from estructura.models import CicloLectivo, Curso, EsquemaHorario, Materia, Nivel, TipoNivel, Turno
from legajos.models import (
    Cargo,
    DocumentoLegajo,
    FuentePago,
    Legajo,
    MotivoBaja,
    SituacionRevista,
    TipoCargo,
    TipoDocumento,
)


@pytest.fixture
def escuela(institucion, db):
    """Estructura mínima para poder designar horas cátedra en un curso."""
    secundario = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    primario = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.PRIMARIO)
    ciclo = CicloLectivo.objects.create(
        institucion=institucion,
        anio=2026,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 15),
    )
    turno = Turno.objects.create(
        institucion=institucion,
        nivel=secundario,
        nombre="Mañana",
        hora_inicio=time(7, 45),
        hora_fin=time(13, 0),
    )
    esquema = EsquemaHorario.objects.create(
        institucion=institucion, turno=turno, nombre="Sin almuerzo"
    )
    curso = Curso.objects.create(
        institucion=institucion,
        ciclo_lectivo=ciclo,
        nivel=secundario,
        anio_estudio=1,
        division="A",
        turno=turno,
        esquema_horario=esquema,
    )
    matematica = Materia.objects.create(
        institucion=institucion, nivel=secundario, nombre="Matemática"
    )
    materia_primaria = Materia.objects.create(
        institucion=institucion, nivel=primario, nombre="Ciencias"
    )
    legajo = Legajo.objects.create(
        institucion=institucion, apellido="Suárez", nombre="Paula", cuil="27-31234567-8"
    )
    return {
        "institucion": institucion,
        "secundario": secundario,
        "primario": primario,
        "curso": curso,
        "matematica": matematica,
        "materia_primaria": materia_primaria,
        "legajo": legajo,
    }


def cargo_base(escuela, **extra):
    datos = {
        "institucion": escuela["institucion"],
        "legajo": escuela["legajo"],
        "tipo": TipoCargo.HORAS_CATEDRA,
        "materia": escuela["matematica"],
        "horas_semanales": 5,
        "situacion_revista": SituacionRevista.TITULAR,
        "fuente_pago": FuentePago.SUBVENCIONADO,
        "fecha_alta": date(2024, 3, 1),
    }
    datos.update(extra)
    return Cargo(**datos)


class TestCargo:
    def test_horas_catedra_exigen_materia(self, escuela):
        cargo = cargo_base(escuela, materia=None)
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "materia" in error.value.message_dict

    def test_horas_catedra_exigen_horas(self, escuela):
        cargo = cargo_base(escuela, horas_semanales=None)
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "horas_semanales" in error.value.message_dict

    def test_cargo_de_jornada_exige_denominacion(self, escuela):
        cargo = cargo_base(escuela, tipo=TipoCargo.CARGO_BASE, materia=None, horas_semanales=None)
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "denominacion" in error.value.message_dict

    def test_preceptor_con_horas_reloj(self, escuela):
        cargo = cargo_base(
            escuela,
            tipo=TipoCargo.HORAS_RELOJ,
            materia=None,
            denominacion="Preceptor/a",
            horas_semanales=25,
        )
        cargo.full_clean()  # no levanta

    def test_curso_y_materia_de_niveles_distintos(self, escuela):
        cargo = cargo_base(escuela, materia=escuela["materia_primaria"], curso=escuela["curso"])
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "curso" in error.value.message_dict

    def test_baja_anterior_al_alta(self, escuela):
        cargo = cargo_base(escuela, fecha_baja=date(2023, 1, 1), motivo_baja=MotivoBaja.CESE)
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "fecha_baja" in error.value.message_dict

    def test_la_baja_exige_motivo(self, escuela):
        cargo = cargo_base(escuela, fecha_baja=date(2025, 1, 1))
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "motivo_baja" in error.value.message_dict

    def test_el_motivo_exige_fecha(self, escuela):
        cargo = cargo_base(escuela, motivo_baja=MotivoBaja.RENUNCIA)
        with pytest.raises(ValidationError) as error:
            cargo.full_clean()
        assert "fecha_baja" in error.value.message_dict

    def test_descripcion_con_curso(self, escuela):
        cargo = cargo_base(escuela, curso=escuela["curso"])
        assert cargo.descripcion == "Matemática · 1°A"

    def test_descripcion_de_cargo_sin_materia(self, escuela):
        cargo = cargo_base(
            escuela,
            tipo=TipoCargo.CARGO_BASE,
            materia=None,
            horas_semanales=None,
            denominacion="Secretaria",
        )
        assert cargo.descripcion == "Secretaria"

    def test_vigencia_por_fecha(self, escuela):
        cargo = cargo_base(escuela, fecha_baja=date(2024, 12, 31), motivo_baja=MotivoBaja.CESE)
        assert cargo.vigente_en(date(2024, 6, 1))
        assert cargo.vigente_en(date(2024, 12, 31))  # el último día todavía cuenta
        assert not cargo.vigente_en(date(2025, 1, 1))
        assert not cargo.vigente_en(date(2024, 1, 1))

    def test_la_fuente_de_pago_define_el_destino(self, escuela):
        subvencionado = cargo_base(escuela)
        interno = cargo_base(escuela, fuente_pago=FuentePago.INTERNO)
        assert subvencionado.es_subvencionado
        assert not interno.es_subvencionado


class TestLegajo:
    def test_horas_catedra_vigentes(self, escuela):
        cargo_base(escuela, horas_semanales=5).save()
        cargo_base(escuela, horas_semanales=3, curso=escuela["curso"]).save()
        # Una baja vieja no suma.
        cargo_base(
            escuela,
            horas_semanales=10,
            fecha_baja=date(2024, 6, 30),
            motivo_baja=MotivoBaja.CESE,
        ).save()
        assert escuela["legajo"].horas_catedra_vigentes == 8

    def test_el_mismo_cuil_puede_existir_en_otra_escuela(self, escuela, otra_institucion):
        """Un docente trabaja en dos escuelas: cada una lleva su propio legajo."""
        Legajo.objects.create(
            institucion=otra_institucion,
            apellido="Suárez",
            nombre="Paula",
            cuil=escuela["legajo"].cuil,
        )
        assert Legajo.objects.filter(cuil=escuela["legajo"].cuil).count() == 2

    def test_nombre_completo(self, escuela):
        assert escuela["legajo"].nombre_completo == "Suárez, Paula"


class TestDocumentacion:
    @pytest.fixture
    def tipo_apto(self, institucion):
        return TipoDocumento.objects.create(
            institucion=institucion, nombre="Apto psicofísico", dias_preaviso=30
        )

    def test_documento_vencido(self, escuela, tipo_apto):
        documento = DocumentoLegajo.objects.create(
            legajo=escuela["legajo"],
            tipo=tipo_apto,
            fecha_vencimiento=date.today() - timedelta(days=5),
        )
        assert documento.esta_vencido
        assert not documento.por_vencer
        assert documento.dias_para_vencer() == -5

    def test_documento_por_vencer_dentro_del_preaviso(self, escuela, tipo_apto):
        documento = DocumentoLegajo.objects.create(
            legajo=escuela["legajo"],
            tipo=tipo_apto,
            fecha_vencimiento=date.today() + timedelta(days=10),
        )
        assert documento.por_vencer
        assert not documento.esta_vencido

    def test_documento_lejano_no_alerta(self, escuela, tipo_apto):
        documento = DocumentoLegajo.objects.create(
            legajo=escuela["legajo"],
            tipo=tipo_apto,
            fecha_vencimiento=date.today() + timedelta(days=200),
        )
        assert not documento.por_vencer
        assert not documento.esta_vencido

    def test_documento_sin_vencimiento(self, escuela, tipo_apto):
        documento = DocumentoLegajo.objects.create(legajo=escuela["legajo"], tipo=tipo_apto)
        assert documento.dias_para_vencer() is None
        assert not documento.esta_vencido
        assert not documento.por_vencer

    def test_vencimiento_anterior_a_la_emision(self, escuela, tipo_apto):
        documento = DocumentoLegajo(
            legajo=escuela["legajo"],
            tipo=tipo_apto,
            fecha_emision=date(2025, 6, 1),
            fecha_vencimiento=date(2025, 1, 1),
        )
        with pytest.raises(ValidationError) as error:
            documento.full_clean()
        assert "fecha_vencimiento" in error.value.message_dict
