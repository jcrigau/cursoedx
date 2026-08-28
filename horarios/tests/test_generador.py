"""El generador: que cumpla lo obligatorio y que optimice lo que se le pide."""

from datetime import time

from horarios.generador import Parametros, generar, recolectar, revisar_factibilidad
from horarios.models import (
    AsignacionHoraria,
    DeclaracionDisponibilidad,
    FranjaNoDisponible,
    se_superponen,
)

from .conftest import (
    crear_curso,
    crear_docente,
    crear_esquema,
    crear_materia,
    crear_plan,
    crear_version,
    designar,
)

RAPIDO = Parametros(segundos_limite=5)


def hay_choque_de_docente(version) -> bool:
    asignaciones = list(version.asignaciones.exclude(legajo=None))
    for i, una in enumerate(asignaciones):
        for otra in asignaciones[i + 1 :]:
            if una.legajo_id != otra.legajo_id or una.dia_semana != otra.dia_semana:
                continue
            if se_superponen(una.hora_inicio, una.hora_fin, otra.hora_inicio, otra.hora_fin):
                return True
    return False


class TestReglasObligatorias:
    def test_ubica_todas_las_horas_del_plan(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        matematica = crear_materia(escuela, "Matemática")
        lengua = crear_materia(escuela, "Lengua")
        crear_plan(curso, matematica, 4)
        crear_plan(curso, lengua, 3)
        designar(escuela, crear_docente(escuela, "Pérez", 1), matematica, curso)
        designar(escuela, crear_docente(escuela, "Gómez", 2), lengua, curso)

        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)

        assert resultado.exito, resultado.problemas
        assert version.asignaciones.filter(materia=matematica).count() == 4
        assert version.asignaciones.filter(materia=lengua).count() == 3

    def test_el_curso_no_tiene_dos_materias_a_la_vez(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        for numero in range(3):
            materia = crear_materia(escuela, f"Materia {numero}")
            crear_plan(curso, materia, 3)
            designar(escuela, crear_docente(escuela, f"Doc{numero}", numero), materia, curso)

        version = crear_version(escuela)
        assert generar(version, RAPIDO).exito

        ocupados = [(a.dia_semana, a.hora_inicio) for a in version.asignaciones.filter(curso=curso)]
        assert len(ocupados) == len(set(ocupados))

    def test_un_docente_no_queda_en_dos_cursos_a_la_vez(self, escuela):
        """El caso delicado: dos cursos con esquemas distintos.

        Sus bloques son filas diferentes en la base, pero caen a la misma hora
        del reloj. Si los choques se detectaran por bloque, el docente quedaría
        partido en dos.
        """
        esquema_a = crear_esquema(escuela, "Sin almuerzo")
        esquema_b = crear_esquema(escuela, "Con almuerzo")
        curso_a = crear_curso(escuela, esquema_a, anio=1, division="A")
        curso_b = crear_curso(escuela, esquema_b, anio=2, division="B")

        matematica = crear_materia(escuela, "Matemática")
        crear_plan(curso_a, matematica, 4)
        crear_plan(curso_b, matematica, 4)
        docente = crear_docente(escuela, "Única", 1)
        designar(escuela, docente, matematica)  # sin curso: cubre los dos

        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)

        assert resultado.exito, resultado.problemas
        assert version.asignaciones.filter(legajo=docente).count() == 8
        assert not hay_choque_de_docente(version)

    def test_respeta_la_declaracion_de_disponibilidad(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
        curso = crear_curso(escuela, esquema)
        matematica = crear_materia(escuela, "Matemática")
        crear_plan(curso, matematica, 4)
        docente = crear_docente(escuela, "Ocupada", 1)
        designar(escuela, docente, matematica, curso)

        # El lunes trabaja en otra escuela toda la mañana.
        declaracion = DeclaracionDisponibilidad.objects.create(
            institucion=escuela["institucion"], legajo=docente, periodo=escuela["periodo"]
        )
        FranjaNoDisponible.objects.create(
            declaracion=declaracion, dia_semana=0, hora_desde=time(7, 0), hora_hasta=time(13, 0)
        )

        version = crear_version(escuela)
        assert generar(version, RAPIDO).exito
        assert not version.asignaciones.filter(legajo=docente, dia_semana=0).exists()

    def test_no_supera_el_maximo_de_horas_diarias_por_materia(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
        curso = crear_curso(escuela, esquema)
        matematica = crear_materia(escuela, "Matemática")
        crear_plan(curso, matematica, 6)
        designar(escuela, crear_docente(escuela, "Pérez", 1), matematica, curso)

        version = crear_version(escuela)
        assert generar(version, Parametros(max_horas_dia_materia=2, segundos_limite=5)).exito

        por_dia = {}
        for asignacion in version.asignaciones.all():
            por_dia[asignacion.dia_semana] = por_dia.get(asignacion.dia_semana, 0) + 1
        assert max(por_dia.values()) <= 2


class TestObjetivos:
    def test_agrupa_las_horas_en_pocos_dias(self, escuela):
        """Lo que pidió la escuela: que el docente venga lo menos posible.

        Con 4 horas y una grilla de 4 horas por día en 3 días, el horario debe
        resolverse en un solo día en vez de repartirse.
        """
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
        curso = crear_curso(escuela, esquema)
        matematica = crear_materia(escuela, "Matemática")
        crear_plan(curso, matematica, 4)
        docente = crear_docente(escuela, "Viajera", 1)
        designar(escuela, docente, matematica, curso)

        version = crear_version(escuela)
        # Sin tope diario, para que pueda concentrar todo el mismo día.
        assert generar(version, Parametros(max_horas_dia_materia=4, segundos_limite=10)).exito

        dias = {a.dia_semana for a in version.asignaciones.filter(legajo=docente)}
        assert len(dias) == 1

    def test_informa_cuantos_dias_viene_cada_docente(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Historia")
        crear_plan(curso, materia, 3)
        docente = crear_docente(escuela, "Suárez", 1)
        designar(escuela, docente, materia, curso)

        version = crear_version(escuela)
        generar(version, RAPIDO)

        assert version.resumen["docentes"] == 1
        assert version.dias_por_docente()[docente] >= 1


class TestAsignacionesBloqueadas:
    def test_conserva_lo_que_la_secretaria_dejo_fijo(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=3)
        curso = crear_curso(escuela, esquema)
        matematica = crear_materia(escuela, "Matemática")
        crear_plan(curso, matematica, 2)
        docente = crear_docente(escuela, "Fija", 1)
        cargo = designar(escuela, docente, matematica, curso)

        version = crear_version(escuela)
        bloque = esquema.bloques.filter(dia_semana=2).order_by("hora_inicio").last()
        fija = AsignacionHoraria.objects.create(
            version=version,
            curso=curso,
            bloque=bloque,
            materia=matematica,
            cargo=cargo,
            bloqueada=True,
        )

        assert generar(version, RAPIDO).exito
        assert AsignacionHoraria.objects.filter(pk=fija.pk).exists()
        assert version.asignaciones.filter(materia=matematica).count() == 2


class TestControlesPrevios:
    def test_avisa_si_el_plan_no_entra_en_la_grilla(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=2, dias=2)  # 4 horas
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 6)
        designar(escuela, crear_docente(escuela, "Pérez", 1), materia, curso)

        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)

        assert not resultado.exito
        assert resultado.estado == "INVIABLE"
        assert any("ofrece 4" in problema for problema in resultado.problemas)

    def test_avisa_si_la_materia_no_entra_con_el_tope_diario(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=2)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 5)  # 2 días × 2 horas = 4 como máximo
        designar(escuela, crear_docente(escuela, "Pérez", 1), materia, curso)

        version = crear_version(escuela)
        resultado = generar(version, Parametros(max_horas_dia_materia=2, segundos_limite=5))

        assert not resultado.exito
        assert any("solo entran" in problema for problema in resultado.problemas)

    def test_avisa_cuando_la_ddjj_deja_sin_lugar(self, escuela):
        esquema = crear_esquema(escuela, horas_por_dia=4, dias=2)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 6)
        docente = crear_docente(escuela, "Sin lugar", 1)
        designar(escuela, docente, materia, curso)

        declaracion = DeclaracionDisponibilidad.objects.create(
            institucion=escuela["institucion"], legajo=docente, periodo=escuela["periodo"]
        )
        FranjaNoDisponible.objects.create(
            declaracion=declaracion, dia_semana=0, hora_desde=time(7, 0), hora_hasta=time(13, 0)
        )

        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)
        assert not resultado.exito
        assert any("momentos libres" in problema for problema in resultado.problemas)

    def test_ubica_las_materias_sin_docente_pero_avisa(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Sin profesor")
        crear_plan(curso, materia, 3)

        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)

        assert resultado.exito
        assert any("Sin docente designado" in aviso for aviso in resultado.avisos)
        assert version.asignaciones.filter(legajo__isnull=True).count() == 3

    def test_sin_plan_de_estudios_no_hay_nada_que_generar(self, escuela):
        crear_curso(escuela, crear_esquema(escuela))
        version = crear_version(escuela)
        resultado = generar(version, RAPIDO)
        assert not resultado.exito
        assert resultado.estado == "SIN_DATOS"


