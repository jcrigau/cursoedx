"""Pantallas de horarios: DDJJ, versiones y generación."""

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from core.admin import AdminInstitucional, InlineInstitucional, registrar_ruta_institucion

from .generador import Parametros, generar
from .models import (
    AsignacionHoraria,
    DeclaracionDisponibilidad,
    EstadoVersion,
    FranjaNoDisponible,
    VersionHorario,
)

registrar_ruta_institucion(FranjaNoDisponible, "declaracion__institucion")
registrar_ruta_institucion(AsignacionHoraria, "version__institucion")


class FranjaInline(InlineInstitucional):
    model = FranjaNoDisponible
    fields = (
        "dia_semana",
        "hora_desde",
        "hora_hasta",
        "motivo",
        "institucion_externa",
        "es_preferencia",
    )
    ordering = ("dia_semana", "hora_desde")
    extra = 1


@admin.register(DeclaracionDisponibilidad)
class DeclaracionDisponibilidadAdmin(AdminInstitucional):
    """Las DDJJ son el insumo del generador: sin ellas el horario choca."""

    list_display = ("legajo", "periodo", "presentada_en", "cantidad_franjas", "tiene_archivo")
    list_filter = ("periodo", "presentada_en")
    search_fields = ("legajo__apellido", "legajo__nombre")
    autocomplete_fields = ("legajo",)
    inlines = [FranjaInline]

    @admin.display(description="franjas declaradas")
    def cantidad_franjas(self, obj):
        duras = obj.franjas_duras().count()
        preferencias = obj.franjas_preferidas().count()
        detalle = f"{duras} no disponible{'s' if duras != 1 else ''}"
        if preferencias:
            detalle += f" · {preferencias} preferencia{'s' if preferencias != 1 else ''}"
        return detalle

    @admin.display(boolean=True, description="firmada")
    def tiene_archivo(self, obj):
        return bool(obj.archivo)


@admin.register(VersionHorario)
class VersionHorarioAdmin(AdminInstitucional):
    list_display = ("nombre", "periodo", "estado", "cantidad_asignaciones", "resumen_corto", "ver")
    list_filter = ("estado", "periodo")
    readonly_fields = ("generada_en", "generada_por", "parametros", "resumen")
    actions = ["accion_generar", "accion_publicar"]

    @admin.display(description="horas ubicadas")
    def cantidad_asignaciones(self, obj):
        return obj.asignaciones.count()

    @admin.display(description="resultado")
    def resumen_corto(self, obj):
        if not obj.resumen:
            return "sin generar"
        return (
            f"{obj.resumen.get('docentes', 0)} docentes · "
            f"{obj.resumen.get('promedio_dias_por_docente', '—')} días promedio"
        )

    @admin.display(description="horario")
    def ver(self, obj):
        if not obj.asignaciones.exists():
            return "—"
        url = reverse("horario_version", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Ver grillas</a>', url)

    @admin.action(description="Generar el horario (puede tardar)")
    def accion_generar(self, request, queryset):
        for version in queryset:
            if version.estado == EstadoVersion.HISTORICO:
                self.message_user(
                    request, f"«{version}» es histórica: no se regenera.", messages.WARNING
                )
                continue

            resultado = generar(version, Parametros(), usuario=request.user)

            for aviso in resultado.avisos:
                self.message_user(request, aviso, messages.WARNING)
            if not resultado.exito:
                for problema in resultado.problemas:
                    self.message_user(request, problema, messages.ERROR)
                continue

            metricas = resultado.metricas
            self.message_user(
                request,
                f"«{version}»: {resultado.asignaciones_creadas} horas ubicadas en "
                f"{metricas['segundos']} s. Cada docente viene "
                f"{metricas['promedio_dias_por_docente']} días en promedio "
                f"(máximo {metricas['maximo_dias_por_docente']}).",
                messages.SUCCESS,
            )

    @admin.action(description="Publicar como horario vigente")
    def accion_publicar(self, request, queryset):
        for version in queryset:
            if not version.asignaciones.exists():
                self.message_user(request, f"«{version}» no tiene horario cargado.", messages.ERROR)
                continue
            version.publicar()
            self.message_user(
                request,
                f"«{version}» quedó vigente; la anterior del período pasó a histórica.",
                messages.SUCCESS,
            )


@admin.register(AsignacionHoraria)
class AsignacionHorariaAdmin(AdminInstitucional):
    """Ajuste fino del borrador, con control de choques al guardar."""

    list_display = (
        "version",
        "curso",
        "materia",
        "legajo",
        "dia_semana",
        "hora_inicio",
        "bloqueada",
    )
    list_filter = ("version", "curso", "dia_semana", "bloqueada")
    search_fields = ("materia__nombre", "legajo__apellido", "legajo__nombre")
    autocomplete_fields = ("curso", "materia", "cargo", "bloque")
    list_editable = ("bloqueada",)
    exclude = ("legajo", "dia_semana", "hora_inicio", "hora_fin")
