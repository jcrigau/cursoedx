"""A quién le escribe el sistema cuando pasa algo en una escuela.

Los correos de gestión —el resumen de las 7:00, el aviso de un docente que
falta— van a las mismas personas: quienes tienen rol de secretaría o de
dirección en esa institución y cargaron su email.
"""

from .models import Membresia, Rol


def emails_de_gestion(institucion) -> list[str]:
    """Los emails de secretaría y dirección de la escuela, sin repetir."""
    return sorted(
        {
            membresia.usuario.email
            for membresia in Membresia.objects.filter(
                institucion=institucion,
                activa=True,
                rol__in=[Rol.SECRETARIA, Rol.DIRECTIVO],
            ).select_related("usuario")
            if membresia.usuario.email
        }
    )
