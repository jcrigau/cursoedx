"""Licencias del personal y cobertura de las horas que dejan libres.

El catálogo de tipos es configurable por institución porque cada jurisdicción
tiene su régimen: artículo, si es con goce de haberes, y los topes de días.
Los topes se controlan al cargar la licencia, que es cuando todavía se puede
corregir; los que admiten prórroga (la enfermedad más allá de los 60 días, con
junta médica) se pueden superar dejando constancia del aval.

Una licencia no obliga a cubrir las horas: la escuela decide caso por caso si
designa un suplente o si el curso queda sin clase. Esa decisión se registra,
porque después hay que explicarla.
"""

from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import ModeloInstitucional, Usuario
from legajos.models import Cargo, Legajo


class TipoLicencia(ModeloInstitucional):
    """Un artículo del régimen de licencias, con sus condiciones."""

    codigo = models.CharField("código", max_length=20, blank=True, help_text='Ej.: "Art. 76".')
    nombre = models.CharField("denominación", max_length=150)
    con_goce = models.BooleanField(
        "con goce de haberes",
        default=True,
        help_text="Si no tiene goce, el descuento se informa a quien liquida.",
    )
    impacta_haberes = models.BooleanField(
        "impacta en la liquidación",
        default=True,
        help_text="Solo se informan las novedades que generan descuento o pago adicional.",
    )
    requiere_certificado = models.BooleanField("requiere certificado", default=False)

    tope_dias_anual = models.PositiveSmallIntegerField(
        "tope de días por año", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    tope_dias_por_caso = models.PositiveSmallIntegerField(
        "tope de días por caso", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    tope_dias_consecutivos = models.PositiveSmallIntegerField(
        "máximo de días consecutivos", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    extensible_con_aval = models.BooleanField(
        "se puede extender con aval",
        default=False,
        help_text="Ej.: enfermedad más allá del tope, con junta médica.",
    )
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "tipo de licencia"
        verbose_name_plural = "tipos de licencia"
        ordering = ["codigo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "nombre"], name="tipo_licencia_unico_por_nombre"
            )
        ]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.nombre}" if self.codigo else self.nombre


class EstadoLicencia(models.TextChoices):
    SOLICITADA = "SOLICITADA", "Solicitada"
    APROBADA = "APROBADA", "Aprobada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    CANCELADA = "CANCELADA", "Cancelada"


class Licencia(ModeloInstitucional):
    """Una licencia concreta de una persona, en un período de fechas."""

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="licencias", verbose_name="docente"
    )
    tipo = models.ForeignKey(
        TipoLicencia, on_delete=models.PROTECT, related_name="licencias", verbose_name="tipo"
    )
    fecha_inicio = models.DateField("desde")
    fecha_fin = models.DateField("hasta")
    estado = models.CharField(
        "estado", max_length=12, choices=EstadoLicencia.choices, default=EstadoLicencia.SOLICITADA
    )

    cargos = models.ManyToManyField(
        Cargo,
        blank=True,
        related_name="licencias",
        verbose_name="cargos afectados",
        help_text="Si se deja vacío, se entiende que afecta a todos los cargos vigentes.",
    )

    certificado = models.FileField("certificado", upload_to="licencias/", blank=True)
    aval = models.FileField(
        "aval de la extensión",
        upload_to="licencias/avales/",
        blank=True,
        help_text="Junta médica u otra autorización, cuando se supera el tope.",
    )
    prorroga_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prorrogas",
        verbose_name="prórroga de",
    )

    solicitada_en = models.DateField("solicitada el", default=date.today)
    resuelta_en = models.DateField("resuelta el", null=True, blank=True)
    resuelta_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="licencias_resueltas",
        verbose_name="resuelta por",
    )
    motivo_rechazo = models.CharField("motivo del rechazo", max_length=300, blank=True)
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "licencia"
        verbose_name_plural = "licencias"
        ordering = ["-fecha_inicio"]
        indexes = [
            models.Index(fields=["institucion", "fecha_inicio", "fecha_fin"]),
            models.Index(fields=["legajo", "estado"]),
        ]

    def __str__(self) -> str:
        return f"{self.legajo} · {self.tipo} ({self.fecha_inicio:%d/%m/%Y} a {self.fecha_fin:%d/%m/%Y})"

    # -- duración y vigencia -------------------------------------------------

    @property
    def dias(self) -> int:
        """Días corridos, contando el primero y el último."""
        return (self.fecha_fin - self.fecha_inicio).days + 1

    def incluye(self, fecha: date) -> bool:
        return self.fecha_inicio <= fecha <= self.fecha_fin

    def vigente_en(self, fecha: date) -> bool:
        """Aprobada y en curso a esa fecha."""
        return self.estado == EstadoLicencia.APROBADA and self.incluye(fecha)

    @property
    def situacion(self) -> str:
        """Cómo está hoy, para mostrar en los listados."""
        hoy = date.today()
        if self.estado != EstadoLicencia.APROBADA:
            return self.get_estado_display()
        if self.fecha_fin < hoy:
            return "Finalizada"
        if self.fecha_inicio > hoy:
            return "Por comenzar"
        return "En curso"

    def cargos_afectados(self):
        """Cargos que quedan sin cubrir mientras dure la licencia."""
        elegidos = self.cargos.all()
        if elegidos.exists():
            return elegidos
        return self.legajo.cargos_vigentes(self.fecha_inicio)

    # -- flujo ---------------------------------------------------------------

    def aprobar(self, usuario=None):
        self.estado = EstadoLicencia.APROBADA
        self.resuelta_en = date.today()
        self.resuelta_por = usuario
        self.save(update_fields=["estado", "resuelta_en", "resuelta_por", "actualizado_en"])

    def rechazar(self, motivo: str = "", usuario=None):
        self.estado = EstadoLicencia.RECHAZADA
        self.motivo_rechazo = motivo
        self.resuelta_en = date.today()
        self.resuelta_por = usuario
        self.save(
            update_fields=[
                "estado",
                "motivo_rechazo",
                "resuelta_en",
                "resuelta_por",
                "actualizado_en",
            ]
        )

    # -- topes ---------------------------------------------------------------

    def dias_usados_en_el_anio(self, excluir_esta: bool = True) -> int:
        """Días del mismo tipo ya tomados en el año de inicio de esta licencia.

        Cuenta solo las licencias aprobadas: una solicitud pendiente todavía no
        consumió nada.
        """
        anio = self.fecha_inicio.year
        otras = Licencia.objects.filter(
            legajo_id=self.legajo_id,
            tipo_id=self.tipo_id,
            estado=EstadoLicencia.APROBADA,
            fecha_inicio__year=anio,
        )
        if excluir_esta and self.pk:
            otras = otras.exclude(pk=self.pk)
        return sum(otra.dias for otra in otras)

    def excesos(self) -> list[str]:
        """Topes que esta licencia supera. Vacío si está todo en orden."""
        if not self.tipo_id or not self.fecha_inicio or not self.fecha_fin:
            return []

        avisos = []
        tipo = self.tipo

        if tipo.tope_dias_por_caso and self.dias > tipo.tope_dias_por_caso:
            avisos.append(
                f"{self.dias} días superan el máximo de {tipo.tope_dias_por_caso} por caso."
            )
        if tipo.tope_dias_consecutivos and self.dias > tipo.tope_dias_consecutivos:
            avisos.append(
                f"{self.dias} días seguidos superan el máximo de "
                f"{tipo.tope_dias_consecutivos} consecutivos."
            )
        if tipo.tope_dias_anual:
            usados = self.dias_usados_en_el_anio()
            if usados + self.dias > tipo.tope_dias_anual:
                avisos.append(
                    f"Con esta licencia acumula {usados + self.dias} días en el año y el "
                    f"tope es de {tipo.tope_dias_anual}."
                )
        return avisos

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "El fin no puede ser anterior al inicio."})

        excesos = self.excesos()
        if not excesos:
            return
        # Los tipos que admiten prórroga se pueden pasar del tope si consta el
        # aval (por ejemplo, la junta médica en las licencias por enfermedad).
        if self.tipo.extensible_con_aval and self.aval:
            return
        detalle = " ".join(excesos)
        if self.tipo.extensible_con_aval:
            detalle += " Se puede continuar adjuntando el aval correspondiente."
        raise ValidationError({"fecha_fin": detalle})


