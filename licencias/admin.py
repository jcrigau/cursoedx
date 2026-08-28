"""Pantallas de licencias, con el flujo de aprobación y la cobertura."""

from django.contrib import admin, messages
from django.utils.html import format_html

from core.admin import AdminInstitucional, InlineInstitucional

from .models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia


@admin.register(TipoLicencia)
class TipoLicenciaAdmin(AdminInstitucional):
    """Catálogo del régimen: se carga una vez y se ajusta si cambia la norma."""

    list_display = (
        "__str__",
        "con_goce",
        "impacta_haberes",
        "topes",
        "extensible_con_aval",
        "requiere_certificado",
        "activo",
    )
    list_filter = ("con_goce", "impacta_haberes", "activo")
    search_fields = ("codigo", "nombre")

    @admin.display(description="topes")
    def topes(self, obj):
        partes = []
        if obj.tope_dias_anual:
            partes.append(f"{obj.tope_dias_anual}/año")
        if obj.tope_dias_por_caso:
            partes.append(f"{obj.tope_dias_por_caso} por caso")
        if obj.tope_dias_consecutivos:
            partes.append(f"máx. {obj.tope_dias_consecutivos} seguidos")
        return " · ".join(partes) or "sin tope"


class CoberturaInline(InlineInstitucional):
    model = Cobertura
    fields = ("cargo", "tipo", "suplente", "fecha_inicio", "fecha_fin", "observaciones")
    autocomplete_fields = ("cargo", "suplente")
    extra = 0


@admin.register(Licencia)
class LicenciaAdmin(AdminInstitucional):
    list_display = (
        "legajo",
        "tipo",
        "fecha_inicio",
        "fecha_fin",
        "cantidad_dias",
        "situacion_actual",
        "cobertura_resuelta",
    )
    list_filter = ("estado", "tipo", "tipo__con_goce")
    search_fields = ("legajo__apellido", "legajo__nombre", "tipo__nombre", "tipo__codigo")
    autocomplete_fields = ("legajo",)
    filter_horizontal = ("cargos",)
    date_hierarchy = "fecha_inicio"
    inlines = [CoberturaInline]
    readonly_fields = ("resuelta_en", "resuelta_por")
    actions = ["accion_aprobar", "accion_rechazar"]

    fieldsets = (
        (None, {"fields": ("legajo", "tipo", "fecha_inicio", "fecha_fin", "estado")}),
        (
            "Alcance",
            {
                "fields": ("cargos", "prorroga_de"),
                "description": "Si no se eligen cargos, la licencia afecta a todos los vigentes.",
            },
        ),
        ("Respaldo", {"fields": ("certificado", "aval", "observaciones")}),
        (
            "Resolución",
            {"fields": ("solicitada_en", "resuelta_en", "resuelta_por", "motivo_rechazo")},
        ),
    )

    @admin.display(description="días")
    def cantidad_dias(self, obj):
        return obj.dias

    @admin.display(description="situación")
    def situacion_actual(self, obj):
        situacion = obj.situacion
        if situacion == "En curso":
            return format_html('<strong style="color:#0f6b63">{}</strong>', situacion)
        return situacion

    @admin.display(description="cobertura")
    def cobertura_resuelta(self, obj):
        """Avisa si quedaron cargos sin decidir qué hacer con sus horas."""
        if obj.estado != EstadoLicencia.APROBADA:
            return "—"
        decididos = obj.coberturas.count()
        afectados = obj.cargos_afectados().count()
        if afectados == 0:
            return "sin cargos"
        if decididos >= afectados:
            sin_cubrir = obj.coberturas.filter(tipo=TipoCobertura.SIN_COBERTURA).count()
            if sin_cubrir:
                return format_html('<span style="color:#a06000">{} sin cubrir</span>', sin_cubrir)
            return "cubierta"
        return format_html(
            '<span style="color:#b4451f;font-weight:600">faltan {}</span>', afectados - decididos
        )

    @admin.action(description="Aprobar las licencias seleccionadas")
    def accion_aprobar(self, request, queryset):
        aprobadas = 0
        for licencia in queryset.exclude(estado=EstadoLicencia.APROBADA):
            excesos = licencia.excesos()
            if excesos and not (licencia.tipo.extensible_con_aval and licencia.aval):
                self.message_user(request, f"{licencia}: {' '.join(excesos)}", messages.ERROR)
                continue
            licencia.aprobar(usuario=request.user)
            aprobadas += 1
        if aprobadas:
            self.message_user(
                request,
                f"Se aprobaron {aprobadas} licencias. Falta definir la cobertura de las horas.",
                messages.SUCCESS,
            )

    @admin.action(description="Rechazar las licencias seleccionadas")
    def accion_rechazar(self, request, queryset):
        for licencia in queryset:
            licencia.rechazar(usuario=request.user)
        self.message_user(request, "Licencias rechazadas.", messages.SUCCESS)


@admin.register(Cobertura)
class CoberturaAdmin(AdminInstitucional):
    """Qué se hizo con las horas de cada licencia."""

    list_display = ("cargo", "tipo", "suplente", "fecha_inicio", "fecha_fin", "designacion")
    list_filter = ("tipo",)
    search_fields = (
        "suplente__apellido",
        "suplente__nombre",
        "cargo__legajo__apellido",
        "cargo__denominacion",
        "cargo__materia__nombre",
    )
    autocomplete_fields = ("licencia", "cargo", "suplente")
    actions = ["accion_designar"]

    @admin.display(description="designación del suplente")
    def designacion(self, obj):
        if obj.tipo == TipoCobertura.SIN_COBERTURA:
            return "los alumnos quedan libres"
        if obj.cargo_suplente_id:
            return "cargo creado"
        return format_html('<span style="color:#b4451f">falta crear el cargo</span>')

    @admin.action(description="Crear el cargo del suplente")
    def accion_designar(self, request, queryset):
        """Le da de alta al suplente el cargo que va a ocupar.

        A partir de ahí aparece en el parte diario y su alta y su cese salen
        como novedades para la liquidación.
        """
        creados = 0
        for cobertura in queryset:
            if cobertura.designar_cargo_del_suplente():
                creados += 1
        if creados:
            self.message_user(
                request, f"Se crearon {creados} designaciones de suplente.", messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "No había nada para designar (o eran coberturas sin suplente).",
                messages.WARNING,
            )