class TestRecoleccion:
    def test_prefiere_el_cargo_asignado_a_la_division(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 3)

        general = crear_docente(escuela, "General", 1)
        especifica = crear_docente(escuela, "DeLaDivision", 2)
        designar(escuela, general, materia)  # sin curso
        designar(escuela, especifica, materia, curso)  # con curso

        requerimientos, _franjas = recolectar(crear_version(escuela))
        assert requerimientos[0].cargo.legajo == especifica

    def test_ignora_las_materias_de_otro_cuatrimestre(self, escuela):
        from datetime import date

        from estructura.models import PeriodoAcademico

        segundo = PeriodoAcademico.objects.create(
            ciclo=escuela["ciclo"],
            nombre="2do cuatrimestre",
            orden=2,
            fecha_inicio=date(2026, 8, 1),
            fecha_fin=date(2026, 12, 15),
        )
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        crear_plan(curso, crear_materia(escuela, "Taller I"), 3, periodo=escuela["periodo"])
        crear_plan(curso, crear_materia(escuela, "Taller II"), 3, periodo=segundo)

        requerimientos, _franjas = recolectar(crear_version(escuela))
        assert [r.materia_nombre for r in requerimientos] == ["Taller I"]

    def test_la_revision_no_marca_problemas_en_un_caso_sano(self, escuela):
        esquema = crear_esquema(escuela)
        curso = crear_curso(escuela, esquema)
        materia = crear_materia(escuela, "Matemática")
        crear_plan(curso, materia, 4)
        designar(escuela, crear_docente(escuela, "Pérez", 1), materia, curso)

        requerimientos, franjas = recolectar(crear_version(escuela))
        problemas, _avisos = revisar_factibilidad(requerimientos, franjas, RAPIDO)
        assert problemas == []
