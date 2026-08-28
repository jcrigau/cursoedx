"""Institución activa del contexto (aislamiento multi-institución).

El SGE guarda los datos de todas las escuelas en una sola base: cada modelo de
negocio lleva ``institucion``. Para que las consultas no crucen datos entre
escuelas, el middleware deja acá la institución sobre la que trabaja el usuario
y los managers la usan al filtrar.

Se usa ``contextvars`` y no ``threading.local`` para que el valor siga siendo
correcto si en el futuro se sirven vistas asíncronas.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_institucion_actual: ContextVar = ContextVar("sge_institucion_actual", default=None)


def get_institucion_actual():
    """Institución sobre la que se está trabajando, o ``None`` fuera de request."""
    return _institucion_actual.get()


def set_institucion_actual(institucion):
    """Fija la institución del contexto y devuelve el token para restaurarla."""
    return _institucion_actual.set(institucion)


def reset_institucion_actual(token) -> None:
    _institucion_actual.reset(token)


@contextmanager
def usar_institucion(institucion):
    """Ejecuta un bloque con otra institución activa (comandos, tests, tareas)."""
    token = set_institucion_actual(institucion)
    try:
        yield institucion
    finally:
        reset_institucion_actual(token)
