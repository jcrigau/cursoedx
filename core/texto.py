"""Buscar como se escribe, no como está guardado.

Nadie escribe «Benítez» con tilde al buscar, y menos con apuro. Postgres
resuelve esto con «unaccent», pero el sistema tiene que andar igual sobre
SQLite —que es con lo que se prueba y con lo que arranca una escuela chica—,
así que la comparación sin tildes se hace acá, en Python.

El costo es aceptable: un legajo por persona, unos cientos como mucho.
"""

import unicodedata


def sin_tildes(texto: str) -> str:
    """«Benítez» y «benitez» terminan siendo lo mismo."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(letra for letra in descompuesto if not unicodedata.combining(letra)).lower()


def contiene(texto: str, buscado: str) -> bool:
    """¿El texto contiene lo buscado, ignorando tildes y mayúsculas?"""
    return sin_tildes(buscado) in sin_tildes(texto)
