"""Legajos del personal: datos, cargos, documentación, títulos y antigüedad.

Decisión central del modelo: **la fuente de pago es un atributo del cargo, no
de la persona**. De ahí sale sola la realidad de la escuela subvencionada —
alguien puede tener horas que paga el estado y otras que paga la escuela— y de
ahí sale también el ruteo de cada novedad a la planilla Oficial o a la Interna
(F4), sin que nadie tenga que elegirlo a mano.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.archivos import CarpetaProtegida, validar_adjunto
from core.models import ModeloInstitucional, Usuario, validador_cuit
from estructura.models import Curso, Materia, Nivel


class EstadoLegajo(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    BAJA = "BAJA", "De baja"


class Plantel(models.TextChoices):
    """En qué plantel trabaja la persona: docente o no docente.

    El estatuto mete a preceptores y directivos en el plantel docente, pero a
    la secretaría le sirve verlos por separado: son puestos distintos, con
    tareas distintas. Administrativos y maestranza son el personal no docente.
    """

    DOCENTE = "DOCENTE", "Docente"
    PRECEPTOR = "PRECEPTOR", "Preceptor/a"
    DIRECTIVO = "DIRECTIVO", "Directivo"
    ADMINISTRATIVO = "ADMINISTRATIVO", "Administrativo"
    MAESTRANZA = "MAESTRANZA", "Maestranza / ordenanza"


# Los que no están frente a alumnos: no se les buscan materias ni aparecen
# como candidatos para cubrir un curso.
PLANTELES_SIN_CLASES = (Plantel.ADMINISTRATIVO, Plantel.MAESTRANZA)


class Legajo(ModeloInstitucional):
    """Carpeta administrativa de una persona que trabaja en la escuela.

    No se confunde con ``core.Usuario``: el liquidador tiene usuario y no
    legajo, y un docente puede tener legajo sin usar todavía el portal.
    """

    numero = models.CharField(
        "número de legajo", max_length=20, blank=True, help_text="Opcional, el que usa la escuela."
    )
    apellido = models.CharField("apellido", max_length=100)
    nombre = models.CharField("nombre", max_length=100)
    foto = models.ImageField(
        "foto",
        upload_to=CarpetaProtegida("fotos"),
        validators=[validar_adjunto],
        blank=True,
        help_text=(
            "Tipo carnet, cuadrada (4x4). JPG o PNG; si no es exactamente "
            "cuadrada, se recorta al mostrarla."
        ),
    )
    cuil = models.CharField(
        "CUIL",
        max_length=13,
        blank=True,
        validators=[validador_cuit],
        help_text=(
            "Es la identidad de la persona para la liquidación. Puede quedar "
            "vacío al arrancar y completarse después; mientras tanto figura "
            "como pendiente."
        ),
    )
    dni = models.CharField("DNI", max_length=15, blank=True)
    fecha_nacimiento = models.DateField("fecha de nacimiento", null=True, blank=True)

    email = models.EmailField("email", blank=True)
    telefono = models.CharField("teléfono", max_length=50, blank=True)

    # Qué puede dar, más allá de lo que da hoy. Los cargos dicen lo segundo;
    # esto dice lo primero, y es lo que permite encontrar un reemplazo cuando
    # un curso queda sin clase: alguien puede estar habilitado en Química sin
    # tener ninguna hora de Química este año.
    materias_que_puede_dar = models.ManyToManyField(
        "estructura.Materia",
        blank=True,
        related_name="personal_habilitado",
        verbose_name="materias que puede dar",
        help_text="Para buscarle reemplazo a un curso sin docente.",
    )
    domicilio = models.CharField("domicilio", max_length=200, blank=True)
    localidad = models.CharField("localidad", max_length=100, blank=True)

    obra_social = models.CharField(
        "obra social",
        max_length=100,
        blank=True,
        help_text="Se informa al liquidador en el alta.",
    )

    fecha_ingreso = models.DateField(
        "ingreso a la institución",
        null=True,
        blank=True,
        help_text="Primer día de trabajo en esta escuela.",
    )
    plantel = models.CharField(
        "plantel",
        max_length=15,
        choices=Plantel.choices,
        default=Plantel.DOCENTE,
        help_text=(
            "Docente, preceptor, directivo, administrativo o maestranza. "
            "Separa las secciones de Personal y define a quién se le buscan "
            "materias para cubrir cursos."
        ),
    )
    estado = models.CharField(
        "estado", max_length=10, choices=EstadoLegajo.choices, default=EstadoLegajo.ACTIVO
    )
    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legajo",
        verbose_name="usuario del portal",
        help_text="Opcional: vincula el legajo con su acceso al sistema.",
    )
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "legajo"
        verbose_name_plural = "legajos"
        ordering = ["apellido", "nombre"]
        constraints = [
            # Condicional a propósito: dos personas sin CUIL todavía no chocan
            # entre sí —una escuela arranca con la lista de apellidos y los CUIL
            # llegan después—, pero dos con el mismo CUIL siguen siendo la misma
            # persona y el sistema no lo permite.
            models.UniqueConstraint(
                fields=["institucion", "cuil"],
                condition=~models.Q(cuil=""),
                name="legajo_unico_por_cuil",
            )
        ]
        indexes = [models.Index(fields=["institucion", "apellido", "nombre"])]

    def __str__(self) -> str:
        return self.nombre_completo

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}"

    @property
    def da_clases(self) -> bool:
        """Si está frente a alumnos (o puede estarlo): docente, preceptor o directivo."""
        return self.plantel not in PLANTELES_SIN_CLASES

    def cargos_vigentes(self, a_fecha: date | None = None):
        """Cargos activos a una fecha (por omisión, hoy)."""
        a_fecha = a_fecha or date.today()
        return self.cargos.filter(
            models.Q(fecha_baja__isnull=True) | models.Q(fecha_baja__gte=a_fecha),
            fecha_alta__lte=a_fecha,
        )

    @property
    def horas_catedra_vigentes(self) -> int:
        return sum(
            cargo.horas_semanales or 0
            for cargo in self.cargos_vigentes()
            if cargo.tipo == TipoCargo.HORAS_CATEDRA
        )

    def documentacion_vencida(self, a_fecha: date | None = None):
        a_fecha = a_fecha or date.today()
        return self.documentos.filter(fecha_vencimiento__lt=a_fecha)


class TipoCargo(models.TextChoices):
    """Cómo se mide la designación."""

    CARGO_BASE = "CARGO_BASE", "Cargo (jornada)"
    HORAS_CATEDRA = "HORAS_CATEDRA", "Horas cátedra (40 min)"
    HORAS_RELOJ = "HORAS_RELOJ", "Horas reloj (60 min)"


class SituacionRevista(models.TextChoices):
    TITULAR = "TITULAR", "Titular"
    PROVISIONAL = "PROVISIONAL", "Provisional / interino"
    SUPLENTE = "SUPLENTE", "Suplente"


class FuentePago(models.TextChoices):
    """Quién paga el cargo. Define a qué planilla va cada novedad (F4)."""

    SUBVENCIONADO = "SUBVENCIONADO", "Subvencionado (lo paga el estado)"
    INTERNO = "INTERNO", "Interno (lo paga la escuela)"


class MotivoBaja(models.TextChoices):
    RENUNCIA = "RENUNCIA", "Renuncia"
    CESE = "CESE", "Cese"
    FIN_SUPLENCIA = "FIN_SUPLENCIA", "Fin de suplencia"
    JUBILACION = "JUBILACION", "Jubilación"
    OTRO = "OTRO", "Otro"


class Cargo(ModeloInstitucional):
    """Designación concreta: qué hace la persona, con cuántas horas y quién la paga.

    Una persona puede tener varios cargos a la vez (el caso "mixto"): por
    ejemplo horas de Matemática subvencionadas y horas de Taller internas.
    """

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="cargos", verbose_name="legajo"
    )
    tipo = models.CharField("tipo", max_length=15, choices=TipoCargo.choices)
    denominacion = models.CharField(
        "denominación",
        max_length=120,
        blank=True,
        help_text='Para cargos que no son materia. Ej.: "Preceptor/a", "Secretaria".',
    )
    nivel = models.ForeignKey(
        Nivel,
        on_delete=models.PROTECT,
        related_name="cargos",
        null=True,
        blank=True,
        verbose_name="nivel",
    )
    materia = models.ForeignKey(
        Materia,
        on_delete=models.PROTECT,
        related_name="cargos",
        null=True,
        blank=True,
        verbose_name="materia",
    )
    curso = models.ForeignKey(
        Curso,
        on_delete=models.PROTECT,
        related_name="cargos",
        null=True,
        blank=True,
        verbose_name="curso",
        help_text="Opcional: si las horas están asignadas a una división concreta.",
    )
    horas_semanales = models.PositiveSmallIntegerField(
        "horas semanales",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
    )
    jornada_completa = models.BooleanField(
        "jornada completa", default=False, help_text="Solo para cargos de jornada."
    )

    situacion_revista = models.CharField(
        "situación de revista", max_length=15, choices=SituacionRevista.choices
    )
    fuente_pago = models.CharField(
        "fuente de pago",
        max_length=15,
        choices=FuentePago.choices,
        help_text="Define si la novedad va a la planilla Oficial o a la Interna.",
    )

    fecha_alta = models.DateField("alta")
    fecha_baja = models.DateField("baja", null=True, blank=True)
    motivo_baja = models.CharField(
        "motivo de baja", max_length=15, choices=MotivoBaja.choices, blank=True
    )

    resolucion_numero = models.CharField("resolución n°", max_length=50, blank=True)
    resolucion_fecha = models.DateField("fecha de la resolución", null=True, blank=True)
    resolucion_archivo = models.FileField(
        "archivo de la resolución",
        upload_to=CarpetaProtegida("resoluciones"),
        blank=True,
        validators=[validar_adjunto],
    )
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "cargo"
        verbose_name_plural = "cargos"
        ordering = ["legajo", "-fecha_alta"]
        indexes = [
            models.Index(fields=["institucion", "fuente_pago"]),
            models.Index(fields=["legajo", "fecha_alta"]),
        ]

    def __str__(self) -> str:
        detalle = self.descripcion
        if self.horas_semanales:
            detalle = f"{detalle} ({self.horas_semanales} hs)"
        return f"{detalle} · {self.get_situacion_revista_display()}"

    @property
    def descripcion(self) -> str:
        """Cómo se nombra el cargo: la materia si la tiene, si no la denominación."""
        base = self.materia.nombre if self.materia_id else self.denominacion
        if self.curso_id:
            return f"{base} · {self.curso}"
        return base

    @property
    def es_subvencionado(self) -> bool:
        return self.fuente_pago == FuentePago.SUBVENCIONADO

    def vigente_en(self, a_fecha: date) -> bool:
        if self.fecha_alta > a_fecha:
            return False
        return self.fecha_baja is None or self.fecha_baja >= a_fecha

    @property
    def esta_vigente(self) -> bool:
        return self.vigente_en(date.today())

    def clean(self):
        errores = {}

        if self.tipo == TipoCargo.HORAS_CATEDRA:
            if not self.materia_id:
                errores["materia"] = "Un cargo de horas cátedra necesita la materia."
            if not self.horas_semanales:
                errores["horas_semanales"] = "Indicá la cantidad de horas semanales."
        elif self.tipo == TipoCargo.CARGO_BASE and not (self.denominacion or self.materia_id):
            errores["denominacion"] = "Indicá qué cargo ocupa (ej.: Preceptor/a)."

        if self.curso_id and self.materia_id and self.curso.nivel_id != self.materia.nivel_id:
            errores["curso"] = "El curso y la materia son de niveles distintos."
        if self.nivel_id and self.materia_id and self.materia.nivel_id != self.nivel_id:
            errores["materia"] = "La materia pertenece a otro nivel."

        if self.fecha_baja and self.fecha_alta and self.fecha_baja < self.fecha_alta:
            errores["fecha_baja"] = "La baja no puede ser anterior al alta."
        if self.fecha_baja and not self.motivo_baja:
            errores["motivo_baja"] = "Indicá el motivo de la baja."
        if self.motivo_baja and not self.fecha_baja:
            errores["fecha_baja"] = "Indicá la fecha de la baja."

        if errores:
            raise ValidationError(errores)


class TipoDocumento(ModeloInstitucional):
    """Catálogo de documentación que la escuela exige en el legajo."""

    nombre = models.CharField("nombre", max_length=120, help_text='Ej.: "Apto psicofísico".')
    lleva_vencimiento = models.BooleanField("lleva vencimiento", default=True)
    dias_preaviso = models.PositiveSmallIntegerField(
        "días de preaviso", default=30, help_text="Con cuánta anticipación avisar que vence."
    )
    obligatorio = models.BooleanField("obligatorio", default=False)

    class Meta:
        verbose_name = "tipo de documento"
        verbose_name_plural = "tipos de documento"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "nombre"], name="tipo_documento_unico_por_nombre"
            )
        ]

    def __str__(self) -> str:
        return self.nombre


class DocumentoLegajo(models.Model):
    """Un documento presentado, con su vencimiento si lo tiene."""

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="documentos", verbose_name="legajo"
    )
    tipo = models.ForeignKey(
        TipoDocumento, on_delete=models.PROTECT, related_name="documentos", verbose_name="tipo"
    )
    archivo = models.FileField(
        "archivo",
        upload_to=CarpetaProtegida("documentos"),
        blank=True,
        validators=[validar_adjunto],
    )
    fecha_emision = models.DateField("emitido el", null=True, blank=True)
    fecha_vencimiento = models.DateField("vence el", null=True, blank=True)
    observaciones = models.CharField("observaciones", max_length=300, blank=True)
    creado_en = models.DateTimeField("cargado en", auto_now_add=True)
    reclamado_en = models.DateTimeField(
        "último reclamo",
        null=True,
        blank=True,
        help_text="Cuándo se le avisó por última vez a la persona que vence.",
    )

    class Meta:
        verbose_name = "documento del legajo"
        verbose_name_plural = "documentación"
        ordering = ["legajo", "tipo"]
        indexes = [models.Index(fields=["fecha_vencimiento"])]

    def __str__(self) -> str:
        return f"{self.tipo} de {self.legajo}"

    def clean(self):
        if (
            self.fecha_emision
            and self.fecha_vencimiento
            and self.fecha_vencimiento < self.fecha_emision
        ):
            raise ValidationError(
                {"fecha_vencimiento": "El vencimiento no puede ser anterior a la emisión."}
            )

    def dias_para_vencer(self, a_fecha: date | None = None) -> int | None:
        if self.fecha_vencimiento is None:
            return None
        return (self.fecha_vencimiento - (a_fecha or date.today())).days

    @property
    def esta_vencido(self) -> bool:
        dias = self.dias_para_vencer()
        return dias is not None and dias < 0

    @property
    def por_vencer(self) -> bool:
        """Dentro de la ventana de preaviso del tipo de documento."""
        dias = self.dias_para_vencer()
        if dias is None or dias < 0:
            return False
        return dias <= self.tipo.dias_preaviso


class TipoFormacion(models.TextChoices):
    TITULO = "TITULO", "Título"
    POSTITULO = "POSTITULO", "Postítulo"
    CURSO = "CURSO", "Curso / capacitación"


class Titulo(models.Model):
    """Formación acreditada: títulos, postítulos y cursos."""

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="titulos", verbose_name="legajo"
    )
    tipo = models.CharField(
        "tipo", max_length=12, choices=TipoFormacion.choices, default=TipoFormacion.TITULO
    )
    nombre = models.CharField("denominación", max_length=200)
    institucion_otorgante = models.CharField("otorgado por", max_length=200, blank=True)
    fecha_egreso = models.DateField("fecha de egreso", null=True, blank=True)
    horas_reloj = models.PositiveSmallIntegerField(
        "horas reloj", null=True, blank=True, help_text="Para cursos y capacitaciones."
    )
    registrado = models.BooleanField(
        "registrado", default=False, help_text="Título registrado ante el organismo."
    )
    archivo = models.FileField(
        "archivo",
        upload_to=CarpetaProtegida("titulos"),
        blank=True,
        validators=[validar_adjunto],
    )

    class Meta:
        verbose_name = "título"
        verbose_name_plural = "títulos y formación"
        ordering = ["legajo", "-fecha_egreso"]

    def __str__(self) -> str:
        return self.nombre


class ServicioAnterior(models.Model):
    """Servicios prestados en otras instituciones, para el cómputo de antigüedad.

    Se cargan a mano con lo que declara y acredita la persona: el sistema no
    tiene forma de conocerlos por su cuenta.
    """

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="servicios_anteriores", verbose_name="legajo"
    )
    institucion_nombre = models.CharField("institución", max_length=200)
    cargo_descripcion = models.CharField("cargo desempeñado", max_length=200, blank=True)
    desde = models.DateField("desde")
    hasta = models.DateField("hasta")
    es_docente = models.BooleanField(
        "antigüedad docente",
        default=True,
        help_text="Desmarcar si el servicio no computa como docente.",
    )
    archivo = models.FileField(
        "certificación",
        upload_to=CarpetaProtegida("servicios"),
        blank=True,
        validators=[validar_adjunto],
    )

    class Meta:
        verbose_name = "servicio anterior"
        verbose_name_plural = "servicios anteriores"
        ordering = ["legajo", "-desde"]

    def __str__(self) -> str:
        return f"{self.institucion_nombre} ({self.desde:%m/%Y} a {self.hasta:%m/%Y})"

    def clean(self):
        if self.desde and self.hasta and self.hasta < self.desde:
            raise ValidationError({"hasta": "El fin no puede ser anterior al inicio."})
