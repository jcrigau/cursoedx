from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from asistencia import views as asistencia_views
from core import views as core_views
from horarios import views as horarios_views
from legajos import views as legajos_views
from novedades import views as novedades_views

urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("institucion/cambiar/", core_views.cambiar_institucion, name="cambiar_institucion"),
    path(
        "legajos/<int:pk>/certificacion/",
        legajos_views.certificacion_servicios,
        name="certificacion_servicios",
    ),
    path("horarios/<int:pk>/", horarios_views.version, name="horario_version"),
    path(
        "horarios/<int:pk>/curso/<int:curso_id>/", horarios_views.grilla_curso, name="horario_curso"
    ),
    path(
        "horarios/<int:pk>/docente/<int:legajo_id>/",
        horarios_views.grilla_docente,
        name="horario_docente",
    ),
    path("asistencia/", asistencia_views.parte_del_dia, name="parte_diario"),
    path("asistencia/resumen/", asistencia_views.resumen_del_mes, name="resumen_asistencia"),
    path("novedades/", novedades_views.periodos, name="novedades_periodos"),
    path("novedades/<int:anio>/<int:mes>/", novedades_views.detalle, name="novedades_detalle"),
    path(
        "novedades/<int:anio>/<int:mes>/exportar/",
        novedades_views.exportar,
        name="novedades_exportar",
    ),
    path(
        "novedades/marcar/<int:pk>/",
        novedades_views.alternar_informada,
        name="novedades_alternar",
    ),
    path("cuentas/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
