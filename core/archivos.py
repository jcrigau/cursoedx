"""Los archivos que sube la escuela: quién puede abrir cuál.

En esta carpeta hay aptos psicofísicos, certificados de antecedentes y
certificados médicos: datos de salud y personales. Django no sirve nada de
esto en producción, y mapearlo en el hosting los dejaría públicos, así que los
sirve la aplicación.

**Estar conectado no alcanza.** Los docentes también tienen usuario: si la
única condición fuera el login, cualquiera podría abrir el certificado médico
de otro con solo escribir la dirección. Cada archivo se autoriza contra el
registro al que pertenece, con la misma regla que el resto del sistema —el rol
dice qué, la institución dice sobre qué datos— más una excepción evidente:
**lo propio siempre se puede ver**.

Un archivo que no corresponde a ningún registro conocido no se entrega. Se
falla cerrado: es preferible un 404 sobre algo válido a una filtración sobre
algo que nadie previó.
"""

from dataclasses import dataclass
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.utils.deconstruct import deconstructible
from django.views.static import serve as servir_archivo


@deconstructible
class CarpetaProtegida:
    """Guarda el archivo bajo un nombre de carpeta impredecible.

    La autorización es lo que protege de verdad; esto evita además que una
    dirección adivinada —«documentos/apto.pdf»— exista siquiera. Los archivos
    que ya estaban guardados siguen donde están y se sirven igual.
    """

    def __init__(self, carpeta: str):
        self.carpeta = carpeta

    def __call__(self, instancia, nombre: str) -> str:
        return f"{self.carpeta}/{uuid4().hex}/{nombre}"

    def __eq__(self, otra):
        return isinstance(otra, CarpetaProtegida) and otra.carpeta == self.carpeta


# Lo único que la escuela necesita subir: papeles escaneados y fotos. Todo lo
# demás se rechaza. Importa sobre todo lo que **no** está: .html y .svg son
# archivos que el navegador ejecuta, y alguien de adentro podría subir uno y
# pasarle el enlace a un compañero para robarle la sesión.
EXTENSIONES_PERMITIDAS = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx", ".odt", ".txt"}
)
MEGAS_MAXIMOS = 10

# Lo que el navegador puede mostrar sin riesgo; el resto se baja en vez de
# abrirse.
SE_MUESTRAN = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".webp"})


def validar_adjunto(archivo):
    """Rechaza lo que no es un papel escaneado o una foto."""
    from pathlib import PurePath

    from django.core.exceptions import ValidationError

    extension = PurePath(archivo.name).suffix.lower()
    if extension not in EXTENSIONES_PERMITIDAS:
        permitidas = ", ".join(sorted(EXTENSIONES_PERMITIDAS))
        raise ValidationError(
            f"«{extension or archivo.name}» no se puede subir. Se aceptan: {permitidas}."
        )
    if archivo.size and archivo.size > MEGAS_MAXIMOS * 1024 * 1024:
        raise ValidationError(
            f"El archivo pesa {archivo.size / 1024 / 1024:.1f} MB y el máximo es "
            f"{MEGAS_MAXIMOS} MB. Escaneá en blanco y negro o con menos calidad."
        )


@dataclass(frozen=True)
class Regla:
    """De qué registro cuelga un archivo y quién puede abrirlo."""

    modelo: str  # "app.Modelo"
    campo: str
    permiso: str
    # Cómo llegar al legajo dueño desde el registro. Vacío: el registro es el
    # legajo (la foto).
    hacia_el_legajo: str = ""


# Prefijo de la ruta -> regla. Se prueban del más específico al más general,
# así «licencias/avales/» no se lo come «licencias/».
REGLAS: dict[str, Regla] = {
    "documentos/": Regla(
        "legajos.DocumentoLegajo", "archivo", "legajos.view_documentolegajo", "legajo"
    ),
    "titulos/": Regla("legajos.Titulo", "archivo", "legajos.view_titulo", "legajo"),
    "servicios/": Regla(
        "legajos.ServicioAnterior", "archivo", "legajos.view_servicioanterior", "legajo"
    ),
    "resoluciones/": Regla("legajos.Cargo", "resolucion_archivo", "legajos.view_cargo", "legajo"),
    "fotos/": Regla("legajos.Legajo", "foto", "legajos.view_legajo"),
    "licencias/avales/": Regla("licencias.Licencia", "aval", "licencias.view_licencia", "legajo"),
    "licencias/": Regla("licencias.Licencia", "certificado", "licencias.view_licencia", "legajo"),
    "ddjj/": Regla(
        "horarios.DeclaracionDisponibilidad",
        "archivo",
        "horarios.view_declaraciondisponibilidad",
        "legajo",
    ),
}


def _regla_de(ruta: str) -> Regla | None:
    for prefijo in sorted(REGLAS, key=len, reverse=True):
        if ruta.startswith(prefijo):
            return REGLAS[prefijo]
    return None


def _duenio_del_archivo(regla: Regla, ruta: str):
    """El legajo al que pertenece el archivo, o None si no existe el registro."""
    from django.apps import apps

    modelo = apps.get_model(regla.modelo)
    registro = modelo.objects.filter(**{regla.campo: ruta}).select_related().first()
    if registro is None:
        return None
    return getattr(registro, regla.hacia_el_legajo) if regla.hacia_el_legajo else registro


def puede_abrir(usuario, legajo, permiso: str) -> bool:
    """¿Este usuario puede abrir un archivo de ese legajo?"""
    if usuario.is_superuser:
        return True
    # Lo propio siempre: es su certificado, su título, su foto.
    if legajo.usuario_id and legajo.usuario_id == usuario.id:
        return True
    # El permiso es global; la institución es la que acota los datos. Hacen
    # falta las dos cosas, o una secretaria vería los legajos de otra escuela.
    return bool(usuario.has_perm(permiso) and usuario.roles_en(legajo.institucion))


@login_required
def servir_media(request, path):
    """Entrega un archivo subido, si quien lo pide tiene por qué verlo."""
    from django.conf import settings

    regla = _regla_de(path)
    if regla is None:
        raise Http404("Archivo desconocido.")

    legajo = _duenio_del_archivo(regla, path)
    # Un 404 y no un 403: quien no puede verlo tampoco tiene por qué enterarse
    # de que existe.
    if legajo is None or not puede_abrir(request.user, legajo, regla.permiso):
        raise Http404("Archivo no disponible.")

    # django.views.static.serve resuelve la ruta contra document_root y
    # rechaza los intentos de salirse de la carpeta.
    respuesta = servir_archivo(request, path, document_root=settings.MEDIA_ROOT)
    return _entregar_con_cuidado(respuesta, path)


def _entregar_con_cuidado(respuesta, ruta: str):
    """Que el navegador no adivine el tipo ni ejecute lo que no corresponde."""
    from pathlib import PurePath

    respuesta["X-Content-Type-Options"] = "nosniff"
    nombre = PurePath(ruta)
    if nombre.suffix.lower() not in SE_MUESTRAN:
        # Un archivo que el navegador no debería abrir se baja y se abre con
        # el programa que corresponda.
        respuesta["Content-Disposition"] = f'attachment; filename="{nombre.name}"'
    return respuesta
