"""Consulta y carga manual de novedades.

La operación normal es la pantalla de novedades del mes; acá se cargan las
novedades que no salen de ningún registro (un pago adicional acordado, una
corrección puntual) y se consulta el histórico.
"""

from django.contrib import admin
from django.utils.html import format_html

from core.admin import AdminInstitucional

from .models import Novedad, Origen, PeriodoNovedades


@admin.register(PeriodoNovedades)
class PeriodoNovedadesAdmin(AdminInstitucional):
    list_display = ("__str__", "estado", "compilado_en", "cerrado_en", "cerrado_por")
    list_filter = ("estado", "anio")
    readonly_fields = ("compilado_en", "cerrado_en", "cerrado_por")


@admin.register(Novedad)
class NovedadAdmin(AdminInstitucional):
    list_display = (
        "periodo",
        "legajo",
        "tipo",
        "fecha",
        "espacio",
        "dias",
        "horas",
        "destino",
        "estado_informe",
    )
    list_filter = ("periodo", "tipo", "destino", "informada", "origen", "impacta_haberes")
    search_fields = ("legajo__apellido", "legajo__nombre", "espacio", "motivo")
    autocomplete_fields = ("legajo", "cargo")
    date_hierarchy = "fecha"
    readonly_fields = ("clave_origen", "informada_en", "informada_por", "congelada")

    fieldsets = (
        (None, {"fields": ("periodo", "legajo", "cargo", "tipo", "destino")}),
        ("Datos", {"fields": ("fecha", "fecha_fin", "dias", "horas", "espacio", "motivo")}),
        (
            "Planilla",
            {
                "fields": (
                    "reemplazante",
                    "presenta_certificado",
                    "jornada_completa",
                    "tiempo_determinado",
                    "impacta_haberes",
                    "observaciones",
                )
            },
        ),
        (
            "Seguimiento",
            {
                "fields": (
                    "origen",
                    "clave_origen",
                    "informada",
                    "informada_en",
                    "informada_por",
                    "congelada",
                )
            },
        ),
    )

    @admin.display(description="estado")
    def estado_informe(self, obj):
        if obj.congelada:
            return format_html('<span style="color:#4a5c6b">cerrada</span>')
        if obj.informada:
            return "informada"
        if not obj.impacta_haberes:
            return format_html('<span style="color:#4a5c6b">no se informa</span>')
        return format_html('<span style="color:#b4451f;font-weight:600">pendiente</span>')

    def save_model(self, request, obj, form, change):
        # Lo que se carga desde acá es manual: la compilación no debe pisarlo.
        if not change:
            obj.origen = Origen.MANUAL
        super().save_model(request, obj, form, change)
