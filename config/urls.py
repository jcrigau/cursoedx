from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views
from legajos import views as legajos_views

urlpatterns = [
    path("", core_views.inicio, name="inicio"),
    path("institucion/cambiar/", core_views.cambiar_institucion, name="cambiar_institucion"),
    path(
        "legajos/<int:pk>/certificacion/",
        legajos_views.certificacion_servicios,
        name="certificacion_servicios",
    ),
    path("cuentas/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
