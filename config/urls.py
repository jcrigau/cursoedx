import os

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from asistencia import views as asistencia_views
from core import views as core_views
from core.archivos import servir_media
from core.vistas_acceso import IngresoView
from horarios import views as horarios_views
from legajos import views as legajos_views
from licencias import views as licencias_views
from novedades import views as novedades_views
from portal import views as portal_views

urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("institucion/cambiar/", core_views.cambiar_institucion, name="cambiar_institucion"),
    path("circuito/", core_views.circuito, name="circuito"),
    path(
        "bienvenida/ocultar/",
        core_views.ocultar_bienvenida,
        name="ocultar_bienvenida",
    ),
    path("sistema/", core_views.estado_del_sistema, name="estado_del_sistema"),
    path("personal/", legajos_views.personal, name="personal"),
    path("personal/exportar/", legajos_views.exportar_personal, name="exportar_personal"),
    path("personal/importar/", legajos_views.importar_personal, name="importar_personal"),
    path("personal/<int:pk>/", legajos_views.ficha, name="ficha_persona"),
    path("personal/<int:pk>/materias/", legajos_views.materias_de, name="materias_de"),
    path(
        "personal/<int:pk>/materias/guardar/",
        legajos_views.guardar_materias,
        name="guardar_materias",
    ),
    path("legajos/buscar/", legajos_views.buscar, name="buscar_personas"),
    path("personal/planta/", legajos_views.control_de_planta, name="control_de_planta"),
    path("personal/<int:pk>/pdf/", legajos_views.legajo_en_pdf, name="legajo_pdf"),
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
        "licencias/cubrir/<int:pk>/",
        licencias_views.cubrir_ahora,
        name="cubrir_ahora",
    ),
    path(
        "licencias/cubrir/<int:pk>/designar/",
        licencias_views.designar_suplente,
        name="designar_suplente",
    ),
    path(
        "licencias/suplencia/<int:pk>/avisar/",
        licencias_views.avisar_suplencia,
        name="avisar_suplencia",
    ),
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
    path("avisos/", portal_views.avisos_recibidos, name="avisos_recibidos"),
    path("avisos/<int:pk>/responder/", portal_views.responder_aviso, name="responder_aviso"),
    path("licencias/calendario/", licencias_views.calendario, name="calendario_licencias"),
    path("licencias/<int:pk>/cubrir/", licencias_views.cubrir_licencia, name="cubrir_licencia"),
    path("asistencia/semana/", asistencia_views.semana, name="semana"),
    path("asistencia/resumen/", asistencia_views.resumen_del_mes, name="resumen_asistencia"),
    path("asistencia/ausentismo/", asistencia_views.ausentismo, name="ausentismo"),
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
    # La propia va antes que las de Django: registra los intentos y frena la
    # fuerza bruta (core/seguridad.py).
    path("cuentas/login/", IngresoView.as_view(), name="login"),
    path("cuentas/", include("django.contrib.auth.urls")),
    # La dirección del panel se puede cambiar en el .env. No es una defensa
    # de verdad —quien tenga la clave entra igual—, pero saca de encima el
    # ruido constante de los robots que prueban /admin/ en todo internet.
    path(os.environ.get("SGE_URL_PANEL", "admin/"), admin.site.urls),
    # Los adjuntos del legajo (fotos, certificados, títulos) los sirve la
    # propia app, detrás de login: ver core/archivos.py. No hay que mapear
    # /media/ en el hosting —eso los dejaría públicos— y así andan igual en
    # desarrollo y en producción.
    re_path(rf"^{settings.MEDIA_URL.lstrip('/')}(?P<path>.*)$", servir_media, name="media"),
]
