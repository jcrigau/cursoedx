"""Horarios: declaraciones juradas, versiones de horario y asignaciones.

Una **versión** es un horario completo para un período académico. Se generan
como borrador, se corrigen a mano y recién entonces se publican: publicar una
versión archiva la anterior, así el cambio de cuatrimestre no pierde el horario
del primero.

Sobre la superposición de horarios: dos cursos pueden seguir esquemas distintos
(uno almuerza y el otro no), de modo que "la tercera hora" no siempre cae a la
misma hora del reloj. Por eso los choques se detectan comparando **horarios
reales**, no la identidad del bloque.
"""

from datetime import time

from django.core.exceptions import ValidationError
from django.db import models

from core.models import ModeloInstitucional, Usuario
from estructura.models import BloqueHorario, Curso, DiaSemana, Materia, PeriodoAcademico
from legajos.models import Cargo, Legajo


def se_superponen(inicio_a: time, fin_a: time, inicio_b: time, fin_b: time) -> bool:
    """¿Dos franjas del mismo día comparten aunque sea un minuto?"""
    return inicio_a < fin_b and inicio_b < fin_a


class DeclaracionDisponibilidad(ModeloInstitucional):
    """DDJJ del docente: cuándo no puede estar en la escuela.

    Es el insumo principal del generador. Sin ella, el horario que se arme
    puede chocar con los compromisos que la persona ya tiene en otra escuela.
    """

    legajo = models.ForeignKey(
        Legajo, on_delete=models.CASCADE, related_name="declaraciones", verbose_name="docente"
    )
    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.CASCADE,
        related_name="declaraciones",
        verbose_name="período",
    )
    presentada_en = models.DateField("presentada el", null=True, blank=True)
    archivo = models.FileField("declaración firmada", upload_to="ddjj/", blank=True)
    observaciones = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "declaración de disponibilidad"
        verbose_name_plural = "declaraciones de disponibilidad (DDJJ)"
        ordering = ["periodo", "legajo"]
        constraints = [
            models.UniqueConstraint(
                fields=["legajo", "periodo"], name="ddjj_unica_por_docente_y_periodo"
            )
        ]

    def __str__(self) -> str:
        return f"DDJJ de {self.legajo} · {self.periodo}"

    def franjas_duras(self):
        """Franjas en las que la persona no puede estar (restricción obligatoria)."""
        return self.franjas.filter(es_preferencia=False)

    def franjas_preferidas(self):
        """Franjas que prefiere evitar (se respetan si se puede)."""
        return self.franjas.filter(es_preferencia=True)


class MotivoNoDisponible(models.TextChoices):
    OTRA_ESCUELA = "OTRA_ESCUELA", "Trabaja en otra institución"
    ESTUDIO = "ESTUDIO", "Estudio o capacitación"
    PERSONAL = "PERSONAL", "Motivo personal"
    OTRO = "OTRO", "Otro"


class FranjaNoDisponible(models.Model):
    """Una franja horaria declarada como no disponible o poco conveniente."""

    declaracion = models.ForeignKey(
        DeclaracionDisponibilidad,
        on_delete=models.CASCADE,
        related_name="franjas",
        verbose_name="declaración",
    )
    dia_semana = models.PositiveSmallIntegerField("día", choices=DiaSemana.choices)
    hora_desde = models.TimeField("desde")
    hora_hasta = models.TimeField("hasta")
    motivo = models.CharField(
        "motivo",
        max_length=15,
        choices=MotivoNoDisponible.choices,
        default=MotivoNoDisponible.OTRA_ESCUELA,
    )
    institucion_externa = models.CharField("institución", max_length=200, blank=True)
    es_preferencia = models.BooleanField(
        "es solo una preferencia",
        default=False,
        help_text="Si se marca, el generador intenta evitarla pero puede usarla si no hay otra opción.",
    )

    class Meta:
        verbose_name = "franja no disponible"
        verbose_name_plural = "franjas no disponibles"
        ordering = ["dia_semana", "hora_desde"]

    def __str__(self) -> str:
        etiqueta = "prefiere no" if self.es_preferencia else "no disponible"
        return (
            f"{self.get_dia_semana_display()} {self.hora_desde:%H:%M}-"
            f"{self.hora_hasta:%H:%M} ({etiqueta})"
        )

    def clean(self):
        if self.hora_desde and self.hora_hasta and self.hora_hasta <= self.hora_desde:
            raise ValidationError({"hora_hasta": "El fin debe ser posterior al inicio."})

    def cubre(self, dia: int, hora_inicio: time, hora_fin: time) -> bool:
        return self.dia_semana == dia and se_superponen(
            self.hora_desde, self.hora_hasta, hora_inicio, hora_fin
        )


