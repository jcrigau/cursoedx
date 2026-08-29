"""Arma el ciclo lectivo nuevo copiando el anterior.

Cada año la estructura es casi la misma: los mismos cursos, las mismas
materias, el mismo plan. Este comando crea el ciclo nuevo con todo eso
copiado del último, listo para retocar en el panel: cambiar una división,
ajustar horas de una materia, mover las fechas de los cuatrimestres.

No copia horarios ni cargos: el horario se genera cuando estén las DDJJ del
período nuevo, y los cargos siguen vigentes por sí solos (no dependen del
ciclo).

    python manage.py abrir_ciclo 2027
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institucion
from estructura.models import CicloLectivo, Curso, EstadoCiclo, MateriaPlan, PeriodoAcademico


class Command(BaseCommand):
    help = "Crea el ciclo lectivo nuevo copiando cursos y plan de estudios del anterior."

    def add_arguments(self, parser):
        parser.add_argument("anio", type=int, help="Año del ciclo a crear, ej. 2027.")
        parser.add_argument(
            "--institucion",
            type=int,
            default=None,
            help="ID de la institución. Sin esto, si hay una sola, usa esa.",
        )
        parser.add_argument(
            "--activar",
            action="store_true",
            help="Dejar el ciclo nuevo como activo (y el anterior cerrado).",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        institucion = self._institucion(opciones)
        anio = opciones["anio"]

        if CicloLectivo.objects.filter(institucion=institucion, anio=anio).exists():
            raise CommandError(f"El ciclo {anio} ya existe en {institucion}.")

        anterior = (
            CicloLectivo.objects.filter(institucion=institucion, anio__lt=anio)
            .order_by("-anio")
            .first()
        )
        if anterior is None:
            raise CommandError(
                f"No hay un ciclo anterior del cual copiar en {institucion}. "
                "El primero se carga desde el panel."
            )

        corrimiento = anio - anterior.anio
        nuevo = CicloLectivo.objects.create(
            institucion=institucion,
            anio=anio,
            fecha_inicio=self._correr(anterior.fecha_inicio, corrimiento),
            fecha_fin=self._correr(anterior.fecha_fin, corrimiento),
            estado=EstadoCiclo.ACTIVO if opciones["activar"] else EstadoCiclo.PLANIFICACION,
        )
        self.stdout.write(self.style.SUCCESS(f"+ Ciclo {nuevo} creado (desde {anterior.anio})."))

        # Los planes cuatrimestrales apuntan a un período: se mapea el viejo al
        # nuevo por su orden (1er cuatrimestre → 1er cuatrimestre).
        periodos_nuevos: dict[int, PeriodoAcademico] = {}
        for periodo in anterior.periodos.order_by("orden"):
            periodos_nuevos[periodo.pk] = PeriodoAcademico.objects.create(
                ciclo=nuevo,
                orden=periodo.orden,
                nombre=periodo.nombre,
                fecha_inicio=self._correr(periodo.fecha_inicio, corrimiento),
                fecha_fin=self._correr(periodo.fecha_fin, corrimiento),
            )
            self.stdout.write(f"  + {periodo.nombre}")

        copiados, horas = 0, 0
        for curso in Curso.objects.filter(institucion=institucion, ciclo_lectivo=anterior):
            copia = Curso.objects.create(
                institucion=institucion,
                ciclo_lectivo=nuevo,
                nivel=curso.nivel,
                turno=curso.turno,
                esquema_horario=curso.esquema_horario,
                anio_estudio=curso.anio_estudio,
                division=curso.division,
            )
            copiados += 1
            for plan in MateriaPlan.objects.filter(curso=curso):
                MateriaPlan.objects.create(
                    curso=copia,
                    materia=plan.materia,
                    horas_semanales=plan.horas_semanales,
                    vigencia=plan.vigencia,
                    periodo=periodos_nuevos.get(plan.periodo_id),
                )
                horas += plan.horas_semanales

        self.stdout.write(f"  + {copiados} cursos con su plan ({horas} horas semanales en total).")

        if opciones["activar"]:
            anterior.estado = EstadoCiclo.CERRADO
            anterior.save(update_fields=["estado", "actualizado_en"])
            self.stdout.write(f"  El ciclo {anterior.anio} queda cerrado.")
        else:
            self.stdout.write(
                "  El ciclo queda «en planificación»: al empezar las clases, "
                "marcalo activo desde el panel."
            )
        self.stdout.write(
            "  Fechas copiadas del año anterior: revisá feriados y ajustalas en el panel."
        )

    def _institucion(self, opciones) -> Institucion:
        if opciones["institucion"] is not None:
            institucion = Institucion.objects.filter(pk=opciones["institucion"]).first()
            if institucion is None:
                raise CommandError(f"No existe la institución {opciones['institucion']}.")
            return institucion
        instituciones = list(Institucion.objects.filter(activa=True))
        if len(instituciones) == 1:
            return instituciones[0]
        raise CommandError(
            "Hay varias instituciones: indicá cuál con --institucion ID. "
            + ", ".join(f"{i.pk}={i}" for i in instituciones)
        )

    @staticmethod
    def _correr(fecha: date, anios: int) -> date:
        try:
            return fecha.replace(year=fecha.year + anios)
        except ValueError:  # 29 de febrero
            return fecha.replace(year=fecha.year + anios, day=28)
