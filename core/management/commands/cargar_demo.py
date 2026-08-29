"""Deja el sistema con datos de ejemplo y **en movimiento**, listo para mostrar.

``cargar_piloto`` arma la escuela —cursos, plan de estudios, personal,
licencias— pero la deja quieta: sin un horario publicado el parte diario no
tiene de dónde salir y el mes de novedades queda vacío, que son justo las dos
pantallas que hay que ver funcionando.

Este comando completa eso: genera el horario y lo publica, marca las novedades
de asistencia de los últimos días de clase, agrega el movimiento del portal
(un aviso de inasistencia y una fichada) y compila el mes.

Se puede volver a correr sin miedo: no duplica nada.

    python manage.py cargar_demo --password una-clave-segura
"""

from datetime import date, time, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from asistencia.models import EstadoAsistencia, RegistroAsistencia
from asistencia.parte import parte_diario
from core.management.commands.cargar_piloto import NOMBRE_ESCUELA_DE_PRUEBA
from core.models import Institucion, Usuario
from core.tenancy import usar_institucion
from estructura.models import PeriodoAcademico
from horarios.generador import Parametros, generar
from horarios.models import VersionHorario
from legajos.models import Legajo
from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia
from novedades.compilador import compilar
from novedades.models import PeriodoNovedades
from portal.models import AvisoInasistencia, Fichada, MotivoAviso, TipoFichada

NOMBRE_VERSION = "Horario de ejemplo"

# Un caso de cada tipo, para que el mes tenga las cuatro clases de novedad de
# asistencia que después hay que informar al liquidador.
GUION_ASISTENCIA = [
    (EstadoAsistencia.AUSENTE, {}, "Ausente sin aviso."),
    (EstadoAsistencia.TARDE, {"hora": time(8, 10)}, "Llegó sobre la 2ª hora."),
    (EstadoAsistencia.PARCIAL, {"horas_afectadas": 2}, "Se retiró por un turno médico."),
    (EstadoAsistencia.RETIRO, {"hora": time(11, 30)}, "Retiro anticipado autorizado."),
]


