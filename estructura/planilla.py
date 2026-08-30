"""La estructura del colegio desde la planilla de carga.

Cargar una escuela a mano son doce cursos, cuarenta materias y ciento ochenta
filas de plan de estudios tipeadas en formularios. Acá entra todo de una vez,
en el orden en que cada cosa se apoya en la anterior: niveles, ciclo, turnos,
grilla, cursos, materias y plan.

Todo es **idempotente**: se busca por la clave natural de cada modelo (el tipo
del nivel, el año del ciclo, el nombre del turno…) y si ya existe se actualiza.
Subir dos veces el mismo archivo no duplica nada, que es la única forma de que
se pueda corregir el Excel y volver a intentar sin miedo.
"""

import re

from django.core.exceptions import ValidationError

from core.planillas import Resultado, entero, fecha, hora, leer, opcion, opciones_de, texto
from core.planillas import clave as _clave

from .models import (
    BloqueHorario,
    CicloLectivo,
    Curso,
    DiaSemana,
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

# "1°A", "1ºA", "1 A", "1A", "5º B"
CURSO = re.compile(r"^\s*(\d+)\s*[°º\-\.]?\s*([A-Za-zÁÉÍÓÚÑ]{1,5})\s*$")


def escuela(institucion, libro) -> Resultado:
    """Los datos de la institución: se completan los que estén, sin pisar el nombre."""
    resultado = Resultado("Escuela")
    campos = {
        "Nombre corto": "nombre_corto",
        "CUE": "cue",
        "CUIT": "cuit",
        "Domicilio": "domicilio",
        "Localidad": "localidad",
        "Teléfono": "telefono",
        "Email": "email",
        "Color": "color",
    }
    for numero, fila in leer(libro, "Escuela"):
        for columna, campo in campos.items():
            valor = texto(fila.get(columna))
            if valor and hasattr(institucion, campo):
                setattr(institucion, campo, valor)
        jurisdiccion = _jurisdiccion(fila.get("Jurisdicción"))
        if jurisdiccion:
            institucion.jurisdiccion = jurisdiccion
        try:
            institucion.full_clean()
        except ValidationError as error:
            resultado.observar(numero, _explicar(error, type(institucion)))
            return resultado
        institucion.save()
        resultado.actualizados += 1
    return resultado


def _jurisdiccion(valor):
    from core.models import Jurisdiccion

    return opcion(valor, Jurisdiccion.choices)


def niveles(institucion, libro) -> Resultado:
    resultado = Resultado("Niveles")
    for orden, (numero, fila) in enumerate(leer(libro, "Niveles"), start=1):
        tipo = opcion(fila.get("Nivel"), TipoNivel.choices)
        if tipo is None:
            resultado.observar(
                numero,
                f"«{texto(fila.get('Nivel'))}» no es un nivel. Vale {opciones_de(TipoNivel.choices)}.",
            )
            continue
        # Las observaciones son para quien completa la planilla, no un campo:
        # el nivel se llama como se llama.
        _nivel_creado, creado = Nivel.objects.get_or_create(
            institucion=institucion, tipo=tipo, defaults={"orden": orden}
        )
        _contar(resultado, creado)
    return resultado


def ciclo_y_periodos(institucion, libro) -> Resultado:
    """El año escolar y sus períodos. El año se repite en cada fila del período."""
    resultado = Resultado("Ciclo y períodos")
    for numero, fila in leer(libro, "Ciclo y períodos"):
        anio = entero(fila.get("Año"))
        inicio, fin = fecha(fila.get("Inicio de clases")), fecha(fila.get("Fin de clases"))
        if not (anio and inicio and fin):
            resultado.observar(numero, "faltan el año, el inicio o el fin de clases.")
            continue
        ciclo, creado = CicloLectivo.objects.get_or_create(
            institucion=institucion,
            anio=anio,
            defaults={"fecha_inicio": inicio, "fecha_fin": fin},
        )
        if not creado:
            ciclo.fecha_inicio, ciclo.fecha_fin = inicio, fin
            ciclo.save()
        _contar(resultado, creado)

        nombre = texto(fila.get("Período"))
        if not nombre:
            continue
        desde, hasta = fecha(fila.get("Desde")), fecha(fila.get("Hasta"))
        if not (desde and hasta):
            resultado.observar(numero, f"el período «{nombre}» no tiene fechas. No se creó.")
            continue
        PeriodoAcademico.objects.update_or_create(
            ciclo=ciclo,
            orden=entero(fila.get("Orden")) or 1,
            defaults={"nombre": nombre, "fecha_inicio": desde, "fecha_fin": hasta},
        )
    return resultado


def turnos(institucion, libro) -> Resultado:
    resultado = Resultado("Turnos")
    for numero, fila in leer(libro, "Turnos"):
        nivel = _nivel(institucion, fila.get("Nivel"))
        nombre = texto(fila.get("Turno"))
        entrada, salida = hora(fila.get("Entrada")), hora(fila.get("Salida"))
        if nivel is None:
            resultado.observar(numero, f"no existe el nivel «{texto(fila.get('Nivel'))}».")
            continue
        if not (nombre and entrada and salida):
            resultado.observar(numero, "faltan el nombre del turno, la entrada o la salida.")
            continue
        _turno, creado = Turno.objects.update_or_create(
            institucion=institucion,
            nivel=nivel,
            nombre=nombre,
            defaults={"hora_inicio": entrada, "hora_fin": salida},
        )
        _contar(resultado, creado)
    return resultado


def grilla(institucion, libro) -> Resultado:
    """Los bloques de cada esquema, día por día."""
    resultado = Resultado("Grilla horaria")
    for numero, fila in leer(libro, "Grilla horaria"):
        turno = _turno_por_nombre(institucion, fila.get("Turno"))
        if turno is None:
            resultado.observar(
                numero,
                f"no existe el turno «{texto(fila.get('Turno'))}». Cargá primero los turnos.",
            )
            continue
        dia = opcion(fila.get("Día"), DiaSemana.choices)
        desde, hasta = hora(fila.get("Desde")), hora(fila.get("Hasta"))
        if dia is None or not (desde and hasta):
            resultado.observar(numero, "falta el día o el horario del bloque.")
            continue

        esquema, _creado = EsquemaHorario.objects.get_or_create(
            institucion=institucion,
            turno=turno,
            nombre=texto(fila.get("Esquema")) or "Único",
            defaults={"predeterminado": True},
        )
        bloque, creado = BloqueHorario.objects.update_or_create(
            esquema=esquema,
            dia_semana=dia,
            orden=entero(fila.get("Orden")) or 1,
            defaults={
                "tipo": opcion(fila.get("Tipo"), TipoBloque.choices, defecto=TipoBloque.CLASE),
                "hora_inicio": desde,
                "hora_fin": hasta,
                "etiqueta": texto(fila.get("Etiqueta"))[:40],
            },
        )
        try:
            bloque.full_clean()
        except ValidationError as error:
            resultado.observar(numero, _explicar(error, BloqueHorario))
            bloque.delete()
            continue
        _contar(resultado, creado)
    return resultado


def cursos(institucion, libro, ciclo) -> Resultado:
    """Las divisiones del ciclo. El turno y el esquema se adivinan si hay uno solo."""
    resultado = Resultado("Cursos")
    if ciclo is None:
        resultado.problema(
            "no hay ciclo lectivo cargado: completá la hoja «Ciclo y períodos» primero."
        )
        return resultado
    for numero, fila in leer(libro, "Cursos"):
        nivel = _nivel(institucion, fila.get("Nivel"))
        anio = entero(fila.get("Año de estudio"))
        division = texto(fila.get("División")).upper()
        if nivel is None or not anio or not division:
            resultado.observar(numero, "faltan el nivel, el año de estudio o la división.")
            continue

        turno, problema = _turno_del_curso(institucion, nivel, fila.get("Turno"))
        if problema:
            resultado.observar(numero, problema)
            continue
        esquema, problema = _esquema_del_curso(turno, fila.get("Esquema"))
        if problema:
            resultado.observar(numero, problema)
            continue

        _curso, creado = Curso.objects.update_or_create(
            institucion=institucion,
            ciclo_lectivo=ciclo,
            nivel=nivel,
            anio_estudio=anio,
            division=division,
            defaults={"turno": turno, "esquema_horario": esquema},
        )
        _contar(resultado, creado)
    return resultado


def _turno_del_curso(institucion, nivel, escrito):
    nombre = texto(escrito)
    disponibles = list(Turno.objects.filter(institucion=institucion, nivel=nivel))
    if nombre:
        for turno in disponibles:
            if _clave(turno.nombre) == _clave(nombre):
                return turno, None
        return None, f"el nivel no tiene un turno «{nombre}»."
    if len(disponibles) == 1:
        return disponibles[0], None
    if not disponibles:
        return None, f"{nivel} no tiene turnos cargados. Completá primero la hoja Turnos."
    return None, "el nivel tiene más de un turno: hay que decir cuál en la columna Turno."


def _esquema_del_curso(turno, escrito):
    nombre = texto(escrito)
    disponibles = list(EsquemaHorario.objects.filter(turno=turno))
    if nombre:
        for esquema in disponibles:
            if _clave(esquema.nombre) == _clave(nombre):
                return esquema, None
        return None, f"el turno {turno.nombre} no tiene un esquema «{nombre}»."
    if len(disponibles) == 1:
        return disponibles[0], None
    if not disponibles:
        return None, (
            f"el turno {turno.nombre} no tiene grilla horaria cargada. Completá primero "
            "la hoja Grilla horaria."
        )
    predeterminado = [esquema for esquema in disponibles if esquema.predeterminado]
    if len(predeterminado) == 1:
        return predeterminado[0], None
    return None, "el turno tiene más de un esquema: hay que decir cuál en la columna Esquema."


def materias(institucion, libro) -> Resultado:
    resultado = Resultado("Materias")
    for numero, fila in leer(libro, "Materias"):
        nivel = _nivel(institucion, fila.get("Nivel"))
        nombre = texto(fila.get("Materia"))
        if nivel is None or not nombre:
            resultado.observar(numero, "faltan el nivel o el nombre de la materia.")
            continue
        _materia, creado = Materia.objects.update_or_create(
            institucion=institucion,
            nivel=nivel,
            nombre=nombre,
            defaults={"abreviatura": texto(fila.get("Abreviatura"))[:20]},
        )
        _contar(resultado, creado)
    return resultado


def plan_de_estudios(institucion, libro, ciclo) -> Resultado:
    resultado = Resultado("Plan de estudios")
    if ciclo is None:
        resultado.problema("no hay ciclo lectivo cargado.")
        return resultado
    for numero, fila in leer(libro, "Plan de estudios"):
        curso, problema = buscar_curso(institucion, ciclo, fila.get("Curso"))
        if problema:
            resultado.observar(numero, problema)
            continue
        materia = _materia(institucion, curso.nivel, fila.get("Materia"))
        if materia is None:
            resultado.observar(
                numero,
                f"la materia «{texto(fila.get('Materia'))}» no existe en {curso.nivel}. "
                "Cargala primero en la hoja Materias, escrita igual.",
            )
            continue
        horas = entero(fila.get("Horas semanales"))
        if not horas:
            resultado.observar(numero, "falta la cantidad de horas semanales.")
            continue

        vigencia = opcion(fila.get("Vigencia"), Vigencia.choices, defecto=Vigencia.ANUAL)
        periodo = None
        if vigencia == Vigencia.PERIODO:
            periodo = _periodo(ciclo, fila.get("Período"))
            if periodo is None:
                resultado.observar(
                    numero,
                    f"dice que se dicta en un período pero «{texto(fila.get('Período'))}» no "
                    "es ninguno de los cargados.",
                )
                continue

        _plan, creado = MateriaPlan.objects.update_or_create(
            curso=curso,
            materia=materia,
            periodo=periodo,
            defaults={"horas_semanales": min(horas, 20), "vigencia": vigencia},
        )
        if horas > 20:
            resultado.avisar("horas semanales por encima de 20: se guardaron como 20")
        _contar(resultado, creado)
    return resultado


def buscar_curso(institucion, ciclo, escrito, nivel=None):
    """De «5°B» al curso. Devuelve ``(curso, problema)``."""
    crudo = texto(escrito)
    if not crudo:
        return None, "falta el curso."
    coincidencia = CURSO.match(crudo)
    if not coincidencia:
        return None, f"no se entiende el curso «{crudo}». Se escribe así: 1°A."
    anio, division = int(coincidencia.group(1)), coincidencia.group(2).upper()
    candidatos = Curso.objects.filter(
        institucion=institucion, ciclo_lectivo=ciclo, anio_estudio=anio, division=division
    )
    if nivel is not None:
        candidatos = candidatos.filter(nivel=nivel)
    candidatos = list(candidatos)
    if not candidatos:
        return None, _por_que_no_esta(institucion, ciclo, anio, division)
    if len(candidatos) > 1:
        return None, f"hay un {anio}°{division} en más de un nivel: no se sabe cuál es."
    return candidatos[0], None


def _por_que_no_esta(institucion, ciclo, anio, division) -> str:
    """«3°AB» no es un curso que falte: son dos cursos que se dictan juntos.

    Pasa todo el tiempo en las plantas funcionales, y decirle «cargalo primero»
    a quien completó la planilla no ayuda: lo que hay que hacer es repartir.
    """
    if len(division) > 1:
        existen = [
            letra
            for letra in division
            if Curso.objects.filter(
                institucion=institucion, ciclo_lectivo=ciclo, anio_estudio=anio, division=letra
            ).exists()
        ]
        if len(existen) > 1:
            juntos = " y ".join(f"{anio}°{letra}" for letra in existen)
            return (
                f"«{anio}°{division}» parece un curso combinado ({juntos} juntos). Poné una "
                "fila por división repartiendo las horas, o dejá el curso vacío si las horas "
                "no son de una división en particular."
            )
    return f"no existe el curso {anio}°{division}. Cargalo primero en la hoja Cursos."


def _nivel(institucion, escrito):
    tipo = opcion(escrito, TipoNivel.choices)
    if tipo is None:
        return None
    return Nivel.objects.filter(institucion=institucion, tipo=tipo).first()


def _turno_por_nombre(institucion, escrito):
    buscado = _clave(escrito)
    for turno in Turno.objects.filter(institucion=institucion):
        if _clave(turno.nombre) == buscado:
            return turno
    return None


def _materia(institucion, nivel, escrito):
    buscado = _clave(escrito)
    if not buscado:
        return None
    for materia in Materia.objects.filter(institucion=institucion, nivel=nivel):
        if _clave(materia.nombre) == buscado:
            return materia
    return None


def _periodo(ciclo, escrito):
    buscado = _clave(escrito)
    if not buscado:
        return None
    for periodo in ciclo.periodos.all():
        if _clave(periodo.nombre) == buscado:
            return periodo
    return None


def _contar(resultado, creado):
    if creado:
        resultado.creados += 1
    else:
        resultado.actualizados += 1


def _explicar(error: ValidationError, modelo=None) -> str:
    """El error de validación en una línea, como lo diría una persona."""
    from legajos.planilla import _en_una_linea

    return _en_una_linea(error, modelo)
