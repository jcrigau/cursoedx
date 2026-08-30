"""Lo común a las planillas de Excel que van y vienen con la escuela.

Las plantillas llevan filas de ejemplo para que se vea de qué forma va cada
dato. Nadie se acuerda de borrarlas, así que el ejemplo se marca: la primera
celda empieza con la palabra ``EJEMPLO`` y cualquier importador la saltea sin
decir nada. Una fila de ejemplo que se cuela es una persona inventada en el
legajero.

Acá también viven las conversiones —fecha, hora, entero, sí/no, opción de una
lista— porque en una planilla el mismo dato viene escrito de cinco maneras y
el sistema tiene que entenderlas todas antes de rechazar nada.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time

MARCA_EJEMPLO = "EJEMPLO"

# La fila 1 es la ayuda, la 2 está en blanco y la 3 es el encabezado.
FILA_ENCABEZADO = 3


def es_ejemplo(primera_celda) -> bool:
    """¿Esta fila es la de muestra que trae la plantilla?"""
    return str(primera_celda or "").strip().upper().startswith(MARCA_EJEMPLO)


def clave(texto) -> str:
    """Texto comparable: sin tildes, sin mayúsculas, sin espacios de más."""
    from core.texto import sin_tildes

    return " ".join(sin_tildes(str(texto or "")).lower().split())


def nombre_de_columna(encabezado) -> str:
    """«Curso (ej. 1°A)» es la columna «Curso»: el paréntesis es la ayuda."""
    return str(encabezado or "").split(" (")[0].strip()


@dataclass
class Resultado:
    """Qué pasó con una hoja: lo que entró, lo que se actualizó y lo que no.

    Los avisos se cuentan agrupados a propósito. «298 cargos sin fecha de
    alta» se lee; 298 líneas iguales, no.
    """

    hoja: str
    creados: int = 0
    actualizados: int = 0
    observaciones: list[str] = field(default_factory=list)
    avisos: Counter = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return self.creados + self.actualizados

    @property
    def hubo_problemas(self) -> bool:
        return bool(self.observaciones)

    def observar(self, numero, texto):
        """Algo que quedó sin cargar, con la fila para poder ir a mirarla."""
        self.observaciones.append(f"fila {numero}: {texto}")

    def problema(self, texto):
        """Algo que frena la hoja entera: no tiene una fila que lo explique."""
        self.observaciones.append(texto)

    def avisar(self, texto):
        """Algo que se resolvió solo, pero conviene que se sepa."""
        self.avisos[texto] += 1


def leer(libro, titulo, *, fila_encabezado: int = FILA_ENCABEZADO):
    """Las filas útiles de una hoja: sin la ayuda, sin encabezado, sin ejemplos.

    Devuelve ``(número de fila, {columna: valor})``. El número es el de Excel,
    para que quien lea el informe pueda abrir el archivo e ir a mirar.
    """
    if titulo not in libro.sheetnames:
        return
    hoja = libro[titulo]
    encabezados = [nombre_de_columna(celda.value) for celda in hoja[fila_encabezado]]
    filas = hoja.iter_rows(min_row=fila_encabezado + 1, values_only=True)
    for numero, fila in enumerate(filas, start=fila_encabezado + 1):
        if fila is None or all(celda in (None, "") for celda in fila):
            continue
        if es_ejemplo(fila[0]):
            continue
        yield numero, dict(zip(encabezados, fila, strict=False))


def tiene_filas(libro, titulo) -> bool:
    return any(True for _ in leer(libro, titulo))


def texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def entero(valor):
    """El número escrito como sea: 5, «5», «5 hs», «5,0»."""
    crudo = texto(valor).replace(",", ".")
    if not crudo:
        return None
    numero = ""
    for caracter in crudo:
        if caracter.isdigit():
            numero += caracter
        elif numero:
            break
    return int(numero) if numero else None


def fecha(valor):
    """dd/mm/aaaa, aaaa-mm-dd o una fecha de verdad de Excel."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    crudo = texto(valor)
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(crudo, formato).date()
        except ValueError:
            continue
    return None


def hora(valor):
    """07:30, «7:30», «7.30» o una hora de Excel."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.time()
    if isinstance(valor, time):
        return valor
    crudo = texto(valor).replace(".", ":").replace("hs", "").strip()
    for formato in ("%H:%M:%S", "%H:%M", "%H"):
        try:
            return datetime.strptime(crudo, formato).time()
        except ValueError:
            continue
    return None


def si_no(valor, *, defecto=False) -> bool:
    crudo = clave(valor)
    if not crudo:
        return defecto
    return crudo[0] in "sxv1t"  # sí, x, verdadero, 1, true


def opcion(valor, choices, *, defecto=None):
    """El valor interno a partir de lo escrito: acepta la etiqueta o el código.

    Tolera que se escriba de menos —«Subvencionado» por «Subvencionado (lo
    paga el estado)»— porque es lo que hace cualquiera que complete a mano.
    """
    buscado = clave(valor)
    if not buscado:
        return defecto
    for codigo, etiqueta in choices:
        if buscado in {clave(codigo), clave(etiqueta)}:
            return codigo
    for codigo, etiqueta in choices:
        if clave(etiqueta).startswith(buscado) or buscado.startswith(clave(etiqueta)):
            return codigo
    return None


def opciones_de(choices) -> str:
    """Para el mensaje de error: qué se podía haber escrito."""
    return ", ".join(f"«{etiqueta}»" for _codigo, etiqueta in choices)
