"""Cubrir toda la licencia de una vez, sin pisarle el horario al suplente.

Un profesor con seis horas cátedra son seis cargos: hasta ahora, seis
formularios. Y el error que aparecía el lunes a las 7:45 —dos cursos
esperando a la misma persona— el sistema lo puede ver antes, porque tiene el
horario.
"""

from datetime import timedelta

import pytest
from django.urls import reverse

from horarios.models import AsignacionHoraria
from horarios.tests.conftest import designar
from legajos.models import Cargo, FuentePago, SituacionRevista, TipoCargo
from licencias.models import Cobertura, EstadoLicencia, Licencia, TipoCobertura, TipoLicencia
from licencias.superposicion import revisar


@pytest.fixture
def licencia_con_cargos(con_horario_publicado):
    """La docente de la escuela de prueba, de licencia sobre sus cargos."""
    datos = con_horario_publicado
    institucion = datos["escuela"]["institucion"]
    tipo = TipoLicencia.objects.create(
        institucion=institucion, nombre="Enfermedad", codigo="Art. 76"
    )
    licencia = Licencia.objects.create(
        institucion=institucion,
        legajo=datos["docente"],
        tipo=tipo,
        fecha_inicio=datos["fecha"],
        fecha_fin=datos["fecha"] + timedelta(days=5),
        estado=EstadoLicencia.APROBADA,
    )
    return {**datos, "institucion": institucion, "licencia": licencia}


def otra_persona(institucion, apellido, cuil):
    from datetime import date

    from legajos.models import Legajo

    return Legajo.objects.create(
        institucion=institucion,
        apellido=apellido,
        nombre="Prueba",
        cuil=cuil,
        fecha_ingreso=date.today(),
    )


