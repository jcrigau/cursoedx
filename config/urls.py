from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from asistencia import views as asistencia_views
from core import views as core_views
from horarios import views as horarios_views
from legajos import views as legajos_views
from licencias import views as licencias_views
from novedades import views as novedades_views
from portal import views as portal_views

urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("institucion/cambiar/", core_views.cambiar_institucion, name="cambiar_institucion"),
    path("sistema/", core_views.estado_del_sistema, name="estado_del_sistema"),
    path("legajos/buscar/", legajos_views.buscar, name="buscar_personas"),
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
    path("asistencia/cursos/", asistencia_views.cursos_del_dia, name="cursos_del_dia"),
    path(
        "licencias/sin-cobertura/",
        licencias_views.dejar_sin_cobertura,
        name="dejar_sin_cobertura",
    ),
    path(
        "licencias/suplencia/<int:pk>/extender/",
        licencias_views.extender_suplencia,
        name="extender_suplencia",
    ),
    path(
        "licencias/suplencia/<int:pk>/cesar/",
        licencias_views.cesar_suplencia,
        name="cesar_suplencia",
    ),
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
    path("portal/", portal_views.inicio, name="portal_inicio"),
    path("portal/horario/", portal_views.mi_horario, name="portal_horario"),
    path("portal/legajo/", portal_views.mi_legajo, name="portal_legajo"),
    path("portal/licencias/", portal_views.mis_licencias, name="portal_licencias"),
    path("portal/avisar/", portal_views.avisar, name="portal_avisar"),
    path("portal/avisar/<int:pk>/anular/", portal_views.anular_aviso, name="portal_anular_aviso"),
    path("portal/fichar/", portal_views.fichar, name="portal_fichar"),
    path("cuentas/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
