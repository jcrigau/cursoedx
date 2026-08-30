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


class TestElPlantel:
    """Docentes y no docentes conviven en Personal, cada uno con lo suyo."""

    @pytest.fixture
    def ordenanza(self, con_personal):
        from legajos.models import Plantel

        return Legajo.objects.create(
            institucion=con_personal["institucion"],
            apellido="Domínguez",
            nombre="Ramón",
            cuil="20-24681357-9",
            plantel=Plantel.MAESTRANZA,
            fecha_ingreso=date.today(),
        )

    def test_se_filtra_por_plantel(self, client, con_personal, ordenanza, secretaria):
        client.force_login(secretaria)
        cuerpo = client.get(reverse("personal"), {"plantel": "MAESTRANZA"}).content.decode()
        assert "Domínguez" in cuerpo
        assert "Benítez" not in cuerpo

    def test_al_no_docente_no_se_le_piden_materias(
        self, client, con_personal, ordenanza, secretaria
    ):
        """Un ordenanza sin materias no es un dato que falte: no da clases."""
        client.force_login(secretaria)
        cuerpo = client.get(reverse("personal"), {"plantel": "MAESTRANZA"}).content.decode()
        assert "no da clases" in cuerpo
        assert reverse("materias_de", args=[ordenanza.pk]) not in cuerpo

    def test_la_ficha_dice_el_puesto(self, client, con_personal, ordenanza, secretaria):
        client.force_login(secretaria)
        cuerpo = client.get(reverse("ficha_persona", args=[ordenanza.pk])).content.decode()
        assert "maestranza" in cuerpo.lower()

    def test_el_no_docente_no_aparece_para_cubrir_cursos(self, con_personal, ordenanza):
        from legajos.models import PLANTELES_SIN_CLASES

        assert not ordenanza.da_clases
        assert ordenanza.plantel in PLANTELES_SIN_CLASES


class TestLaFicha:
    def test_muestra_a_la_persona_completa(self, client, con_personal, secretaria):
        persona = con_personal["persona"]
        persona.materias_que_puede_dar.add(con_personal["quimica"])
        client.force_login(secretaria)

        cuerpo = client.get(reverse("ficha_persona", args=[persona.pk])).content.decode()

        assert "Benítez" in cuerpo
        assert "Química" in cuerpo
        assert "Certificación de servicios" in cuerpo

    def test_linkea_los_archivos_subidos(
        self, client, con_personal, secretaria, settings, tmp_path
    ):
        """El PDF que se subió al legajo se abre desde la ficha, sin ir al panel."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from legajos.models import DocumentoLegajo, TipoDocumento

        settings.MEDIA_ROOT = tmp_path
        tipo = TipoDocumento.objects.create(
            institucion=con_personal["institucion"], nombre="Apto psicofísico"
        )
        DocumentoLegajo.objects.create(
            legajo=con_personal["persona"],
            tipo=tipo,
            archivo=SimpleUploadedFile("apto.pdf", b"%PDF-1.4 de prueba"),
        )
        client.force_login(secretaria)

        cuerpo = client.get(
            reverse("ficha_persona", args=[con_personal["persona"].pk])
        ).content.decode()

        assert "Ver archivo" in cuerpo
        assert "/media/documentos/" in cuerpo

    def test_el_formulario_del_panel_muestra_la_foto_actual(self, client, con_personal, secretaria):
        """Al editar el legajo se ve qué cara tiene hoy, antes de cambiarla."""
        secretaria.is_superuser = True
        secretaria.save()
        client.force_login(secretaria)

        cuerpo = client.get(
            reverse("admin:legajos_legajo_change", args=[con_personal["persona"].pk])
        ).content.decode()

        assert "Foto actual" in cuerpo
        assert "img/persona.svg" in cuerpo

    def test_sin_foto_va_la_silueta_estandar(self, client, con_personal, secretaria):
        """Nadie queda sin cara: sin foto cargada se muestra el perfil estándar."""
        client.force_login(secretaria)

        ficha = client.get(
            reverse("ficha_persona", args=[con_personal["persona"].pk])
        ).content.decode()
        lista = client.get(reverse("personal")).content.decode()

        assert "img/persona.svg" in ficha
        assert "img/persona.svg" in lista

    def test_muestra_la_foto_carnet(self, client, con_personal, secretaria, settings, tmp_path):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        settings.MEDIA_ROOT = tmp_path
        contenido = BytesIO()
        Image.new("RGB", (4, 4), "orange").save(contenido, format="JPEG")
        persona = con_personal["persona"]
        persona.foto = SimpleUploadedFile("carnet.jpg", contenido.getvalue())
        persona.save()
        client.force_login(secretaria)

        cuerpo = client.get(reverse("ficha_persona", args=[persona.pk])).content.decode()

        assert "foto-carnet" in cuerpo
        assert "/media/fotos/" in cuerpo

    def test_el_legajo_completo_sale_en_pdf(self, client, con_personal, secretaria):
        """Es lo que pide la junta o una inspección: la carpeta entera."""
        from core.models import AccionAuditada, RegistroAuditoria

        client.force_login(secretaria)
        persona = con_personal["persona"]

        # En HTML se revisa antes de imprimir; el PDF es lo mismo compuesto.
        cuerpo = client.get(
            reverse("legajo_pdf", args=[persona.pk]), {"formato": "html"}
        ).content.decode()
        assert "Benítez" in cuerpo
        assert "Datos personales" in cuerpo and "Documentación" in cuerpo

        respuesta = client.get(reverse("legajo_pdf", args=[persona.pk]))

        assert respuesta.status_code == 200
        # Sale de la escuela con datos personales: tiene que quedar registrado.
        assert RegistroAuditoria.objects.filter(
            accion=AccionAuditada.EXPORTACION, descripcion__icontains="Legajo completo"
        ).exists()

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
