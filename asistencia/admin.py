"""Consulta y corrección de los registros de asistencia.

La carga del día a día se hace en el parte diario (una pantalla propia); acá se
consulta el histórico y se corrige algún caso puntual.
"""

from django.contrib import admin
from django.utils.html import format_html

from core.admin import AdminInstitucional

from .models import RegistroAsistencia


@admin.register(RegistroAsistencia)
class RegistroAsistenciaAdmin(AdminInstitucional):
    list_display = (
        "fecha",
        "legajo",
        "estado",
        "horas_afectadas",
        "justificacion",
        "registrado_por",
    )
    list_filter = ("estado", "fecha")
    search_fields = ("legajo__apellido", "legajo__nombre", "observaciones")
    autocomplete_fields = ("legajo", "licencia")
    date_hierarchy = "fecha"
    readonly_fields = ("registrado_por",)

    @admin.display(description="justificación")
    def justificacion(self, obj):
        if not obj.es_ausencia:
            return "—"
        if obj.justificada:
            return str(obj.licencia.tipo)
        return format_html('<span style="color:#b4451f;font-weight:600">injustificada</span>')
