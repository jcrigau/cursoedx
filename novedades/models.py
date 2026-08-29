"""Novedades para la liquidación y cierre mensual.

Todo lo que el sistema fue registrando durante el mes —altas, bajas, licencias,
inasistencias, suplencias— se compila acá en el formato que espera quien
liquida, separado en **Planilla Oficial** (los cargos que paga el estado) y
**Planilla Interna** (los que paga la escuela). El destino no lo elige nadie:
sale de la fuente de pago del cargo que originó la novedad, que es justamente
donde hoy se cometen los errores de ruteo.

Una vez cerrado el período las novedades quedan congeladas. Reabrirlo es
posible, pero queda registrado: son datos que ya se usaron para pagar sueldos.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloInstitucional, Usuario
from legajos.models import Cargo, FuentePago, Legajo

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class EstadoPeriodo(models.TextChoices):
    ABIERTO = "ABIERTO", "Abierto"
    CERRADO = "CERRADO", "Cerrado"
    REABIERTO = "REABIERTO", "Reabierto"


class PeriodoNovedades(ModeloInstitucional):
    """Un mes de liquidación."""

    anio = models.PositiveSmallIntegerField("año")
    mes = models.PositiveSmallIntegerField("mes")
    estado = models.CharField(
        "estado", max_length=10, choices=EstadoPeriodo.choices, default=EstadoPeriodo.ABIERTO
    )
    compilado_en = models.DateTimeField("compilado en", null=True, blank=True)
    cerrado_en = models.DateTimeField("cerrado en", null=True, blank=True)
    cerrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periodos_cerrados",
        verbose_name="cerrado por",
    )
    motivo_reapertura = models.CharField("motivo de la reapertura", max_length=300, blank=True)
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "período de novedades"
        verbose_name_plural = "períodos de novedades"
        ordering = ["-anio", "-mes"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "anio", "mes"], name="periodo_novedades_unico"
            )
        ]

    def __str__(self) -> str:
        return f"{MESES[self.mes - 1].capitalize()} {self.anio}"

    @property
    def esta_cerrado(self) -> bool:
        return self.estado == EstadoPeriodo.CERRADO

    @property
    def editable(self) -> bool:
        return not self.esta_cerrado

    def cerrar(self, usuario=None):
        """Congela las novedades del mes: ya no se tocan."""
        from django.utils import timezone

        from core.models import AccionAuditada, registrar_auditoria

        self.novedades.update(congelada=True)
        self.estado = EstadoPeriodo.CERRADO
        self.cerrado_en = timezone.now()
        self.cerrado_por = usuario
        self.save(update_fields=["estado", "cerrado_en", "cerrado_por", "actualizado_en"])

        registrar_auditoria(
            AccionAuditada.CIERRE_PERIODO,
            self,
            usuario=usuario,
            descripcion=f"Cierre de {self}",
            datos={"novedades": self.novedades.count()},
        )

    def reabrir(self, motivo: str, usuario=None):
        """Vuelve a abrir el mes. Queda auditado: los datos ya se usaron."""
        from core.models import AccionAuditada, registrar_auditoria

        self.novedades.update(congelada=False)
        self.estado = EstadoPeriodo.REABIERTO
        self.motivo_reapertura = motivo
        self.save(update_fields=["estado", "motivo_reapertura", "actualizado_en"])

        registrar_auditoria(
            AccionAuditada.REAPERTURA_PERIODO,
            self,
            usuario=usuario,
            descripcion=f"Reapertura de {self}: {motivo}",
        )

    def resumen(self) -> dict:
        novedades = self.novedades.all()
        a_informar = [n for n in novedades if n.impacta_haberes]
        return {
            "total": len(novedades),
            "a_informar": len(a_informar),
            "oficial": sum(1 for n in a_informar if n.destino == Destino.OFICIAL),
            "interna": sum(1 for n in a_informar if n.destino == Destino.INTERNA),
            "informadas": sum(1 for n in a_informar if n.informada),
            "pendientes": sum(1 for n in a_informar if not n.informada),
        }


class TipoNovedad(models.TextChoices):
    """Los mismos tipos que usa hoy la planilla del liquidador."""

    LICENCIA = "LICENCIA", "Licencia"
    ALTA = "ALTA", "Alta"
    CESE = "CESE", "Cese"
    RENUNCIA = "RENUNCIA", "Renuncia"
    CAMBIO = "CAMBIO", "Cambio"
    INASISTENCIA = "INASISTENCIA", "Inasistencia injustificada"
    TARDANZA = "TARDANZA", "Llegadas tarde"
    OTRA = "OTRA", "Otra novedad"


class Destino(models.TextChoices):
    OFICIAL = "OFICIAL", "Planilla Oficial"
    INTERNA = "INTERNA", "Planilla Interna"

    @classmethod
    def desde_fuente(cls, fuente_pago: str) -> str:
        """La planilla sale de quién paga el cargo, no de una elección manual."""
        return cls.OFICIAL if fuente_pago == FuentePago.SUBVENCIONADO else cls.INTERNA


class Origen(models.TextChoices):
    AUTOMATICA = "AUTOMATICA", "Compilada por el sistema"
    MANUAL = "MANUAL", "Cargada a mano"


class Novedad(ModeloInstitucional):
    """Una línea del informe mensual a quien liquida."""

    periodo = models.ForeignKey(
        PeriodoNovedades, on_delete=models.CASCADE, related_name="novedades", verbose_name="período"
    )
    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="novedades", verbose_name="docente"
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="novedades",
        verbose_name="cargo",
    )
    tipo = models.CharField("tipo", max_length=15, choices=TipoNovedad.choices)
    destino = models.CharField("planilla", max_length=10, choices=Destino.choices)

    fecha = models.DateField("fecha")
    fecha_fin = models.DateField("hasta", null=True, blank=True)
    dias = models.PositiveSmallIntegerField("días", null=True, blank=True)
    horas = models.PositiveSmallIntegerField("horas", null=True, blank=True)

    espacio = models.CharField(
        "espacio curricular / cargo",
        max_length=200,
        blank=True,
        help_text="Materia o denominación del cargo, como figura en la planilla.",
    )
    motivo = models.CharField("motivo", max_length=200, blank=True)
    reemplazante = models.CharField("reemplazante", max_length=200, blank=True)
    presenta_certificado = models.BooleanField("presenta certificado", default=False)
    jornada_completa = models.BooleanField("jornada completa", default=False)
    tiempo_determinado = models.BooleanField("tiempo determinado", default=False)
    observaciones = models.TextField("observaciones", blank=True)

    impacta_haberes = models.BooleanField(
        "impacta en la liquidación",
        default=True,
        help_text="Solo se informa lo que genera descuento o pago adicional.",
    )
    origen = models.CharField(
        "origen", max_length=12, choices=Origen.choices, default=Origen.AUTOMATICA
    )
    clave_origen = models.CharField(
        "clave de origen",
        max_length=100,
        blank=True,
        help_text="Identifica el hecho que la generó, para no duplicarla al recompilar.",
    )

    informada = models.BooleanField("informada al liquidador", default=False)
    informada_en = models.DateTimeField("informada el", null=True, blank=True)
    informada_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="novedades_informadas",
        verbose_name="informada por",
    )
    congelada = models.BooleanField(
        "congelada", default=False, help_text="Se congela al cerrar el período."
    )

    class Meta:
        verbose_name = "novedad"
        verbose_name_plural = "novedades"
        ordering = ["destino", "legajo__apellido", "fecha"]
        constraints = [
            models.UniqueConstraint(
                fields=["periodo", "clave_origen"],
                condition=models.Q(clave_origen__gt=""),
                name="una_novedad_por_hecho",
            )
        ]
        indexes = [
            models.Index(fields=["periodo", "destino"]),
            models.Index(fields=["periodo", "informada"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} · {self.legajo} · {self.fecha:%d/%m/%Y}"

    @property
    def nivel(self) -> str:
        if self.cargo_id and self.cargo.nivel_id:
            return self.cargo.nivel.get_tipo_display()
        return ""

    def marcar_informada(self, usuario=None):
        from django.utils import timezone

        self.informada = True
        self.informada_en = timezone.now()
        self.informada_por = usuario
        self.save(update_fields=["informada", "informada_en", "informada_por", "actualizado_en"])

    def save(self, *args, **kwargs):
        if self.congelada and self.pk:
            # Se permite marcar como informada aun con el período cerrado: es
            # el seguimiento del traspaso, no un cambio del dato liquidado.
            campos = set(kwargs.get("update_fields") or [])
            permitidos = {"informada", "informada_en", "informada_por", "actualizado_en"}
            if campos and not campos <= permitidos:
                raise ValidationError(
                    "La novedad está congelada: hay que reabrir el período para modificarla."
                )
        return super().save(*args, **kwargs)

    def clean(self):
        if self.fecha_fin and self.fecha and self.fecha_fin < self.fecha:
            raise ValidationError({"fecha_fin": "El fin no puede ser anterior al inicio."})

    def de_donde_salio(self) -> dict | None:
        """El hecho que originó esta novedad, en castellano y con su link.

        La pregunta inevitable frente al mes compilado es «¿y este renglón de
        dónde salió?». La respuesta ya está guardada en ``clave_origen``, que
        es lo que hace idempotente la compilación; acá se traduce a algo que
        se pueda leer y abrir.
        """
        if self.origen != Origen.AUTOMATICA or not self.clave_origen:
            return None

        from django.urls import NoReverseMatch, reverse

        partes = self.clave_origen.split(":")
        tipo = partes[0]
        identificador = partes[1] if len(partes) > 1 else ""

        textos = {
            "cargo_alta": "el alta del cargo",
            "cargo_baja": "la baja del cargo",
            "licencia": "la licencia cargada",
            "inasistencia": "lo marcado en el parte",
            "tardanzas": "las tardanzas marcadas en el parte",
        }
        destinos = {
            "cargo_alta": "admin:legajos_cargo_change",
            "cargo_baja": "admin:legajos_cargo_change",
            "licencia": "admin:licencias_licencia_change",
            "inasistencia": "admin:asistencia_registroasistencia_change",
        }

        texto = textos.get(tipo)
        if texto is None:
            return None

        url = ""
        if tipo in destinos and identificador.isdigit():
            try:
                url = reverse(destinos[tipo], args=[identificador])
            except NoReverseMatch:
                url = ""
        return {"texto": texto, "url": url}


def periodo_de(institucion, anio: int, mes: int, crear: bool = True):
    """Devuelve (y crea si hace falta) el período de un mes."""
    if crear:
        periodo, _creado = PeriodoNovedades.objects.get_or_create(
            institucion=institucion, anio=anio, mes=mes
        )
        return periodo
    return PeriodoNovedades.objects.filter(institucion=institucion, anio=anio, mes=mes).first()


def hoy_es_de(periodo) -> bool:
    """¿El período corresponde al mes en curso?"""
    hoy = date.today()
    return (periodo.anio, periodo.mes) == (hoy.year, hoy.month)
