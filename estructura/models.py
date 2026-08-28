"""Estructura del colegio: niveles, ciclo lectivo, grilla horaria, cursos y materias.

Sobre esta base se apoyan los horarios (F2), la asistencia (F3) y las novedades
(F4), así que los modelos priorizan flexibilidad: la grilla no se asume
uniforme — cada día puede tener bloques distintos y cada curso puede seguir un
esquema propio (con almuerzo o sin él).
"""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import ModeloInstitucional


class TipoNivel(models.TextChoices):
    INICIAL = "INICIAL", "Inicial"
    PRIMARIO = "PRIMARIO", "Primario"
    SECUNDARIO = "SECUNDARIO", "Secundario"


class DiaSemana(models.IntegerChoices):
    LUNES = 0, "Lunes"
    MARTES = 1, "Martes"
    MIERCOLES = 2, "Miércoles"
    JUEVES = 3, "Jueves"
    VIERNES = 4, "Viernes"
    SABADO = 5, "Sábado"


class Nivel(ModeloInstitucional):
    """Nivel educativo de la escuela (inicial, primario, secundario)."""

    tipo = models.CharField("tipo", max_length=15, choices=TipoNivel.choices)
    nombre = models.CharField(
        "nombre", max_length=100, blank=True, help_text="Opcional: cómo lo llama la escuela."
    )
    orden = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        verbose_name = "nivel"
        verbose_name_plural = "niveles"
        ordering = ["orden", "tipo"]
        constraints = [
            models.UniqueConstraint(fields=["institucion", "tipo"], name="nivel_unico_por_tipo")
        ]

    def __str__(self) -> str:
        return self.nombre or self.get_tipo_display()


class EstadoCiclo(models.TextChoices):
    PLANIFICACION = "PLANIFICACION", "En planificación"
    ACTIVO = "ACTIVO", "Activo"
    CERRADO = "CERRADO", "Cerrado"


class CicloLectivo(ModeloInstitucional):
    """Año escolar. Todo lo que cambia año a año cuelga de acá."""

    anio = models.PositiveSmallIntegerField(
        "año", validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    fecha_inicio = models.DateField("inicio de clases")
    fecha_fin = models.DateField("fin de clases")
    estado = models.CharField(
        "estado", max_length=15, choices=EstadoCiclo.choices, default=EstadoCiclo.PLANIFICACION
    )

    class Meta:
        verbose_name = "ciclo lectivo"
        verbose_name_plural = "ciclos lectivos"
        ordering = ["-anio"]
        constraints = [
            models.UniqueConstraint(fields=["institucion", "anio"], name="ciclo_unico_por_anio")
        ]

    def __str__(self) -> str:
        return str(self.anio)

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError(
                {"fecha_fin": "El fin de clases no puede ser anterior al inicio."}
            )


class PeriodoAcademico(models.Model):
    """División del ciclo lectivo: cuatrimestre, trimestre o el año completo.

    Existe porque algunas materias cambian de cuatrimestre, y con ellas el
    horario y la designación del docente. Cada versión de horario se publica
    para un período.
    """

    ciclo = models.ForeignKey(
        CicloLectivo,
        on_delete=models.CASCADE,
        related_name="periodos",
        verbose_name="ciclo lectivo",
    )
    nombre = models.CharField("nombre", max_length=50, help_text='Ej.: "1er cuatrimestre".')
    orden = models.PositiveSmallIntegerField("orden", default=1)
    fecha_inicio = models.DateField("desde")
    fecha_fin = models.DateField("hasta")

    class Meta:
        verbose_name = "período académico"
        verbose_name_plural = "períodos académicos"
        ordering = ["ciclo", "orden"]
        constraints = [
            models.UniqueConstraint(fields=["ciclo", "orden"], name="periodo_unico_por_orden")
        ]

    def __str__(self) -> str:
        return f"{self.nombre} {self.ciclo.anio}"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({"fecha_fin": "El fin no puede ser anterior al inicio."})

    def incluye(self, fecha) -> bool:
        return self.fecha_inicio <= fecha <= self.fecha_fin


class Turno(ModeloInstitucional):
    """Turno de un nivel (mañana, tarde). Cada nivel tiene su propio horario."""

    nivel = models.ForeignKey(
        Nivel, on_delete=models.CASCADE, related_name="turnos", verbose_name="nivel"
    )
    nombre = models.CharField("nombre", max_length=50, help_text='Ej.: "Mañana".')
    hora_inicio = models.TimeField("entrada")
    hora_fin = models.TimeField("salida")
    orden = models.PositiveSmallIntegerField("orden", default=0)

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["nivel", "orden", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(fields=["nivel", "nombre"], name="turno_unico_por_nivel")
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.nivel})"


