from django.apps import AppConfig


class AsistenciaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "asistencia"
    verbose_name = "Asistencia"

    def ready(self):
        from . import signals  # noqa: F401  (registra los receptores)
