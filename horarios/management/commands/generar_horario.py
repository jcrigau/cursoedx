"""Genera el horario de una versión desde la terminal.

Conviene usarlo cuando la generación puede tardar (muchos cursos, muchas
restricciones): desde el panel de administración el navegador podría cortar la
espera, acá no.

    python manage.py generar_horario 3 --segundos 120
"""

from django.core.management.base import BaseCommand, CommandError

from horarios.generador import Parametros, generar
from horarios.models import VersionHorario


class Command(BaseCommand):
    help = "Genera el horario de una versión con el optimizador."

    def add_arguments(self, parser):
        # Se toma posicional: "--version" ya lo usa Django para su propia opción.
        parser.add_argument("version_id", type=int, help="ID de la versión de horario.")
        parser.add_argument("--segundos", type=int, default=60, help="Tiempo máximo de búsqueda.")
        parser.add_argument(
            "--peso-dias",
            type=int,
            default=100,
            help="Importancia de que cada docente venga menos días.",
        )
        parser.add_argument(
            "--peso-huecos", type=int, default=10, help="Importancia de evitar horas libres."
        )
        parser.add_argument(
            "--max-horas-dia-materia",
            type=int,
            default=2,
            help="Máximo de horas de la misma materia en un día.",
        )

    def handle(self, *args, **opciones):
        try:
            version = VersionHorario.objects.get(pk=opciones["version_id"])
        except VersionHorario.DoesNotExist as error:
            raise CommandError(f"No existe la versión {opciones['version_id']}.") from error

        parametros = Parametros(
            peso_dias_docente=opciones["peso_dias"],
            peso_huecos=opciones["peso_huecos"],
            max_horas_dia_materia=opciones["max_horas_dia_materia"],
            segundos_limite=opciones["segundos"],
        )

        self.stdout.write(f"Generando «{version}»…")
        resultado = generar(version, parametros)

        for aviso in resultado.avisos:
            self.stdout.write(self.style.WARNING(f"  aviso: {aviso}"))

        if not resultado.exito:
            for problema in resultado.problemas:
                self.stdout.write(self.style.ERROR(f"  {problema}"))
            raise CommandError(f"No se generó el horario ({resultado.estado}).")

        metricas = resultado.metricas
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Horario generado ({resultado.estado.lower()})."))
        self.stdout.write(f"  horas ubicadas: {resultado.asignaciones_creadas}")
        self.stdout.write(f"  tiempo: {metricas['segundos']} s")
        self.stdout.write(f"  docentes: {metricas['docentes']}")
        self.stdout.write(
            f"  días por docente: {metricas['promedio_dias_por_docente']} promedio, "
            f"{metricas['maximo_dias_por_docente']} máximo"
        )