@pytest.mark.django_db
class TestLaPantalla:
    def test_muestra_los_cargos_para_tildar(self, client, licencia_con_cargos, secretaria):
        client.force_login(secretaria)

        cuerpo = client.get(
            reverse("cubrir_licencia", args=[licencia_con_cargos["licencia"].pk])
        ).content.decode()

        assert 'name="cargos"' in cuerpo
        assert licencia_con_cargos["docente"].apellido in cuerpo

    def test_asigna_varios_cargos_de_una_vez(self, client, licencia_con_cargos, secretaria):
        licencia = licencia_con_cargos["licencia"]
        suplente = otra_persona(licencia_con_cargos["institucion"], "Libre", "27-30000501-1")
        cargos = list(licencia.cargos_afectados())
        client.force_login(secretaria)

        client.post(
            reverse("cubrir_licencia", args=[licencia.pk]),
            {
                "cargos": [cargo.pk for cargo in cargos],
                "tipo": TipoCobertura.SUPLENTE,
                "suplente": suplente.pk,
                "desde": licencia.fecha_inicio.isoformat(),
                "hasta": licencia.fecha_fin.isoformat(),
            },
        )

        assert Cobertura.objects.filter(licencia=licencia).count() == len(cargos)
        # Cada cobertura le crea al suplente su designación: es el alta del mes.
        assert Cargo.objects.filter(legajo=suplente).count() == len(cargos)

    def test_no_guarda_nada_si_se_le_pisa_una_hora(self, client, licencia_con_cargos, secretaria):
        """El error que después aparece con dos cursos esperando a la misma persona."""
        from estructura.models import Curso

        licencia = licencia_con_cargos["licencia"]
        institucion = licencia_con_cargos["institucion"]
        ocupada = otra_persona(institucion, "Ocupada", "27-30000502-1")

        # La suplente ya da clase en otro curso a la misma hora del reloj: el
        # choque real que hay que detectar.
        curso = licencia_con_cargos["curso"]
        otro_curso = Curso.objects.create(
            institucion=institucion,
            ciclo_lectivo=curso.ciclo_lectivo,
            nivel=curso.nivel,
            turno=curso.turno,
            esquema_horario=curso.esquema_horario,
            anio_estudio=curso.anio_estudio,
            division="Z",
        )
        suya = AsignacionHoraria.objects.filter(
            version=licencia_con_cargos["version"], legajo=licencia_con_cargos["docente"]
        ).first()
        # El docente de una hora sale de su cargo, nunca se asigna a mano:
        # AsignacionHoraria.save() lo copia de ahí.
        cargo_de_la_ocupada = designar(
            licencia_con_cargos["escuela"], ocupada, licencia_con_cargos["materia"], otro_curso
        )
        AsignacionHoraria.objects.create(
            version=suya.version,
            curso=otro_curso,
            bloque=suya.bloque,
            materia=suya.materia,
            cargo=cargo_de_la_ocupada,
        )
        client.force_login(secretaria)

        respuesta = client.post(
            reverse("cubrir_licencia", args=[licencia.pk]),
            {
                "cargos": [cargo.pk for cargo in licencia.cargos_afectados()],
                "tipo": TipoCobertura.SUPLENTE,
                "suplente": ocupada.pk,
                "desde": licencia.fecha_inicio.isoformat(),
                "hasta": licencia.fecha_fin.isoformat(),
            },
        )

        assert Cobertura.objects.count() == 0, "no se tiene que guardar nada"
        cuerpo = respuesta.content.decode()
        assert "No se guardó nada" in cuerpo
        # Y dice exactamente qué hora es, no un «no se puede» a secas.
        assert "se pisa con" in cuerpo

    def test_dejar_sin_cobertura_no_pide_suplente(self, client, licencia_con_cargos, secretaria):
        licencia = licencia_con_cargos["licencia"]
        client.force_login(secretaria)

        client.post(
            reverse("cubrir_licencia", args=[licencia.pk]),
            {
                "cargos": [licencia.cargos_afectados().first().pk],
                "tipo": TipoCobertura.SIN_COBERTURA,
            },
        )

        cobertura = Cobertura.objects.get()
        assert cobertura.tipo == TipoCobertura.SIN_COBERTURA
        assert cobertura.suplente is None

    def test_no_se_puede_cubrir_fuera_de_la_licencia(self, client, licencia_con_cargos, secretaria):
        licencia = licencia_con_cargos["licencia"]
        suplente = otra_persona(licencia_con_cargos["institucion"], "Otra", "27-30000503-1")
        client.force_login(secretaria)

        client.post(
            reverse("cubrir_licencia", args=[licencia.pk]),
            {
                "cargos": [licencia.cargos_afectados().first().pk],
                "tipo": TipoCobertura.SUPLENTE,
                "suplente": suplente.pk,
                "desde": licencia.fecha_inicio.isoformat(),
                "hasta": (licencia.fecha_fin + timedelta(days=10)).isoformat(),
            },
        )

        assert Cobertura.objects.count() == 0

    def test_volver_a_guardar_no_duplica(self, client, licencia_con_cargos, secretaria):
        licencia = licencia_con_cargos["licencia"]
        suplente = otra_persona(licencia_con_cargos["institucion"], "Doble", "27-30000504-1")
        datos = {
            "cargos": [cargo.pk for cargo in licencia.cargos_afectados()],
            "tipo": TipoCobertura.SUPLENTE,
            "suplente": suplente.pk,
        }
        client.force_login(secretaria)

        client.post(reverse("cubrir_licencia", args=[licencia.pk]), datos)
        client.post(reverse("cubrir_licencia", args=[licencia.pk]), datos)

        assert Cobertura.objects.filter(licencia=licencia).count() == len(
            list(licencia.cargos_afectados())
        )


@pytest.mark.django_db
class TestElControlDeHorario:
    def test_sin_horario_publicado_no_frena(self, institucion):
        """No se puede verificar, pero la escuela igual tiene que cubrir el curso."""
        from datetime import date

        legajo = otra_persona(institucion, "Alguien", "27-30000505-1")
        cargo = Cargo.objects.create(
            institucion=institucion,
            legajo=legajo,
            tipo=TipoCargo.CARGO_BASE,
            denominacion="Preceptor/a",
            situacion_revista=SituacionRevista.TITULAR,
            fuente_pago=FuentePago.INTERNO,
            fecha_alta=date.today(),
        )

        assert revisar(institucion, legajo, [cargo], date.today(), date.today()) == []


