"""El cartel del primer ingreso, distinto según el puesto.

Un usuario nuevo entra y ve una pantalla llena de cosas sin saber cuál es la
suya. Tres renglones alcanzan para orientarlo: qué hace acá, qué es lo único
que lo frena, y dónde está lo suyo. Se cierra y no vuelve.
"""

from .models import Rol

BIENVENIDAS = {
    Rol.DIRECTIVO: {
        "titulo": "Bienvenido/a. Esto es lo que te toca.",
        "puntos": [
            "Las <strong>licencias esperando aprobación</strong> te aparecen acá "
            "arriba. Hasta que no las resolvés, esas personas siguen figurando "
            "en el parte como si fueran a venir.",
            "También decidís las <strong>coberturas</strong>: quién reemplaza, o "
            "si el curso queda sin clase.",
            "El resto lo podés consultar todo, pero no hace falta que lo cargues.",
        ],
    },
    Rol.SECRETARIA: {
        "titulo": "Bienvenido/a. Así es el día.",
        "puntos": [
            "A la mañana: <strong>Cursos de hoy</strong> para ver qué queda sin "
            "clase, y <strong>Parte diario</strong> para marcar las novedades. "
            "Lo que no marques cuenta como presente.",
            "A fin de mes: <strong>Novedades</strong>, compilar, revisar y cerrar. "
            "Recién cerrado lo ve el liquidador.",
            "Todo lo que se carga y se edita está en "
            "<strong>Administración</strong>, y lo pendiente te aparece acá con "
            "el link a donde se resuelve.",
        ],
    },
    Rol.LIQUIDADOR: {
        "titulo": "Bienvenido/a. Acá está lo suyo.",
        "puntos": [
            "Va a ver los meses <strong>cuando la escuela los cierre</strong>. "
            "Antes no, porque un borrador todavía puede cambiar.",
            "De cada mes cerrado descarga la planilla en Excel, CSV o PDF, con "
            "las columnas de siempre y separada en Oficial e Interna.",
            "No tiene acceso a legajos ni horarios: solo a las novedades.",
        ],
    },
    Rol.DOCENTE: {
        "titulo": "Bienvenido/a a tu portal.",
        "puntos": [
            "En <strong>Hoy</strong> registrás tu entrada y ves tus clases del día.",
            "Si no vas a poder ir, <strong>Avisar</strong> le llega a secretaría "
            "en el momento. No reemplaza a la licencia: esa se carga después, "
            "con el certificado.",
            "En <strong>Mi legajo</strong> ves tus cargos y qué documentación te está por vencer.",
        ],
    },
}


def para(usuario, institucion) -> dict | None:
    """El texto que le corresponde, o nada si ya lo vio."""
    if usuario.vio_la_bienvenida:
        return None

    roles = usuario.roles_en(institucion)
    # Con más de un rol gana el que más trabajo tiene: es el que necesita la
    # explicación más completa.
    for rol in (Rol.SECRETARIA, Rol.DIRECTIVO, Rol.LIQUIDADOR, Rol.DOCENTE):
        if rol in roles:
            return BIENVENIDAS[rol]
    if usuario.is_superuser:
        return BIENVENIDAS[Rol.SECRETARIA]
    return None
