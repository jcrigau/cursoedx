"""Deja la escuela de ejemplo con un día de trabajo por resolver.

``cargar_demo`` deja el sistema andando y prolijo. Este comando lo desprolija
a propósito: planta las situaciones que aparecen un martes cualquiera —una
licencia esperando aprobación, otra aprobada que nadie decidió cómo cubrir, un
docente que avisó por el celular que no viene, un mes sin cerrar— y crea un
usuario por cada puesto para poder recorrerlas desde los cuatro lados.

Sirve para probar el sistema como se usa, y para mostrárselo a una escuela.

    python manage.py cargar_escenario --password una-clave-segura
"""

from datetime import date, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from asistencia.parte import parte_diario, version_vigente
from core.management.commands.cargar_piloto import (
    NOMBRE_ESCUELA_DE_PRUEBA,
    NOMBRES_ANTERIORES,
)
from core.models import Institucion, Membresia, Rol, Usuario
from core.tenancy import usar_institucion
from horarios.models import AsignacionHoraria
from legajos.models import Cargo, FuentePago, Legajo, MotivoBaja, SituacionRevista
from licencias.models import EstadoLicencia, Licencia, TipoLicencia
from novedades.models import Origen, PeriodoNovedades
from portal.models import AvisoInasistencia, Fichada, MotivoAviso

# Un usuario por puesto, todos con la misma contraseña para poder saltar de uno
# a otro mientras se recorre el escenario.
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def en_castellano(fecha) -> str:
    """«lunes 31/08». strftime devolvería el día en inglés."""
    return f"{DIAS[fecha.weekday()]} {fecha:%d/%m}"


PUESTOS = [
    ("secretaria", Rol.SECRETARIA, "Secretaría", "Escuela"),
    ("directivo", Rol.DIRECTIVO, "Dirección", "Escuela"),
    ("liquidador", Rol.LIQUIDADOR, "Liquidación", "Estudio"),
]


