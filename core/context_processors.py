"""Datos comunes a todas las plantillas."""

from .tenancy import get_institucion_actual


def institucion_actual(request):
    """Expone la institución activa y las disponibles para el selector."""
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"institucion_actual": None, "instituciones_disponibles": []}
    return {
        "institucion_actual": get_institucion_actual(),
        "instituciones_disponibles": usuario.instituciones(),
    }
