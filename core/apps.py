from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Base y accesos"

    def ready(self):
        from . import signals  # noqa: F401  (registra los receptores)

        # Los grupos de rol se dejan al día en cada migrate, para que un
        # despliegue nuevo o una fase que agregue modelos no requiera un paso
        # manual. Django emite la señal una vez por app instalada y la
        # sincronización es idempotente: al terminar, todos los permisos —
        # incluidos los de las apps que migraron después — quedan asignados.
        post_migrate.connect(sincronizar_grupos_de_rol)


def sincronizar_grupos_de_rol(sender, **kwargs):
    from .permisos import sincronizar_permisos

    sincronizar_permisos()
