"""Modelos base: institución, usuarios, roles y auditoría."""

from urllib.parse import quote

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from .managers import InstitucionManager


class Jurisdiccion(models.TextChoices):
    """Provincia de la que depende la escuela: define régimen y organismo."""

    BUENOS_AIRES = "AR-B", "Buenos Aires"
    CABA = "AR-C", "Ciudad Autónoma de Buenos Aires"
    CATAMARCA = "AR-K", "Catamarca"
    CHACO = "AR-H", "Chaco"
    CHUBUT = "AR-U", "Chubut"
    CORDOBA = "AR-X", "Córdoba"
    CORRIENTES = "AR-W", "Corrientes"
    ENTRE_RIOS = "AR-E", "Entre Ríos"
    FORMOSA = "AR-P", "Formosa"
    JUJUY = "AR-Y", "Jujuy"
    LA_PAMPA = "AR-L", "La Pampa"
    LA_RIOJA = "AR-F", "La Rioja"
    MENDOZA = "AR-M", "Mendoza"
    MISIONES = "AR-N", "Misiones"
    NEUQUEN = "AR-Q", "Neuquén"
    RIO_NEGRO = "AR-R", "Río Negro"
    SALTA = "AR-A", "Salta"
    SAN_JUAN = "AR-J", "San Juan"
    SAN_LUIS = "AR-D", "San Luis"
    SANTA_CRUZ = "AR-Z", "Santa Cruz"
    SANTA_FE = "AR-S", "Santa Fe"
    SANTIAGO_DEL_ESTERO = "AR-G", "Santiago del Estero"
    TIERRA_DEL_FUEGO = "AR-V", "Tierra del Fuego"
    TUCUMAN = "AR-T", "Tucumán"


validador_cuit = RegexValidator(
    regex=r"^\d{2}-?\d{8}-?\d$",
    message="El CUIT/CUIL debe tener 11 dígitos (con o sin guiones).",
)

validador_color = RegexValidator(
    regex=r"^#[0-9a-fA-F]{6}$",
    message='El color va en hexadecimal de seis dígitos, por ejemplo "#c2560f".',
)


class Institucion(models.Model):
    """Una escuela. Es la raíz del aislamiento de datos del sistema."""

    nombre = models.CharField("nombre", max_length=200)
    nombre_corto = models.CharField(
        "nombre corto", max_length=50, help_text="Para encabezados y listados."
    )
    cue = models.CharField(
        "CUE", max_length=20, blank=True, help_text="Código Único de Establecimiento."
    )
    cuit = models.CharField("CUIT", max_length=13, blank=True, validators=[validador_cuit])
    jurisdiccion = models.CharField(
        "jurisdicción", max_length=8, choices=Jurisdiccion.choices, default=Jurisdiccion.SAN_LUIS
    )
    domicilio = models.CharField("domicilio", max_length=200, blank=True)
    localidad = models.CharField("localidad", max_length=100, blank=True)
    telefono = models.CharField("teléfono", max_length=50, blank=True)
    email = models.EmailField("email", blank=True)
    # Ubicación del establecimiento: la usa el fichaje del portal docente para
    # saber si la persona marcó estando en la escuela.
    latitud = models.FloatField(
        "latitud", null=True, blank=True, help_text="Se puede copiar de Google Maps."
    )
    longitud = models.FloatField("longitud", null=True, blank=True)
    radio_fichaje_metros = models.PositiveIntegerField(
        "radio para fichar (m)",
        default=200,
        help_text="Distancia máxima desde la escuela para considerar válida una fichada.",
    )

    # Identidad visual. Con el sistema alojando varias escuelas, y con una de
    # prueba conviviendo con la real, hay que poder ver de un vistazo dónde se
    # está parado antes de cargar algo. Cuando no hay institución activa
    # —el superusuario mirando algo que no es de ninguna escuela— no se aplica
    # ningún color: la pantalla queda con el aspecto neutro del sistema.
    color = models.CharField(
        "color de la escuela",
        max_length=7,
        blank=True,
        validators=[validador_color],
        help_text='Hexadecimal, ej.: "#c2560f". Vacío deja el color del sistema.',
    )
    emblema = models.CharField(
        "emblema",
        max_length=4,
        blank=True,
        help_text="Un emoji que identifique a la escuela. Va en el encabezado y en la solapa.",
    )

    activa = models.BooleanField("activa", default=True)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "instituciones"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre_corto or self.nombre

    @property
    def icono_svg(self) -> str:
        """El emblema como favicon, sin archivos ni pedidos al servidor."""
        if not self.emblema:
            return ""
        emoji = quote(self.emblema)
        return (
            "data:image/svg+xml,"
            "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
            f"%3Ctext y='.9em' font-size='90'%3E{emoji}%3C/text%3E%3C/svg%3E"
        )


