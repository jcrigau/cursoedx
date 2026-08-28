"""Lo que llega desde el portal, para que secretaría lo revise."""

from django.contrib import admin, messages
from django.utils.html import format_html

from core.admin import AdminInstitucional

from .models import AvisoInasistencia, EstadoAviso, Fichada


@admin.register(AvisoInasistencia)
class AvisoInasistenciaAdmin(AdminInstitucional):
    """Avisos de los docentes. Aparecen también en el parte del día."""

    list_display = ("fecha", "legajo", "motivo", "detalle", "estado", "creado_en")
    list_filter = ("estado", "motivo", "fecha")
    search_fields = ("legajo__apellido", "legajo__nombre", "detalle")
    autocomplete_fields = ("legajo",)
    date_hierarchy = "fecha"
    readonly_fields = ("visto_en",)
    actions = ["accion_marcar_visto"]

    @admin.action(description="Marcar como visto")
    def accion_marcar_visto(self, request, queryset):
        vistos = 0
        for aviso in queryset.filter(estado=EstadoAviso.ENVIADO):
            aviso.marcar_visto()
            vistos += 1
        self.message_user(request, f"{vistos} avisos marcados como vistos.", messages.SUCCESS)


@admin.register(Fichada)
class FichadaAdmin(AdminInstitucional):
    """Marcas de entrada y salida hechas desde el celular."""

    list_display = ("fecha", "hora", "legajo", "tipo", "ubicacion")
    list_filter = ("tipo", "en_la_escuela", "fecha")
    search_fields = ("legajo__apellido", "legajo__nombre")
    autocomplete_fields = ("legajo",)
    date_hierarchy = "fecha"
    readonly_fields = ("distancia_metros", "en_la_escuela")

    @admin.display(description="ubicación")
    def ubicacion(self, obj):
        if obj.latitud is None:
            return format_html('<span style="color:#a06000">sin ubicación</span>')
        if obj.en_la_escuela:
            return format_html('<span style="color:#2f6b3a">en la escuela</span>')
        return format_html(
            '<span style="color:#b4451f;font-weight:600">a {} m</span>', obj.distancia_metros
        )
