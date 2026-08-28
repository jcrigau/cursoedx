"""Managers para los modelos con institución.

El filtrado por institución es **explícito**: ``Modelo.objects.all()`` devuelve
todo (necesario para migraciones, comandos y soporte), mientras que
``Modelo.objects.del_contexto()`` devuelve solo lo de la institución activa.
Las vistas y el admin usan siempre la versión filtrada — el admin lo hace por
su cuenta en ``core.admin.AdminInstitucional``.
"""

from django.db import models

from .tenancy import get_institucion_actual


class InstitucionQuerySet(models.QuerySet):
    def de(self, institucion):
        """Filtra por una institución concreta."""
        return self.filter(institucion=institucion)

    def del_contexto(self):
        """Filtra por la institución activa; sin contexto no devuelve nada.

        Devolver un queryset vacío (en vez de todo) evita que un olvido de
        contexto termine mostrando datos de otra escuela.
        """
        institucion = get_institucion_actual()
        if institucion is None:
            return self.none()
        return self.filter(institucion=institucion)


InstitucionManager = models.Manager.from_queryset(InstitucionQuerySet)
