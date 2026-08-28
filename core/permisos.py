"""Qué puede hacer cada rol dentro del sistema.

Los permisos de Django son globales (no distinguen institución); el aislamiento
por escuela lo garantiza la capa de tenancy. La combinación es la correcta:
el rol define **qué** puede tocar una persona y la institución activa define
**sobre qué datos**.

Los grupos se crean y actualizan con ``python manage.py sincronizar_permisos``,
que también corre solo al aplicar las migraciones.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from .models import Rol

TODAS = ("add", "change", "delete", "view")
SOLO_VER = ("view",)

# Modelos de la estructura del colegio que administra la secretaría.
ESTRUCTURA = [
    "nivel",
    "ciclolectivo",
    "periodoacademico",
    "turno",
    "esquemahorario",
    "bloquehorario",
    "curso",
    "materia",
    "materiaplan",
]

# Legajos del personal: datos sensibles, incluida documentación de salud.
LEGAJOS = [
    "legajo",
    "cargo",
    "tipodocumento",
    "documentolegajo",
    "titulo",
    "servicioanterior",
]

# Horarios: DDJJ, versiones y asignaciones.
HORARIOS = [
    "declaraciondisponibilidad",
    "franjanodisponible",
    "versionhorario",
    "asignacionhoraria",
]

LICENCIAS = ["tipolicencia", "licencia", "cobertura"]
ASISTENCIA = ["registroasistencia"]
NOVEDADES = ["periodonovedades", "novedad"]
# Lo que llega del portal: la secretaría lo consulta y lo confirma.
PORTAL = ["avisoinasistencia", "fichada"]

# rol -> {app_label: {modelo: acciones}}
PERMISOS_POR_ROL: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    Rol.SECRETARIA: {
        "estructura": {modelo: TODAS for modelo in ESTRUCTURA},
        "legajos": {modelo: TODAS for modelo in LEGAJOS},
        "horarios": {modelo: TODAS for modelo in HORARIOS},
        "licencias": {modelo: TODAS for modelo in LICENCIAS},
        "asistencia": {modelo: TODAS for modelo in ASISTENCIA},
        "novedades": {modelo: TODAS for modelo in NOVEDADES},
        "portal": {modelo: TODAS for modelo in PORTAL},
        "core": {"membresia": SOLO_VER, "registroauditoria": SOLO_VER},
    },
    # El directivo consulta todo y además aprueba o rechaza licencias.
    Rol.DIRECTIVO: {
        "estructura": {modelo: SOLO_VER for modelo in ESTRUCTURA},
        "legajos": {modelo: SOLO_VER for modelo in LEGAJOS},
        "horarios": {modelo: SOLO_VER for modelo in HORARIOS},
        "licencias": {"tipolicencia": SOLO_VER, "licencia": TODAS, "cobertura": TODAS},
        "asistencia": {modelo: SOLO_VER for modelo in ASISTENCIA},
        "novedades": {modelo: SOLO_VER for modelo in NOVEDADES},
        "portal": {modelo: SOLO_VER for modelo in PORTAL},
        "core": {"membresia": SOLO_VER, "registroauditoria": SOLO_VER},
    },
    # El docente usa el portal (F5), no el panel de administración. Podrá ver
    # su propio horario desde ahí.
    Rol.DOCENTE: {},
    # El liquidador entra a ver y descargar las novedades de los períodos ya
    # cerrados; las vistas se encargan de no mostrarle los borradores.
    Rol.LIQUIDADOR: {"novedades": {modelo: SOLO_VER for modelo in NOVEDADES}},
}

# Roles que necesitan entrar al panel de administración.
ROLES_CON_ADMIN = {Rol.SECRETARIA, Rol.DIRECTIVO}

NOMBRE_GRUPO = {rol: f"Rol: {etiqueta}" for rol, etiqueta in Rol.choices}


def grupo_de(rol: str) -> Group:
    """Devuelve (creando si hace falta) el grupo que representa a ese rol."""
    grupo, _creado = Group.objects.get_or_create(name=NOMBRE_GRUPO[rol])
    return grupo


def sincronizar_permisos() -> dict[str, int]:
    """Crea los grupos de rol y deja sus permisos como los define este módulo.

    Es idempotente: se puede correr cuantas veces se quiera, y se debe correr
    después de agregar modelos nuevos (cada fase suma los suyos).
    """
    resumen = {}
    for rol, por_app in PERMISOS_POR_ROL.items():
        permisos = []
        for app_label, modelos in por_app.items():
            for modelo, acciones in modelos.items():
                tipo = ContentType.objects.filter(app_label=app_label, model=modelo).first()
                if tipo is None:
                    # El modelo todavía no existe (fase no implementada).
                    continue
                permisos.extend(
                    Permission.objects.filter(
                        content_type=tipo,
                        codename__in=[f"{accion}_{modelo}" for accion in acciones],
                    )
                )
        grupo = grupo_de(rol)
        grupo.permissions.set(permisos)
        resumen[rol] = len(permisos)
    return resumen
