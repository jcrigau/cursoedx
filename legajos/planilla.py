"""El personal en Excel: se baja, se corrige, se vuelve a subir.

Una planta de 130 personas no se tipea en formularios. El circuito es el que
la secretaría ya conoce de las planillas: se descarga la lista actual, se
corrige o se agregan filas en Excel, y se sube. Lo que ya existe se
actualiza, lo nuevo se crea, y lo dudoso se observa sin tocar nada.

La identidad es el CUIL: es el único dato que no cambia. Una fila sin CUIL, o
con uno inválido, se observa y se saltea.

Los cargos no viajan acá a propósito: un cargo tiene materia, curso, fuente
de pago y situación de revista, y eso mal importado son errores de
liquidación. Se cargan en el sistema, donde cada campo valida.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from estructura.models import Materia

from .models import EstadoLegajo, Legajo, Plantel

ENCABEZADOS = [
    "CUIL",
    "Apellido",
    "Nombre",
    "DNI",
    "Email",
    "Teléfono",
    "Fecha de ingreso",
    "Fecha de nacimiento",
    "Obra social",
    "Domicilio",
    "Localidad",
    "Estado",
    "Plantel",
    "Materias que puede dar",
]

SEPARADOR_MATERIAS = " | "


def exportar(institucion):
    """La planta completa, lista para corregir y volver a subir."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Personal"

    hoja.append(ENCABEZADOS)
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="0F6B63")

    personas = (
        Legajo.objects.filter(institucion=institucion)
        .prefetch_related("materias_que_puede_dar")
        .order_by("apellido", "nombre")
    )
    for legajo in personas:
        hoja.append(
            [
                legajo.cuil,
                legajo.apellido,
                legajo.nombre,
                legajo.dni,
                legajo.email,
                legajo.telefono,
                legajo.fecha_ingreso,
                legajo.fecha_nacimiento,
                legajo.obra_social,
                legajo.domicilio,
                legajo.localidad,
                legajo.get_estado_display(),
                legajo.get_plantel_display(),
                SEPARADOR_MATERIAS.join(
                    materia.nombre for materia in legajo.materias_que_puede_dar.all()
                ),
            ]
        )

    anchos = [15, 22, 22, 12, 32, 16, 14, 14, 18, 26, 16, 10, 16, 40]
    for indice, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    hoja.freeze_panes = "A2"
    return libro


@dataclass
class ResultadoImportacion:
    creados: int = 0
    actualizados: int = 0
    observaciones: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.creados + self.actualizados