class Command(BaseCommand):
    help = "Prepara un día de trabajo por resolver, con un usuario por cada puesto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="",
            help="Contraseña de los cuatro usuarios. Sin esto no se puede iniciar sesión.",
        )
        parser.add_argument(
            "--dominio",
            default="ejemplo.edu.ar",
            help="Dominio de los correos de los usuarios.",
        )
        parser.add_argument(
            "--segundos", type=int, default=45, help="Tiempo máximo del generador de horarios."
        )
        parser.add_argument(
            "--reiniciar",
            action="store_true",
            help=(
                "Borrar la escuela de ejemplo y rearmarla desde cero. Útil cuando una "
                "base vieja quedó con datos de versiones anteriores."
            ),
        )
        parser.add_argument(
            "--sin-demo",
            dest="con_demo",
            action="store_false",
            help="No rearmar la escuela: plantar las situaciones sobre la que ya está.",
        )

    def handle(self, *args, **opciones):
        if opciones["con_demo"]:
            call_command(
                "cargar_demo",
                password=opciones["password"],
                email=f"secretaria@{opciones['dominio']}",
                segundos=opciones["segundos"],
                reiniciar=opciones["reiniciar"],
            )
            self.stdout.write("")

        institucion = Institucion.objects.filter(
            nombre__in=[NOMBRE_ESCUELA_DE_PRUEBA, *NOMBRES_ANTERIORES]
        ).first()
        if institucion is None:
            raise CommandError(
                "No está la escuela de ejemplo. Corré primero «python manage.py cargar_demo»."
            )

        self.stdout.write(self.style.MIGRATE_HEADING("Preparando el día de trabajo"))

        with usar_institucion(institucion):
            usuarios = self._crear_los_puestos(institucion, opciones)

            dia = self._dia_de_trabajo(institucion)
            if dia is None:
                # Sin horario publicado no hay parte, y sin parte no hay día que
                # plantar. Los usuarios y el mes por cerrar igual quedan hechos.
                self.stdout.write(
                    self.style.WARNING(
                        "No hay clases en la próxima semana: falta publicar un horario "
                        "para el período en curso. Los cuatro usuarios quedaron creados; "
                        "generá el horario y volvé a correr este comando para plantar "
                        "las situaciones del día."
                    )
                )
                self._dejar_el_mes_sin_compilar(institucion, date.today())
                self._imprimir_guia(usuarios, opciones, None)
                return
            if dia != date.today():
                self.stdout.write(
                    self.style.WARNING(
                        f"Hoy no hay clases, así que el día de trabajo es el "
                        f"{en_castellano(dia)}: las pantallas abren con ?fecha={dia:%Y-%m-%d}."
                    )
                )

            self._licencia_esperando_aprobacion(institucion, dia)
            self._licencia_sin_decidir_la_cobertura(institucion, dia)
            self._el_caso_mixto(institucion, dia)
            self._una_baja_del_mes(institucion, dia)
            self._devolver_pendientes_al_docente(institucion, dia)
            self._dejar_el_mes_sin_compilar(institucion, dia)

        self._imprimir_guia(usuarios, opciones, dia)

    # -- los cuatro puestos ---------------------------------------------------

    def _crear_los_puestos(self, institucion, opciones) -> dict:
        """Un usuario por rol. El del portal ya lo dejó cargar_piloto."""
        usuarios = {}
        for prefijo, rol, nombre, apellido in PUESTOS:
            email = f"{prefijo}@{opciones['dominio']}"
            usuario, creado = Usuario.objects.get_or_create(
                email=email, defaults={"nombre": nombre, "apellido": apellido}
            )
            if opciones["password"]:
                usuario.set_password(opciones["password"])
                usuario.save(update_fields=["password"])
            Membresia.objects.get_or_create(usuario=usuario, institucion=institucion, rol=rol)
            usuarios[rol] = usuario
            self._paso(f"{rol.label}: {email}", creado)

        docente = Legajo.objects.filter(institucion=institucion, usuario__isnull=False).first()
        if docente is not None:
            if opciones["password"]:
                docente.usuario.set_password(opciones["password"])
                docente.usuario.save(update_fields=["password"])
            usuarios[Rol.DOCENTE] = docente.usuario
            usuarios["legajo_docente"] = docente
            self._paso(f"Docente: {docente.usuario.email} ({docente.nombre_completo})", False)
        return usuarios

    # -- las situaciones ------------------------------------------------------

    def _licencia_esperando_aprobacion(self, institucion, hoy):
        """Lo primero que mira el directivo al entrar."""
        tipo = TipoLicencia.objects.filter(institucion=institucion, codigo="Art. 76").first()
        legajo = self._alguien_disponible(institucion, hoy, salteando=0)
        if tipo is None or legajo is None:
            return

        licencia, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=legajo,
            tipo=tipo,
            fecha_inicio=hoy + timedelta(days=1),
            defaults={
                "fecha_fin": hoy + timedelta(days=5),
                "estado": EstadoLicencia.SOLICITADA,
                "observaciones": "Presenta certificado médico por cinco días.",
            },
        )
        self._paso(f"Licencia a aprobar: {legajo.nombre_completo}, desde mañana", creada)

    def _licencia_sin_decidir_la_cobertura(self, institucion, hoy):
        """Aprobada, en curso, y nadie resolvió qué pasa con sus horas."""
        tipo = TipoLicencia.objects.filter(institucion=institucion, codigo="Art. 91").first()
        legajo = self._alguien_disponible(institucion, hoy, salteando=1)
        if tipo is None or legajo is None:
            return

        licencia, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=legajo,
            tipo=tipo,
            fecha_inicio=hoy,
            defaults={
                "fecha_fin": hoy + timedelta(days=3),
                "estado": EstadoLicencia.APROBADA,
                "observaciones": "Internación de un familiar directo.",
            },
        )
        # Sin Cobertura a propósito: el parte lo va a marcar «sin resolver».
        licencia.coberturas.all().delete()
        self._paso(f"Cobertura sin decidir: {legajo.nombre_completo}, desde hoy", creada)

    def _el_caso_mixto(self, institucion, hoy):
        """Una persona con cargos de las dos fuentes, de licencia este mes.

        Es el caso donde se cometían los errores al hacerlo a mano: la licencia
        tiene que generar dos líneas, una a cada planilla.
        """
        legajo = self._alguien_disponible(institucion, hoy, salteando=2)
        tipo = TipoLicencia.objects.filter(institucion=institucion, codigo="Art. 93.4").first()
        if legajo is None or tipo is None:
            return

        cargo = legajo.cargos.order_by("id").first()
        if cargo is None:
            return

        # Un segundo cargo, de la otra fuente de pago.
        otra_fuente = (
            FuentePago.INTERNO
            if cargo.fuente_pago == FuentePago.SUBVENCIONADO
            else FuentePago.SUBVENCIONADO
        )
        _cargo, creado = Cargo.objects.get_or_create(
            institucion=institucion,
            legajo=legajo,
            materia=cargo.materia,
            curso=cargo.curso,
            fuente_pago=otra_fuente,
            defaults={
                "tipo": cargo.tipo,
                "nivel": cargo.nivel,
                "horas_semanales": 2,
                "situacion_revista": SituacionRevista.PROVISIONAL,
                "fecha_alta": hoy.replace(day=1),
            },
        )
        Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=legajo,
            tipo=tipo,
            fecha_inicio=hoy - timedelta(days=2),
            defaults={
                "fecha_fin": hoy - timedelta(days=2),
                "estado": EstadoLicencia.APROBADA,
                "observaciones": "Trámite personal.",
            },
        )
        self._paso(f"Caso mixto: {legajo.nombre_completo}, cargos de las dos fuentes", creado)

    def _una_baja_del_mes(self, institucion, hoy):
        """Una renuncia, para que el mes tenga altas y bajas."""
        legajo = self._alguien_disponible(institucion, hoy, salteando=3)
        if legajo is None:
            return
        # Si ya se dio de baja en una corrida anterior, no se da otra.
        if legajo.cargos.exclude(fecha_baja=None).exists():
            self._paso(f"Baja del mes: {legajo.nombre_completo} ya renunció a un cargo", False)
            return

        cargo = legajo.cargos.filter(fecha_baja=None).order_by("-id").first()
        if cargo is None:
            return

        cargo.fecha_baja = hoy - timedelta(days=1)
        cargo.motivo_baja = MotivoBaja.RENUNCIA
        cargo.save(update_fields=["fecha_baja", "motivo_baja", "actualizado_en"])
        self._paso(f"Baja del mes: {legajo.nombre_completo} renunció a un cargo", True)

    def _devolver_pendientes_al_docente(self, institucion, hoy):
        """Que el docente tenga algo para hacer: fichar y avisar."""
        Fichada.objects.filter(institucion=institucion, fecha=hoy).delete()

        legajo = Legajo.objects.filter(institucion=institucion, usuario__isnull=False).first()
        if legajo is not None:
            AvisoInasistencia.objects.filter(institucion=institucion, legajo=legajo).delete()

        # Un aviso de otra persona, que la secretaría tiene que ver en el parte.
        otro = self._alguien_disponible(institucion, hoy, salteando=4)
        if otro is not None:
            _aviso, creado = AvisoInasistencia.objects.get_or_create(
                institucion=institucion,
                legajo=otro,
                fecha=hoy,
                defaults={
                    "motivo": MotivoAviso.ENFERMEDAD,
                    "detalle": "Amanecí con fiebre, llevo el certificado mañana.",
                },
            )
            self._paso(f"Aviso sin resolver: {otro.nombre_completo} no viene hoy", creado)
        self._paso("Fichadas del día borradas: el docente ficha desde el portal", True)

    def _dejar_el_mes_sin_compilar(self, institucion, hoy):
        """El mes vuelve a foja cero, para hacer el cierre completo."""
        periodo = PeriodoNovedades.objects.filter(
            institucion=institucion, anio=hoy.year, mes=hoy.month
        ).first()
        if periodo is None:
            return
        if periodo.esta_cerrado:
            periodo.reabrir("Preparación del escenario de prueba.")
        periodo.novedades.filter(origen=Origen.AUTOMATICA).delete()
        periodo.compilado_en = None
        periodo.save(update_fields=["compilado_en", "actualizado_en"])
        self._paso(f"Mes de {periodo} sin compilar: el cierre queda por hacer", True)

    # -- ayudantes ------------------------------------------------------------

    def _dia_de_trabajo(self, institucion):
        """El día sobre el que se planta el escenario.

        Hoy, si hay clases; si no —un sábado, un feriado del calendario—, el
        próximo día que las tenga. Un escenario que solo funciona de lunes a
        viernes no sirve para mostrarle el sistema a nadie un fin de semana.
        """
        fecha = date.today()
        for _ in range(8):
            if parte_diario(institucion, fecha).lineas:
                return fecha
            fecha += timedelta(days=1)
        return None

    def _alguien_disponible(self, institucion, dia, salteando: int):
        """Un docente con horas ese día, siempre el mismo.

        Sale del horario y no del parte: el parte va cambiando a medida que se
        plantan licencias, así que elegir desde ahí haría que una segunda
        corrida cayera sobre otra persona y plantara todo de nuevo. Desde el
        horario, el orden no se mueve y el escenario se puede recargar.
        """
        version = version_vigente(institucion, dia)
        if version is None:
            return None

        con_clase = set(
            AsignacionHoraria.objects.filter(version=version, dia_semana=dia.weekday())
            .exclude(legajo=None)
            .values_list("legajo_id", flat=True)
        )
        # Se saltea al del portal: ese tiene su propio recorrido y conviene
        # que llegue al día sin novedades encima.
        candidatos = list(
            Legajo.objects.filter(institucion=institucion, id__in=con_clase, usuario=None).order_by(
                "apellido", "nombre", "id"
            )[: salteando + 1]
        )
        if len(candidatos) <= salteando:
            return None
        return candidatos[salteando]

    def _paso(self, texto, nuevo):
        marca = self.style.SUCCESS("+") if nuevo else self.style.WARNING("=")
        self.stdout.write(f"{marca} {texto}")

    def _imprimir_guia(self, usuarios, opciones, dia):
        dominio = opciones["dominio"]
        sufijo = "" if dia is None or dia == date.today() else f"?fecha={dia:%Y-%m-%d}"
        self.stdout.write("")
        titulo = (
            "Los usuarios están listos. Recorrelo así:"
            if dia is None
            else f"El día está listo ({en_castellano(dia)}). Recorrelo así:"
        )
        self.stdout.write(self.style.MIGRATE_HEADING(titulo))
        if sufijo:
            self.stdout.write(
                f"  Ojo: el parte y los cursos abren en hoy. Agregales «{sufijo}» a la"
            )
            self.stdout.write("  dirección, o movete con el calendario de la propia pantalla.")
        self.stdout.write("")
        for titulo, email, pasos in [
            (
                "1 · DIRECTIVO",
                f"directivo@{dominio}",
                [
                    "Administración → Licencias: hay una «Solicitada». Tildala y usá",
                    "  la acción «Aprobar las licencias seleccionadas».",
                    "Mirá el tablero: recién ahí esa persona desaparece del parte.",
                ],
            ),
            (
                "2 · SECRETARÍA",
                f"secretaria@{dominio}",
                [
                    "Cursos de hoy: mirá qué cursos quedan sin clase, marcados en rojo.",
                    "Parte diario: aparece quién avisó que no viene. Marcalo ausente y guardá.",
                    "El aviso de arriba te dice qué licencia no tiene cobertura decidida:",
                    "  Administración → Coberturas de licencias → Agregar. Elegí suplente,",
                    "  o «Sin cobertura» si los alumnos quedan libres.",
                    "Volvé a Cursos de hoy: esas horas cambiaron de color.",
                    "Novedades → Compilar el mes → revisá → marcá las informadas → Cerrar.",
                ],
            ),
            (
                "3 · DOCENTE (portal, /portal/)",
                f"docente@{dominio}",
                [
                    "Hoy: registrá tu entrada. Después miralo en el parte de secretaría.",
                    "Mi horario, Mi legajo, Mis licencias: lo que ve cada docente de lo suyo.",
                    "Avisar una inasistencia: cargá una para mañana y fijate cómo llega.",
                ],
            ),
            (
                "4 · LIQUIDADOR",
                f"liquidador@{dominio}",
                [
                    "Novedades: solo ve los meses cerrados. Si secretaría todavía no cerró,",
                    "  no le aparece nada — que es justamente el control.",
                    "Con el mes cerrado, descarga el Excel con las columnas de su planilla.",
                ],
            ),
        ]:
            self.stdout.write(self.style.SUCCESS(titulo) + f"   {email}")
            for paso in pasos:
                self.stdout.write(f"    {paso}")
            self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("Con qué entrar"))
        for prefijo, rol, _nombre, _apellido in PUESTOS:
            self.stdout.write(f"  {rol.label:24} {prefijo}@{dominio}")
        self.stdout.write(f"  {'Docente (portal)':24} docente@{dominio}")
        self.stdout.write("")

        if opciones["password"]:
            # Se repite la contraseña textual a propósito: es el dato que más
            # se pierde entre el resto de la salida, y sin él no se entra.
            self.stdout.write(
                f"  Contraseña de los cuatro: {self.style.SUCCESS(opciones['password'])}"
            )
            self.stdout.write(
                "  (es la que pasaste en --password; para cambiarla, volvé a correr "
                "este comando con --sin-demo y otra)"
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    "  No pasaste --password, así que las contraseñas quedaron como "
                    "estaban.\n"
                    "  Para ponerles una: python manage.py cargar_escenario --sin-demo "
                    "--password LA-QUE-QUIERAS"
                )
            )
