"""Lo común a las planillas de Excel que van y vienen con la escuela.

Las plantillas llevan una fila de ejemplo para que se vea de qué forma va
cada dato. Nadie se acuerda de borrarla, así que el ejemplo se marca: la
primera celda empieza con la palabra ``EJEMPLO`` y cualquier importador la
saltea sin decir nada. Una fila de ejemplo que se cuela es una persona
inventada en el legajero.
"""

MARCA_EJEMPLO = "EJEMPLO"


def es_ejemplo(primera_celda) -> bool:
    """¿Esta fila es la de muestra que trae la plantilla?"""
    return str(primera_celda or "").strip().upper().startswith(MARCA_EJEMPLO)
