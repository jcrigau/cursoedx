"""Le da acceso al sistema a alguien de la escuela.

Hasta acá los usuarios salían de los datos de ejemplo o del ``createsuperuser``
de Django, que crea un administrador de todo. Una escuela de verdad necesita lo
contrario: una persona, en **una** institución, con **un** rol.

    python manage.py crear_usuario ana@escuela.edu.ar --nombre Ana \\
        --apellido Pérez --rol secretaria --institucion "Instituto Aleluya"

Si no se pasa contraseña se genera una y se muestra **una sola vez**: es para
entregar en mano y cambiar al primer ingreso. El comando es idempotente —
volver a correrlo agrega el rol, no duplica la persona— así que sirve para
darle a alguien un segundo rol en otra escuela.
"""

import secrets
import string

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institucion, Membresia, Rol, Usuario

# Sin caracteres que se confundan al dictarla por teléfono: l, I, 1, O, 0.
ALFABETO = "".join(sorted(set(string.ascii_letters + string.digits) - set("lI1O0")))


def clave_al_azar(largo: int = 14) -> str:
    return "".join(secrets.choice(ALFABETO) for _ in range(largo))


class Command(BaseCommand):
    help = "Crea (o actualiza) un usuario y le da un rol en una institución."

    def add_arguments(self, parser):
        parser.add_argument("email", help="Con esto entra al sistema.")
        parser.add_argument("--nombre", default="", help="Nombre de pila.")
        parser.add_argument("--apellido", default="")
        parser.add_argument(
            "--rol",
            required=True,
            help="secretaria, directivo, docente o liquidador.",
        )
        parser.add_argument(
            "--institucion",
            help="Nombre de la escuela. Si hay una sola cargada, se usa esa.",
        )
        parser.add_argument(
            "--password",
            help="Si no se pasa, se genera una y se muestra una sola vez.",
        )
        parser.add_argument(
            "--legajo",
            help="CUIL o «Apellido, Nombre» del legajo a vincular (para el portal docente).",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        institucion = self._institucion(opciones.get("institucion"))
        rol = self._rol(opciones["rol"])
        email = Usuario.objects.normalize_email(opciones["email"])

        usuario = Usuario.objects.filter(email__iexact=email).first()
        clave = opciones.get("password") or clave_al_azar()
        if usuario is None:
            usuario = Usuario.objects.create_user(
                email=email,
                password=clave,
                nombre=opciones["nombre"],
                apellido=opciones["apellido"],
                # El panel de administración es la interfaz del sistema: sin
                # esto la persona entra y no puede hacer su trabajo.
                is_staff=rol != Rol.DOCENTE,
            )
            self.stdout.write(self.style.SUCCESS(f"Usuario creado: {email}"))
            self.stdout.write(f"  Contraseña: {self.style.MIGRATE_LABEL(clave)}")
            self.stdout.write("  Se muestra una sola vez. Entregala en mano y que la cambie.")
        else:
            self.stdout.write(f"Ya existía el usuario {email}.")
            if opciones.get("password"):
                usuario.set_password(clave)
                usuario.save()
                self.stdout.write("  Se le cambió la contraseña.")

        _membresia, nueva = Membresia.objects.get_or_create(
            usuario=usuario, institucion=institucion, rol=rol, defaults={"activa": True}
        )
        verbo = "Se le dio" if nueva else "Ya tenía"
        self.stdout.write(f"  {verbo} el rol {Rol(rol).label} en {institucion.nombre}.")

        if opciones.get("legajo"):
            self._vincular(usuario, institucion, opciones["legajo"])

    def _institucion(self, nombre) -> Institucion:
        if nombre:
            institucion = Institucion.objects.filter(nombre__icontains=nombre).first()
            if institucion is None:
                raise CommandError(f"No hay ninguna escuela que se llame «{nombre}».")
            return institucion
        escuelas = list(Institucion.objects.all()[:2])
        if len(escuelas) == 1:
            return escuelas[0]
        if not escuelas:
            raise CommandError("No hay ninguna escuela cargada todavía.")
        raise CommandError(
            "Hay más de una escuela cargada: indicá cuál con --institucion. Dar un rol "
            "en la escuela equivocada es dar acceso a datos de otro colegio."
        )

    def _rol(self, escrito) -> str:
        from core.planillas import opcion, opciones_de

        rol = opcion(escrito, Rol.choices)
        if rol is None:
            raise CommandError(f"«{escrito}» no es un rol. Vale {opciones_de(Rol.choices)}.")
        return rol

    def _vincular(self, usuario, institucion, buscado):
        """Ata el usuario a su legajo: es lo que hace andar el portal docente."""
        from core.planillas import clave as comparable
        from legajos.models import Legajo

        candidatos = Legajo.objects.filter(institucion=institucion)
        objetivo = comparable(buscado)
        for legajo in candidatos:
            nombres = {
                comparable(legajo.cuil),
                comparable(f"{legajo.apellido}, {legajo.nombre}"),
                comparable(f"{legajo.apellido} {legajo.nombre}"),
            }
            if objetivo in nombres - {""}:
                if legajo.usuario_id and legajo.usuario_id != usuario.pk:
                    raise CommandError(f"El legajo de {legajo} ya está vinculado a otro usuario.")
                legajo.usuario = usuario
                legajo.save(update_fields=["usuario"])
                self.stdout.write(f"  Vinculado al legajo de {legajo}.")
                return
        raise CommandError(
            f"No hay ningún legajo que sea «{buscado}» en {institucion.nombre}. "
            "Probá con el CUIL, o con «Apellido, Nombre» tal cual está cargado."
        )
