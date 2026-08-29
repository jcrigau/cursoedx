"""Carga una institución de ejemplo con la estructura del colegio piloto.

Sirve para probar el sistema sin cargar todo a mano y como punto de partida
real: reproduce lo relevado en el documento de requerimientos (turno mañana,
horas de 40' de a pares, recreos variables y dos esquemas — con y sin
almuerzo). Los horarios exactos son aproximados: se ajustan desde el admin.

    python manage.py cargar_piloto --email secretaria@escuela.edu.ar
"""

from datetime import date, time, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institucion, Jurisdiccion, Membresia, Rol, Usuario
from estructura.models import (
    BloqueHorario,
    CicloLectivo,
    Curso,
    EsquemaHorario,
    EstadoCiclo,
    Materia,
    MateriaPlan,
    Nivel,
    PeriodoAcademico,
    TipoBloque,
    TipoNivel,
    Turno,
)
from horarios.models import DeclaracionDisponibilidad, FranjaNoDisponible, MotivoNoDisponible
from legajos.models import (
    Cargo,
    DocumentoLegajo,
    FuentePago,
    Legajo,
    MotivoBaja,
    ServicioAnterior,
    SituacionRevista,
    TipoDocumento,
)
from legajos.models import TipoCargo as TipoCargoLegajo
from licencias.models import (
    Cobertura,
    EstadoLicencia,
    Licencia,
    TipoCobertura,
    TipoLicencia,
)


# La escuela de ejemplo se llama así y se pinta de naranja a propósito: es la
# señal de que lo que se está mirando no es la escuela real.
def _correo_de(nombre: str, apellido: str) -> str:
    """Un correo inventado y consistente para el personal de ejemplo."""
    from unicodedata import combining, normalize

    junto = f"{nombre}.{apellido}".lower().replace(" ", "")
    sin_tildes = "".join(letra for letra in normalize("NFKD", junto) if not combining(letra))
    return f"{sin_tildes}@ejemplo.edu.ar"


NOMBRE_ESCUELA_DE_PRUEBA = "Escuela Orange"
COLOR_ESCUELA_DE_PRUEBA = "#c2560f"
EMBLEMA_ESCUELA_DE_PRUEBA = "🍊"

# Cómo se llamó antes, para reconocerla en una instalación que ya venía andando.
NOMBRES_ANTERIORES = ["Instituto de ejemplo"]

# Grilla del turno mañana: las horas van de a pares con recreos de duración
# variable, y algunos cursos cortan para almorzar.
GRILLA_MANIANA = [
    (TipoBloque.CLASE, time(7, 45), time(8, 25), "1ª hora"),
    (TipoBloque.CLASE, time(8, 25), time(9, 5), "2ª hora"),
    (TipoBloque.RECREO, time(9, 5), time(9, 15), "Recreo"),
    (TipoBloque.CLASE, time(9, 15), time(9, 55), "3ª hora"),
    (TipoBloque.CLASE, time(9, 55), time(10, 35), "4ª hora"),
    (TipoBloque.RECREO, time(10, 35), time(10, 50), "Recreo largo"),
    (TipoBloque.CLASE, time(10, 50), time(11, 30), "5ª hora"),
    (TipoBloque.CLASE, time(11, 30), time(12, 10), "6ª hora"),
    (TipoBloque.RECREO, time(12, 10), time(12, 20), "Recreo"),
    (TipoBloque.CLASE, time(12, 20), time(13, 0), "7ª hora"),
]

BLOQUE_ALMUERZO = (TipoBloque.ALMUERZO, time(13, 0), time(13, 40), "Almuerzo")

MATERIAS_SECUNDARIA = [
    ("Matemática", "MAT", 5),
    ("Lengua y Literatura", "LEN", 5),
    ("Inglés", "ING", 3),
    ("Historia", "HIS", 3),
    ("Geografía", "GEO", 3),
    ("Biología", "BIO", 3),
    ("Química", "QUI", 3),
    ("Educación Física", "EF", 3),
    ("Educación Artística", "ART", 2),
    ("Formación Ética y Ciudadana", "FEC", 2),
    ("Catequesis", "CAT", 2),
]

DIAS_HABILES = range(5)  # lunes a viernes

# Tope de horas semanales que se le carga a un docente inventado.
TOPE_HORAS_DOCENTE = 18

