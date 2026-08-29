"""La planta completa, y qué puede dar cada uno.

Las materias declaradas son la diferencia entre encontrar un reemplazo y no
encontrarlo: alguien habilitado en Química sirve aunque este año no tenga
horas de Química.
"""

from datetime import date

import pytest
from django.urls import reverse

from estructura.models import Materia
from legajos.models import Legajo


@pytest.fixture
def con_personal(institucion, secretaria):
    from estructura.models import Nivel, TipoNivel

    nivel = Nivel.objects.create(institucion=institucion, tipo=TipoNivel.SECUNDARIO)
    quimica = Materia.objects.create(institucion=institucion, nivel=nivel, nombre="Química")
    Materia.objects.create(institucion=institucion, nivel=nivel, nombre="Historia")
    persona = Legajo.objects.create(
        institucion=institucion,
        apellido="Benítez",
        nombre="Ana",
        cuil="27-30000001-1",
        fecha_ingreso=date.today(),
    )
    return {"institucion": institucion, "persona": persona, "quimica": quimica}


class TestLaPlanta:
    def test_lista_a_todo_el_personal(self, client, con_personal, secretaria):
        client.force_login(secretaria)
        cuerpo = client.get(reverse("personal")).content.decode()
        assert "Benítez" in cuerpo

    def test_se_busca_sin_tildes(self, client, con_personal, secretaria):
        """Nadie escribe «Benítez» con tilde cuando busca."""
        client.force_login(secretaria)
        cuerpo = client.get(reverse("personal"), {"q": "benitez"}).content.decode()
        assert "Benítez" in cuerpo

    def test_la_busqueda_general_tampoco_pide_la_tilde(self, client, con_personal, secretaria):
        client.force_login(secretaria)
        cuerpo = client.get(reverse("buscar_personas"), {"q": "BENITEZ"}).content.decode()
        assert "Benítez" in cuerpo

    def test_no_es_publica(self, client, con_personal, db):
        assert client.get(reverse("personal")).status_code in (302, 403)


class TestMateriasQuePuedeDar:
    def test_se_guardan_las_tildadas(self, client, con_personal, secretaria):
        client.force_login(secretaria)

        client.post(
            reverse("guardar_materias", args=[con_personal["persona"].pk]),
            {"materias": [con_personal["quimica"].pk]},
        )

        assert list(con_personal["persona"].materias_que_puede_dar.all()) == [
            con_personal["quimica"]
        ]

    def test_destildar_las_saca(self, client, con_personal, secretaria):
        persona = con_personal["persona"]
        persona.materias_que_puede_dar.add(con_personal["quimica"])
        client.force_login(secretaria)

        client.post(reverse("guardar_materias", args=[persona.pk]), {"materias": []})

        assert persona.materias_que_puede_dar.count() == 0

    def test_no_se_pueden_tildar_materias_de_otra_escuela(
        self, client, con_personal, otra_institucion, secretaria
    ):
        """El aislamiento entre escuelas también vale acá."""
        from estructura.models import Nivel, TipoNivel

        nivel = Nivel.objects.create(institucion=otra_institucion, tipo=TipoNivel.SECUNDARIO)
        ajena = Materia.objects.create(institucion=otra_institucion, nivel=nivel, nombre="Ajena")
        client.force_login(secretaria)

        client.post(
            reverse("guardar_materias", args=[con_personal["persona"].pk]),
            {"materias": [ajena.pk]},
        )

        assert con_personal["persona"].materias_que_puede_dar.count() == 0


class TestLaFicha:
    def test_muestra_a_la_persona_completa(self, client, con_personal, secretaria):
        persona = con_personal["persona"]
        persona.materias_que_puede_dar.add(con_personal["quimica"])
        client.force_login(secretaria)

        cuerpo = client.get(reverse("ficha_persona", args=[persona.pk])).content.decode()

        assert "Benítez" in cuerpo
        assert "Química" in cuerpo
        assert "Certificación de servicios" in cuerpo

    def test_no_muestra_gente_de_otra_escuela(
        self, client, con_personal, otra_institucion, secretaria
    ):
        ajena = Legajo.objects.create(
            institucion=otra_institucion,
            apellido="Ajena",
            nombre="Otra",
            cuil="20-99999999-1",
            fecha_ingreso=date.today(),
        )
        client.force_login(secretaria)

        assert client.get(reverse("ficha_persona", args=[ajena.pk])).status_code == 404


class TestFiltroPorMateria:
    def test_filtra_por_lo_declarado(self, client, con_personal, secretaria):
        con_personal["persona"].materias_que_puede_dar.add(con_personal["quimica"])
        Legajo.objects.create(
            institucion=con_personal["institucion"],
            apellido="Otro",
            nombre="Docente",
            cuil="20-30000002-1",
            fecha_ingreso=date.today(),
        )
        client.force_login(secretaria)

        cuerpo = client.get(
            reverse("personal"), {"materia": con_personal["quimica"].pk}
        ).content.decode()

        assert "Benítez" in cuerpo
        assert "Otro" not in cuerpo

    def test_el_color_es_estable_por_materia(self):
        from legajos.templatetags.materias import color_materia

        class Falsa:
            pk = 11

        assert color_materia(Falsa()) == color_materia(Falsa())
        assert color_materia(Falsa()) == "tono-3"
        assert color_materia(None) == ""
