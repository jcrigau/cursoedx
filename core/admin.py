"""Panel de administración: base multi-institución y ABM de accesos.

``AdminInstitucional`` es la clase de la que heredan todas las pantallas de
datos de la escuela. Se encarga de tres cosas que, si quedaran libradas a cada
pantalla, tarde o temprano filtrarían datos entre escuelas:

1. mostrar solo lo de la institución activa,
2. asignarla sola al crear un registro,
3. limitar los desplegables a esa misma institución.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from django.db import models as django_models

from .models import Institucion, Membresia, RegistroAuditoria, Usuario

# Modelos que llegan a la institución por una relación en vez de tenerla propia.
RUTAS_INSTITUCION: dict[type, str] = {}


def registrar_ruta_institucion(modelo: type, ruta: str) -> None:
    """Declara cómo se llega desde ``modelo`` hasta su institución."""
    RUTAS_INSTITUCION[modelo] = ruta


def ruta_institucion(modelo: type) -> str | None:
    """Lookup para filtrar ese modelo por institución, o ``None`` si no aplica."""
    if modelo in RUTAS_INSTITUCION:
        return RUTAS_INSTITUCION[modelo]
    try:
        campo = modelo._meta.get_field("institucion")
    except Exception:
        return None
    return "institucion" if isinstance(campo, django_models.ForeignKey) else None


def filtrar_por_institucion(queryset, institucion):
    """Acota un queryset a la institución activa (vacío si no hay ninguna)."""
    ruta = ruta_institucion(queryset.model)
    if ruta is None:
        return queryset
    if institucion is None:
        return queryset.none()
    return queryset.filter(**{ruta: institucion})


class MezclaInstitucional:
    """Comportamiento compartido por admins e inlines con institución."""

    def get_queryset(self, request):
        return filtrar_por_institucion(super().get_queryset(request), request.institucion)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if "queryset" not in kwargs:
            relacionado = db_field.remote_field.model
            if ruta_institucion(relacionado) is not None:
                kwargs["queryset"] = filtrar_por_institucion(
                    relacionado._default_manager.all(), request.institucion
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if hasattr(obj, "institucion_id") and obj.institucion_id is None:
            obj.institucion = request.institucion
        super().save_model(request, obj, form, change)


class AdminInstitucional(MezclaInstitucional, admin.ModelAdmin):
    """Admin de datos de una escuela: siempre acotado a la institución activa."""

    exclude = ("institucion",)

    def has_add_permission(self, request):
        # Sin institución activa no hay dónde guardar.
        if request.institucion is None:
            return False
        return super().has_add_permission(request)


class InlineInstitucional(MezclaInstitucional, admin.TabularInline):
    """Inline de un modelo con institución (o que llega a ella por relación)."""

    extra = 0

    def save_new_objects(self, *args, **kwargs):  # pragma: no cover - compatibilidad
        return super().save_new_objects(*args, **kwargs)


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    """Alta de escuelas: tarea del administrador del producto."""

    list_display = ("nombre_corto", "nombre", "jurisdiccion", "localidad", "activa")
    list_filter = ("activa", "jurisdiccion")
    search_fields = ("nombre", "nombre_corto", "cue", "cuit")
    fieldsets = (
        (None, {"fields": ("nombre", "nombre_corto", "activa")}),
        ("Identificación", {"fields": ("cue", "cuit", "jurisdiccion")}),
        ("Contacto", {"fields": ("domicilio", "localidad", "telefono", "email")}),
        (
            "Ubicación (para el fichaje del portal)",
            {
                "fields": ("latitud", "longitud", "radio_fichaje_metros"),
                "classes": ("collapse",),
                "description": (
                    "Coordenadas de la escuela. Se pueden copiar de Google Maps: "
                    "botón derecho sobre el edificio → el primer valor es la latitud."
                ),
            },
        ),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class MembresiaInline(admin.TabularInline):
    model = Membresia
    extra = 1
    autocomplete_fields = ("institucion",)


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Usuarios del sistema, identificados por email."""

    add_form = UserCreationForm
    form = UserChangeForm
    change_password_form = AdminPasswordChangeForm
    model = Usuario
    inlines = [MembresiaInline]

    list_display = ("email", "apellido", "nombre", "is_active", "is_staff")
    list_filter = ("is_active", "is_staff", "is_superuser", "membresias__rol")
    search_fields = ("email", "nombre", "apellido")
    ordering = ("apellido", "nombre")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("nombre", "apellido", "telefono")}),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nombre", "apellido", "password1", "password2"),
            },
        ),
    )


@admin.register(Membresia)
class MembresiaAdmin(AdminInstitucional):
    """Quién entra a esta escuela y con qué rol."""

    list_display = ("usuario", "rol", "activa", "creada_en")
    list_filter = ("rol", "activa")
    search_fields = ("usuario__email", "usuario__nombre", "usuario__apellido")
    autocomplete_fields = ("usuario",)


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Bitácora de solo lectura: se consulta, no se edita."""

    list_display = ("creado_en", "accion", "modelo", "objeto_id", "usuario", "descripcion")
    list_filter = ("accion", "modelo")
    search_fields = ("descripcion", "objeto_id", "usuario__email")
    date_hierarchy = "creado_en"

    def get_queryset(self, request):
        return filtrar_por_institucion(super().get_queryset(request), request.institucion)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "SGE · Gestión escolar"
admin.site.site_title = "SGE"
admin.site.index_title = "Administración"
