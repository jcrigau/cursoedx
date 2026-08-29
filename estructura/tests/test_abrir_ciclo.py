"""El año nuevo se arma copiando el anterior, no recargando todo a mano."""

import pytest
from django.core.management import CommandError, call_command

from estructura.models import CicloLectivo, Curso, EstadoCiclo, MateriaPlan, Vigencia


@pytest.fixture
def escuela_2026(db):
    call_command("cargar_piloto", verbosity=0)
    from core.models import Institucion

    return Institucion.objects.get()


class TestAbrirCiclo:
    def test_copia_cursos_periodos_y_plan(self, escuela_2026):
        call_command("abrir_ciclo", 2027, verbosity=0)

        nuevo = CicloLectivo.objects.get(anio=2027)
        viejo = CicloLectivo.objects.get(anio=2026)

        assert nuevo.estado == EstadoCiclo.PLANIFICACION
        assert nuevo.periodos.count() == viejo.periodos.count()
        assert (
            Curso.objects.filter(ciclo_lectivo=nuevo).count()
            == Curso.objects.filter(ciclo_lectivo=viejo).count()
        )
        assert (
            MateriaPlan.objects.filter(curso__ciclo_lectivo=nuevo).count()
            == MateriaPlan.objects.filter(curso__ciclo_lectivo=viejo).count()
        )

    def test_un_plan_cuatrimestral_apunta_al_periodo_nuevo(self, escuela_2026):
        """Si quedara apuntando al cuatrimestre viejo, la materia desaparecería."""
        plan = MateriaPlan.objects.filter(curso__ciclo_lectivo__anio=2026).first()
        periodo_viejo = CicloLectivo.objects.get(anio=2026).periodos.first()
        plan.vigencia = Vigencia.PERIODO
        plan.periodo = periodo_viejo
        plan.save()

        call_command("abrir_ciclo", 2027, verbosity=0)

        copiado = MateriaPlan.objects.get(
            curso__ciclo_lectivo__anio=2027,
            curso__division=plan.curso.division,
            curso__anio_estudio=plan.curso.anio_estudio,
            materia=plan.materia,
        )
        assert copiado.periodo is not None
        assert copiado.periodo.ciclo.anio == 2027
        assert copiado.periodo.orden == periodo_viejo.orden

    def test_no_pisa_un_ciclo_que_ya_existe(self, escuela_2026):
        call_command("abrir_ciclo", 2027, verbosity=0)
        with pytest.raises(CommandError):
            call_command("abrir_ciclo", 2027, verbosity=0)
