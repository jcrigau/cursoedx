"""El color de cada materia, estable en todas las pantallas.

Con diez etiquetas del mismo color, encontrar «quién puede dar Química» es
leer una por una. Con un color por materia, es un golpe de vista.

El color se asigna por el id de la materia, que no cambia nunca: Química es
del mismo color hoy, mañana y en cualquier pantalla, y agregar una materia
nueva no repinta a las demás. La paleta es de ocho tonos verificados para
daltonismo; con más de ocho materias los tonos se repiten, y no pasa nada:
el nombre está siempre escrito, el color solo ayuda a encontrarlo.
"""

from django import template

register = template.Library()

CANTIDAD_DE_TONOS = 8


@register.filter
def color_materia(materia) -> str:
    """La clase CSS del tono que le toca a esta materia."""
    if materia is None or not getattr(materia, "pk", None):
        return ""
    return f"tono-{materia.pk % CANTIDAD_DE_TONOS}"