class EstadoVersion(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    VIGENTE = "VIGENTE", "Vigente"
    HISTORICO = "HISTORICO", "Histórico"


class VersionHorario(ModeloInstitucional):
    """Un horario completo para un período académico."""

    periodo = models.ForeignKey(
        PeriodoAcademico,
        on_delete=models.CASCADE,
        related_name="versiones_horario",
        verbose_name="período",
    )
    nombre = models.CharField("nombre", max_length=120, help_text='Ej.: "Borrador 1".')
    estado = models.CharField(
        "estado", max_length=12, choices=EstadoVersion.choices, default=EstadoVersion.BORRADOR
    )
    generada_en = models.DateTimeField("generada en", null=True, blank=True)
    generada_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="horarios_generados",
        verbose_name="generada por",
    )
    parametros = models.JSONField("parámetros de generación", default=dict, blank=True)
    resumen = models.JSONField("resumen", default=dict, blank=True)
    notas = models.TextField("notas", blank=True)

    class Meta:
        verbose_name = "versión de horario"
        verbose_name_plural = "versiones de horario"
        ordering = ["-periodo__ciclo__anio", "periodo__orden", "-creado_en"]

    def __str__(self) -> str:
        return f"{self.nombre} · {self.periodo}"

    def publicar(self):
        """Deja esta versión como vigente y archiva la anterior del período."""
        (
            VersionHorario.objects.filter(periodo=self.periodo, estado=EstadoVersion.VIGENTE)
            .exclude(pk=self.pk)
            .update(estado=EstadoVersion.HISTORICO)
        )
        self.estado = EstadoVersion.VIGENTE
        self.save(update_fields=["estado", "actualizado_en"])

    def horas_por_curso(self) -> dict:
        conteo = {}
        for asignacion in self.asignaciones.select_related("curso"):
            conteo[asignacion.curso] = conteo.get(asignacion.curso, 0) + 1
        return conteo

    def dias_por_docente(self) -> dict:
        """Cuántos días tiene que venir cada docente. Es el objetivo principal."""
        dias = {}
        for asignacion in self.asignaciones.exclude(legajo=None).select_related("legajo"):
            dias.setdefault(asignacion.legajo, set()).add(asignacion.dia_semana)
        return {legajo: len(jornadas) for legajo, jornadas in dias.items()}


class AsignacionHoraria(models.Model):
    """Una materia dictada por un docente, en un curso y un bloque concretos."""

    version = models.ForeignKey(
        VersionHorario,
        on_delete=models.CASCADE,
        related_name="asignaciones",
        verbose_name="versión",
    )
    curso = models.ForeignKey(
        Curso, on_delete=models.CASCADE, related_name="asignaciones", verbose_name="curso"
    )
    bloque = models.ForeignKey(
        BloqueHorario, on_delete=models.CASCADE, related_name="asignaciones", verbose_name="bloque"
    )
    materia = models.ForeignKey(
        Materia, on_delete=models.PROTECT, related_name="asignaciones", verbose_name="materia"
    )
    cargo = models.ForeignKey(
        Cargo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asignaciones",
        verbose_name="cargo del docente",
    )
    legajo = models.ForeignKey(
        Legajo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asignaciones",
        verbose_name="docente",
        help_text="Se completa solo a partir del cargo.",
    )

    # Copiados del bloque: permiten detectar choques entre cursos que siguen
    # esquemas distintos, donde "la misma hora" no es el mismo bloque.
    dia_semana = models.PositiveSmallIntegerField("día", choices=DiaSemana.choices)
    hora_inicio = models.TimeField("desde")
    hora_fin = models.TimeField("hasta")

    bloqueada = models.BooleanField(
        "bloqueada",
        default=False,
        help_text="El generador no la mueve: sirve para fijar lo que ya está bien.",
    )

    class Meta:
        verbose_name = "asignación horaria"
        verbose_name_plural = "asignaciones horarias"
        ordering = ["version", "curso", "dia_semana", "hora_inicio"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "curso", "bloque"], name="una_materia_por_bloque_y_curso"
            ),
            models.UniqueConstraint(
                fields=["version", "legajo", "dia_semana", "hora_inicio"],
                condition=models.Q(legajo__isnull=False),
                name="docente_en_un_solo_lugar_por_hora",
            ),
        ]
        indexes = [
            models.Index(fields=["version", "curso"]),
            models.Index(fields=["version", "legajo", "dia_semana"]),
        ]

    def __str__(self) -> str:
        return f"{self.curso} · {self.materia} · {self.get_dia_semana_display()} {self.hora_inicio:%H:%M}"

    def save(self, *args, **kwargs):
        # El horario real y el docente se copian del bloque y del cargo para
        # poder consultarlos sin recorrer relaciones en cada comparación.
        if self.bloque_id:
            self.dia_semana = self.bloque.dia_semana
            self.hora_inicio = self.bloque.hora_inicio
            self.hora_fin = self.bloque.hora_fin
        self.legajo_id = self.cargo.legajo_id if self.cargo_id else None
        super().save(*args, **kwargs)

    def clean(self):
        if not self.bloque_id or not self.version_id:
            return

        dia = self.bloque.dia_semana
        inicio, fin = self.bloque.hora_inicio, self.bloque.hora_fin

        del_curso = (
            AsignacionHoraria.objects.filter(
                version_id=self.version_id, curso_id=self.curso_id, dia_semana=dia
            )
            .exclude(pk=self.pk)
            .select_related("materia")
        )
        for otra in del_curso:
            if se_superponen(inicio, fin, otra.hora_inicio, otra.hora_fin):
                raise ValidationError(f"El curso ya tiene {otra.materia} en ese horario.")

        legajo_id = self.cargo.legajo_id if self.cargo_id else None
        if legajo_id is None:
            return
        del_docente = (
            AsignacionHoraria.objects.filter(
                version_id=self.version_id, legajo_id=legajo_id, dia_semana=dia
            )
            .exclude(pk=self.pk)
            .select_related("curso")
        )
        for otra in del_docente:
            if se_superponen(inicio, fin, otra.hora_inicio, otra.hora_fin):
                raise ValidationError(f"El docente ya está en {otra.curso} en ese horario.")
