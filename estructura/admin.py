"""Pantallas de carga de la estructura del colegio."""

from django.contrib import admin, messages
from django.db import transaction

from core.admin import AdminInstitucional, InlineInstitucional, registrar_ruta_institucion

from .models import (
    BloqueHorario,
    CicloLectivo,
    Curso,
    EsquemaHorario,
    Materia,
    MateriaPlan,
    Nivel,
    PeriodoAcademico,
    Turno,
)

# Estos modelos no guardan la institución: se llega por su relación padre.
registrar_ruta_institucion(PeriodoAcademico, "ciclo__institucion")
registrar_ruta_institucion(BloqueHorario, "esquema__institucion")
registrar_ruta_institucion(MateriaPlan, "curso__institucion")


@admin.register(Nivel)
class NivelAdmin(AdminInstitucional):
    list_display = ("__str__", "tipo", "orden")
    list_editable = ("orden",)
    ordering = ("orden",)


class PeriodoAcademicoInline(InlineInstitucional):
    model = PeriodoAcademico
    fields = ("orden", "nombre", "fecha_inicio", "fecha_fin")
    ordering = ("orden",)


@admin.register(CicloLectivo)
class CicloLectivoAdmin(AdminInstitucional):
    list_display = ("anio", "fecha_inicio", "fecha_fin", "estado", "cantidad_periodos")
    list_filter = ("estado",)
    inlines = [PeriodoAcademicoInline]

    @admin.display(description="períodos")
    def cantidad_periodos(self, obj):
        return obj.periodos.count()


@admin.register(Turno)
class TurnoAdmin(AdminInstitucional):
    list_display = ("nombre", "nivel", "hora_inicio", "hora_fin", "orden")
    list_filter = ("nivel",)


class BloqueHorarioInline(InlineInstitucional):
    model = BloqueHorario
    fields = ("dia_semana", "orden", "tipo", "hora_inicio", "hora_fin", "etiqueta")
    ordering = ("dia_semana", "hora_inicio")


@admin.register(EsquemaHorario)
class EsquemaHorarioAdmin(AdminInstitucional):
    list_display = ("nombre", "turno", "predeterminado", "horas_semanales", "cursos_que_lo_usan")
    list_filter = ("turno", "predeterminado")
    inlines = [BloqueHorarioInline]
    actions = ["replicar_lunes"]

    @admin.display(description="horas de clase por semana")
    def horas_semanales(self, obj):
        return obj.cantidad_horas_semanales

    @admin.display(description="cursos")
    def cursos_que_lo_usan(self, obj):
        return obj.cursos.count()

    @admin.action(description="Copiar los bloques del lunes al resto de la semana")
    def replicar_lunes(self, request, queryset):
        """Carga la grilla una vez y replica; después se ajustan las diferencias.

        Solo completa los días que están vacíos: nunca pisa lo ya cargado.
        """
        creados = 0
        omitidos = []
        for esquema in queryset:
            lunes = list(esquema.bloques.filter(dia_semana=0).order_by("hora_inicio"))
            if not lunes:
                omitidos.append(f"{esquema} (no tiene bloques el lunes)")
                continue
            with transaction.atomic():
                for dia in range(1, 5):
                    if esquema.bloques.filter(dia_semana=dia).exists():
                        continue
                    BloqueHorario.objects.bulk_create(
                        BloqueHorario(
                            esquema=esquema,
                            dia_semana=dia,
                            orden=bloque.orden,
                            tipo=bloque.tipo,
                            hora_inicio=bloque.hora_inicio,
                            hora_fin=bloque.hora_fin,
                            etiqueta=bloque.etiqueta,
                        )
                        for bloque in lunes
                    )
                    creados += len(lunes)
        if creados:
            self.message_user(request, f"Se crearon {creados} bloques.", messages.SUCCESS)
        for aviso in omitidos:
            self.message_user(request, f"Sin cambios en {aviso}.", messages.WARNING)
        if not creados and not omitidos:
            self.message_user(request, "No había días vacíos para completar.", messages.INFO)


@admin.register(BloqueHorario)
class BloqueHorarioAdmin(AdminInstitucional):
    """Edición masiva de la grilla, con filtros por esquema y por día."""

    list_display = ("esquema", "dia_semana", "orden", "tipo", "hora_inicio", "hora_fin", "duracion")
    list_filter = ("esquema", "dia_semana", "tipo")
    list_editable = ("hora_inicio", "hora_fin", "tipo")
    ordering = ("esquema", "dia_semana", "hora_inicio")
    exclude = ()

    @admin.display(description="duración")
    def duracion(self, obj):
        return f"{obj.duracion_minutos} min"


@admin.register(Materia)
class MateriaAdmin(AdminInstitucional):
    list_display = ("nombre", "nivel", "abreviatura")
    list_filter = ("nivel",)
    search_fields = ("nombre", "abreviatura")


class MateriaPlanInline(InlineInstitucional):
    model = MateriaPlan
    fields = ("materia", "horas_semanales", "vigencia", "periodo")
    autocomplete_fields = ("materia",)


@admin.register(Curso)
class CursoAdmin(AdminInstitucional):
    list_display = (
        "__str__",
        "nivel",
        "turno",
        "ciclo_lectivo",
        "esquema_horario",
        "horas_del_plan",
        "horas_de_la_grilla",
    )
    list_filter = ("ciclo_lectivo", "nivel", "turno")
    # Necesario para que otros módulos puedan elegir el curso por autocompletado.
    search_fields = ("anio_estudio", "division")
    inlines = [MateriaPlanInline]

    @admin.display(description="horas del plan")
    def horas_del_plan(self, obj):
        return obj.horas_asignadas()

    @admin.display(description="horas de la grilla")
    def horas_de_la_grilla(self, obj):
        """Cuántas horas de clase entran en la semana del curso.

        Si el plan pide más horas que las que ofrece la grilla, el horario no
        va a poder armarse: conviene verlo acá y no recién al generarlo.
        """
        return obj.esquema_horario.cantidad_horas_semanales


@admin.register(MateriaPlan)
class MateriaPlanAdmin(AdminInstitucional):
    list_display = ("curso", "materia", "horas_semanales", "vigencia", "periodo")
    list_filter = ("curso__ciclo_lectivo", "curso__nivel", "vigencia")
    search_fields = ("materia__nombre",)
    autocomplete_fields = ("materia",)
    exclude = ()
