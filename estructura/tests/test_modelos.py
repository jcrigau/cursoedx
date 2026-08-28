"""Reglas de la estructura: la grilla y el plan de estudios tienen que ser coherentes.

Los errores que se atajan acá (bloques superpuestos, una materia de otro nivel,
un curso con más horas de plan que de grilla) son los que después harían
imposible generar el horario en la F2.
"""

from datetime import date, time

import pytest
from django.core.exceptions import ValidationError

from estructura.models import (
    BloqueHorario,
    CicloLectivo,
    Curso,
    EsquemaHorario,
    Materia,
    MateriaPlan,
    Nivel,
    PeriodoAcademico,
    TipoBloque,
    TipoNivel,
    Turno,
    Vigencia,
)


@pytest.fixture
def base(institucion, db):
    secundario = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    primario = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.PRIMARIO)
    ciclo = CicloLectivo.objects.create(
        institucion=institucion,
        anio=2026,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 12, 15),
    )
    periodo1 = PeriodoAcademico.objects.create(
        ciclo=ciclo,
        nombre="1er cuatrimestre",
        orden=1,
        fecha_inicio=date(2026, 3, 1),
        fecha_fin=date(2026, 7, 31),
    )
    periodo2 = PeriodoAcademico.objects.create(
        ciclo=ciclo,
        nombre="2do cuatrimestre",
        orden=2,
        fecha_inicio=date(2026, 8, 1),
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
        institucion=institucion, turno=turno, nombre="Sin almuerzo", predeterminado=True
    )
    curso = Curso.objects.create(
        institucion=institucion,
        ciclo_lectivo=ciclo,
        nivel=secundario,
        anio_estudio=3,
        division="A",
        turno=turno,
        esquema_horario=esquema,
    )
    return {
        "institucion": institucion,
        "secundario": secundario,
        "primario": primario,
        "ciclo": ciclo,
        "periodo1": periodo1,
        "periodo2": periodo2,
        "turno": turno,
        "esquema": esquema,
        "curso": curso,
    }