class EsquemaHorario(ModeloInstitucional):
    """Plantilla de grilla semanal: qué bloques tiene cada día.

    Un mismo turno puede tener más de un esquema — por ejemplo "con almuerzo" y
    "sin almuerzo" — y cada curso sigue el que le corresponde. Así se modela una
    realidad que no es uniforme sin llenar de excepciones el resto del sistema.
    """

    turno = models.ForeignKey(
        Turno, on_delete=models.CASCADE, related_name="esquemas", verbose_name="turno"
    )
    nombre = models.CharField("nombre", max_length=80, help_text='Ej.: "Con almuerzo".')
    predeterminado = models.BooleanField(
        "predeterminado", default=False, help_text="Se propone al crear un curso de este turno."
    )

    class Meta:
        verbose_name = "esquema horario"
        verbose_name_plural = "esquemas horarios"
        ordering = ["turno", "nombre"]
        constraints = [
            models.UniqueConstraint(fields=["turno", "nombre"], name="esquema_unico_por_turno")
        ]

    def __str__(self) -> str:
        return f"{self.nombre} · {self.turno}"

    def bloques_de_clase(self, dia=None):
        """Bloques dictables (excluye recreos y almuerzo), en orden."""
        qs = self.bloques.filter(tipo=TipoBloque.CLASE)
        if dia is not None:
            qs = qs.filter(dia_semana=dia)
        return qs.order_by("dia_semana", "hora_inicio")

    @property
    def cantidad_horas_semanales(self) -> int:
        """Cuántas horas de clase ofrece la grilla por semana."""
        return self.bloques.filter(tipo=TipoBloque.CLASE).count()


class TipoBloque(models.TextChoices):
    CLASE = "CLASE", "Hora de clase"
    RECREO = "RECREO", "Recreo"
    ALMUERZO = "ALMUERZO", "Almuerzo"
    OTRO = "OTRO", "Otro"