def importar(institucion, archivo) -> ResultadoImportacion:
    """Lee la planilla y aplica lo que se pueda; lo dudoso se observa.

    No borra a nadie: una fila que falta en el archivo no es una baja, es una
    fila que falta. Las bajas se hacen en el sistema, con su motivo.
    """
    from openpyxl import load_workbook

    resultado = ResultadoImportacion()
    try:
        hoja = load_workbook(archivo, data_only=True).active
    except Exception:
        resultado.observaciones.append(
            "No se pudo leer el archivo. Tiene que ser el Excel descargado de acá "
            "(.xlsx), no un CSV ni una planilla de otro formato."
        )
        return resultado

    materias = {
        _clave(materia.nombre): materia
        for materia in Materia.objects.filter(institucion=institucion)
    }

    filas = hoja.iter_rows(min_row=2, values_only=True)
    for numero, fila in enumerate(filas, start=2):
        if fila is None or all(celda in (None, "") for celda in fila):
            continue
        fila = list(fila) + [None] * (len(ENCABEZADOS) - len(fila))

        cuil = _normalizar_cuil(fila[0])
        if cuil is None:
            resultado.observaciones.append(
                f"Fila {numero}: CUIL vacío o inválido «{fila[0] or ''}». Se salteó."
            )
            continue

        apellido = str(fila[1] or "").strip()
        nombre = str(fila[2] or "").strip()
        if not apellido or not nombre:
            resultado.observaciones.append(
                f"Fila {numero} ({cuil}): falta el apellido o el nombre. Se salteó."
            )
            continue

        ingreso = _como_fecha(fila[6])
        legajo = Legajo.objects.filter(institucion=institucion, cuil=cuil).first()
        nuevo = legajo is None
        if nuevo:
            if ingreso is None:
                resultado.observaciones.append(
                    f"Fila {numero} ({apellido}): es una persona nueva y no tiene fecha "
                    "de ingreso. Se salteó."
                )
                continue
            legajo = Legajo(institucion=institucion, cuil=cuil, fecha_ingreso=ingreso)

        legajo.apellido = apellido
        legajo.nombre = nombre
        legajo.dni = str(fila[3] or "").strip()
        legajo.email = str(fila[4] or "").strip()
        legajo.telefono = str(fila[5] or "").strip()
        if ingreso is not None:
            legajo.fecha_ingreso = ingreso
        legajo.fecha_nacimiento = _como_fecha(fila[7])
        legajo.obra_social = str(fila[8] or "").strip()
        legajo.domicilio = str(fila[9] or "").strip()
        legajo.localidad = str(fila[10] or "").strip()

        estado = _clave(str(fila[11] or ""))
        if estado.startswith("baja") or estado == "de baja":
            legajo.estado = EstadoLegajo.BAJA
        elif estado:
            legajo.estado = EstadoLegajo.ACTIVO

        plantel = _plantel_de(fila[12])
        if plantel is not None:
            legajo.plantel = plantel
        elif fila[12] not in (None, ""):
            resultado.observaciones.append(
                f"Fila {numero} ({apellido}): plantel «{fila[12]}» no reconocido; quedó "
                f"«{legajo.get_plantel_display()}». Vale: docente, preceptor, directivo, "
                "administrativo o maestranza."
            )

        legajo.save()

        elegidas, desconocidas = _materias_de(fila[13], materias)
        legajo.materias_que_puede_dar.set(elegidas)
        for nombre_materia in desconocidas:
            resultado.observaciones.append(
                f"Fila {numero} ({apellido}): la materia «{nombre_materia}» no existe "
                "en la escuela; se ignoró. Cargala primero en Materias."
            )

        if nuevo:
            resultado.creados += 1
        else:
            resultado.actualizados += 1

    return resultado


def _clave(texto: str) -> str:
    from core.texto import sin_tildes

    return sin_tildes(texto).strip()


def _normalizar_cuil(crudo) -> str | None:
    """Acepta el CUIL como venga —con guiones, como número de Excel— o nada."""
    if crudo is None:
        return None
    digitos = re.sub(r"\D", "", str(crudo))
    if len(digitos) != 11:
        return None
    return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"


def _plantel_de(crudo) -> str | None:
    """El plantel de la celda, escrito como sea: «Preceptora», «ordenanza»…"""
    clave = _clave(str(crudo or ""))
    if not clave:
        return None
    equivalencias = {
        "docente": Plantel.DOCENTE,
        "profesor": Plantel.DOCENTE,
        "precept": Plantel.PRECEPTOR,
        "directiv": Plantel.DIRECTIVO,
        "administrat": Plantel.ADMINISTRATIVO,
        "secretari": Plantel.ADMINISTRATIVO,
        "maestranza": Plantel.MAESTRANZA,
        "ordenanza": Plantel.MAESTRANZA,
    }
    for prefijo, valor in equivalencias.items():
        if clave.startswith(prefijo):
            return valor
    return None


def _como_fecha(crudo):
    """Excel devuelve datetime; una edición a mano puede dejar texto."""
    if crudo in (None, ""):
        return None
    if isinstance(crudo, datetime):
        return crudo.date()
    if isinstance(crudo, date):
        return crudo
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(crudo).strip(), formato).date()
        except ValueError:
            continue
    return None


def _materias_de(crudo, materias: dict) -> tuple[list, list[str]]:
    """Las materias de la celda, separadas por | o por coma."""
    if not crudo:
        return [], []
    encontradas, desconocidas = [], []
    for pedazo in re.split(r"[|,;]", str(crudo)):
        nombre = pedazo.strip()
        if not nombre:
            continue
        materia = materias.get(_clave(nombre))
        if materia is None:
            desconocidas.append(nombre)
        else:
            encontradas.append(materia)
    return encontradas, desconocidas
