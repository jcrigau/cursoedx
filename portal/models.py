"""Portal del docente: avisos de inasistencia y fichaje.

Son los dos datos que hoy llegan por WhatsApp o por teléfono y que la
secretaría transcribe. Acá los carga la propia persona, con hora y —en el
fichaje— con la ubicación desde donde lo hizo.

Un aviso **no** es una licencia ni una falta justificada: es lo que la persona
informa. La secretaría lo confirma en el parte y, si corresponde, después se
carga la licencia con su certificado.
"""

from datetime import date, datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloInstitucional
from legajos.models import Legajo

RADIO_TIERRA_METROS = 6_371_000


def distancia_en_metros(lat_a: float, lon_a: float, lat_b: float, lon_b: float) -> float:
    """Distancia entre dos coordenadas sobre la superficie terrestre.

    Fórmula del semiverseno: para las distancias de una cuadra a unos
    kilómetros es más que suficiente y no necesita ninguna dependencia.
    """
    lat_a, lon_a, lat_b, lon_b = map(radians, (lat_a, lon_a, lat_b, lon_b))
    diferencia_lat = lat_b - lat_a
    diferencia_lon = lon_b - lon_a
    a = sin(diferencia_lat / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin(diferencia_lon / 2) ** 2
    return 2 * RADIO_TIERRA_METROS * asin(sqrt(a))


class MotivoAviso(models.TextChoices):
    ENFERMEDAD = "ENFERMEDAD", "Enfermedad"
    FAMILIAR = "FAMILIAR", "Atención de familiar"
    PARTICULAR = "PARTICULAR", "Razones particulares"
    TRAMITE = "TRAMITE", "Trámite o turno médico"
    OTRO = "OTRO", "Otro"


class EstadoAviso(models.TextChoices):
    ENVIADO = "ENVIADO", "Enviado"
    VISTO = "VISTO", "Visto por secretaría"
    ANULADO = "ANULADO", "Anulado por el docente"


class AvisoInasistencia(ModeloInstitucional):
    """El docente informa que no va a poder asistir."""

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="avisos", verbose_name="docente"
    )
    fecha = models.DateField("fecha de la ausencia")
    motivo = models.CharField("motivo", max_length=12, choices=MotivoAviso.choices)
    detalle = models.CharField("detalle", max_length=300, blank=True)
    estado = models.CharField(
        "estado", max_length=10, choices=EstadoAviso.choices, default=EstadoAviso.ENVIADO
    )
    visto_en = models.DateTimeField("visto en", null=True, blank=True)

    class Meta:
        verbose_name = "aviso de inasistencia"
        verbose_name_plural = "avisos de inasistencia"
        ordering = ["-fecha", "-creado_en"]
        constraints = [models.UniqueConstraint(fields=["legajo", "fecha"], name="un_aviso_por_dia")]
        indexes = [models.Index(fields=["institucion", "fecha"])]

    def __str__(self) -> str:
        return f"{self.legajo} avisa que falta el {self.fecha:%d/%m/%Y}"

    @property
    def anulable(self) -> bool:
        """Se puede dar de baja mientras la secretaría no lo haya visto."""
        return self.estado == EstadoAviso.ENVIADO and self.fecha >= date.today()

    def marcar_visto(self):
        from django.utils import timezone

        self.estado = EstadoAviso.VISTO
        self.visto_en = timezone.now()
        self.save(update_fields=["estado", "visto_en", "actualizado_en"])

    def clean(self):
        # Avisar de un día que ya pasó no tiene sentido: eso lo carga la
        # secretaría en el parte.
        if self.fecha and self.fecha < date.today():
            raise ValidationError({"fecha": "El aviso es para hoy o para un día que viene."})
        if self.fecha and self.fecha > date.today() + timedelta(days=60):
            raise ValidationError({"fecha": "La fecha está demasiado lejos."})


class TipoFichada(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada"
    SALIDA = "SALIDA", "Salida"


class Fichada(ModeloInstitucional):
    """Marca de entrada o salida hecha desde el celular.

    Se guarda siempre, esté o no dentro del radio de la escuela: la ubicación
    puede fallar por mil motivos y no se le puede negar a alguien la constancia
    de que llegó. Lo que queda es el dato para que la escuela lo revise.
    """

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="fichadas", verbose_name="docente"
    )
    fecha = models.DateField("fecha")
    hora = models.TimeField("hora")
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoFichada.choices, default=TipoFichada.ENTRADA
    )
    latitud = models.FloatField("latitud", null=True, blank=True)
    longitud = models.FloatField("longitud", null=True, blank=True)
    precision_metros = models.PositiveIntegerField("precisión (m)", null=True, blank=True)
    distancia_metros = models.PositiveIntegerField(
        "distancia a la escuela (m)", null=True, blank=True
    )
    en_la_escuela = models.BooleanField(
        "dentro del radio",
        default=False,
        help_text="Se calcula al fichar, comparando con la ubicación de la escuela.",
    )
    observaciones = models.CharField("observaciones", max_length=200, blank=True)

    class Meta:
        verbose_name = "fichada"
        verbose_name_plural = "fichadas"
        ordering = ["-fecha", "-hora"]
        constraints = [
            models.UniqueConstraint(
                fields=["legajo", "fecha", "tipo"], name="una_fichada_por_tipo_y_dia"
            )
        ]
        indexes = [models.Index(fields=["institucion", "fecha"])]

    def __str__(self) -> str:
        return f"{self.legajo} · {self.get_tipo_display()} {self.fecha:%d/%m} {self.hora:%H:%M}"

    @property
    def cuando(self) -> datetime:
        return datetime.combine(self.fecha, self.hora)

    def calcular_ubicacion(self):
        """Compara con la ubicación de la escuela, si está configurada."""
        institucion = self.institucion
        if None in (self.latitud, self.longitud, institucion.latitud, institucion.longitud):
            self.distancia_metros = None
            self.en_la_escuela = False
            return

        distancia = distancia_en_metros(
            self.latitud, self.longitud, institucion.latitud, institucion.longitud
        )
        self.distancia_metros = int(distancia)
        self.en_la_escuela = distancia <= institucion.radio_fichaje_metros

    def save(self, *args, **kwargs):
        if self.institucion_id and self.distancia_metros is None:
            self.calcular_ubicacion()
        super().save(*args, **kwargs)
