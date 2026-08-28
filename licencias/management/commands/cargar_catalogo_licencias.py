"""Precarga el catálogo de tipos de licencia de San Luis.

Los artículos y los topes son los que usa hoy la secretaría del colegio piloto.
Se cargan como punto de partida: cada institución después ajusta lo suyo desde
el panel, y otra jurisdicción define su propio catálogo.

Los que figuran con tope "a confirmar" se dejan sin tope, para que el sistema
no rechace una licencia por un número que todavía no está verificado.

    python manage.py cargar_catalogo_licencias --institucion 1
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import Institucion
from licencias.models import TipoLicencia

# (código, nombre, con goce, tope anual, tope por caso, tope consecutivos,
#  extensible con aval, requiere certificado)
CATALOGO_SAN_LUIS = [
    ("Art. 76", "Enfermedad / Estudio médico", True, 60, None, None, True, True),
    ("Art. 83", "Maternidad", True, None, 180, None, False, True),
    ("Art. 91", "Atención de familiar", True, 30, None, None, False, True),
    ("Art. 93.1", "Matrimonio", True, None, 12, None, False, False),
    ("Art. 93.2", "Fallecimiento de familiar", True, None, None, None, False, False),
    ("Art. 93.3", "Nacimiento de hijo (padre)", True, None, None, None, False, False),
    ("Art. 93.4", "Razones particulares", True, 5, None, None, False, False),
    ("Art. 94.1", "Exámenes", True, 20, None, 5, False, True),
    ("Art. 97", "Congresos, cursos y jornadas", True, None, None, None, False, True),
    ("Art. 98", "Deportiva", True, None, None, None, False, True),
    ("Art. 100", "Cargo de mayor jerarquía", True, None, None, None, False, False),
    ("Art. 107", "Binomio madre-hijo", True, None, None, None, False, True),
    ("", "Estudios / Investigación", True, None, None, None, False, True),
    ("", "Licencia especial sin goce de haberes", False, None, None, None, False, False),
    ("", "Relevo de funciones", True, None, None, None, False, False),
]


class Command(BaseCommand):
    help = "Carga el catálogo de tipos de licencia (régimen de San Luis)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--institucion",
            type=int,
            help="ID de la institución. Si se omite y hay una sola, usa esa.",
        )

    def handle(self, *args, **opciones):
        institucion = self._institucion(opciones.get("institucion"))

        creados, existentes = 0, 0
        for (
            codigo,
            nombre,
            con_goce,
            anual,
            por_caso,
            consecutivos,
            extensible,
            certificado,
        ) in CATALOGO_SAN_LUIS:
            _tipo, creado = TipoLicencia.objects.get_or_create(
                institucion=institucion,
                nombre=nombre,
                defaults={
                    "codigo": codigo,
                    "con_goce": con_goce,
                    # Regla vigente del liquidador: solo se informa lo que genera
                    # descuento o pago adicional. Una licencia con goce no
                    # descuenta; lo que sí se informa es el alta del suplente.
                    "impacta_haberes": not con_goce,
                    "tope_dias_anual": anual,
                    "tope_dias_por_caso": por_caso,
                    "tope_dias_consecutivos": consecutivos,
                    "extensible_con_aval": extensible,
                    "requiere_certificado": certificado,
                },
            )
            if creado:
                creados += 1
                self.stdout.write(f"  + {codigo} {nombre}".rstrip())
            else:
                existentes += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo cargado en «{institucion}»: {creados} nuevos, {existentes} ya estaban."
            )
        )
        self.stdout.write(
            "Revisá desde el panel los topes marcados a confirmar y cuáles impactan "
            "en la liquidación."
        )

    def _institucion(self, institucion_id):
        if institucion_id:
            try:
                return Institucion.objects.get(pk=institucion_id)
            except Institucion.DoesNotExist as error:
                raise CommandError(f"No existe la institución {institucion_id}.") from error

        instituciones = list(Institucion.objects.all()[:2])
        if not instituciones:
            raise CommandError("No hay ninguna institución cargada.")
        if len(instituciones) > 1:
            raise CommandError("Hay varias instituciones: indicá cuál con --institucion.")
        return instituciones[0]
