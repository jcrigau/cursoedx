"""Datos comunes a todas las plantillas."""

from .tenancy import get_institucion_actual
from .version import etiqueta


def institucion_actual(request):
    """Expone la institución activa y las disponibles para el selector."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"institucion_actual": None, "instituciones_disponibles": []}
    return {
        "institucion_actual": get_institucion_actual(),
        "instituciones_disponibles": usuario.instituciones(),
    }


def version_del_sistema(request):
    """La versión al pie de cada pantalla.

    Sirve para el soporte: cuando alguien avisa que algo no anda, lo primero
    es saber qué versión está mirando.
    """
    return {"version_sge": etiqueta()}