APELLIDOS = [
    "Aguirre",
    "Benítez",
    "Cabrera",
    "Domínguez",
    "Echeverría",
    "Funes",
    "Gallardo",
    "Herrera",
    "Ibarra",
    "Juárez",
    "Ledesma",
    "Maldonado",
    "Navarro",
    "Olmedo",
    "Ponce",
    "Quinteros",
    "Rivas",
    "Sosa",
    "Toledo",
    "Urquiza",
    "Villalba",
    "Zárate",
]

NOMBRES = [
    "Carolina",
    "Martín",
    "Silvina",
    "Gustavo",
    "Natalia",
    "Federico",
    "Mariela",
    "Ezequiel",
    "Romina",
    "Sebastián",
    "Valeria",
    "Alejandro",
    "Daniela",
    "Pablo",
]

# (nombre, lleva vencimiento, días de preaviso, obligatorio)
TIPOS_DOCUMENTO = [
    ("Apto psicofísico", True, 30, True),
    ("Certificado de antecedentes penales", True, 60, True),
    ("Título registrado", False, 30, True),
    ("Constancia de CUIL", False, 30, False),
]

# Personal inventado que cubre los casos que el sistema debe soportar.
PERSONAL_DE_EJEMPLO = [
    {
        "apellido": "Ferreyra",
        "nombre": "Marina Soledad",
        "cuil": "27-30123456-4",
        "obra_social": "OSDE",
        "dias_de_antiguedad": 3200,
        "cargos": [
            {
                "tipo": TipoCargoLegajo.HORAS_CATEDRA,
                "materia": "Matemática",
                "curso": "1°A",
                "horas": 5,
                "revista": SituacionRevista.TITULAR,
                "fuente": FuentePago.SUBVENCIONADO,
                "dias_desde_alta": 3200,
            },
            {
                "tipo": TipoCargoLegajo.HORAS_CATEDRA,
                "materia": "Matemática",
                "curso": "1°B",
                "horas": 5,
                "revista": SituacionRevista.TITULAR,
                "fuente": FuentePago.SUBVENCIONADO,
                "dias_desde_alta": 3200,
            },
        ],
        "documentos": [("Apto psicofísico", -20), ("Certificado de antecedentes penales", 300)],
        "servicios_anteriores": [
            {
                "institucion": "Escuela N° 12 «Los Álamos»",
                "cargo": "Profesora de Matemática",
                "desde": date(2012, 3, 1),
                "hasta": date(2016, 12, 31),
            }
        ],
    },
    {
        # Caso mixto: horas que paga el estado y horas que paga la escuela.
        "apellido": "Ocampo",
        "nombre": "Lucía Beatriz",
        "cuil": "27-33456789-1",
        "obra_social": "Jerárquicos Salud",
        "dias_de_antiguedad": 1500,
        "cargos": [
            {
                "tipo": TipoCargoLegajo.HORAS_CATEDRA,
                "materia": "Lengua y Literatura",
                "curso": "3°A",
                "horas": 5,
                "revista": SituacionRevista.PROVISIONAL,
                "fuente": FuentePago.SUBVENCIONADO,
                "dias_desde_alta": 1500,
            },
            {
                "tipo": TipoCargoLegajo.HORAS_CATEDRA,
                "materia": "Educación Artística",
                "curso": "3°B",
                "horas": 2,
                "revista": SituacionRevista.PROVISIONAL,
                "fuente": FuentePago.INTERNO,
                "dias_desde_alta": 700,
            },
        ],
        "documentos": [("Apto psicofísico", 25), ("Título registrado", None)],
    },
    {
        "apellido": "Quiroga",
        "nombre": "Hernán Darío",
        "cuil": "20-28987654-3",
        "dias_de_antiguedad": 900,
        "cargos": [
            {
                "tipo": TipoCargoLegajo.HORAS_RELOJ,
                "denominacion": "Preceptor/a",
                "horas": 25,
                "revista": SituacionRevista.PROVISIONAL,
                "fuente": FuentePago.SUBVENCIONADO,
                "dias_desde_alta": 900,
            }
        ],
        "documentos": [("Apto psicofísico", 400)],
    },
    {
        "apellido": "Bustos",
        "nombre": "Verónica Andrea",
        "cuil": "27-25678912-7",
        "dias_de_antiguedad": 2400,
        "cargos": [
            {
                "tipo": TipoCargoLegajo.CARGO_BASE,
                "denominacion": "Secretaria",
                "jornada_completa": True,
                "revista": SituacionRevista.TITULAR,
                "fuente": FuentePago.INTERNO,
                "dias_desde_alta": 2400,
            }
        ],
        "documentos": [("Certificado de antecedentes penales", 15)],
    },
    {
        # Suplente con designación a término.
        "apellido": "Peralta",
        "nombre": "Iván Nicolás",
        "cuil": "20-35789456-2",
        "dias_de_antiguedad": 40,
        "cargos": [
            {
                "tipo": TipoCargoLegajo.HORAS_CATEDRA,
                "materia": "Historia",
                "curso": "5°A",
                "horas": 3,
                "revista": SituacionRevista.SUPLENTE,
                "fuente": FuentePago.SUBVENCIONADO,
                "dias_desde_alta": 40,
                "dias_hasta_baja": 50,
                "motivo_baja": MotivoBaja.FIN_SUPLENCIA,
            }
        ],
        "documentos": [("Apto psicofísico", 500)],
    },
]