class TipoCobertura(models.TextChoices):
    SUPLENTE = "SUPLENTE", "Se designa un suplente"
    SIN_COBERTURA = "SIN_COBERTURA", "Sin cobertura (los alumnos quedan libres)"


class ViaAviso(models.TextChoices):
    EMAIL = "EMAIL", "Email"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    OTRO = "OTRO", "En persona o por teléfono"


class Cobertura(ModeloInstitucional):
    """Qué se hace con las horas de un cargo mientras el titular está de licencia.

    Se registra también la decisión de **no** cubrir: es información que la
    escuela necesita para saber qué cursos quedaron sin clase y por qué.
    """

    licencia = models.ForeignKey(
        Licencia, on_delete=models.CASCADE, related_name="coberturas", verbose_name="licencia"
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.CASCADE,
        related_name="coberturas",
        verbose_name="cargo del titular",
    )
    tipo = models.CharField(
        "decisión", max_length=15, choices=TipoCobertura.choices, default=TipoCobertura.SUPLENTE
    )
    suplente = models.ForeignKey(
        Legajo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="suplencias",
        verbose_name="suplente",
    )
    cargo_suplente = models.OneToOneField(
        Cargo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cobertura_de_origen",
        verbose_name="designación del suplente",
        help_text="Se crea automáticamente al designar, para que el suplente tenga su cargo.",
    )
    fecha_inicio = models.DateField("desde")
    fecha_fin = models.DateField("hasta")
    observaciones = models.CharField("observaciones", max_length=300, blank=True)

    # Designar no es avisar: el suplente tiene que enterarse, y la escuela
    # necesita saber si ya se le avisó o todavía no. Sin esto, la pregunta
    # «¿alguien lo llamó?» solo se responde preguntando.
    notificada_en = models.DateTimeField("avisado el", null=True, blank=True)
    notificada_por = models.CharField(
        "avisado por", max_length=10, choices=ViaAviso.choices, blank=True
    )

    class Meta:
        verbose_name = "cobertura"
        verbose_name_plural = "coberturas de licencias"
        ordering = ["-fecha_inicio"]
        indexes = [models.Index(fields=["institucion", "fecha_inicio", "fecha_fin"])]

    def __str__(self) -> str:
        if self.tipo == TipoCobertura.SIN_COBERTURA:
            return f"{self.cargo.descripcion} · sin cobertura"
        return f"{self.cargo.descripcion} · cubre {self.suplente}"

    @property
    def dias(self) -> int:
        return (self.fecha_fin - self.fecha_inicio).days + 1

    def incluye(self, fecha: date) -> bool:
        return self.fecha_inicio <= fecha <= self.fecha_fin

    @property
    def por_vencer(self) -> bool:
        """Termina dentro de la semana: conviene avisar para renovar o cesar."""
        if self.tipo != TipoCobertura.SUPLENTE:
            return False
        faltan = (self.fecha_fin - date.today()).days
        return 0 <= faltan <= 7

    def clean(self):
        errores = {}
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            errores["fecha_fin"] = "El fin no puede ser anterior al inicio."

        if self.tipo == TipoCobertura.SUPLENTE and not self.suplente_id:
            errores["suplente"] = "Indicá quién cubre el cargo."
        if self.tipo == TipoCobertura.SIN_COBERTURA and self.suplente_id:
            errores["suplente"] = "Sin cobertura no lleva suplente."
        if self.suplente_id and self.cargo_id and self.suplente_id == self.cargo.legajo_id:
            errores["suplente"] = "Una persona no puede ser suplente de sí misma."

        if self.licencia_id and self.fecha_inicio and self.fecha_fin:
            licencia = self.licencia
            if self.fecha_inicio < licencia.fecha_inicio or self.fecha_fin > licencia.fecha_fin:
                errores["fecha_inicio"] = (
                    "La cobertura tiene que estar dentro del período de la licencia "
                    f"({licencia.fecha_inicio:%d/%m/%Y} a {licencia.fecha_fin:%d/%m/%Y})."
                )

        if errores:
            raise ValidationError(errores)

    def designar_cargo_del_suplente(self) -> Cargo | None:
        """Le crea al suplente el cargo que va a ocupar, copiado del titular.

        Así el suplente aparece en el parte diario y en las grillas mientras
        dure la suplencia, y su alta y su cese salen como novedades (F4).
        """
        if self.tipo != TipoCobertura.SUPLENTE or not self.suplente_id:
            return None
        if self.cargo_suplente_id:
            return self.cargo_suplente

        from legajos.models import SituacionRevista

        titular = self.cargo
        cargo = Cargo.objects.create(
            institucion=self.institucion,
            legajo=self.suplente,
            tipo=titular.tipo,
            denominacion=titular.denominacion,
            nivel=titular.nivel,
            materia=titular.materia,
            curso=titular.curso,
            horas_semanales=titular.horas_semanales,
            jornada_completa=titular.jornada_completa,
            situacion_revista=SituacionRevista.SUPLENTE,
            fuente_pago=titular.fuente_pago,
            fecha_alta=self.fecha_inicio,
            fecha_baja=self.fecha_fin,
            motivo_baja="FIN_SUPLENCIA",
            observaciones=f"Suplencia de {titular.legajo.nombre_completo}.",
        )
        self.cargo_suplente = cargo
        self.save(update_fields=["cargo_suplente", "actualizado_en"])
        return cargo


def licencias_vigentes(institucion, fecha: date):
    """Licencias aprobadas que cubren esa fecha."""
    return Licencia.objects.filter(
        institucion=institucion,
        estado=EstadoLicencia.APROBADA,
        fecha_inicio__lte=fecha,
        fecha_fin__gte=fecha,
    ).select_related("legajo", "tipo")


def coberturas_vigentes(institucion, fecha: date):
    """Coberturas (suplencias o decisiones de no cubrir) activas esa fecha."""
    return Cobertura.objects.filter(
        institucion=institucion, fecha_inicio__lte=fecha, fecha_fin__gte=fecha
    ).select_related("cargo", "suplente", "licencia")


def suplencias_por_vencer(institucion, dias: int = 7):
    """Suplencias que terminan en los próximos días."""
    hoy = date.today()
    return Cobertura.objects.filter(
        institucion=institucion,
        tipo=TipoCobertura.SUPLENTE,
        fecha_fin__gte=hoy,
        fecha_fin__lte=hoy + timedelta(days=dias),
    ).select_related("suplente", "cargo", "licencia")
