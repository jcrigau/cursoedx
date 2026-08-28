"""Reutiliza la escuela de prueba que arma el módulo de horarios.

El parte diario se apoya en el horario vigente, así que necesita exactamente la
misma estructura: no tiene sentido construir otra distinta.
"""

from horarios.tests.conftest import escuela  # noqa: F401  (fixture reexportada)