class Command(BaseCommand):
    help = "Carga una institución de ejemplo con la estructura del colegio piloto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default="secretaria@ejemplo.edu.ar",
            help="Email del usuario de secretaría que se crea (o reutiliza).",
        )
        parser.add_argument(
            "--password",
            default="",
            help="Contraseña del usuario. Si se omite, no se puede iniciar sesión con él.",
        )
        parser.add_argument(
            "--anio", type=int, default=date.today().year, help="Ciclo lectivo a crear."
        )
        parser.add_argument(
            "--reiniciar",
            action="store_true",
            help=(
                "Borrar la escuela de ejemplo y volver a armarla desde cero. "
                "Solo toca esa escuela; cualquier otra institución queda intacta."
            ),
        )
        parser.add_argument(
            "--sin-planta",
            dest="con_planta",
            action="store_false",
            help="No generar la planta docente completa (solo el personal de muestra).",
        )

    @transaction.atomic
    def handle(self, *args, **opciones):
        anio = opciones["anio"]

        if opciones["reiniciar"]:
            self._borrar_la_escuela_de_prueba()

        institucion, creada = self._escuela_de_prueba()
        self._informar("Institución", institucion, creada)

        usuario = self._crear_usuario(institucion, opciones)
        niveles = self._crear_niveles(institucion)
        ciclo = self._crear_ciclo(institucion, anio)
        esquemas = self._crear_grilla(institucion, niveles[TipoNivel.SECUNDARIO])
        self._crear_cursos_y_plan(institucion, niveles[TipoNivel.SECUNDARIO], ciclo, esquemas)
        self._crear_personal(institucion, niveles[TipoNivel.SECUNDARIO], ciclo)
        if opciones["con_planta"]:
            self._crear_planta_docente(institucion, niveles[TipoNivel.SECUNDARIO], ciclo)
        self._crear_licencias(institucion)
        self._declarar_materias(institucion)
        docente = self._dar_acceso_al_portal(institucion, opciones)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Listo. Institución «{institucion}» preparada."))
        self.stdout.write(f"Usuario de secretaría: {usuario.email}")
        if docente:
            self.stdout.write(f"Usuario del portal docente: {docente.email}")
        if not opciones["password"]:
            self.stdout.write(
                "Sin contraseña: asignale una con "
                f"«python manage.py changepassword {usuario.email}»."
            )

    # -- pasos ----------------------------------------------------------------

    def _borrar_la_escuela_de_prueba(self):
        """Vacía la escuela de ejemplo, sin tocar ninguna otra institución.

        Sirve cuando una base vieja arrastra datos inconsistentes de versiones
        anteriores. Se filtra por nombre: una escuela real nunca entra acá.

        Las claves foráneas hacia la institución son ``PROTECT`` —lo que evita
        borrados accidentales—, así que no alcanza con borrarla de un saque.
        Se recorren sus modelos borrando los que se dejen, y se repite: en cada
        vuelta caen los que quedaron sin quien los proteja. Lo que llega a la
        institución por una relación (las asignaciones de un horario, la
        documentación de un legajo) se va en cascada con su padre.
        """
        from django.apps import apps
        from django.db import transaction
        from django.db.models import ProtectedError

        from core.models import ModeloInstitucional

        institucion = Institucion.objects.filter(
            nombre__in=[NOMBRE_ESCUELA_DE_PRUEBA, *NOMBRES_ANTERIORES]
        ).first()
        if institucion is None:
            return

        pendientes = [
            modelo
            for modelo in apps.get_models()
            if issubclass(modelo, ModeloInstitucional) and not modelo._meta.abstract
        ]
        borrados = 0
        while pendientes:
            avanzo = False
            for modelo in list(pendientes):
                try:
                    with transaction.atomic():
                        cuantos, _ = modelo.objects.filter(institucion=institucion).delete()
                except ProtectedError:
                    continue  # todavía lo protege otro modelo; en la próxima vuelta
                borrados += cuantos
                pendientes.remove(modelo)
                avanzo = True
            if not avanzo:
                nombres = ", ".join(m.__name__ for m in pendientes)
                raise CommandError(
                    f"No se pudo vaciar la escuela de ejemplo: quedaron {nombres}. "
                    "Es un error del comando, no de tus datos: nada se borró."
                )

        if borrados:
            self.stdout.write(
                self.style.WARNING(
                    f"Escuela de ejemplo vaciada ({borrados} registros). Se rearma de cero."
                )
            )

    def _escuela_de_prueba(self):
        """La escuela de ejemplo, creada o puesta al día.

        Se busca también por los nombres que tuvo antes: una instalación que ya
        venía andando tiene que quedar renombrada y repintada, no convivir con
        una segunda escuela vacía al lado.
        """
        institucion = Institucion.objects.filter(
            nombre__in=[NOMBRE_ESCUELA_DE_PRUEBA, *NOMBRES_ANTERIORES]
        ).first()
        creada = institucion is None
        if creada:
            institucion = Institucion(
                jurisdiccion=Jurisdiccion.SAN_LUIS,
                localidad="San Luis",
                # Ubicación aproximada, para poder probar el fichaje del portal.
                latitud=-33.301726,
                longitud=-66.337752,
                radio_fichaje_metros=200,
            )

        # La identidad se reescribe siempre, incluso sobre una escuela que ya
        # existía: es lo único que distingue la de prueba de la real, y no
        # puede quedar librado a que alguien la haya editado.
        institucion.nombre = NOMBRE_ESCUELA_DE_PRUEBA
        institucion.nombre_corto = "Orange"
        institucion.color = COLOR_ESCUELA_DE_PRUEBA
        institucion.emblema = EMBLEMA_ESCUELA_DE_PRUEBA
        institucion.save()
        return institucion, creada

    def _crear_usuario(self, institucion, opciones):
        usuario, creado = Usuario.objects.get_or_create(
            email=opciones["email"],
            defaults={"nombre": "Secretaría", "apellido": "Escuela", "is_staff": True},
        )
        if opciones["password"]:
            usuario.set_password(opciones["password"])
            usuario.save(update_fields=["password"])
        Membresia.objects.get_or_create(
            usuario=usuario, institucion=institucion, rol=Rol.SECRETARIA
        )
        self._informar("Usuario", usuario.email, creado)
        return usuario

    def _crear_niveles(self, institucion):
        niveles = {}
        for orden, tipo in enumerate(
            [TipoNivel.INICIAL, TipoNivel.PRIMARIO, TipoNivel.SECUNDARIO], start=1
        ):
            nivel, creado = Nivel.objects.get_or_create(
                institucion=institucion, tipo=tipo, defaults={"orden": orden}
            )
            niveles[tipo] = nivel
            self._informar("Nivel", nivel, creado)
        return niveles

    def _crear_ciclo(self, institucion, anio):
        ciclo, creado = CicloLectivo.objects.get_or_create(
            institucion=institucion,
            anio=anio,
            defaults={
                "fecha_inicio": date(anio, 3, 1),
                "fecha_fin": date(anio, 12, 15),
                "estado": EstadoCiclo.ACTIVO,
            },
        )
        self._informar("Ciclo lectivo", ciclo, creado)

        for orden, (nombre, inicio, fin) in enumerate(
            [
                ("1er cuatrimestre", date(anio, 3, 1), date(anio, 7, 31)),
                ("2do cuatrimestre", date(anio, 8, 1), date(anio, 12, 15)),
            ],
            start=1,
        ):
            periodo, creado = PeriodoAcademico.objects.get_or_create(
                ciclo=ciclo,
                orden=orden,
                defaults={"nombre": nombre, "fecha_inicio": inicio, "fecha_fin": fin},
            )
            self._informar("Período", periodo, creado)
        return ciclo

    def _crear_grilla(self, institucion, nivel):
        turno, creado = Turno.objects.get_or_create(
            institucion=institucion,
            nivel=nivel,
            nombre="Mañana",
            defaults={"hora_inicio": time(7, 45), "hora_fin": time(13, 40), "orden": 1},
        )
        self._informar("Turno", turno, creado)

        esquemas = {}
        for nombre, con_almuerzo, predeterminado in [
            ("Sin almuerzo", False, True),
            ("Con almuerzo", True, False),
        ]:
            esquema, creado = EsquemaHorario.objects.get_or_create(
                institucion=institucion,
                turno=turno,
                nombre=nombre,
                defaults={"predeterminado": predeterminado},
            )
            self._informar("Esquema", esquema, creado)
            if creado or not esquema.bloques.exists():
                self._cargar_bloques(esquema, con_almuerzo)
            esquemas[nombre] = esquema
        return esquemas

    def _cargar_bloques(self, esquema, con_almuerzo):
        franjas = list(GRILLA_MANIANA)
        if con_almuerzo:
            franjas.append(BLOQUE_ALMUERZO)
        bloques = [
            BloqueHorario(
                esquema=esquema,
                dia_semana=dia,
                orden=orden,
                tipo=tipo,
                hora_inicio=inicio,
                hora_fin=fin,
                etiqueta=etiqueta,
            )
            for dia in DIAS_HABILES
            for orden, (tipo, inicio, fin, etiqueta) in enumerate(franjas, start=1)
        ]
        BloqueHorario.objects.bulk_create(bloques)
        self.stdout.write(f"  + {len(bloques)} bloques en «{esquema.nombre}»")

    def _crear_cursos_y_plan(self, institucion, nivel, ciclo, esquemas):
        materias = {}
        for nombre, abreviatura, _ in MATERIAS_SECUNDARIA:
            materia, _creada = Materia.objects.get_or_create(
                institucion=institucion,
                nivel=nivel,
                nombre=nombre,
                defaults={"abreviatura": abreviatura},
            )
            materias[nombre] = materia

        turno = Turno.objects.get(institucion=institucion, nivel=nivel, nombre="Mañana")
        for anio_estudio in range(1, 7):
            for division in ("A", "B"):
                # Los cursos más chicos almuerzan en la escuela; los mayores no.
                esquema = esquemas["Con almuerzo" if anio_estudio <= 3 else "Sin almuerzo"]
                curso, creado = Curso.objects.get_or_create(
                    institucion=institucion,
                    ciclo_lectivo=ciclo,
                    nivel=nivel,
                    anio_estudio=anio_estudio,
                    division=division,
                    defaults={"turno": turno, "esquema_horario": esquema},
                )
                self._informar("Curso", curso, creado)
                if creado:
                    MateriaPlan.objects.bulk_create(
                        MateriaPlan(curso=curso, materia=materias[nombre], horas_semanales=horas)
                        for nombre, _abrev, horas in MATERIAS_SECUNDARIA
                    )

    def _crear_personal(self, institucion, nivel, ciclo):
        """Personal de muestra, con los casos que el sistema tiene que soportar.

        Las personas son inventadas. Incluye un caso mixto (horas del estado y
        horas de la escuela en la misma persona), un suplente, documentación
        vencida y por vencer, y servicios anteriores para el cómputo de
        antigüedad.
        """
        tipos_documento = {}
        for nombre, vence, preaviso, obligatorio in TIPOS_DOCUMENTO:
            tipo, _creado = TipoDocumento.objects.get_or_create(
                institucion=institucion,
                nombre=nombre,
                defaults={
                    "lleva_vencimiento": vence,
                    "dias_preaviso": preaviso,
                    "obligatorio": obligatorio,
                },
            )
            tipos_documento[nombre] = tipo

        materias = {
            materia.nombre: materia
            for materia in Materia.objects.filter(institucion=institucion, nivel=nivel)
        }
        cursos = {
            str(curso): curso
            for curso in Curso.objects.filter(institucion=institucion, ciclo_lectivo=ciclo)
        }
        hoy = date.today()

        for datos in PERSONAL_DE_EJEMPLO:
            legajo, creado = Legajo.objects.get_or_create(
                institucion=institucion,
                cuil=datos["cuil"],
                defaults={
                    "apellido": datos["apellido"],
                    "nombre": datos["nombre"],
                    "obra_social": datos.get("obra_social", ""),
                    "fecha_ingreso": hoy - timedelta(days=datos["dias_de_antiguedad"]),
                    # Contacto inventado, para poder probar el aviso al suplente.
                    "email": _correo_de(datos["nombre"], datos["apellido"]),
                    "telefono": f"2664{datos['cuil'][-8:-2]}",
                },
            )
            self._informar("Legajo", legajo, creado)
            if not creado:
                continue

            for cargo in datos["cargos"]:
                Cargo.objects.create(
                    institucion=institucion,
                    legajo=legajo,
                    tipo=cargo["tipo"],
                    denominacion=cargo.get("denominacion", ""),
                    nivel=nivel,
                    materia=materias.get(cargo.get("materia", "")),
                    curso=cursos.get(cargo.get("curso", "")),
                    horas_semanales=cargo.get("horas"),
                    jornada_completa=cargo.get("jornada_completa", False),
                    situacion_revista=cargo["revista"],
                    fuente_pago=cargo["fuente"],
                    fecha_alta=hoy - timedelta(days=cargo.get("dias_desde_alta", 365)),
                    fecha_baja=(
                        hoy + timedelta(days=cargo["dias_hasta_baja"])
                        if "dias_hasta_baja" in cargo
                        else None
                    ),
                    motivo_baja=cargo.get("motivo_baja", ""),
                )

            for nombre_tipo, dias in datos.get("documentos", []):
                DocumentoLegajo.objects.create(
                    legajo=legajo,
                    tipo=tipos_documento[nombre_tipo],
                    fecha_emision=hoy - timedelta(days=365),
                    fecha_vencimiento=hoy + timedelta(days=dias) if dias is not None else None,
                )

            for servicio in datos.get("servicios_anteriores", []):
                ServicioAnterior.objects.create(
                    legajo=legajo,
                    institucion_nombre=servicio["institucion"],
                    cargo_descripcion=servicio.get("cargo", ""),
                    desde=servicio["desde"],
                    hasta=servicio["hasta"],
                )

    def _crear_planta_docente(self, institucion, nivel, ciclo):
        """Cubre todas las materias de todos los cursos con docentes inventados.

        Reparte cada materia entre los docentes que hagan falta, sin pasar el
        tope de horas de uno solo, y les carga una DDJJ: es la situación real
        que tiene que resolver el generador de horarios.
        """
        cursos = list(
            Curso.objects.filter(institucion=institucion, ciclo_lectivo=ciclo).order_by(
                "anio_estudio", "division"
            )
        )
        if not cursos:
            return

        materias = {
            materia.nombre: materia
            for materia in Materia.objects.filter(institucion=institucion, nivel=nivel)
        }
        periodos = list(PeriodoAcademico.objects.filter(ciclo=ciclo).order_by("orden"))
        hoy = date.today()
        creados = 0

        for indice_materia, (nombre_materia, _abrev, horas) in enumerate(MATERIAS_SECUNDARIA):
            materia = materias.get(nombre_materia)
            if materia is None:
                continue

            # El número del docente cuenta dentro de su materia, no sobre el
            # total: así la misma corrida sobre la misma escuela vuelve a dar
            # exactamente las mismas personas, y recargar no duplica la planta.
            numero, docente, acumuladas = 0, None, 0
            for curso in cursos:
                # Un docente no toma más de TOPE_HORAS_DOCENTE horas.
                if docente is None or acumuladas + horas > TOPE_HORAS_DOCENTE:
                    docente, nuevo_docente = self._docente_inventado(
                        institucion, indice_materia, numero, hoy
                    )
                    orden = indice_materia * 10 + numero
                    numero += 1
                    acumuladas = 0
                    if nuevo_docente:
                        creados += 1
                        self._cargar_ddjj(institucion, docente, periodos, orden)

                # No es get_or_create a propósito: una misma persona puede
                # tener legítimamente dos cargos de la misma materia y curso
                # —el caso mixto, uno por fuente de pago—, y una base vieja
                # puede arrastrar duplicados. Lo que importa es no agregar otro.
                ya_lo_tiene = Cargo.objects.filter(
                    institucion=institucion, legajo=docente, materia=materia, curso=curso
                ).exists()
                if not ya_lo_tiene:
                    Cargo.objects.create(
                        institucion=institucion,
                        legajo=docente,
                        materia=materia,
                        curso=curso,
                        tipo=TipoCargoLegajo.HORAS_CATEDRA,
                        nivel=nivel,
                        horas_semanales=horas,
                        situacion_revista=SituacionRevista.TITULAR
                        if orden % 3
                        else SituacionRevista.PROVISIONAL,
                        fuente_pago=FuentePago.SUBVENCIONADO if orden % 4 else FuentePago.INTERNO,
                        fecha_alta=hoy - timedelta(days=400 + orden * 30),
                    )
                acumuladas += horas

        self.stdout.write(f"  + {creados} docentes con sus cargos y declaraciones juradas")

    def _docente_inventado(self, institucion, indice_materia, numero, hoy):
        """Un docente de la planta de ejemplo. Devuelve (legajo, si es nuevo).

        El CUIL sale de la materia y del número dentro de ella, así que es el
        mismo en cada corrida: volver a cargar el piloto reencuentra a la misma
        persona en lugar de inventar otra.
        """
        apellido = APELLIDOS[(indice_materia * 7 + numero) % len(APELLIDOS)]
        nombre = NOMBRES[(indice_materia * 5 + numero) % len(NOMBRES)]
        cuil = f"27-{30000000 + indice_materia * 1000 + numero:08d}-1"
        return Legajo.objects.get_or_create(
            institucion=institucion,
            cuil=cuil,
            defaults={
                "apellido": apellido,
                "nombre": nombre,
                "fecha_ingreso": hoy - timedelta(days=400 + numero * 30),
                # Datos de contacto inventados, para poder probar el aviso al
                # suplente sin cargarlos a mano uno por uno.
                "email": _correo_de(nombre, apellido),
                "telefono": f"2664{500000 + indice_materia * 100 + numero:06d}",
            },
        )

    def _cargar_ddjj(self, institucion, docente, periodos, numero):
        """Le carga compromisos en otra escuela, como pasa en la realidad."""
        if not periodos or numero % 3:
            return
        # Uno de cada tres docentes trabaja media jornada en otra institución.
        dia = numero % 5
        declaracion, _creada = DeclaracionDisponibilidad.objects.get_or_create(
            institucion=institucion,
            legajo=docente,
            periodo=periodos[0],
            defaults={"presentada_en": date.today()},
        )
        FranjaNoDisponible.objects.get_or_create(
            declaracion=declaracion,
            dia_semana=dia,
            hora_desde=time(7, 45),
            hora_hasta=time(10, 35),
            defaults={
                "motivo": MotivoNoDisponible.OTRA_ESCUELA,
                "institucion_externa": "Escuela N° 24",
            },
        )

    def _crear_licencias(self, institucion):
        """Catálogo del régimen y un par de licencias en curso, con y sin cobertura."""
        call_command("cargar_catalogo_licencias", institucion=institucion.pk, verbosity=0)

        docentes = list(
            Legajo.objects.filter(institucion=institucion, cargos__isnull=False)
            .distinct()
            .order_by("apellido", "nombre")[:2]
        )
        if len(docentes) < 2:
            return

        # Alta express de un suplente: entra sin cargos propios y recibe los
        # del titular al designarlo.
        suplente, _creado = Legajo.objects.get_or_create(
            institucion=institucion,
            cuil="27-38999111-2",
            defaults={
                "apellido": "Vega",
                "nombre": "Julieta",
                "fecha_ingreso": date.today(),
            },
        )

        hoy = date.today()
        enfermedad = TipoLicencia.objects.filter(institucion=institucion, codigo="Art. 76").first()
        particulares = TipoLicencia.objects.filter(
            institucion=institucion, codigo="Art. 93.4"
        ).first()
        if not (enfermedad and particulares):
            return

        # Una licencia larga cubierta por un suplente.
        titular, otro = docentes[0], docentes[1]
        licencia, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=titular,
            tipo=enfermedad,
            fecha_inicio=hoy - timedelta(days=10),
            defaults={
                "fecha_fin": hoy + timedelta(days=5),
                "estado": EstadoLicencia.APROBADA,
            },
        )
        if creada:
            for cargo in titular.cargos_vigentes(licencia.fecha_inicio):
                cobertura = Cobertura.objects.create(
                    institucion=institucion,
                    licencia=licencia,
                    cargo=cargo,
                    tipo=TipoCobertura.SUPLENTE,
                    suplente=suplente,
                    fecha_inicio=licencia.fecha_inicio,
                    fecha_fin=licencia.fecha_fin,
                )
                cobertura.designar_cargo_del_suplente()
            self._informar("Licencia", licencia, True)

        # Una licencia corta que la escuela decidió no cubrir.
        corta, creada = Licencia.objects.get_or_create(
            institucion=institucion,
            legajo=otro,
            tipo=particulares,
            fecha_inicio=hoy,
            defaults={"fecha_fin": hoy, "estado": EstadoLicencia.APROBADA},
        )
        if creada:
            for cargo in otro.cargos_vigentes(hoy):
                Cobertura.objects.create(
                    institucion=institucion,
                    licencia=corta,
                    cargo=cargo,
                    tipo=TipoCobertura.SIN_COBERTURA,
                    fecha_inicio=hoy,
                    fecha_fin=hoy,
                    observaciones="No hubo suplente disponible.",
                )
            self._informar("Licencia", corta, True)

    def _declarar_materias(self, institucion):
        """Cada docente queda habilitado en lo que ya dicta.

        Es el piso obvio: quien da Química puede dar Química. Sobre eso, a
        algunos se les agrega una materia afín que hoy no dictan, para que la
        búsqueda de reemplazos tenga el caso interesante: el habilitado sin
        horas. En una escuela real esto se completa a mano, en Personal.
        """
        from legajos.models import Cargo

        con_materia = (
            Cargo.objects.filter(institucion=institucion, materia__isnull=False)
            .select_related("legajo", "materia")
            .order_by("id")
        )
        declaradas = 0
        for cargo in con_materia:
            if not cargo.legajo.materias_que_puede_dar.filter(pk=cargo.materia_id).exists():
                cargo.legajo.materias_que_puede_dar.add(cargo.materia)
                declaradas += 1

        # Materias afines: quien da una ciencia queda habilitado en la otra.
        afinidades = [
            ("Biología", "Química"),
            ("Química", "Biología"),
            ("Historia", "Geografía"),
            ("Geografía", "Historia"),
        ]
        materias = {
            materia.nombre: materia for materia in Materia.objects.filter(institucion=institucion)
        }
        for da, tambien in afinidades:
            origen, extra = materias.get(da), materias.get(tambien)
            if origen is None or extra is None:
                continue
            docente = (
                Legajo.objects.filter(institucion=institucion, cargos__materia=origen)
                .order_by("apellido")
                .first()
            )
            if docente is not None:
                docente.materias_que_puede_dar.add(extra)

        if declaradas:
            self.stdout.write(f"  + {declaradas} habilitaciones de materia declaradas")

    def _dar_acceso_al_portal(self, institucion, opciones):
        """Le crea usuario al primer docente, para poder probar el portal."""
        email = f"docente@{opciones['email'].split('@')[-1]}"
        usuario = Usuario.objects.filter(email=email).first()

        # Si ya se corrió antes, el usuario del portal ya tiene su legajo. Hay
        # que quedarse con ese: Legajo.usuario es uno a uno, y asignárselo a
        # otra persona rompe con un error de clave duplicada.
        legajo = Legajo.objects.filter(institucion=institucion, usuario=usuario).first()

        if legajo is None:
            # Se elige alguien que esté trabajando: si estuviera de licencia, el
            # portal mostraría eso y no se vería el fichaje ni el horario.
            hoy = date.today()
            legajo = (
                Legajo.objects.filter(institucion=institucion, cargos__isnull=False, usuario=None)
                .exclude(
                    licencias__estado=EstadoLicencia.APROBADA,
                    licencias__fecha_inicio__lte=hoy,
                    licencias__fecha_fin__gte=hoy,
                )
                .distinct()
                .order_by("apellido", "nombre")
                .first()
            )
        if legajo is None:
            return None

        usuario, creado = Usuario.objects.get_or_create(
            email=email,
            defaults={"nombre": legajo.nombre, "apellido": legajo.apellido},
        )
        if opciones["password"]:
            usuario.set_password(opciones["password"])
            usuario.save(update_fields=["password"])
        Membresia.objects.get_or_create(usuario=usuario, institucion=institucion, rol=Rol.DOCENTE)
        legajo.usuario = usuario
        legajo.save(update_fields=["usuario", "actualizado_en"])
        self._informar("Portal docente", f"{legajo} → {email}", creado)
        return usuario

    def _informar(self, etiqueta, objeto, creado):
        marca = self.style.SUCCESS("+") if creado else self.style.WARNING("=")
        self.stdout.write(f"{marca} {etiqueta}: {objeto}")
