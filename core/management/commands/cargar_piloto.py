"""Carga una institución de ejemplo con la estructura del colegio piloto.

Sirve para probar el sistema sin cargar todo a mano y como punto de partida
real: reproduce lo relevado en el documento de requerimientos (turno mañana,
horas de 40' de a pares, recreos variables y dos esquemas — con y sin
almuerzo). Los horarios exactos son aproximados: se ajustan desde el admin.

    python manage.py cargar_piloto --email secretaria@escuela.edu.ar
"""

from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
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

    @transaction.atomic
    def handle(self, *args, **opciones):
        anio = opciones["anio"]

        institucion, creada = Institucion.objects.get_or_create(
            nombre="Instituto de ejemplo",
            defaults={
                "nombre_corto": "Instituto",
                "jurisdiccion": Jurisdiccion.SAN_LUIS,
                "localidad": "San Luis",
            },
        )
        self._informar("Institución", institucion, creada)

        usuario = self._crear_usuario(institucion, opciones)
        niveles = self._crear_niveles(institucion)
        ciclo = self._crear_ciclo(institucion, anio)
        esquemas = self._crear_grilla(institucion, niveles[TipoNivel.SECUNDARIO])
        self._crear_cursos_y_plan(institucion, niveles[TipoNivel.SECUNDARIO], ciclo, esquemas)
        self._crear_personal(institucion, niveles[TipoNivel.SECUNDARIO], ciclo)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Listo. Institución «{institucion}» preparada."))
        self.stdout.write(f"Usuario de secretaría: {usuario.email}")
        if not opciones["password"]:
            self.stdout.write(
                "Sin contraseña: asignale una con "
                f"«python manage.py changepassword {usuario.email}»."
            )

    # -- pasos ----------------------------------------------------------------

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

    def _informar(self, etiqueta, objeto, creado):
        marca = self.style.SUCCESS("+") if creado else self.style.WARNING("=")
        self.stdout.write(f"{marca} {etiqueta}: {objeto}")