class UsuarioManager(BaseUserManager):
    """Manager de usuarios que identifica por email en lugar de username."""

    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio.")
        usuario = self.model(email=self.normalize_email(email), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra.get("is_staff") or not extra.get("is_superuser"):
            raise ValueError("Un superusuario debe tener is_staff e is_superuser en True.")
        return self._crear(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Persona que entra al sistema.

    No confundir con el legajo del personal (F1): un usuario puede no tener
    legajo (el liquidador externo) y una persona con legajo puede no tener
    usuario (docente que todavía no usa el portal).
    """

    email = models.EmailField("email", unique=True)
    nombre = models.CharField("nombre", max_length=100)
    apellido = models.CharField("apellido", max_length=100)
    telefono = models.CharField("teléfono", max_length=50, blank=True)
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField(
        "acceso al admin", default=False, help_text="Permite entrar al panel de administración."
    )
    date_joined = models.DateTimeField("alta", default=timezone.now)

    objects = UsuarioManager()

    # La bienvenida del primer ingreso se muestra una sola vez. Va en el
    # usuario y no en la sesión: si volviera en cada login sería un cartel más
    # que se aprende a ignorar.
    vio_la_bienvenida = models.BooleanField("vio la bienvenida", default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nombre", "apellido"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["apellido", "nombre"]

    def __str__(self) -> str:
        return f"{self.nombre_completo} <{self.email}>"

    @property
    def nombre_completo(self) -> str:
        return f"{self.apellido}, {self.nombre}".strip(", ")

    def get_full_name(self) -> str:
        return self.nombre_completo

    def get_short_name(self) -> str:
        return self.nombre

    def instituciones(self):
        """Instituciones donde el usuario tiene alguna membresía activa."""
        if self.is_superuser:
            return Institucion.objects.filter(activa=True)
        return Institucion.objects.filter(
            membresias__usuario=self, membresias__activa=True, activa=True
        ).distinct()

    def roles_en(self, institucion) -> set[str]:
        if institucion is None:
            return set()
        return set(
            self.membresias.filter(institucion=institucion, activa=True).values_list(
                "rol", flat=True
            )
        )

    def tiene_rol(self, institucion, *roles) -> bool:
        """¿Tiene alguno de esos roles en la institución? El superusuario siempre."""
        if self.is_superuser:
            return True
        return bool(self.roles_en(institucion) & set(roles))


class Rol(models.TextChoices):
    """Rol dentro de una institución. Se asigna por escuela, no globalmente."""

    SECRETARIA = "SECRETARIA", "Secretaría"
    DIRECTIVO = "DIRECTIVO", "Equipo directivo"
    DOCENTE = "DOCENTE", "Docente"
    LIQUIDADOR = "LIQUIDADOR", "Liquidador / Contador"


class Membresia(models.Model):
    """Vincula un usuario con una institución y le da un rol."""

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name="membresias", verbose_name="usuario"
    )
    institucion = models.ForeignKey(
        Institucion, on_delete=models.CASCADE, related_name="membresias", verbose_name="institución"
    )
    rol = models.CharField("rol", max_length=20, choices=Rol.choices)
    activa = models.BooleanField("activa", default=True)
    creada_en = models.DateTimeField("creada en", auto_now_add=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        ordering = ["institucion", "usuario"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "institucion", "rol"], name="membresia_unica_por_rol"
            )
        ]

    def __str__(self) -> str:
        return f"{self.usuario.nombre_completo} · {self.get_rol_display()} en {self.institucion}"


class ModeloInstitucional(models.Model):
    """Base de todo modelo de negocio: pertenece siempre a una institución."""

    institucion = models.ForeignKey(
        Institucion, on_delete=models.CASCADE, verbose_name="institución"
    )
    creado_en = models.DateTimeField("creado en", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado en", auto_now=True)

    objects = InstitucionManager()

    class Meta:
        abstract = True


class AccionAuditada(models.TextChoices):
    CREACION = "CREACION", "Creación"
    MODIFICACION = "MODIFICACION", "Modificación"
    BAJA = "BAJA", "Baja"
    CIERRE_PERIODO = "CIERRE_PERIODO", "Cierre de período"
    REAPERTURA_PERIODO = "REAPERTURA_PERIODO", "Reapertura de período"
    APROBACION = "APROBACION", "Aprobación"
    EXPORTACION = "EXPORTACION", "Exportación de datos"


class RegistroAuditoria(models.Model):
    """Bitácora inmutable de acciones sensibles.

    Los cierres de período y las novedades ya informadas se auditan para poder
    reconstruir quién cambió qué y cuándo. Los registros no se editan ni se
    borran desde la aplicación.
    """

    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditoria",
        verbose_name="institución",
    )
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditoria",
        verbose_name="usuario",
    )
    accion = models.CharField("acción", max_length=30, choices=AccionAuditada.choices)
    modelo = models.CharField("modelo", max_length=100)
    objeto_id = models.CharField("id del objeto", max_length=50, blank=True)
    descripcion = models.CharField("descripción", max_length=300, blank=True)
    datos = models.JSONField("datos", default=dict, blank=True)
    creado_en = models.DateTimeField("fecha y hora", auto_now_add=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["institucion", "-creado_en"]),
            models.Index(fields=["modelo", "objeto_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.creado_en:%d/%m/%Y %H:%M} · {self.get_accion_display()} · {self.modelo}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Los registros de auditoría no se modifican.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Los registros de auditoría no se borran.")


def registrar_auditoria(
    accion: str,
    objeto=None,
    *,
    usuario=None,
    institucion=None,
    descripcion: str = "",
    datos: dict | None = None,
    modelo: str = "",
) -> RegistroAuditoria:
    """Deja constancia de una acción sensible.

    Si se pasa ``objeto``, toma de él el modelo, el id y —cuando corresponde—
    la institución.
    """
    if objeto is not None:
        modelo = modelo or objeto.__class__.__name__
        objeto_id = str(getattr(objeto, "pk", "") or "")
        institucion = institucion or getattr(objeto, "institucion", None)
    else:
        objeto_id = ""
    return RegistroAuditoria.objects.create(
        institucion=institucion,
        usuario=usuario,
        accion=accion,
        modelo=modelo,
        objeto_id=objeto_id,
        descripcion=descripcion,
        datos=datos or {},
    )