class BloqueHorario(models.Model):
    """Una franja de la grilla en un día concreto.

    Se guarda día por día (y no una sola columna semanal) porque los recreos
    duran distinto según el momento de la mañana y no todos los días son
    iguales.
    """

    esquema = models.ForeignKey(
        EsquemaHorario, on_delete=models.CASCADE, related_name="bloques", verbose_name="esquema"
    )
    dia_semana = models.PositiveSmallIntegerField("día", choices=DiaSemana.choices)
    orden = models.PositiveSmallIntegerField("orden en el día", default=1)
    tipo = models.CharField(
        "tipo", max_length=10, choices=TipoBloque.choices, default=TipoBloque.CLASE
    )
    hora_inicio = models.TimeField("desde")
    hora_fin = models.TimeField("hasta")
    etiqueta = models.CharField(
        "etiqueta", max_length=40, blank=True, help_text='Opcional. Ej.: "1ª hora".'
    )

    class Meta:
        verbose_name = "bloque horario"
        verbose_name_plural = "bloques horarios"
        ordering = ["esquema", "dia_semana", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["esquema", "dia_semana", "orden"], name="bloque_unico_por_dia_y_orden"
            )
        ]
        indexes = [models.Index(fields=["esquema", "dia_semana"])]

    def __str__(self) -> str:
        etiqueta = self.etiqueta or self.get_tipo_display()
        return f"{self.get_dia_semana_display()} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M} · {etiqueta}"

    @property
    def duracion_minutos(self) -> int:
        inicio = datetime.combine(datetime.min, self.hora_inicio)
        fin = datetime.combine(datetime.min, self.hora_fin)
        if fin <= inicio:
            fin += timedelta(days=1)
        return int((fin - inicio).total_seconds() // 60)

    def clean(self):
        if self.hora_inicio and self.hora_fin and self.hora_fin <= self.hora_inicio:
            raise ValidationError({"hora_fin": "El fin debe ser posterior al inicio."})
        if not (self.esquema_id and self.hora_inicio and self.hora_fin):
            return
        solapados = (
            BloqueHorario.objects.filter(
                esquema_id=self.esquema_id,
                dia_semana=self.dia_semana,
                hora_inicio__lt=self.hora_fin,
                hora_fin__gt=self.hora_inicio,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if solapados:
            raise ValidationError("Se superpone con otro bloque del mismo día en este esquema.")


class Curso(ModeloInstitucional):
    """División concreta de un año de estudio: 3°A del turno mañana."""

    ciclo_lectivo = models.ForeignKey(
        CicloLectivo, on_delete=models.CASCADE, related_name="cursos", verbose_name="ciclo lectivo"
    )
    nivel = models.ForeignKey(
        Nivel, on_delete=models.PROTECT, related_name="cursos", verbose_name="nivel"
    )
    anio_estudio = models.PositiveSmallIntegerField(
        "año de estudio", validators=[MinValueValidator(1), MaxValueValidator(7)]
    )
    division = models.CharField("división", max_length=5, help_text='Ej.: "A".')
    turno = models.ForeignKey(
        Turno, on_delete=models.PROTECT, related_name="cursos", verbose_name="turno"
    )
    esquema_horario = models.ForeignKey(
        EsquemaHorario,
        on_delete=models.PROTECT,
        related_name="cursos",
        verbose_name="esquema horario",
        help_text="Grilla que sigue este curso (con almuerzo, sin almuerzo, etc.).",
    )

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["ciclo_lectivo", "nivel", "anio_estudio", "division"]
        constraints = [
            models.UniqueConstraint(
                fields=["ciclo_lectivo", "nivel", "anio_estudio", "division"],
                name="curso_unico_por_ciclo",
            )
        ]

    def __str__(self) -> str:
        return f"{self.anio_estudio}°{self.division}"

    @property
    def nombre_completo(self) -> str:
        return f"{self.anio_estudio}°{self.division} · {self.turno.nombre} · {self.nivel}"

    def clean(self):
        if self.turno_id and self.nivel_id and self.turno.nivel_id != self.nivel_id:
            raise ValidationError({"turno": "El turno pertenece a otro nivel."})
        if (
            self.esquema_horario_id
            and self.turno_id
            and self.esquema_horario.turno_id != self.turno_id
        ):
            raise ValidationError({"esquema_horario": "El esquema pertenece a otro turno."})

    def horas_asignadas(self, periodo=None) -> int:
        """Horas semanales que suma el plan de estudios del curso."""
        planes = self.plan.all()
        if periodo is not None:
            planes = [plan for plan in planes if plan.rige_en(periodo)]
        return sum(plan.horas_semanales for plan in planes)


class Materia(ModeloInstitucional):
    """Espacio curricular del catálogo de la escuela (Matemática, Lengua...)."""

    nivel = models.ForeignKey(
        Nivel, on_delete=models.CASCADE, related_name="materias", verbose_name="nivel"
    )
    nombre = models.CharField("nombre", max_length=120)
    abreviatura = models.CharField("abreviatura", max_length=20, blank=True)

    class Meta:
        verbose_name = "materia"
        verbose_name_plural = "materias"
        ordering = ["nivel", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["institucion", "nivel", "nombre"], name="materia_unica_por_nivel"
            )
        ]

    def __str__(self) -> str:
        return self.nombre


class Vigencia(models.TextChoices):
    """Cuándo se dicta una materia dentro del ciclo lectivo."""

    ANUAL = "ANUAL", "Todo el año"
    PERIODO = "PERIODO", "Solo un período"


class MateriaPlan(models.Model):
    """Materia dictada en un curso, con su carga horaria y su vigencia.

    Es el plan de estudios que el generador de horarios (F2) tiene que cubrir:
    cada fila pide tantas horas semanales en la grilla del curso.
    """

    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="plan", verbose_name="curso"
    )
    materia = models.ForeignKey(
        Materia, on_delete=models.PROTECT, related_name="planes", verbose_name="materia"
    )
    horas_semanales = models.PositiveSmallIntegerField(
        "horas semanales", validators=[MinValueValidator(1), MaxValueValidator(20)]
    )
    vigencia = models.CharField(
        "vigencia", max_length=10, choices=Vigencia.choices, default=Vigencia.ANUAL
    )
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.CASCADE,
        related_name="planes",
        null=True,
        blank=True,
        verbose_name="período",
        help_text="Solo si la materia se dicta en un período y no todo el año.",
    )

    class Meta:
        verbose_name = "materia del plan"
        verbose_name_plural = "plan de estudios"
        ordering = ["curso", "materia"]
        constraints = [
            models.UniqueConstraint(
                fields=["curso", "materia", "periodo"], name="materia_unica_por_curso_y_periodo"
            )
        ]

    def __str__(self) -> str:
        return f"{self.materia} en {self.curso} ({self.horas_semanales} hs)"

    def clean(self):
        if self.curso_id and self.materia_id and self.materia.nivel_id != self.curso.nivel_id:
            raise ValidationError({"materia": "La materia es de otro nivel."})
        if self.vigencia == Vigencia.PERIODO and self.periodo_id is None:
            raise ValidationError({"periodo": "Indicá el período en el que se dicta."})
        if self.vigencia == Vigencia.ANUAL and self.periodo_id is not None:
            raise ValidationError({"periodo": "Una materia anual no lleva período."})
        if (
            self.periodo_id
            and self.curso_id
            and self.periodo.ciclo_id != self.curso.ciclo_lectivo_id
        ):
            raise ValidationError({"periodo": "El período es de otro ciclo lectivo."})

    def rige_en(self, periodo) -> bool:
        """¿Se dicta en ese período?"""
        if self.vigencia == Vigencia.ANUAL:
            return True
        return self.periodo_id == getattr(periodo, "pk", periodo)
