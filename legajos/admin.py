"""Pantallas de legajos: la carpeta de cada persona y sus cargos."""

from datetime import date, timedelta

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.admin import AdminInstitucional, InlineInstitucional, registrar_ruta_institucion

from .antiguedad import calcular_antiguedad
from .models import (
    Cargo,
    DocumentoLegajo,
    Legajo,
    ServicioAnterior,
    TipoDocumento,
    Titulo,
)

# Modelos que llegan a la institución a través del legajo.
for modelo in (DocumentoLegajo, Titulo, ServicioAnterior):
    registrar_ruta_institucion(modelo, "legajo__institucion")


class EstadoVencimiento(admin.SimpleListFilter):
    """Filtro por vencimiento: lo que la secretaría necesita reclamar."""

    title = "vencimiento"
    parameter_name = "vencimiento"

    def lookups(self, request, model_admin):
        return [
            ("vencido", "Vencidos"),
            ("por_vencer", "Vencen en 60 días"),
            ("vigente", "Vigentes"),
            ("sin_fecha", "Sin vencimiento"),
        ]

    def queryset(self, request, queryset):
        hoy = date.today()
        if self.value() == "vencido":
            return queryset.filter(fecha_vencimiento__lt=hoy)
        if self.value() == "por_vencer":
            return queryset.filter(
                fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=hoy + timedelta(days=60)
            )
        if self.value() == "vigente":
            return queryset.filter(fecha_vencimiento__gte=hoy)
        if self.value() == "sin_fecha":
            return queryset.filter(fecha_vencimiento__isnull=True)
        return queryset


class CargoInline(InlineInstitucional):
    model = Cargo
    fields = (
        "tipo",
        "denominacion",
        "materia",
        "curso",
        "horas_semanales",
        "situacion_revista",
        "fuente_pago",
        "fecha_alta",
        "fecha_baja",
        "motivo_baja",
    )
    autocomplete_fields = ("materia", "curso")
    ordering = ("-fecha_alta",)


class DocumentoInline(InlineInstitucional):
    model = DocumentoLegajo
    fields = ("tipo", "archivo", "fecha_emision", "fecha_vencimiento", "observaciones")


class TituloInline(InlineInstitucional):
    model = Titulo
    fields = ("tipo", "nombre", "institucion_otorgante", "fecha_egreso", "registrado", "archivo")


class ServicioAnteriorInline(InlineInstitucional):
    model = ServicioAnterior
    fields = ("institucion_nombre", "cargo_descripcion", "desde", "hasta", "es_docente", "archivo")


