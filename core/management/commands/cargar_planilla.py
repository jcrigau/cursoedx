"""Carga una escuela entera desde la planilla de ``plantilla_carga``.

Una escuela real son doce cursos, cuarenta materias, ciento siete personas y
trescientos cargos. Tipeado en formularios es una semana; acá es un comando y
un informe de lo que no entró.

    python manage.py cargar_planilla escuela.xlsx --simular
    python manage.py cargar_planilla escuela.xlsx

Va hoja por hoja **en orden**, porque cada una se apoya en la anterior: sin
turnos no hay grilla, sin grilla no hay cursos, sin cursos no hay cargos. Lo
que no se puede resolver no se inventa: queda observado con el número de fila,
se corrige el Excel y se vuelve a correr. Todo es idempotente, así que volver a
correrlo actualiza en vez de duplicar.

``--simular`` hace el recorrido completo dentro de una transacción que se
deshace al final: dice exactamente qué pasaría sin tocar la base. Es lo que
conviene correr primero.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import AccionAuditada, Institucion, registrar_auditoria
from core.planillas import Resultado, leer, texto, tiene_filas
from core.tenancy import usar_institucion
from estructura import planilla as estructura
from estructura.models import CicloLectivo
from legajos import planilla as legajos

# Las que todavía se cargan a mano en el panel. Si vienen con datos, el
# informe lo dice: es peor creer que entraron.
SIN_IMPORTADOR = ["Licencias", "Documentación", "Disponibilidad (DDJJ)"]


class Deshacer(Exception):
    """Para volver atrás la simulación sin que parezca un error."""


class Command(BaseCommand):
    help = "Carga niveles, cursos, materias, personal y cargos desde la planilla."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="El .xlsx completado.")
        parser.add_argument(
            "--institucion",
            help="Nombre de la escuela donde cargar. Si no está, se usa la hoja «Escuela».",
        )
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Recorre todo y muestra el informe, pero no guarda nada.",
        )

    def handle(self, *args, **opciones):
        from openpyxl import load_workbook

        try:
            libro = load_workbook(opciones["archivo"], data_only=True)
        except Exception as error:
            raise CommandError(
                f"No se pudo abrir «{opciones['archivo']}». Tiene que ser el .xlsx que "
                f"genera «plantilla_carga». ({error})"
            ) from error

        self.archivo = opciones["archivo"]
        if opciones["simular"]:
            self.stdout.write(self.style.WARNING("Simulación: no se va a guardar nada.\n"))

        self.libro = libro
        self.avisos: list[str] = []
        resultados: list[Resultado] = []
        institucion = None
        # La escuela se busca (o se crea) adentro de la transacción: si no, una
        # simulación dejaría la institución creada y vacía.
        try:
            with transaction.atomic():
                institucion = self._escuela(libro, opciones.get("institucion"))
                self.stdout.write(f"Escuela: {self.style.MIGRATE_LABEL(institucion.nombre)}")
                resultados = self._cargar(institucion, libro)
                if opciones["simular"]:
                    raise Deshacer
        except Deshacer:
            pass

        self._informar(resultados, simulado=opciones["simular"])
        if not opciones["simular"]:
            registrar_auditoria(
                AccionAuditada.IMPORTACION,
                institucion=institucion,
                descripcion=(
                    "Carga masiva desde planilla: "
                    + "; ".join(f"{r.hoja} {r.creados}+{r.actualizados}" for r in resultados)
                )[:500],
            )

    # -- el recorrido -------------------------------------------------------

    def _cargar(self, institucion, libro) -> list[Resultado]:
        with usar_institucion(institucion):
            resultados = [
                estructura.escuela(institucion, libro),
                estructura.niveles(institucion, libro),
                estructura.ciclo_y_periodos(institucion, libro),
                estructura.turnos(institucion, libro),
                estructura.grilla(institucion, libro),
            ]
            ciclo = CicloLectivo.objects.filter(institucion=institucion).order_by("-anio").first()
            resultados += [
                estructura.cursos(institucion, libro, ciclo),
                estructura.materias(institucion, libro),
                estructura.plan_de_estudios(institucion, libro, ciclo),
                legajos.importar(institucion, self.archivo),
                legajos.importar_cargos(institucion, libro, ciclo),
            ]
            self.avisos = estructura.revisar(institucion, ciclo)
            return resultados

    def _escuela(self, libro, nombre_pedido) -> Institucion:
        """A qué escuela va todo esto. Sin esto claro, no se carga nada."""
        if nombre_pedido:
            institucion = Institucion.objects.filter(nombre__iexact=nombre_pedido).first()
            if institucion is None:
                raise CommandError(
                    f"No hay ninguna escuela llamada «{nombre_pedido}». Creala primero en "
                    "Administración → Instituciones, o dejá que la cree la hoja «Escuela»."
                )
            return institucion

        nombre = corto = ""
        for _numero, fila in leer(libro, "Escuela"):
            nombre = texto(fila.get("Nombre"))
            corto = texto(fila.get("Nombre corto")) or nombre[:50]
            break
        if not nombre:
            raise CommandError(
                "La hoja «Escuela» está vacía y no se indicó --institucion: no sé dónde "
                "cargar los datos. Una carga en la escuela equivocada mezcla datos "
                "laborales de dos colegios."
            )
        institucion, creada = Institucion.objects.get_or_create(
            nombre=nombre, defaults={"nombre_corto": corto}
        )
        if creada:
            self.stdout.write(self.style.SUCCESS(f"Se creó la escuela «{nombre}»."))
        return institucion

    # -- el informe ---------------------------------------------------------

    def _informar(self, resultados, *, simulado: bool):
        self.stdout.write("")
        for resultado in resultados:
            estado = f"{resultado.creados} nuevos, {resultado.actualizados} actualizados"
            titulo = f"{resultado.hoja:22s} {estado}"
            if resultado.hubo_problemas:
                self.stdout.write(
                    self.style.WARNING(f"{titulo}  ·  {len(resultado.observaciones)} sin cargar")
                )
            else:
                self.stdout.write(self.style.SUCCESS(titulo))
            for aviso, veces in resultado.avisos.most_common():
                self.stdout.write(f"      ({veces}) {aviso}")
            for observacion in resultado.observaciones[:15]:
                self.stdout.write(f"      · {observacion}")
            resto = len(resultado.observaciones) - 15
            if resto > 0:
                self.stdout.write(f"      · … y {resto} más del mismo tipo o parecidas.")

        if self.avisos:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Cargado, pero conviene mirar esto:"))
            for aviso in self.avisos:
                self.stdout.write(f"      · {aviso}")

        pendientes = [hoja for hoja in SIN_IMPORTADOR if tiene_filas(self.libro, hoja)]
        if pendientes:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Estas hojas traen datos pero todavía se cargan a mano en el panel: "
                    + ", ".join(pendientes)
                )
            )
        self.stdout.write("")
        if simulado:
            self.stdout.write(
                self.style.WARNING(
                    "Era una simulación: no se guardó nada. Corregí lo observado en el "
                    "Excel y volvé a correrlo sin --simular."
                )
            )
        else:
            self.stdout.write(
                "Listo. Revisá lo observado, corregí el Excel y volvé a correr el comando: "
                "no duplica nada."
            )
