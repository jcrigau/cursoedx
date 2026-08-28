"""Efectos de una licencia sobre la asistencia ya registrada.

El caso real: el docente falta, la secretaría lo marca ausente, y días después
trae el certificado. Al aprobarse la licencia, esas faltas tienen que quedar
justificadas solas — si no, aparecerían como inasistencias injustificadas en el
resumen del mes y se le descontarían mal.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from licencias.models import EstadoLicencia, Licencia

from .models import EstadoAsistencia, RegistroAsistencia


@receiver(post_save, sender=Licencia)
def justificar_ausencias_alcanzadas(sender, instance: Licencia, **kwargs):
    """Vincula a la licencia las ausencias ya registradas que ahora cubre."""
    if instance.estado != EstadoLicencia.APROBADA:
        return

    RegistroAsistencia.objects.filter(
        legajo_id=instance.legajo_id,
        fecha__gte=instance.fecha_inicio,
        fecha__lte=instance.fecha_fin,
        estado__in=[EstadoAsistencia.AUSENTE, EstadoAsistencia.PARCIAL],
        licencia__isnull=True,
    ).update(licencia=instance)
