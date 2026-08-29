"""Qué versión del sistema está corriendo.

Con el sistema en más de un lado —el servidor de la escuela, la PC de la
secretaría, la prueba de otra institución— lo primero que hay que saber cuando
algo no anda es si todos están mirando la misma versión. Un "a mí me funciona"
casi siempre es una versión distinta.

El número lo fija el equipo en ``VERSION``. La revisión exacta sale, por orden:

1. de la variable ``SGE_REVISION``, para cuando se despliega sin el repositorio;
2. de un archivo ``REVISION`` en la raíz, que puede escribir el despliegue;
3. de git, que es lo que hay en un servidor donde se clonó el proyecto.

Si no hay ninguna de las tres, se informa como desconocida y no pasa nada: es
un dato de diagnóstico, no algo de lo que dependa el funcionamiento.
"""

import importlib.util
import os
import platform
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import django
from django.conf import settings

# Se sube la minor al terminar cada fase (ver CHANGELOG.md). El 1.0 queda para
# cuando el sistema esté en uso diario en una escuela.
VERSION = "0.5.0"

# En qué punto del plan estamos, en castellano, para que se entienda sin tener
# que abrir el documento de requerimientos.
FASE = "F5 · Portal docente"

SIN_DATO = "desconocida"


@lru_cache(maxsize=1)
def revision() -> str:
    """Identificador corto del commit desplegado."""
    del_entorno = os.environ.get("SGE_REVISION", "").strip()
    if del_entorno:
        return del_entorno[:12]

    archivo = Path(settings.BASE_DIR) / "REVISION"
    try:
        guardada = archivo.read_text(encoding="utf-8").strip()
    except OSError:
        guardada = ""
    if guardada:
        return guardada[:12]

    return _preguntarle_a_git("%h")


@lru_cache(maxsize=1)
def fecha_revision() -> str:
    """Fecha del commit desplegado, en formato dd/mm/aaaa."""
    crudo = _preguntarle_a_git("%cd", "--date=format:%d/%m/%Y")
    return crudo


def _preguntarle_a_git(formato: str, *extra: str) -> str:
    """Consulta a git. Si no está, o esto no es un repositorio, no importa."""
    try:
        salida = subprocess.run(
            ["git", "log", "-1", f"--pretty=format:{formato}", *extra],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return SIN_DATO
    if salida.returncode != 0:
        return SIN_DATO
    return salida.stdout.strip() or SIN_DATO


def etiqueta() -> str:
    """Lo que se muestra al pie de cada pantalla: «SGE 0.5.0 · a1b2c3d»."""
    marca = f"SGE {VERSION}"
    revisada = revision()
    if revisada == SIN_DATO:
        return marca
    return f"{marca} · {revisada}"


def informacion() -> dict:
    """Todo lo que sirve para diagnosticar, en un solo lugar."""
    return {
        "version": VERSION,
        "fase": FASE,
        "revision": revision(),
        "fecha_revision": fecha_revision(),
        "python": platform.python_version(),
        "django": django.get_version(),
        "modo_depuracion": settings.DEBUG,
        "base_de_datos": _nombre_del_motor(),
        "zona_horaria": settings.TIME_ZONE,
        "hosts_permitidos": ", ".join(settings.ALLOWED_HOSTS) or "(ninguno)",
        "ejecutable": sys.executable,
        "opcionales": _dependencias_opcionales(),
    }


def _nombre_del_motor() -> str:
    motor = settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]
    return {
        "sqlite3": "SQLite (archivo local)",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
    }.get(motor, motor)


def _dependencias_opcionales() -> list[dict]:
    """Las pesadas, que pueden faltar en un hospedaje chico.

    No son un error: el sistema está hecho para funcionar sin ellas. Pero hay
    que poder ver de un vistazo por qué los PDF salen como página web o por qué
    el generador de horarios no aparece.
    """
    return [
        {
            "nombre": "OR-Tools",
            "para": "Generar los horarios automáticamente.",
            "disponible": importlib.util.find_spec("ortools") is not None,
            "sin_ella": "Los horarios se cargan a mano.",
        },
        {
            "nombre": "WeasyPrint",
            "para": "Certificaciones y planillas en PDF.",
            "disponible": _weasyprint_anda(),
            "sin_ella": "Los documentos salen como página web; se imprimen con Ctrl+P.",
        },
        {
            "nombre": "openpyxl",
            "para": "Exportar las novedades a Excel.",
            "disponible": importlib.util.find_spec("openpyxl") is not None,
            "sin_ella": "Queda la exportación a CSV.",
        },
    ]


def _weasyprint_anda() -> bool:
    """WeasyPrint se instala con pip pero necesita librerías del sistema.

    Que el paquete esté no alcanza: en Windows y en hospedajes pelados falta
    Pango y la importación falla. Por eso se prueba a importarlo de verdad.
    """
    try:
        import weasyprint  # noqa: F401
    except Exception:
        return False
    return True