class TestGrillaHoraria:
    def test_duracion_de_una_hora_catedra(self, base):
        bloque = BloqueHorario.objects.create(
            esquema=base["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        assert bloque.duracion_minutos == 40

    def test_duracion_de_una_hora_reloj(self, base):
        # Los preceptores computan horas de 60 minutos, no de 40.
        bloque = BloqueHorario.objects.create(
            esquema=base["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(8, 0),
            hora_fin=time(9, 0),
        )
        assert bloque.duracion_minutos == 60

    def test_rechaza_bloques_superpuestos_el_mismo_dia(self, base):
        BloqueHorario.objects.create(
            esquema=base["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        invasor = BloqueHorario(
            esquema=base["esquema"],
            dia_semana=0,
            orden=2,
            hora_inicio=time(8, 0),
            hora_fin=time(8, 40),
        )
        with pytest.raises(ValidationError):
            invasor.full_clean()

    def test_permite_el_mismo_horario_en_dias_distintos(self, base):
        BloqueHorario.objects.create(
            esquema=base["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        martes = BloqueHorario(
            esquema=base["esquema"],
            dia_semana=1,
            orden=1,
            hora_inicio=time(7, 45),
            hora_fin=time(8, 25),
        )
        martes.full_clean()  # no levanta

    def test_rechaza_fin_anterior_al_inicio(self, base):
        bloque = BloqueHorario(
            esquema=base["esquema"],
            dia_semana=0,
            orden=1,
            hora_inicio=time(9, 0),
            hora_fin=time(8, 0),
        )
        with pytest.raises(ValidationError):
            bloque.full_clean()

    def test_solo_cuenta_como_horas_las_de_clase(self, base):
        for orden, (tipo, inicio, fin) in enumerate(
            [
                (TipoBloque.CLASE, time(7, 45), time(8, 25)),
                (TipoBloque.CLASE, time(8, 25), time(9, 5)),
                (TipoBloque.RECREO, time(9, 5), time(9, 15)),
                (TipoBloque.ALMUERZO, time(13, 0), time(13, 40)),
            ],
            start=1,
        ):
            BloqueHorario.objects.create(
                esquema=base["esquema"],
                dia_semana=0,
                orden=orden,
                tipo=tipo,
                hora_inicio=inicio,
                hora_fin=fin,
            )
        assert base["esquema"].cantidad_horas_semanales == 2


class TestCurso:
    def test_rechaza_un_turno_de_otro_nivel(self, base, institucion):
        turno_primario = Turno.objects.create(
            institucion=institucion,
            nivel=base["primario"],
            nombre="Mañana",
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
        )
        curso = Curso(
            institucion=institucion,
            ciclo_lectivo=base["ciclo"],
            nivel=base["secundario"],
            anio_estudio=1,
            division="B",
            turno=turno_primario,
            esquema_horario=base["esquema"],
        )
        with pytest.raises(ValidationError) as error:
            curso.full_clean()
        assert "turno" in error.value.message_dict

    def test_rechaza_un_esquema_de_otro_turno(self, base, institucion):
        otro_turno = Turno.objects.create(
            institucion=institucion,
            nivel=base["secundario"],
            nombre="Tarde",
            hora_inicio=time(13, 0),
            hora_fin=time(18, 0),
        )
        esquema_tarde = EsquemaHorario.objects.create(
            institucion=institucion, turno=otro_turno, nombre="Tarde"
        )
        curso = Curso(
            institucion=institucion,
            ciclo_lectivo=base["ciclo"],
            nivel=base["secundario"],
            anio_estudio=1,
            division="C",
            turno=base["turno"],
            esquema_horario=esquema_tarde,
        )
        with pytest.raises(ValidationError) as error:
            curso.full_clean()
        assert "esquema_horario" in error.value.message_dict

    def test_nombre_legible(self, base):
        assert str(base["curso"]) == "3°A"


class TestPlanDeEstudios:
    def _materia(self, base, nombre="Matemática", nivel=None):
        return Materia.objects.create(
            institucion=base["institucion"], nivel=nivel or base["secundario"], nombre=nombre
        )

    def test_suma_las_horas_del_plan(self, base):
        MateriaPlan.objects.create(
            curso=base["curso"], materia=self._materia(base), horas_semanales=5
        )
        MateriaPlan.objects.create(
            curso=base["curso"], materia=self._materia(base, "Lengua"), horas_semanales=4
        )
        assert base["curso"].horas_asignadas() == 9

    def test_rechaza_una_materia_de_otro_nivel(self, base):
        ajena = self._materia(base, "Matemática primaria", nivel=base["primario"])
        plan = MateriaPlan(curso=base["curso"], materia=ajena, horas_semanales=4)
        with pytest.raises(ValidationError) as error:
            plan.full_clean()
        assert "materia" in error.value.message_dict

    def test_una_materia_por_periodo_exige_periodo(self, base):
        plan = MateriaPlan(
            curso=base["curso"],
            materia=self._materia(base),
            horas_semanales=4,
            vigencia=Vigencia.PERIODO,
        )
        with pytest.raises(ValidationError) as error:
            plan.full_clean()
        assert "periodo" in error.value.message_dict

    def test_una_materia_anual_no_lleva_periodo(self, base):
        plan = MateriaPlan(
            curso=base["curso"],
            materia=self._materia(base),
            horas_semanales=4,
            vigencia=Vigencia.ANUAL,
            periodo=base["periodo1"],
        )
        with pytest.raises(ValidationError) as error:
            plan.full_clean()
        assert "periodo" in error.value.message_dict

    def test_materias_que_cambian_de_cuatrimestre(self, base):
        """El caso real: una materia en el 1er cuatrimestre y otra en el 2do."""
        primera = MateriaPlan.objects.create(
            curso=base["curso"],
            materia=self._materia(base, "Taller I"),
            horas_semanales=3,
            vigencia=Vigencia.PERIODO,
            periodo=base["periodo1"],
        )
        segunda = MateriaPlan.objects.create(
            curso=base["curso"],
            materia=self._materia(base, "Taller II"),
            horas_semanales=3,
            vigencia=Vigencia.PERIODO,
            periodo=base["periodo2"],
        )
        anual = MateriaPlan.objects.create(
            curso=base["curso"], materia=self._materia(base), horas_semanales=5
        )

        assert primera.rige_en(base["periodo1"]) and not primera.rige_en(base["periodo2"])
        assert segunda.rige_en(base["periodo2"])
        assert anual.rige_en(base["periodo1"]) and anual.rige_en(base["periodo2"])
        # Las horas del cuatrimestre no suman las dos versiones del taller.
        assert base["curso"].horas_asignadas(base["periodo1"]) == 8

    def test_periodo_de_otro_ciclo(self, base, institucion):
        otro_ciclo = CicloLectivo.objects.create(
            institucion=institucion,
            anio=2027,
            fecha_inicio=date(2027, 3, 1),
            fecha_fin=date(2027, 12, 15),
        )
        periodo_ajeno = PeriodoAcademico.objects.create(
            ciclo=otro_ciclo,
            nombre="1er cuatrimestre",
            orden=1,
            fecha_inicio=date(2027, 3, 1),
            fecha_fin=date(2027, 7, 31),
        )
        plan = MateriaPlan(
            curso=base["curso"],
            materia=self._materia(base),
            horas_semanales=4,
            vigencia=Vigencia.PERIODO,
            periodo=periodo_ajeno,
        )
        with pytest.raises(ValidationError) as error:
            plan.full_clean()
        assert "periodo" in error.value.message_dict


class TestCicloLectivo:
    def test_rechaza_fechas_invertidas(self, institucion):
        ciclo = CicloLectivo(
            institucion=institucion,
            anio=2026,
            fecha_inicio=date(2026, 12, 1),
            fecha_fin=date(2026, 3, 1),
        )
        with pytest.raises(ValidationError):
            ciclo.full_clean()

    def test_el_periodo_reconoce_sus_fechas(self, base):
        assert base["periodo1"].incluye(date(2026, 5, 20))
        assert not base["periodo1"].incluye(date(2026, 9, 20))
