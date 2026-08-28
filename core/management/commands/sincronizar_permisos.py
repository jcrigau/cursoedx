"""Crea los grupos de rol, actualiza sus permisos y los reaplica a los usuarios.

Hay que correrlo después de cada fase que agregue modelos nuevos, para que los
roles existentes puedan administrarlos. Es idempotente.
"""

from django.core.management.base import BaseCommand

from core.models import Membresia, Rol
from core.permisos import ROLES_CON_ADMIN, grupo_de, sincronizar_permisos


class Command(BaseCommand):
    help = "Crea los grupos de rol, les asigna permisos y los reaplica a los usuarios."

    def handle(self, *args, **opciones):
        resumen = sincronizar_permisos()
        etiquetas = dict(Rol.choices)
        for rol, cantidad in resumen.items():
            self.stdout.write(f"  {etiquetas[rol]}: {cantidad} permisos")

        # Las membresías anteriores a esta sincronización pueden haber quedado
        # sin grupo: se las vuelve a aplicar.
        reaplicadas = 0
        for membresia in Membresia.objects.filter(activa=True).select_related("usuario"):
            usuario = membresia.usuario
            usuario.groups.add(grupo_de(membresia.rol))
            if membresia.rol in ROLES_CON_ADMIN and not usuario.is_staff:
                usuario.is_staff = True
                usuario.save(update_fields=["is_staff"])
            reaplicadas += 1

        self.stdout.write(f"  membresías reaplicadas: {reaplicadas}")
        self.stdout.write(self.style.SUCCESS("Permisos sincronizados."))
