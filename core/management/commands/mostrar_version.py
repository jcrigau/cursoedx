"""Muestra la versión desde la terminal.

Es el comando que se corre en el servidor después de actualizar, para
confirmar que lo que quedó instalado es lo que se esperaba.

    python manage.py mostrar_version
"""

from django.core.management.base import BaseCommand

from core.version import informacion


class Command(BaseCommand):
    help = "Muestra la versión del sistema y con qué está funcionando."

    def handle(self, *args, **opciones):
        datos = informacion()

        self.stdout.write(self.style.SUCCESS(f"SGE {datos['version']}") + f" — {datos['fase']}")
        self.stdout.write(f"  revisión:      {datos['revision']} ({datos['fecha_revision']})")
        self.stdout.write(f"  base de datos: {datos['base_de_datos']}")
        self.stdout.write(f"  direcciones:   {datos['hosts_permitidos']}")
        self.stdout.write(f"  Django:        {datos['django']} sobre Python {datos['python']}")

        if datos["modo_depuracion"]:
            self.stdout.write(
                self.style.WARNING(
                    "  modo:          depuración — no corresponde en un servidor con "
                    "datos reales (SGE_DEBUG=0)."
                )
            )

        self.stdout.write("")
        for dependencia in datos["opcionales"]:
            if dependencia["disponible"]:
                marca = self.style.SUCCESS("  ✓")
                detalle = ""
            else:
                marca = self.style.WARNING("  ✗")
                detalle = f" — {dependencia['sin_ella']}"
            self.stdout.write(f"{marca} {dependencia['nombre']}: {dependencia['para']}{detalle}")
