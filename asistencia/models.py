"""Registro de asistencia del personal.

Se guarda un registro por persona y día, y solo cuando hay algo que anotar: la
secretaría marca las novedades del día (quién faltó, quién llegó tarde) y no
tiene que confirmar uno por uno a los que vinieron.

Una ausencia queda **justificada** cuando está vinculada a una licencia
aprobada. Las que no lo estén son las que después se informan como inasistencia
injustificada.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloInstitucional, Usuario
from legajos.models import Legajo
from licencias.models import Licencia


class EstadoAsistencia(models.TextChoices):
    PRESENTE = "PRESENTE", "Presente"
    AUSENTE = "AUSENTE", "Ausente"
    TARDE = "TARDE", "Llegada tarde"
    RETIRO = "RETIRO", "Retiro anticipado"
    PARCIAL = "PARCIAL", "Ausencia parcial"


class RegistroAsistencia(ModeloInstitucional):
    """Lo que pasó con una persona en un día."""

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="asistencias", verbose_name="docente"
    )
    fecha = models.DateField("fecha")
    estado = models.CharField("estado", max_length=10, choices=EstadoAsistencia.choices)
    horas_afectadas = models.PositiveSmallIntegerField(
        "horas afectadas",
        null=True,
        blank=True,
        help_text="Para ausencias parciales: cuántas horas no dio.",
    )
    hora = models.TimeField(
        "hora",
        null=True,
        blank=True,
        help_text="Hora de llegada o de retiro, según el caso.",
    )
    licencia = models.ForeignKey(
        Licencia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asistencias",
        verbose_name="licencia que la justifica",
    )
    observaciones = models.CharField("observaciones", max_length=300, blank=True)
    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asistencias_registradas",
        verbose_name="registrado por",
    )

    class Meta:
        verbose_name = "registro de asistencia"
        verbose_name_plural = "asistencia"
        ordering = ["-fecha", "legajo"]
        constraints = [
            models.UniqueConstraint(
                fields=["legajo", "fecha"], name="un_registro_por_persona_y_dia"
            )
        ]
        indexes = [models.Index(fields=["institucion", "fecha"])]

    def __str__(self) -> str:
        return f"{self.legajo} · {self.fecha:%d/%m/%Y} · {self.get_estado_display()}"

    @property
    def es_ausencia(self) -> bool:
        return self.estado in {EstadoAsistencia.AUSENTE, EstadoAsistencia.PARCIAL}

    @property
    def justificada(self) -> bool:
        """Una ausencia está justificada si se apoya en una licencia aprobada."""
        return self.licencia_id is not None

    @property
    def injustificada(self) -> bool:
        return self.es_ausencia and not self.justificada

    def clean(self):
        errores = {}

        if self.estado == EstadoAsistencia.PARCIAL and not self.horas_afectadas:
            errores["horas_afectadas"] = "Indicá cuántas horas no dio."
        if self.estado in {EstadoAsistencia.TARDE, EstadoAsistencia.RETIRO} and not self.hora:
            errores["hora"] = "Indicá la hora."
        if self.licencia_id and self.legajo_id and self.licencia.legajo_id != self.legajo_id:
            errores["licencia"] = "La licencia es de otra persona."
        if self.licencia_id and self.fecha and not self.licencia.incluye(self.fecha):
            errores["licencia"] = "La licencia no cubre esa fecha."
        if self.fecha and self.fecha > date.today():
            errores["fecha"] = "No se puede registrar asistencia de un día que no pasó."

        if errores:
            raise ValidationError(errores)


def buscar_licencia_que_justifica(legajo, fecha: date):
    """Licencia aprobada de esa persona que cubra la fecha, si existe."""
    from licencias.models import EstadoLicencia

    return (
        Licencia.objects.filter(
            legajo=legajo,
            estado=EstadoLicencia.APROBADA,
            fecha_inicio__lte=fecha,
            fecha_fin__gte=fecha,
        )
        .select_related("tipo")
        .first()
    )
