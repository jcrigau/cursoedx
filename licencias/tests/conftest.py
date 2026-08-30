"""Fixtures del módulo de licencias.

La escuela de prueba se reutiliza de horarios: para decidir una cobertura hace
falta un cargo real sobre un curso, que es lo que arma esa estructura.
"""

from asistencia.tests.conftest import con_horario_publicado  # noqa: F401  (fixture reexportada)
from horarios.tests.conftest import escuela  # noqa: F401  (fixture reexportada)
