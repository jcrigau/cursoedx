"""Errores de plantilla que no rompen nada: se imprimen en pantalla.

Son los peores de detectar mirando el código, porque Django no se queja: los
muestra al usuario como si fueran texto del sistema.
"""

import re
from pathlib import Path

from django.conf import settings

PLANTILLAS = sorted(Path(settings.BASE_DIR).glob("templates/**/*.html"))


def test_no_hay_comentarios_de_varias_lineas():
    """``{# … #}`` es de una sola línea; uno de varias se imprime tal cual.

    Para comentar varias líneas va ``{% comment %}``. El error no da ningún
    aviso: aparece el comentario impreso arriba de la pantalla.
    """
    fallas = []
    for plantilla in PLANTILLAS:
        texto = plantilla.read_text(encoding="utf-8")
        for apertura in re.finditer(r"\{#", texto):
            resto = texto[apertura.start() :]
            cierre = resto.find("#}")
            if cierre == -1 or "\n" in resto[:cierre]:
                linea = texto[: apertura.start()].count("\n") + 1
                fallas.append(f"{plantilla.name}:{linea}")

    assert not fallas, "Comentarios {# #} de varias líneas (usá {% comment %}): " + ", ".join(
        fallas
    )
