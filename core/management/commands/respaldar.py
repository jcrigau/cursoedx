"""Una copia de todo, en un archivo que se pueda bajar y guardar aparte.

Los legajos, las licencias y los cierres de la escuela viven en la base de
datos, y los certificados escaneados en ``media/``. Un respaldo sirve solo si
tiene las dos cosas: una base sin los adjuntos deja legajos incompletos.

    python manage.py respaldar
    python manage.py respaldar --destino /home/usuario/respaldos --conservar 8

Se programa como el resumen diario (en PythonAnywhere, pestaña *Tasks*) y el
archivo se baja desde la pestaña *Files*. **Guardarlo fuera del servidor**: un
respaldo que vive en la misma máquina que se puede perder no es un respaldo.
"""

import sqlite3
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Arma un ZIP con la base de datos y los archivos subidos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--destino",
            default=None,
            help="Carpeta donde dejar el ZIP. Por omisión, «respaldos/» del proyecto.",
        )
        parser.add_argument(
            "--conservar",
            type=int,
            default=8,
            help="Cuántos respaldos dejar en la carpeta (0 = todos). Por omisión, 8.",
        )

    def handle(self, *args, **opciones):
        destino = Path(opciones["destino"] or settings.BASE_DIR / "respaldos")
        destino.mkdir(parents=True, exist_ok=True)

        archivo = destino / f"respaldo-{date.today():%Y-%m-%d}.zip"
        temporal = destino / "base-copia.sqlite3"

        base = self._copiar_la_base(temporal)
        try:
            with ZipFile(archivo, "w", ZIP_DEFLATED) as zip_:
                if base is not None:
                    zip_.write(base, "base-de-datos.sqlite3")
                adjuntos = self._agregar_los_adjuntos(zip_)
        finally:
            temporal.unlink(missing_ok=True)

        peso = archivo.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f"Respaldo listo: {archivo}"))
        self.stdout.write(f"  {adjuntos} archivos adjuntos · {peso:.1f} MB")
        self.stdout.write(
            self.style.WARNING(
                "  Bajalo y guardalo fuera del servidor: una copia en la misma "
                "máquina se pierde junto con ella."
            )
        )
        self._limpiar_viejos(destino, opciones["conservar"])

    def _copiar_la_base(self, temporal: Path) -> Path | None:
        """Copia la base con la escuela trabajando, sin dejarla a medias.

        SQLite tiene una copia en caliente que respeta las transacciones en
        curso; copiar el archivo a mano puede llevarse una escritura por la
        mitad. Con Postgres el respaldo lo hace el motor (``pg_dump``), así
        que acá se avisa en vez de guardar algo que no sirve.
        """
        if connection.vendor != "sqlite":
            self.stdout.write(
                self.style.WARNING(
                    f"La base es {connection.vendor}: su respaldo se hace con la "
                    "herramienta del motor (pg_dump). Acá van solo los adjuntos."
                )
            )
            return None

        origen = connection.settings_dict["NAME"]
        if origen in (":memory:", "") or str(origen).startswith("file:memory"):
            # Base en memoria (las pruebas): no hay archivo que copiar, pero
            # los adjuntos sí se respaldan.
            self.stdout.write(self.style.WARNING("La base está en memoria: van solo los adjuntos."))
            return None
        if not Path(origen).exists():
            raise CommandError(f"No se encontró el archivo de la base de datos: {origen}.")

        with sqlite3.connect(origen) as viva, sqlite3.connect(temporal) as copia:
            viva.backup(copia)
        return temporal

    def _agregar_los_adjuntos(self, zip_: ZipFile) -> int:
        """Fotos, certificados, títulos y resoluciones."""
        media = Path(settings.MEDIA_ROOT)
        if not media.is_dir():
            return 0
        agregados = 0
        for archivo in sorted(media.rglob("*")):
            if archivo.is_file():
                zip_.write(archivo, f"archivos/{archivo.relative_to(media)}")
                agregados += 1
        return agregados

    def _limpiar_viejos(self, destino: Path, conservar: int):
        """Deja los últimos, para no llenar el disco del hospedaje."""
        if conservar <= 0:
            return
        respaldos = sorted(destino.glob("respaldo-*.zip"))
        sobrantes = respaldos[:-conservar] if len(respaldos) > conservar else []
        for viejo in sobrantes:
            viejo.unlink()
        if sobrantes:
            self.stdout.write(f"  Se borraron {len(sobrantes)} respaldos viejos.")
