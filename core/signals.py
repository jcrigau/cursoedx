"""Efectos automáticos al dar de alta o de baja una membresía."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Membresia
from .permisos import ROLES_CON_ADMIN, grupo_de


@receiver(post_save, sender=Membresia)
def aplicar_rol(sender, instance: Membresia, **kwargs):
    """Al asignar un rol, el usuario recibe sus permisos y el acceso al panel."""
    usuario = instance.usuario
    grupo = grupo_de(instance.rol)

    if instance.activa:
        usuario.groups.add(grupo)
        if instance.rol in ROLES_CON_ADMIN and not usuario.is_staff:
            usuario.is_staff = True
            usuario.save(update_fields=["is_staff"])
    else:
        quitar_rol_si_ya_no_lo_tiene(usuario, instance.rol)


@receiver(post_delete, sender=Membresia)
def quitar_rol(sender, instance: Membresia, **kwargs):
    quitar_rol_si_ya_no_lo_tiene(instance.usuario, instance.rol)


def quitar_rol_si_ya_no_lo_tiene(usuario, rol: str) -> None:
    """Saca el grupo solo si el usuario perdió ese rol en todas las escuelas.

    Alguien puede ser secretaria en dos instituciones: perder una no lo deja
    sin permisos en la otra.
    """
    if usuario.membresias.filter(rol=rol, activa=True).exists():
        return
    usuario.groups.remove(grupo_de(rol))

    sin_roles_de_admin = not usuario.membresias.filter(
        rol__in=ROLES_CON_ADMIN, activa=True
    ).exists()
    if sin_roles_de_admin and usuario.is_staff and not usuario.is_superuser:
        usuario.is_staff = False
        usuario.save(update_fields=["is_staff"])