@admin.register(Legajo)
class LegajoAdmin(AdminInstitucional):
    list_display = (
        "nombre_completo",
        "cuil",
        "plantel",
        "estado",
        "resumen_cargos",
        "antiguedad_total",
        "alerta_documentacion",
        "certificacion",
    )
    list_filter = ("plantel", "estado", "cargos__fuente_pago", "cargos__situacion_revista")
    search_fields = ("apellido", "nombre", "cuil", "dni", "numero")
    inlines = [CargoInline, DocumentoInline, TituloInline, ServicioAnteriorInline]

    fieldsets = (
        (None, {"fields": ("numero", "apellido", "nombre", "estado")}),
        ("Identificación", {"fields": ("cuil", "dni", "fecha_nacimiento", "obra_social")}),
        ("Contacto", {"fields": ("email", "telefono", "domicilio", "localidad")}),
        ("En la institución", {"fields": ("plantel", "fecha_ingreso", "usuario", "observaciones")}),
        (
            "Materias que puede dar",
            {
                "fields": ("materias_que_puede_dar",),
                "description": (
                    "No es lo que da hoy —eso sale de los cargos— sino lo que está "
                    "en condiciones de dar. Es lo que el sistema mira para buscarle "
                    "reemplazo a un curso que quedó sin clase."
                ),
            },
        ),
    )
    filter_horizontal = ("materias_que_puede_dar",)

    @admin.display(description="cargos vigentes")
    def resumen_cargos(self, obj):
        vigentes = list(obj.cargos_vigentes())
        if not vigentes:
            return "—"
        horas = sum(cargo.horas_semanales or 0 for cargo in vigentes)
        detalle = f"{len(vigentes)} cargo{'s' if len(vigentes) != 1 else ''}"
        if horas:
            detalle += f" · {horas} hs"
        # El origen del pago es lo que define a qué planilla va cada novedad.
        fuentes = {cargo.get_fuente_pago_display().split(" (")[0] for cargo in vigentes}
        return f"{detalle} ({', '.join(sorted(fuentes))})"

    @admin.display(description="antigüedad")
    def antiguedad_total(self, obj):
        return str(calcular_antiguedad(obj))

    @admin.display(description="documentación")
    def alerta_documentacion(self, obj):
        documentos = list(obj.documentos.select_related("tipo"))
        vencidos = [doc for doc in documentos if doc.esta_vencido]
        por_vencer = [doc for doc in documentos if doc.por_vencer]
        if vencidos:
            return format_html(
                '<span style="color:#b4451f;font-weight:600">{} vencido{}</span>',
                len(vencidos),
                "s" if len(vencidos) != 1 else "",
            )
        if por_vencer:
            return format_html('<span style="color:#a06000">{} por vencer</span>', len(por_vencer))
        return "al día"

    @admin.display(description="certificación")
    def certificacion(self, obj):
        url = reverse("certificacion_servicios", args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Certificar servicios</a>', url)


@admin.register(Cargo)
class CargoAdmin(AdminInstitucional):
    """Vista transversal de cargos: es la que se mira para armar las novedades."""

    list_display = (
        "legajo",
        "descripcion",
        "tipo",
        "horas_semanales",
        "situacion_revista",
        "fuente_pago",
        "fecha_alta",
        "fecha_baja",
        "vigente",
    )
    list_filter = ("fuente_pago", "situacion_revista", "tipo", "nivel", "motivo_baja")
    search_fields = ("legajo__apellido", "legajo__nombre", "denominacion", "materia__nombre")
    autocomplete_fields = ("legajo", "materia", "curso")
    date_hierarchy = "fecha_alta"

    @admin.display(boolean=True, description="vigente")
    def vigente(self, obj):
        return obj.esta_vigente


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(AdminInstitucional):
    list_display = ("nombre", "lleva_vencimiento", "dias_preaviso", "obligatorio")
    list_filter = ("lleva_vencimiento", "obligatorio")


@admin.register(DocumentoLegajo)
class DocumentoLegajoAdmin(AdminInstitucional):
    """Listado transversal para reclamar la documentación que vence."""

    list_display = ("legajo", "tipo", "fecha_emision", "fecha_vencimiento", "situacion")
    list_filter = (EstadoVencimiento, "tipo")
    search_fields = ("legajo__apellido", "legajo__nombre")
    autocomplete_fields = ("legajo",)
    date_hierarchy = "fecha_vencimiento"
    exclude = ()

    @admin.display(description="situación")
    def situacion(self, obj):
        if obj.esta_vencido:
            return format_html(
                '<span style="color:#b4451f;font-weight:600">vencido hace {} días</span>',
                abs(obj.dias_para_vencer()),
            )
        if obj.por_vencer:
            return format_html(
                '<span style="color:#a06000">vence en {} días</span>', obj.dias_para_vencer()
            )
        return "vigente"


@admin.register(Titulo)
class TituloAdmin(AdminInstitucional):
    list_display = ("legajo", "tipo", "nombre", "institucion_otorgante", "registrado")
    list_filter = ("tipo", "registrado")
    search_fields = ("legajo__apellido", "legajo__nombre", "nombre")
    autocomplete_fields = ("legajo",)
    exclude = ()


@admin.register(ServicioAnterior)
class ServicioAnteriorAdmin(AdminInstitucional):
    list_display = ("legajo", "institucion_nombre", "desde", "hasta", "es_docente")
    list_filter = ("es_docente",)
    search_fields = ("legajo__apellido", "legajo__nombre", "institucion_nombre")
    autocomplete_fields = ("legajo",)
    exclude = ()