class Command(BaseCommand):
    help = "Carga la escuela de ejemplo y la deja funcionando: horario publicado, asistencia y novedades del mes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="secretaria@ejemplo.edu.ar",
            help="Email del usuario de secretaría.",
        )
        parser.add_argument(
            "--password", default="", help="Contraseña de los usuarios que se crean."
        )
        parser.add_argument(
            "--segundos",
            type=int,
            default=30,
            help="Tiempo máximo que puede tardar el generador de horarios.",
        )
        parser.add_argument(
            "--dias",
            type=int,
            default=6,
            help="Cuántos días de clase hacia atrás se marcan con novedades.",
        )
        parser.add_argument(
            "--sin-piloto",
            dest="con_piloto",
            action="store_false",
            help="No volver a cargar la escuela: usar la que ya está en la base.",
        )

    def handle(self, *args, **opciones):
        if opciones["con_piloto"]:
            call_command(
                "cargar_piloto",
                email=opciones["email"],
                password=opciones["password"],
            )
            self.stdout.write("")

        institucion = Institucion.objects.filter(nombre=NOMBRE_ESCUELA_DE_PRUEBA).first()
        if institucion is None:
            raise CommandError(
                "No está la escuela de ejemplo. Corré primero «python manage.py cargar_piloto»."
            )

        usuario = Usuario.objects.filter(email=opciones["email"]).first()

        with usar_institucion(institucion):
            version = self._publicar_horario(institucion, opciones["segundos"])
            if version is not None:
                self._licencias_del_dia(institucion)
                # El portal antes que la asistencia: no se marca ausente a
                # quien dejó constancia de que llegó.
                self._movimiento_del_portal(institucion)
                self._registrar_asistencia(institucion, usuario, opciones["dias"])
            self._compilar_novedades(institucion, usuario)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Listo. La escuela de ejemplo quedó en marcha."))
        self.stdout.write("  Tablero:  http://127.0.0.1:8000/")
        self.stdout.write("  Portal:   http://127.0.0.1:8000/portal/")

    # -- pasos ----------------------------------------------------------------

    def _publicar_horario(self, institucion, segundos) -> VersionHorario | None:
        """Genera el horario del período en curso y lo deja vigente."""
        periodo = (
            PeriodoAcademico.objects.filter(
                ciclo__institucion=institucion,
                fecha_inicio__lte=date.today(),
                fecha_fin__gte=date.today(),
            )
            .select_related("ciclo")
            .first()
        )
        if periodo is None:
            self.stdout.write(
                self.style.WARNING(
                    "Hoy queda fuera del ciclo lectivo de la escuela de ejemplo, así que no "
                    "hay período al que ponerle horario. Probá con «--anio» en cargar_piloto."
                )
            )
            return None

        version, _creada = VersionHorario.objects.get_or_create(
            institucion=institucion, periodo=periodo, nombre=NOMBRE_VERSION
        )

        if version.asignaciones.exists():
            self.stdout.write(f"= Horario: «{version}» ya estaba generado.")
        else:
            self.stdout.write(f"  Generando el horario (hasta {segundos} s)…")
            resultado = generar(version, Parametros(segundos_limite=segundos))
            for aviso in resultado.avisos:
                self.stdout.write(self.style.WARNING(f"  aviso: {aviso}"))
            if not resultado.exito:
                for problema in resultado.problemas:
                    self.stdout.write(self.style.ERROR(f"  {problema}"))
                self.stdout.write(
                    self.style.WARNING(
                        "Sin horario no hay parte diario ni asistencia. El resto de los "
                        "datos de ejemplo igual quedó cargado."
                    )
                )
                return None
            metricas = resultado.metricas
            self.stdout.write(
                self.style.SUCCESS(
                    f"+ Horario: {resultado.asignaciones_creadas} horas ubicadas, "
                    f"{metricas['promedio_dias_por_docente']} días por docente en promedio."
                )
            )

        version.publicar()
        self.stdout.write(f"+ Publicado: «{version}» queda vigente.")
        return version

    def _registrar_asistencia(self, institucion, usuario, dias: int):
        """Marca novedades en los últimos días con clase.

        Se eligen desde el parte diario, que es quien sabe realmente quién
        tenía que estar: así nunca se marca a alguien de licencia ni a un
        docente que ese día no venía.
        """
        creados = 0
        con_clase = 0
        fecha = date.today()
        tope = fecha - timedelta(days=45)

        while con_clase < dias and fecha > tope:
            parte = parte_diario(institucion, fecha)
            # Quien fichó dejó constancia de que llegó: marcarlo ausente sería
            # contradecir al propio sistema.
            candidatos = [linea for linea in parte.lineas if linea.fichada is None]
            if candidatos:
                estado, extra, nota = GUION_ASISTENCIA[con_clase % len(GUION_ASISTENCIA)]
                linea = candidatos[con_clase % len(candidatos)]
                _registro, creado = RegistroAsistencia.objects.get_or_create(
                    legajo=linea.legajo,
                    fecha=fecha,
                    defaults={
                        "institucion": institucion,
                        "estado": estado,
                        "registrado_por": usuario,
                        "observaciones": nota,
                        **extra,
                    },
                )
                creados += int(creado)
                con_clase += 1
            fecha -= timedelta(days=1)

        if con_clase == 0:
            self.stdout.write(
                self.style.WARNING("No se encontraron días con clase para registrar asistencia.")
            )
        else:
            self.stdout.write(
                f"+ Asistencia: {creados} novedades nuevas en {con_clase} días de clase."
            )

    def _licencias_del_dia(self, institucion):
        """Deja el parte de hoy mostrando los dos casos que importan.

        Las licencias del piloto se eligen antes de que exista el horario, así
        que pueden caer en docentes que hoy no tienen clase y el parte queda
        sin nada que mostrar. Acá, con el horario ya publicado, se agrega una
        licencia cubierta por un suplente y otra sin cubrir, sobre gente que
        efectivamente trabaja hoy: así se ve el reemplazo en la grilla y las
        horas que quedan sin docente.
        """
        hoy = date.today()
        # Quien ya está de licencia no aparece en el parte, así que estos
        # candidatos son necesariamente gente disponible.
        candidatos = [linea.legajo for linea in parte_diario(institucion, hoy).lineas]
        if len(candidatos) < 2:
            return

        enfermedad = TipoLicencia.objects.filter(institucion=institucion, codigo="Art. 76").first()
        particulares = TipoLicencia.objects.filter(
            institucion=institucion, codigo="Art. 93.4"
        ).first()
        if not (enfermedad and particulares):
            return

        # Una licencia cubierta: las horas pasan al suplente.
        cubierta, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=candidatos[0],
            tipo=enfermedad,
            fecha_inicio=hoy - timedelta(days=1),
            defaults={"fecha_fin": hoy + timedelta(days=6), "estado": EstadoLicencia.APROBADA},
        )
        if creada:
            suplente, _ = Legajo.objects.get_or_create(
                institucion=institucion,
                cuil="20-33444555-6",
                defaults={"apellido": "Ríos", "nombre": "Marcos", "fecha_ingreso": hoy},
            )
            for cargo in candidatos[0].cargos_vigentes(cubierta.fecha_inicio):
                cobertura = Cobertura.objects.create(
                    institucion=institucion,
                    licencia=cubierta,
                    cargo=cargo,
                    tipo=TipoCobertura.SUPLENTE,
                    suplente=suplente,
                    fecha_inicio=cubierta.fecha_inicio,
                    fecha_fin=cubierta.fecha_fin,
                )
                cobertura.designar_cargo_del_suplente()
            self.stdout.write(f"+ Licencia cubierta: {candidatos[0]}, suplente {suplente}.")

        # Y una sin cubrir: esos cursos quedan sin clase, y el parte lo dice.
        libre, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=candidatos[1],
            tipo=particulares,
            fecha_inicio=hoy,
            defaults={"fecha_fin": hoy, "estado": EstadoLicencia.APROBADA},
        )
        if creada:
            for cargo in candidatos[1].cargos_vigentes(hoy):
                Cobertura.objects.create(
                    institucion=institucion,
                    licencia=libre,
                    cargo=cargo,
                    tipo=TipoCobertura.SIN_COBERTURA,
                    fecha_inicio=hoy,
                    fecha_fin=hoy,
                    observaciones="No hubo suplente disponible.",
                )
            self.stdout.write(f"+ Licencia sin cubrir: {candidatos[1]}, los alumnos quedan libres.")

    def _movimiento_del_portal(self, institucion):
        """Un aviso de inasistencia y una fichada, para que el parte los muestre."""
        hoy = date.today()
        parte = parte_diario(institucion, hoy)
        presentes = [linea.legajo for linea in parte.lineas]
        if not presentes:
            return

        # Ficha alguien que hoy tiene clase, así el parte muestra la llegada.
        # Se prefiere al docente que tiene usuario del portal, que es con el
        # que se entra a probarlo.
        del_portal = Legajo.objects.filter(institucion=institucion, usuario__isnull=False).first()
        fichador = del_portal if del_portal in presentes else presentes[0]

        _fichada, creada = Fichada.objects.get_or_create(
            legajo=fichador,
            fecha=hoy,
            tipo=TipoFichada.ENTRADA,
            defaults={
                "institucion": institucion,
                "hora": time(7, 38),
                # A media cuadra de la escuela: entra en el radio de 200 m.
                "latitud": institucion.latitud + 0.0004,
                "longitud": institucion.longitud + 0.0004,
                "precision_metros": 12,
            },
        )
        if creada:
            self.stdout.write(f"+ Fichada: {fichador} marcó entrada 07:38.")

        # Y otro avisa que no viene: es la novedad que la secretaría ve apenas
        # abre el parte, antes de que llegue el certificado.
        otro = next((legajo for legajo in presentes if legajo != fichador), None)
        if otro is not None:
            _aviso, creado = AvisoInasistencia.objects.get_or_create(
                legajo=otro,
                fecha=hoy,
                defaults={
                    "institucion": institucion,
                    "motivo": MotivoAviso.ENFERMEDAD,
                    "detalle": "Cuadro febril, presenta certificado mañana.",
                },
            )
            if creado:
                self.stdout.write(f"+ Aviso: {otro} informó que no viene.")

    def _compilar_novedades(self, institucion, usuario):
        """Arma el mes en curso, que es lo que se le manda al liquidador."""
        hoy = date.today()
        periodo, _creado = PeriodoNovedades.objects.get_or_create(
            institucion=institucion, anio=hoy.year, mes=hoy.month
        )
        resultado = compilar(periodo, usuario=usuario)
        for aviso in resultado.avisos:
            self.stdout.write(self.style.WARNING(f"  aviso: {aviso}"))

        resumen = periodo.resumen()
        self.stdout.write(
            f"+ Novedades de {periodo}: {resultado.creadas} nuevas, "
            f"{resultado.actualizadas} actualizadas."
        )
        self.stdout.write(
            f"  A informar: {resumen['a_informar']} "
            f"({resumen['oficial']} Oficial, {resumen['interna']} Interna)."
        )
