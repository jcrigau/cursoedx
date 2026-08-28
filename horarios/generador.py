"""Generador automático de horarios (OR-Tools CP-SAT).

Qué resuelve: ubicar todas las horas del plan de estudios de cada curso en su
grilla, con el docente designado, sin que nadie quede en dos lugares a la vez.

Reglas obligatorias
    1. Cada materia recibe exactamente las horas semanales que pide su plan.
    2. Un curso no puede tener dos materias en el mismo horario.
    3. Un docente no puede estar en dos cursos a la vez.
    4. No se asignan horas donde el docente declaró que no puede (DDJJ).
    5. Una materia no supera el máximo de horas por día (evita 5 horas
       seguidas de la misma materia).

Qué se busca optimizar, en orden de importancia
    1. **Que cada docente venga la menor cantidad de días posible** — es lo que
       pidió la escuela y por eso lleva el peso más alto.
    2. Que no le queden horas libres en el medio del día.
    3. Que se respeten las franjas que declaró preferir evitar.

Sobre los choques: dos cursos pueden seguir esquemas distintos (uno almuerza y
el otro no), así que "la tercera hora" no siempre cae a la misma hora del
reloj. Por eso los choques de docente se resuelven comparando horarios reales.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import time

from django.db import transaction
from django.utils import timezone

from estructura.models import BloqueHorario, Curso, MateriaPlan, TipoBloque
from legajos.models import Cargo, TipoCargo

from .models import AsignacionHoraria, DeclaracionDisponibilidad, VersionHorario, se_superponen


@dataclass
class Parametros:
    """Pesos y límites de la generación. Se guardan en la versión."""

    # El objetivo n° 1 de la escuela: menos días de asistencia por docente.
    peso_dias_docente: int = 100
    peso_huecos: int = 10
    peso_preferencias: int = 3
    max_horas_dia_materia: int = 2
    segundos_limite: int = 30

    def como_dict(self) -> dict:
        return {
            "peso_dias_docente": self.peso_dias_docente,
            "peso_huecos": self.peso_huecos,
            "peso_preferencias": self.peso_preferencias,
            "max_horas_dia_materia": self.max_horas_dia_materia,
            "segundos_limite": self.segundos_limite,
        }


@dataclass(frozen=True)
class Slot:
    """Un lugar posible en la grilla de un curso."""

    bloque_id: int
    dia: int
    inicio: time
    fin: time

    def se_superpone_con(self, otro: "Slot") -> bool:
        return self.dia == otro.dia and se_superponen(self.inicio, self.fin, otro.inicio, otro.fin)

    def contiene(self, dia: int, momento: time) -> bool:
        return self.dia == dia and self.inicio <= momento < self.fin


@dataclass
class Requerimiento:
    """Una materia de un curso que hay que ubicar, con su docente."""

    plan_id: int
    curso: Curso
    materia_id: int
    materia_nombre: str
    horas: int
    cargo: Cargo | None
    slots: list[Slot] = field(default_factory=list)

    @property
    def legajo_id(self) -> int | None:
        return self.cargo.legajo_id if self.cargo else None

    def __str__(self) -> str:
        return f"{self.materia_nombre} en {self.curso}"


@dataclass
class Resultado:
    """Qué pasó al generar."""

    exito: bool
    estado: str
    problemas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    metricas: dict = field(default_factory=dict)
    asignaciones_creadas: int = 0


# -- recolección de datos ----------------------------------------------------


def slots_del_curso(curso: Curso) -> list[Slot]:
    """Bloques dictables de la grilla que sigue el curso."""
    bloques = BloqueHorario.objects.filter(
        esquema_id=curso.esquema_horario_id, tipo=TipoBloque.CLASE
    ).order_by("dia_semana", "hora_inicio")
    return [
        Slot(bloque_id=b.id, dia=b.dia_semana, inicio=b.hora_inicio, fin=b.hora_fin)
        for b in bloques
    ]


def buscar_cargo(plan: MateriaPlan, cargos: Iterable[Cargo]) -> Cargo | None:
    """Docente designado para esa materia en ese curso.

    Se prefiere el cargo asignado explícitamente a la división; si no hay, se
    toma uno de la misma materia sin curso indicado.
    """
    candidatos = [
        cargo
        for cargo in cargos
        if cargo.materia_id == plan.materia_id and cargo.tipo == TipoCargo.HORAS_CATEDRA
    ]
    con_curso = [cargo for cargo in candidatos if cargo.curso_id == plan.curso_id]
    if con_curso:
        return con_curso[0]
    sin_curso = [cargo for cargo in candidatos if cargo.curso_id is None]
    return sin_curso[0] if sin_curso else None


def recolectar(version: VersionHorario) -> tuple[list[Requerimiento], dict]:
    """Arma los requerimientos del período y las franjas no disponibles."""
    periodo = version.periodo
    cursos = (
        Curso.objects.filter(institucion=version.institucion, ciclo_lectivo=periodo.ciclo)
        .select_related("esquema_horario", "nivel", "turno")
        .order_by("nivel", "anio_estudio", "division")
    )

    cargos = list(
        Cargo.objects.filter(institucion=version.institucion)
        .filter(fecha_alta__lte=periodo.fecha_fin)
        .exclude(fecha_baja__lt=periodo.fecha_inicio)
        .select_related("legajo", "materia", "curso")
    )

    requerimientos = []
    for curso in cursos:
        slots = slots_del_curso(curso)
        planes = MateriaPlan.objects.filter(curso=curso).select_related("materia", "periodo")
        for plan in planes:
            if not plan.rige_en(periodo):
                continue
            requerimientos.append(
                Requerimiento(
                    plan_id=plan.id,
                    curso=curso,
                    materia_id=plan.materia_id,
                    materia_nombre=plan.materia.nombre,
                    horas=plan.horas_semanales,
                    cargo=buscar_cargo(plan, cargos),
                    slots=slots,
                )
            )

    # Franjas declaradas por los docentes para este período.
    franjas_duras: dict[int, list] = defaultdict(list)
    franjas_preferidas: dict[int, list] = defaultdict(list)
    declaraciones = DeclaracionDisponibilidad.objects.filter(
        institucion=version.institucion, periodo=periodo
    ).prefetch_related("franjas")
    for declaracion in declaraciones:
        for franja in declaracion.franjas.all():
            destino = franjas_preferidas if franja.es_preferencia else franjas_duras
            destino[declaracion.legajo_id].append(franja)

    return requerimientos, {"duras": franjas_duras, "preferidas": franjas_preferidas}


# -- controles previos -------------------------------------------------------


def revisar_factibilidad(
    requerimientos: list[Requerimiento], franjas: dict, parametros: Parametros
) -> tuple[list[str], list[str]]:
    """Detecta de antemano lo que haría imposible (o pobre) el horario.

    Vale la pena hacerlo antes de resolver: el solver solo diría "sin solución",
    mientras que acá se puede decir exactamente qué curso o qué docente es.
    """
    problemas, avisos = [], []

    por_curso: dict[int, list[Requerimiento]] = defaultdict(list)
    for requerimiento in requerimientos:
        por_curso[requerimiento.curso.id].append(requerimiento)

    for pedidos in por_curso.values():
        curso = pedidos[0].curso
        disponibles = len(pedidos[0].slots)
        pedidas = sum(pedido.horas for pedido in pedidos)
        if not disponibles:
            problemas.append(f"{curso} no tiene bloques de clase cargados en su grilla.")
        elif pedidas > disponibles:
            problemas.append(
                f"El plan de {curso} pide {pedidas} horas y su grilla ofrece {disponibles}."
            )

        for pedido in pedidos:
            dias = len({slot.dia for slot in pedido.slots})
            tope = dias * parametros.max_horas_dia_materia
            if pedido.horas > tope:
                problemas.append(
                    f"{pedido} pide {pedido.horas} horas, pero con un máximo de "
                    f"{parametros.max_horas_dia_materia} por día solo entran {tope}."
                )

    sin_docente = [str(pedido) for pedido in requerimientos if pedido.cargo is None]
    if sin_docente:
        avisos.append(
            "Sin docente designado (se ubican igual, para reservar el lugar): "
            + ", ".join(sorted(sin_docente))
        )

    # Carga de cada docente contra las horas que tiene realmente disponibles.
    por_docente: dict[int, list[Requerimiento]] = defaultdict(list)
    for requerimiento in requerimientos:
        if requerimiento.legajo_id:
            por_docente[requerimiento.legajo_id].append(requerimiento)

    for legajo_id, pedidos in por_docente.items():
        horas = sum(pedido.horas for pedido in pedidos)
        libres = set()
        for pedido in pedidos:
            for slot in pedido.slots:
                if not _bloqueado_por_ddjj(legajo_id, slot, franjas["duras"]):
                    libres.add((slot.dia, slot.inicio))
        if horas > len(libres):
            docente = pedidos[0].cargo.legajo
            problemas.append(
                f"{docente} tiene {horas} horas asignadas pero solo {len(libres)} "
                "momentos libres según su declaración de disponibilidad."
            )

    return problemas, avisos


def _bloqueado_por_ddjj(legajo_id: int, slot: Slot, franjas_duras: dict) -> bool:
    return any(
        franja.cubre(slot.dia, slot.inicio, slot.fin) for franja in franjas_duras.get(legajo_id, [])
    )


# -- modelo de optimización --------------------------------------------------


def generar(
    version: VersionHorario, parametros: Parametros | None = None, usuario=None
) -> Resultado:
    """Genera el horario de la versión y guarda las asignaciones."""
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        # OR-Tools es pesado y en algunos hospedajes chicos no entra. El resto
        # del sistema funciona igual: se puede cargar el horario a mano.
        return Resultado(
            exito=False,
            estado="SIN_OPTIMIZADOR",
            problemas=[
                "El optimizador (OR-Tools) no está instalado en este servidor, así que "
                "el horario no se puede generar automáticamente. Se puede cargar a mano "
                "desde «Asignaciones horarias», o instalarlo con «pip install ortools»."
            ],
        )

    parametros = parametros or Parametros()
    requerimientos, franjas = recolectar(version)

    if not requerimientos:
        return Resultado(
            exito=False,
            estado="SIN_DATOS",
            problemas=[
                "No hay materias para ubicar: revisá que los cursos tengan plan de "
                "estudios cargado para este período."
            ],
        )

    problemas, avisos = revisar_factibilidad(requerimientos, franjas, parametros)
    if problemas:
        return Resultado(exito=False, estado="INVIABLE", problemas=problemas, avisos=avisos)

    modelo = cp_model.CpModel()
    x: dict[tuple[int, int], object] = {}  # (indice del requerimiento, bloque) -> bool

    for indice, requerimiento in enumerate(requerimientos):
        for slot in requerimiento.slots:
            if requerimiento.legajo_id and _bloqueado_por_ddjj(
                requerimiento.legajo_id, slot, franjas["duras"]
            ):
                continue  # la DDJJ lo prohíbe: la variable ni se crea
            x[(indice, slot.bloque_id)] = modelo.NewBoolVar(f"x_{indice}_{slot.bloque_id}")

    slots_por_bloque = {
        slot.bloque_id: slot for requerimiento in requerimientos for slot in requerimiento.slots
    }

    # 1. Cada materia recibe exactamente sus horas.
    for indice, requerimiento in enumerate(requerimientos):
        variables = [
            x[(indice, s.bloque_id)] for s in requerimiento.slots if (indice, s.bloque_id) in x
        ]
        modelo.Add(sum(variables) == requerimiento.horas)

        # 5. Tope de horas por día de una misma materia.
        por_dia: dict[int, list] = defaultdict(list)
        for slot in requerimiento.slots:
            if (indice, slot.bloque_id) in x:
                por_dia[slot.dia].append(x[(indice, slot.bloque_id)])
        for variables_del_dia in por_dia.values():
            modelo.Add(sum(variables_del_dia) <= parametros.max_horas_dia_materia)

    # 2. Un curso, una materia por bloque.
    por_curso_bloque: dict[tuple[int, int], list] = defaultdict(list)
    for indice, requerimiento in enumerate(requerimientos):
        for slot in requerimiento.slots:
            if (indice, slot.bloque_id) in x:
                por_curso_bloque[(requerimiento.curso.id, slot.bloque_id)].append(
                    x[(indice, slot.bloque_id)]
                )
    for variables in por_curso_bloque.values():
        if len(variables) > 1:
            modelo.AddAtMostOne(variables)

    # 3. Un docente no puede estar en dos lugares a la vez. Se compara por
    #    horario real, no por bloque, porque los esquemas difieren entre cursos.
    variables_por_docente: dict[int, list[tuple[int, Slot]]] = defaultdict(list)
    for indice, requerimiento in enumerate(requerimientos):
        if not requerimiento.legajo_id:
            continue
        for slot in requerimiento.slots:
            if (indice, slot.bloque_id) in x:
                variables_por_docente[requerimiento.legajo_id].append((indice, slot))

    for pares in variables_por_docente.values():
        momentos = sorted({(slot.dia, slot.inicio) for _indice, slot in pares})
        for dia, momento in momentos:
            simultaneas = [
                x[(indice, slot.bloque_id)] for indice, slot in pares if slot.contiene(dia, momento)
            ]
            if len(simultaneas) > 1:
                modelo.AddAtMostOne(simultaneas)

    # -- objetivos -----------------------------------------------------------
    terminos = []

    for legajo_id, pares in variables_por_docente.items():
        dias_del_docente = sorted({slot.dia for _indice, slot in pares})

        for dia in dias_del_docente:
            del_dia = [(indice, slot) for indice, slot in pares if slot.dia == dia]
            momentos = sorted({slot.inicio for _indice, slot in del_dia})

            # Una variable por momento: el docente está o no está a esa hora.
            ocupado = []
            for momento in momentos:
                simultaneas = [
                    x[(indice, slot.bloque_id)]
                    for indice, slot in del_dia
                    if slot.contiene(dia, momento)
                ]
                marca = modelo.NewBoolVar(f"ocupado_{legajo_id}_{dia}_{momento}")
                modelo.AddMaxEquality(marca, simultaneas)
                ocupado.append(marca)

            # Objetivo 1: que venga la menor cantidad de días posible.
            viene = modelo.NewBoolVar(f"viene_{legajo_id}_{dia}")
            modelo.AddMaxEquality(viene, ocupado)
            terminos.append(parametros.peso_dias_docente * viene)

            # Objetivo 2: sin horas libres en el medio. Se mide como la
            # diferencia entre la ventana que pasa en la escuela y las horas
            # que efectivamente da.
            if len(ocupado) < 2:
                continue
            cantidad = len(ocupado)
            carga = sum(ocupado)
            posiciones_inicio, posiciones_fin = [], []
            for k, marca in enumerate(ocupado):
                inicio_k = modelo.NewIntVar(0, cantidad, f"ini_{legajo_id}_{dia}_{k}")
                modelo.Add(inicio_k == k).OnlyEnforceIf(marca)
                modelo.Add(inicio_k == cantidad).OnlyEnforceIf(marca.Not())
                posiciones_inicio.append(inicio_k)

                fin_k = modelo.NewIntVar(0, cantidad, f"fin_{legajo_id}_{dia}_{k}")
                modelo.Add(fin_k == k).OnlyEnforceIf(marca)
                modelo.Add(fin_k == 0).OnlyEnforceIf(marca.Not())
                posiciones_fin.append(fin_k)

            primera = modelo.NewIntVar(0, cantidad, f"primera_{legajo_id}_{dia}")
            ultima = modelo.NewIntVar(0, cantidad, f"ultima_{legajo_id}_{dia}")
            modelo.AddMinEquality(primera, posiciones_inicio)
            modelo.AddMaxEquality(ultima, posiciones_fin)

            huecos = modelo.NewIntVar(0, cantidad, f"huecos_{legajo_id}_{dia}")
            modelo.Add(huecos >= ultima - primera + 1 - carga - cantidad * (1 - viene))
            terminos.append(parametros.peso_huecos * huecos)

        # Objetivo 3: evitar las franjas que la persona prefiere no tomar.
        preferidas = franjas["preferidas"].get(legajo_id, [])
        if preferidas:
            penalizadas = [
                x[(indice, slot.bloque_id)]
                for indice, slot in pares
                if any(franja.cubre(slot.dia, slot.inicio, slot.fin) for franja in preferidas)
            ]
            if penalizadas:
                terminos.append(parametros.peso_preferencias * sum(penalizadas))

    if terminos:
        modelo.Minimize(sum(terminos))

    # Lo que la secretaría dejó fijo no se mueve.
    fijadas = _fijar_bloqueadas(modelo, x, requerimientos, version)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(parametros.segundos_limite)
    solver.parameters.num_search_workers = 8
    estado = solver.Solve(modelo)

    if estado not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return Resultado(
            exito=False,
            estado="SIN_SOLUCION",
            problemas=[
                "No se encontró un horario que cumpla todas las condiciones. "
                "Suele deberse a declaraciones de disponibilidad muy ajustadas o a "
                "asignaciones bloqueadas que se contradicen."
            ],
            avisos=avisos,
        )

    creadas = _guardar(version, requerimientos, x, solver, slots_por_bloque)
    metricas = _metricas(version, parametros, solver, estado, fijadas)

    version.generada_en = timezone.now()
    version.generada_por = usuario
    version.parametros = parametros.como_dict()
    version.resumen = metricas
    version.save(update_fields=["generada_en", "generada_por", "parametros", "resumen"])

    return Resultado(
        exito=True,
        estado="OPTIMO" if estado == cp_model.OPTIMAL else "FACTIBLE",
        avisos=avisos,
        metricas=metricas,
        asignaciones_creadas=creadas,
    )


def _fijar_bloqueadas(modelo, x, requerimientos, version) -> int:
    """Obliga a mantener las asignaciones que la secretaría marcó como fijas."""
    indice_por_clave = {
        (requerimiento.curso.id, requerimiento.materia_id): indice
        for indice, requerimiento in enumerate(requerimientos)
    }
    fijadas = 0
    for asignacion in version.asignaciones.filter(bloqueada=True):
        indice = indice_por_clave.get((asignacion.curso_id, asignacion.materia_id))
        variable = x.get((indice, asignacion.bloque_id)) if indice is not None else None
        if variable is not None:
            modelo.Add(variable == 1)
            fijadas += 1
    return fijadas


@transaction.atomic
def _guardar(version, requerimientos, x, solver, slots_por_bloque) -> int:
    """Reemplaza las asignaciones de la versión, conservando las bloqueadas."""
    version.asignaciones.filter(bloqueada=False).delete()

    ya_estan = {
        (asignacion.curso_id, asignacion.bloque_id)
        for asignacion in version.asignaciones.filter(bloqueada=True)
    }

    nuevas = []
    for indice, requerimiento in enumerate(requerimientos):
        for slot in requerimiento.slots:
            variable = x.get((indice, slot.bloque_id))
            if variable is None or not solver.BooleanValue(variable):
                continue
            if (requerimiento.curso.id, slot.bloque_id) in ya_estan:
                continue
            nuevas.append(
                AsignacionHoraria(
                    version=version,
                    curso=requerimiento.curso,
                    bloque_id=slot.bloque_id,
                    materia_id=requerimiento.materia_id,
                    cargo=requerimiento.cargo,
                    legajo_id=requerimiento.legajo_id,
                    dia_semana=slot.dia,
                    hora_inicio=slot.inicio,
                    hora_fin=slot.fin,
                )
            )
    AsignacionHoraria.objects.bulk_create(nuevas)
    return len(nuevas)


def _metricas(version, parametros, solver, estado, fijadas) -> dict:
    dias = version.dias_por_docente()
    total_docentes = len(dias) or 1
    return {
        "estado": "óptimo" if estado == 4 else "factible",
        "segundos": round(solver.WallTime(), 1),
        "docentes": len(dias),
        "promedio_dias_por_docente": round(sum(dias.values()) / total_docentes, 2),
        "maximo_dias_por_docente": max(dias.values(), default=0),
        "asignaciones_fijas_respetadas": fijadas,
        "parametros": parametros.como_dict(),
    }