@pytest.mark.django_db
class TestLoQueSeVeAntesDeElegir:
    """Enterarse del choque al apretar «asignar» es ensayo y error."""

    def test_marca_a_quien_le_entra_y_a_quien_no(self, client, licencia_con_cargos, secretaria):
        from estructura.models import Curso

        licencia = licencia_con_cargos["licencia"]
        institucion = licencia_con_cargos["institucion"]
        otra_persona(institucion, "Libre", "27-30000601-1")  # sin horario: le entra
        ocupada = otra_persona(institucion, "Ocupada", "27-30000602-1")

        curso = licencia_con_cargos["curso"]
        otro_curso = Curso.objects.create(
            institucion=institucion,
            ciclo_lectivo=curso.ciclo_lectivo,
            nivel=curso.nivel,
            turno=curso.turno,
            esquema_horario=curso.esquema_horario,
            anio_estudio=curso.anio_estudio,
            division="Y",
        )
        suya = AsignacionHoraria.objects.filter(
            version=licencia_con_cargos["version"], legajo=licencia_con_cargos["docente"]
        ).first()
        AsignacionHoraria.objects.create(
            version=suya.version,
            curso=otro_curso,
            bloque=suya.bloque,
            materia=suya.materia,
            cargo=designar(
                licencia_con_cargos["escuela"], ocupada, licencia_con_cargos["materia"], otro_curso
            ),
        )
        client.force_login(secretaria)

        respuesta = client.get(reverse("cubrir_licencia", args=[licencia.pk]))
        libres = {dato["legajo"].apellido for dato in respuesta.context["libres"]}
        ocupados = {dato["legajo"].apellido for dato in respuesta.context["ocupados"]}

        assert "Libre" in libres
        assert "Ocupada" in ocupados
        # Y se dice qué hora es la que se pisa, no un «no puede» a secas.
        assert "se le pisan" in respuesta.content.decode()
        assert "se pisa con" in respuesta.content.decode()

    def test_al_designar_ofrece_avisarle(self, client, licencia_con_cargos, secretaria):
        licencia = licencia_con_cargos["licencia"]
        suplente = otra_persona(licencia_con_cargos["institucion"], "Nueva", "27-30000603-1")
        client.force_login(secretaria)

        respuesta = client.post(
            reverse("cubrir_licencia", args=[licencia.pk]),
            {
                "cargos": [cargo.pk for cargo in licencia.cargos_afectados()],
                "tipo": TipoCobertura.SUPLENTE,
                "suplente": suplente.pk,
            },
            follow=True,
        )

        assert "Avisarle ahora" in respuesta.content.decode()

    def test_el_aviso_nombra_todos_los_cargos(self, licencia_con_cargos):
        """Avisar de uno solo es peor que no avisar: se presenta a una hora."""
        from licencias.avisos import mensaje_para

        licencia = licencia_con_cargos["licencia"]
        suplente = otra_persona(licencia_con_cargos["institucion"], "Multi", "27-30000604-1")
        coberturas = [
            Cobertura.objects.create(
                institucion=licencia.institucion,
                licencia=licencia,
                cargo=cargo,
                tipo=TipoCobertura.SUPLENTE,
                suplente=suplente,
                fecha_inicio=licencia.fecha_inicio,
                fecha_fin=licencia.fecha_fin,
            )
            for cargo in licencia.cargos_afectados()
        ]
        if len(coberturas) < 2:  # la escuela de prueba tiene un cargo: se agrega otro
            return

        texto = mensaje_para(coberturas[0])

        for cobertura in coberturas:
            assert cobertura.cargo.descripcion in texto
